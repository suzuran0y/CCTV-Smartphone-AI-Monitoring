import io
import concurrent.futures

import cv2
import numpy as np
import pytest

from app.core.auth import AuthStore
from conftest import authenticate
from html.parser import HTMLParser


def test_access_panel_is_collapsed_and_keeps_controls_inside(system):
    app, *_ = system

    class AccessPanelParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.inside = False
            self.panel = None
            self.controls = set()

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "details" and attrs.get("id") == "accessPanel":
                self.panel = attrs
                self.inside = True
            if self.inside and "id" in attrs:
                self.controls.add(attrs["id"])

        def handle_endtag(self, tag):
            if tag == "details":
                self.inside = False

    parser = AccessPanelParser()
    parser.feed(app.test_client().get("/").get_data(as_text=True))
    assert parser.panel is not None
    assert "open" not in parser.panel
    assert {"accessStatus", "loginForm", "logoutBtn", "devicePanel", "pairingBtn", "deviceList"} <= parser.controls


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/config"), ("GET", "/api/ai/events"), ("GET", "/api/ai/status"),
    ("GET", "/api/log/tail"), ("GET", "/api/devices"),
    ("PUT", "/api/config"), ("POST", "/api/config/save"), ("POST", "/api/config/load"),
    ("POST", "/api/record/start"), ("POST", "/api/record/stop"),
    ("POST", "/api/ingest/enable"), ("POST", "/api/ingest/disable"),
    ("POST", "/api/snapshot"), ("POST", "/api/system/shutdown"),
    ("POST", "/api/devices/pairing-code"), ("DELETE", "/api/devices/anything"),
])
def test_visitors_and_device_tokens_cannot_administer(system, method, path):
    app, auth, _, *_ = system
    client = app.test_client()
    paired = auth.pair(auth.pairing_code(), "camera")
    for authorization in ("", "Bearer " + paired["device_token"]):
        assert client.open(path, method=method, headers={"X-Sentinel-Request": "1", "Authorization": authorization}).status_code == 401


def test_privacy_applies_to_existing_streams_and_status(system):
    app, auth, token, cfg, *_ = system
    visitor = app.test_client()
    admin = authenticate(app.test_client(), auth, token)
    assert visitor.get("/api/status").status_code == 200
    assert "out_root" not in visitor.get("/api/status").json
    stream = visitor.get("/stream", buffered=False)
    next(stream.response)
    cfg.set_key("viewer_auth_required", True)
    with pytest.raises(StopIteration):
        next(stream.response)
    stream.close()
    assert visitor.get("/stream").status_code == 401
    assert visitor.get("/api/status").status_code == 401
    assert visitor.get("/").status_code == 200
    assert admin.get("/api/status").status_code == 200


def test_csrf_logout_and_live_admin_reset(system):
    app, auth, token, *_ = system
    client = authenticate(app.test_client(), auth, token)
    assert client.put("/api/config", json={"viewer_auth_required": True}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/ingest/enable", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert client.post("/api/ingest/enable").status_code == 200
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/config").status_code == 401
    authenticate(client, auth, token)
    replacement = AuthStore(auth.path).initialize(reset=True)
    assert replacement != token
    assert client.get("/api/config").status_code == 401
    assert auth.login(token) is None
    assert auth.login(replacement)


def test_pair_upload_revoke_and_single_use(system):
    app, auth, token, cfg, frame, *_ = system
    admin = authenticate(app.test_client(), auth, token)
    phone = app.test_client()
    phone.environ_base["HTTP_X_SENTINEL_REQUEST"] = "1"
    code = admin.post("/api/devices/pairing-code").json["code"]
    paired = phone.post("/api/devices/pair", json={"code": code, "name": "Front door"})
    assert paired.status_code == 200
    assert phone.post("/api/devices/pair", json={"code": code}).status_code == 401
    secret = paired.json["device_token"]
    assert secret not in admin.get("/api/devices").get_data(as_text=True)
    assert phone.post("/upload").status_code == 401
    assert admin.post("/upload").status_code == 401
    cfg.set_key("ingest_enabled", True)
    _, jpg = cv2.imencode(".jpg", np.zeros((16, 16, 3), dtype=np.uint8))
    result = phone.post("/upload", headers={"Authorization": "Bearer " + secret},
                        data={"image": (io.BytesIO(jpg.tobytes()), "image.jpg")})
    assert result.status_code == 200
    assert frame.get_copy() is not None
    assert admin.delete("/api/devices/" + paired.json["device_id"]).status_code == 200
    assert phone.post("/upload", headers={"Authorization": "Bearer " + secret}).status_code == 401


def test_expiry_rate_limit_and_concurrent_pairing(system):
    app, auth, token, *_ = system
    expired = auth.pairing_code()
    with auth.connect() as db:
        db.execute("UPDATE pairing SET expires=0")
    assert auth.pair(expired, "phone") is None
    code = auth.pairing_code()
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: auth.pair(code, "phone"), range(2)))
    assert sum(result is not None for result in results) == 1
    session = auth.login(token)[0]
    with auth.connect() as db:
        db.execute("UPDATE sessions SET expires=0")
    assert auth.session(session) is None
    client = app.test_client()
    for _ in range(10):
        assert client.post("/api/auth/login", json={"token": "wrong"}, headers={"X-Sentinel-Request": "1"}).status_code == 401
    assert client.post("/api/auth/login", json={"token": token}, headers={"X-Sentinel-Request": "1"}).status_code == 429


def test_auth_file_does_not_store_plaintext_and_reset_keeps_devices(system):
    _, auth, token, *_ = system
    paired = auth.pair(auth.pairing_code(), "phone")
    auth.initialize(reset=True)
    assert auth.device_valid(paired["device_token"])
    with auth.connect() as db:
        values = repr(list(db.iterdump()))
    assert token not in values
    assert paired["device_token"] not in values


def test_authenticated_shutdown_uses_host_callback(system):
    import threading
    app, auth, token, *_ = system
    called = threading.Event()
    app.config["SERVER_SHUTDOWN"] = called.set
    client = authenticate(app.test_client(), auth, token)
    assert client.post("/api/system/shutdown").status_code == 200
    assert called.wait(2)


def test_privacy_persists_without_autosave(system):
    app, auth, token, cfg, *_ = system
    client = authenticate(app.test_client(), auth, token)
    assert client.put("/api/config", json={"viewer_auth_required": True}).status_code == 200
    cfg.set_key("viewer_auth_required", False)
    cfg.load_from_disk()
    assert cfg.get_copy()["viewer_auth_required"] is True


def test_failed_privacy_save_is_reported_and_invalid_load_preserves_mode(system, monkeypatch):
    app, auth, token, cfg, *_ = system
    client = authenticate(app.test_client(), auth, token)
    monkeypatch.setattr(cfg, "save_to_disk", lambda *_: False)
    assert client.put("/api/config", json={"viewer_auth_required": True}).status_code == 500
    assert cfg.get_copy()["viewer_auth_required"] is True
    from pathlib import Path
    Path(cfg.path).write_text("not json", encoding="utf-8")
    assert client.post("/api/config/load").status_code == 400
    assert cfg.get_copy()["viewer_auth_required"] is True
