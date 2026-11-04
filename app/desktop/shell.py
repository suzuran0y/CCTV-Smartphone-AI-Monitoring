"""Loopback-only desktop controls; no JavaScript-to-Python bridge in the dashboard."""
import json
import secrets
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file

THEMES = {"modern", "dark", "luna"}


class Preferences:
    def __init__(self, path):
        self.path = Path(path)
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            self.theme = saved["theme"] if saved["theme"] in THEMES else "modern"
        except (OSError, ValueError, KeyError, TypeError):
            self.theme = "modern"

    def save(self, theme):
        pending = self.path.with_suffix(".tmp")
        pending.write_text(json.dumps({"theme": theme}), encoding="utf-8")
        pending.replace(self.path)
        self.theme = theme


def create_shell(settings, service_port):
    app = Flask(__name__)
    key = secrets.token_urlsafe(32)
    app.config.update(MAX_CONTENT_LENGTH=4096, DESKTOP_KEY=key)

    @app.before_request
    def authorize():
        if request.remote_addr != "127.0.0.1" or request.host != app.config["SHELL_HOST"]:
            abort(403)
        if request.path.startswith("/control/"):
            supplied = request.headers.get("X-Sentinel-Desktop", "")
            if not secrets.compare_digest(supplied.encode(), key.encode()):
                abort(403)
            origin = request.headers.get("Origin")
            if origin and origin != "http://" + app.config["SHELL_HOST"]:
                abort(403)

    @app.after_request
    def protect(response):
        response.headers.update({
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'self'; object-src 'none'; base-uri 'none'; "
                                       f"frame-src http://127.0.0.1:{service_port}; frame-ancestors 'none'",
        })
        return response

    @app.get("/")
    def desktop():
        return render_template("shell.html")

    @app.get("/theme.css")
    def theme_styles():
        return send_file(Path(__file__).resolve().parents[1] / "web/static/themes.css", mimetype="text/css")

    @app.get("/control/status")
    def status():
        return jsonify(**app.config["CONTROLLER"].snapshot(), theme=settings.theme)

    @app.post("/control/<action>")
    def control(action):
        controller = app.config["CONTROLLER"]
        if action in ("start", "reset"):
            if app.config["CLOSING"].is_set() or not controller.start(reset=action == "reset"):
                return jsonify(error="Service is busy."), 409
        elif action == "stop":
            controller.stop()
        elif action == "forget-token":
            controller.forget_token()
        elif action == "theme":
            value = request.get_json(silent=True)
            theme = value.get("theme") if isinstance(value, dict) else None
            if not isinstance(theme, str) or theme not in THEMES:
                return jsonify(error="Invalid theme."), 400
            with controller.lock:
                try:
                    settings.save(theme)
                except OSError:
                    return jsonify(error="Could not save appearance preferences."), 500
        else:
            abort(404)
        return jsonify(ok=True)

    return app
