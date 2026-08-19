import io
import logging
import threading

import cv2
import numpy as np

from app.ai.ai_store import AiRuntime, EventStore
from app.config.config_store import ConfigStore, DEFAULT_CONFIG
from app.core.frame_buffer import FrameBuffer
from app.core.runtime import RecorderRuntime
from app.core.upload_stats import UploadStats
from app.web.webapp import MAX_UPLOAD_BYTES, create_app


def _make_upload_client(tmp_path):
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
    )
    return app.test_client(), frame_buf, stats


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
    assert oversized.status_code == 413
    counts = stats.snapshot_counts()
    assert counts["400_missing_image"] == 1
    assert counts["400_decode_failed"] == 1
    assert counts["413_image_too_large"] == 1
