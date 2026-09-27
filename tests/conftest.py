import logging
import threading

import pytest

from app.core.auth import AuthStore
from app.ai.ai_store import AiRuntime, EventStore
from app.config.config_store import ConfigStore, DEFAULT_CONFIG
from app.core.frame_buffer import FrameBuffer
from app.core.runtime import RecorderRuntime
from app.core.upload_stats import UploadStats
from app.web.webapp import create_app


def authenticate(client, auth, token, device=False):
    client.environ_base["HTTP_X_SENTINEL_REQUEST"] = "1"
    response = client.post("/api/auth/login", json={"token": token})
    assert response.status_code == 200
    client.environ_base["HTTP_X_CSRF_TOKEN"] = response.json["csrf"]
    if device:
        paired = auth.pair(auth.pairing_code(), "Test camera")
        client.environ_base["HTTP_AUTHORIZATION"] = "Bearer " + paired["device_token"]
    return client


@pytest.fixture
def system(tmp_path):
    auth = AuthStore(tmp_path / "auth.sqlite3")
    token = auth.initialize()
    cfg = ConfigStore(str(tmp_path / "config.json"), {**DEFAULT_CONFIG, "out_root": str(tmp_path / "recordings")})
    frame = FrameBuffer()
    runtime = RecorderRuntime()
    app = create_app(cfg, frame, UploadStats(), runtime, AiRuntime(),
                     EventStore(str(tmp_path / "events.jsonl")), logging.getLogger("test"),
                     threading.Event(), {}, str(tmp_path / "server.log"), auth_store=auth)
    app.config["TESTING"] = True
    return app, auth, token, cfg, frame, runtime
