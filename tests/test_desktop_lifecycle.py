import io
import socket
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import cv2
import numpy as np
import pytest
import requests

from app.desktop.controller import ServiceController, child_command
from app.desktop.shell import Preferences, create_shell


def wait_for_state(controller, expected):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = controller.snapshot()
        if state["status"] == expected:
            return state
        if state["status"] == "failed":
            pytest.fail(state["error"])
        time.sleep(.05)
    pytest.fail("Timed out waiting for " + expected)


def test_desktop_shell_requires_local_capability_and_remembers_theme(tmp_path):
    settings = Preferences(tmp_path / "preferences.json")
    app = create_shell(settings, 8000)
    import threading
    controller = SimpleNamespace(lock=threading.Lock(), snapshot=lambda: {"status": "stopped"})
    app.config.update(SHELL_HOST="127.0.0.1:19001", CONTROLLER=controller)
    client = app.test_client()
    base = "http://127.0.0.1:19001"
    headers = {"X-Sentinel-Desktop": app.config["DESKTOP_KEY"]}
    assert client.get("/control/status", base_url=base).status_code == 403
    assert client.get("/control/status", base_url="http://example.invalid", headers=headers).status_code == 403
    assert client.post("/control/theme", base_url=base, json={"theme": "luna"},
                       headers={**headers, "Origin": "https://example.invalid"}).status_code == 403
    assert client.post("/control/theme", base_url=base, json={"theme": "luna"}, headers=headers).status_code == 200
    assert Preferences(settings.path).theme == "luna"


def test_desktop_service_media_graceful_restart_and_port_conflict(tmp_path):
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        port = occupied.getsockname()[1]
        controller = ServiceController(child_command(root), tmp_path, port, 19001, host="127.0.0.1")
        assert controller.start()
        assert not controller.start()
        assert controller.finished.wait(15)
        assert controller.snapshot()["status"] == "failed"
        assert "Cannot listen" in controller.snapshot()["error"]
    session = requests.Session()
    session.trust_env = False
    try:
        assert controller.start()
        state = wait_for_state(controller, "running")
        url = state["url"]
        headers = {"X-Sentinel-Request": "1"}
        auth = session.post(url + "api/auth/login", json={"token": state["token"]}, headers=headers, timeout=5)
        assert auth.ok
        headers["X-CSRF-Token"] = auth.json()["csrf"]
        page = session.get(url, timeout=5)
        assert page.headers["Content-Security-Policy"] == "frame-ancestors http://127.0.0.1:19001"
        other_host = session.get(url, headers={"Host": "localhost:" + str(port)}, timeout=5)
        assert other_host.headers["X-Frame-Options"] == "DENY"
        assert session.post(url + "api/ingest/enable", headers=headers, timeout=5).ok
        code = session.post(url + "api/devices/pairing-code", headers=headers, timeout=5).json()["code"]
        device = session.post(url + "api/devices/pair", headers=headers,
                              json={"code": code, "name": "Desktop test"}, timeout=5).json()["device_token"]
        ok, frame = cv2.imencode(".jpg", np.full((64, 96, 3), 110, dtype=np.uint8))
        assert ok
        assert session.post(url + "upload", headers={"Authorization": "Bearer " + device},
                            files={"image": ("frame.jpg", io.BytesIO(frame.tobytes()), "image/jpeg")}, timeout=5).ok
        with session.get(url + "stream", stream=True, timeout=5) as response:
            assert response.raw.read(9).startswith(b"--frame")
        assert session.post(url + "api/snapshot", headers=headers, timeout=5).ok
        item = session.get(url + "api/media?kind=snapshots", timeout=5).json()["items"][0]
        download = session.get(url + "api/media/download", params={"kind": "snapshots", "path": item["path"]}, timeout=5)
        assert download.content.startswith(b"\xff\xd8")
        assert session.post(url + "api/record/start", headers=headers, timeout=5).ok
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            if session.get(url + "api/status", timeout=3).json()["recorder_opened"]:
                break
            time.sleep(.1)
        else:
            pytest.fail("Recording did not open")
        time.sleep(.25)
        controller.stop()
        assert controller.finished.wait(15)
        assert controller.snapshot()["status"] == "stopped"
        paths = list((tmp_path / "recordings/videos").glob("*/*.mp4")) + list((tmp_path / "recordings/videos").glob("*/*.avi"))
        assert len(paths) == 1
        video = cv2.VideoCapture(str(paths[0]))
        try:
            assert video.read()[0]
        finally:
            video.release()
        assert controller.start()
        wait_for_state(controller, "running")
        assert session.post(url + "api/system/shutdown", headers=headers, timeout=5).ok
        assert controller.finished.wait(15)
        assert controller.snapshot()["status"] == "stopped"
    finally:
        session.close()
        controller.stop()
        assert controller.finished.wait(15)
