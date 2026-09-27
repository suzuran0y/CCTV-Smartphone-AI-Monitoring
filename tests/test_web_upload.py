import io
import logging
import threading
import re

import cv2
import numpy as np

from app.ai.ai_store import AiRuntime, EventStore
from app.config.config_store import ConfigStore, DEFAULT_CONFIG
from app.core.frame_buffer import FrameBuffer
from app.core.runtime import RecorderRuntime
from app.core.upload_stats import UploadStats
from app.web.webapp import MAX_UPLOAD_BYTES, create_app
from app.core.auth import AuthStore
from conftest import authenticate


def _make_upload_client(tmp_path):
    auth = AuthStore(tmp_path / "auth.sqlite3")
    token = auth.initialize()
    frame_buf = FrameBuffer()
    stats = UploadStats()
    app = create_app(
        cfg_store=ConfigStore(path=str(tmp_path / "config.json"), initial=DEFAULT_CONFIG.copy()),
        frame_buf=frame_buf,
        stats=stats,
        rec_rt=RecorderRuntime(),
        ai_rt=AiRuntime(),
        event_store=EventStore(path=str(tmp_path / "ai_events.jsonl")),
        logger=logging.getLogger("test-web-upload"),
        stop_event=threading.Event(),
        threads={},
        server_log_path=str(tmp_path / "server.log"),
        auth_store=auth,
    )
    return authenticate(app.test_client(), auth, token, device=True), frame_buf, stats


def test_upload_requires_ingest_then_accepts_jpeg(tmp_path):
    client, frame_buf, stats = _make_upload_client(tmp_path)

    rejected = client.post(
        "/upload",
        data={"image": (io.BytesIO(b"not-read"), "frame.jpg")},
        content_type="multipart/form-data",
    )
    assert rejected.status_code == 503

    assert client.post("/api/ingest/enable").status_code == 200
    ok, encoded = cv2.imencode(".jpg", np.zeros((24, 32, 3), dtype=np.uint8))
    assert ok

    accepted = client.post(
        "/upload",
        data={"image": (io.BytesIO(encoded.tobytes()), "frame.jpg")},
        content_type="multipart/form-data",
    )

    assert accepted.status_code == 200
    assert frame_buf.get_copy().shape == (24, 32, 3)
    assert stats.snapshot_counts()["200_ok"] == 1
    assert stats.snapshot_counts()["503_ingest_disabled"] == 1


def test_upload_tracks_missing_invalid_and_oversized_images(tmp_path):
    client, _, stats = _make_upload_client(tmp_path)
    client.post("/api/ingest/enable")

    missing = client.post("/upload", data={}, content_type="multipart/form-data")
    empty = client.post("/upload", data={"image": (io.BytesIO(b""), "empty.jpg")})
    invalid = client.post(
        "/upload",
        data={"image": (io.BytesIO(b"not-a-jpeg"), "frame.jpg")},
        content_type="multipart/form-data",
    )
    oversized = client.post(
        "/upload",
        data={"image": (io.BytesIO(b"x" * (MAX_UPLOAD_BYTES + 1)), "frame.jpg")},
        content_type="multipart/form-data",
    )

    assert missing.status_code == 400
    assert invalid.status_code == 400
    assert empty.status_code == 400
    assert oversized.status_code == 413
    counts = stats.snapshot_counts()
    assert counts["400_missing_image"] == 1
    assert counts["400_decode_failed"] == 2
    assert counts["413_image_too_large"] == 1


def test_upload_diagnostics_correlate_without_logging_secrets(tmp_path, caplog):
    client, _, _ = _make_upload_client(tmp_path)
    client.post("/api/ingest/enable")
    _, encoded = cv2.imencode(".jpg", np.zeros((24, 32, 3), dtype=np.uint8))
    with caplog.at_level(logging.INFO):
        response = client.post("/upload", headers={"X-CamFlow-Upload-ID": "123456abcdef"},
                               data={"image": (io.BytesIO(encoded.tobytes()), "private-filename.jpg")})
    assert response.status_code == 200
    assert response.headers["X-CamFlow-Upload-ID"] == "123456abcdef"
    assert float(response.headers["X-Sentinel-Upload-Ms"]) >= 0
    assert caplog.text.count("upload begin id=123456abcdef") == 1
    assert caplog.text.count("upload end id=123456abcdef status=200") == 1
    assert "read_ms=" in caplog.text and "decode_ms=" in caplog.text
    assert "private-filename" not in caplog.text
    assert client.environ_base["HTTP_AUTHORIZATION"] not in caplog.text


def test_upload_diagnostics_sanitize_id_and_include_rejection(tmp_path, caplog):
    client, _, _ = _make_upload_client(tmp_path)
    with caplog.at_level(logging.INFO):
        response = client.post("/upload", headers={"X-CamFlow-Upload-ID": "secret-invalid-id"})
    assert response.status_code == 503
    assert re.fullmatch(r"[a-f0-9]{12}", response.headers["X-CamFlow-Upload-ID"])
    assert "secret-invalid-id" not in caplog.text
    assert "status=503" in caplog.text
    assert float(response.headers["X-Sentinel-Upload-Ms"]) >= 0
