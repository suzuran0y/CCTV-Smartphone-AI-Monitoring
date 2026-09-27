"""Local credentials, revocable browser sessions and one-time camera pairing."""
import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path

from flask import g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AuthStore:
    SESSION_SECONDS = 8 * 3600

    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.attempts = {}
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (hash TEXT PRIMARY KEY, csrf TEXT, expires REAL);
                CREATE TABLE IF NOT EXISTS devices (id TEXT PRIMARY KEY, name TEXT, hash TEXT, created REAL);
                CREATE TABLE IF NOT EXISTS pairing (hash TEXT PRIMARY KEY, expires REAL);
            """)
        if os.name != "nt":
            os.chmod(self.path, 0o600)

    def connect(self):
        # Each operation owns a connection; context manager commits/rolls back and closes it.
        from contextlib import contextmanager

        @contextmanager
        def connection():
            db = sqlite3.connect(self.path, timeout=10)
            try:
                with db:
                    yield db
            finally:
                db.close()
        return connection()

    def initialize(self, reset=False):
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not reset and db.execute("SELECT 1 FROM settings WHERE name='admin'").fetchone():
                return None
            token = secrets.token_urlsafe(32)
            db.execute("INSERT OR REPLACE INTO settings VALUES ('admin', ?)",
                       (generate_password_hash(token, method="pbkdf2:sha256:600000"),))
            db.execute("DELETE FROM sessions")
            db.execute("DELETE FROM pairing")
            return token

    def allow_attempt(self, scope, address):
        now = time.monotonic()
        with self.lock:
            self.attempts = {k: v for k, v in self.attempts.items() if v[0] > now - 60}
            keys = [(scope, "*", 60), (scope, address, 10)]
            if any(self.attempts.get((s, a), (now, 0))[1] >= limit for s, a, limit in keys):
                return False
            for s, a, _ in keys:
                started, count = self.attempts.get((s, a), (now, 0))
                self.attempts[(s, a)] = (started, count + 1)
            return True

    def login(self, token):
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT value FROM settings WHERE name='admin'").fetchone()
            if not row or not isinstance(token, str) or len(token) > 256 or not check_password_hash(row[0], token):
                return None
            session, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            db.execute("INSERT INTO sessions VALUES (?, ?, ?)",
                       (digest(session), csrf, time.time() + self.SESSION_SECONDS))
            return session, csrf

    def session(self, token):
        with self.connect() as db:
            return db.execute("SELECT csrf FROM sessions WHERE hash=? AND expires>?",
                              (digest(token), time.time())).fetchone()

    def logout(self, token):
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE hash=?", (digest(token),))

    def pairing_code(self):
        code = secrets.token_hex(4).upper()
        with self.connect() as db:
            db.execute("DELETE FROM pairing")
            db.execute("INSERT INTO pairing VALUES (?, ?)", (digest(code), time.time() + 300))
        return code

    def pair(self, code, name):
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT hash FROM pairing WHERE hash=? AND expires>?",
                             (digest(code.strip().upper()), time.time())).fetchone()
            if not row:
                return None
            db.execute("DELETE FROM pairing WHERE hash=?", (row[0],))
            token, device_id = secrets.token_urlsafe(32), secrets.token_hex(12)
            db.execute("INSERT INTO devices VALUES (?, ?, ?, ?)",
                       (device_id, name[:80], digest(token), time.time()))
            return {"device_id": device_id, "device_token": token}

    def device_valid(self, token):
        with self.connect() as db:
            return bool(token and db.execute("SELECT 1 FROM devices WHERE hash=?", (digest(token),)).fetchone())

    def devices(self):
        with self.connect() as db:
            return [dict(zip(("id", "name", "created"), row))
                    for row in db.execute("SELECT id, name, created FROM devices ORDER BY created")]

    def revoke(self, device_id):
        with self.connect() as db:
            return db.execute("DELETE FROM devices WHERE id=?", (device_id,)).rowcount > 0


def install_auth(app, store, cfg_store):
    cookie = "sentinel_session"

    def error(message, code):
        return jsonify(ok=False, error=message), code

    @app.before_request
    def authorize():
        g.auth_session = store.session(request.cookies.get(cookie, ""))
        g.is_admin = bool(g.auth_session)
        path = request.path
        if request.method not in ("GET", "HEAD", "OPTIONS") and path != "/upload":
            origin = request.headers.get("Origin")
            if origin and origin != request.host_url.rstrip("/"):
                return error("cross-origin request denied", 403)
            if request.headers.get("X-Sentinel-Request") != "1":
                return error("X-Sentinel-Request header required", 403)
        if path == "/upload":
            authorization = request.headers.get("Authorization", "")
            token = authorization[7:] if authorization.startswith("Bearer ") else ""
            if not store.device_valid(token):
                return error("device pairing required; use CamFlow 1.1.2", 401)
            return None
        public = {"/", "/dashboard", "/ping", "/api/version", "/api/auth/status",
                  "/api/auth/login", "/api/devices/pair"}
        if path in public or path.startswith("/static/"):
            return None
        if path in ("/stream", "/api/status"):
            if not cfg_store.get_copy().get("viewer_auth_required") or g.is_admin:
                return None
        if not g.is_admin:
            return error("administrator login required", 401)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), g.auth_session[0]):
                return error("invalid CSRF token", 403)

    @app.after_request
    def secure_response(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.get("/api/auth/status")
    def auth_status():
        return jsonify(ok=True, admin=g.is_admin, csrf=g.auth_session[0] if g.is_admin else None,
                       viewer_auth_required=bool(cfg_store.get_copy().get("viewer_auth_required")))

    @app.post("/api/auth/login")
    def auth_login():
        if not store.allow_attempt("login", request.remote_addr):
            return error("too many attempts; retry in 60 seconds", 429)
        data = request.get_json(silent=True)
        result = store.login(data.get("token") if isinstance(data, dict) else None)
        if not result:
            return error("invalid administrator token", 401)
        store.logout(request.cookies.get(cookie, ""))
        response = jsonify(ok=True, csrf=result[1])
        response.set_cookie(cookie, result[0], httponly=True, samesite="Strict", secure=request.is_secure)
        return response

    @app.post("/api/auth/logout")
    def auth_logout():
        store.logout(request.cookies.get(cookie, ""))
        response = jsonify(ok=True)
        response.delete_cookie(cookie)
        return response

    @app.post("/api/devices/pairing-code")
    def pairing_code():
        return jsonify(ok=True, code=store.pairing_code(), expires_in=300)

    @app.post("/api/devices/pair")
    def pair_device():
        if not store.allow_attempt("pair", request.remote_addr):
            return error("too many attempts; retry in 60 seconds", 429)
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get("code"), str):
            return error("pairing code required", 400)
        name = data.get("name", "CamFlow")
        if not isinstance(name, str) or not name.strip() or len(name) > 80 or len(data["code"]) > 32:
            return error("invalid device name or code", 400)
        result = store.pair(data["code"], name.strip())
        return jsonify(ok=True, **result) if result else error("invalid or expired pairing code", 401)

    @app.get("/api/devices")
    def devices():
        return jsonify(ok=True, devices=store.devices())

    @app.delete("/api/devices/<device_id>")
    def revoke_device(device_id):
        return jsonify(ok=True) if store.revoke(device_id) else error("device not found", 404)
