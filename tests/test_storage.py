import logging
import os
import sqlite3
import threading
from types import SimpleNamespace

import pytest

from app.recorder.storage import GIB, maintain_storage, register_recording, safe_root
from app.config.config_store import DEFAULT_CONFIG, validate_and_normalize
from conftest import authenticate


def setup_storage(tmp_path):
    root = tmp_path / "recordings" / "videos"
    day = root / "20260101"
    day.mkdir(parents=True)
    files = [day / ("phone_20260101_00000%d.mp4" % i) for i in range(3)]
    for path in files:
        path.write_bytes(b"video")
        register_recording(root, path)
    with sqlite3.connect(str(root / ".sentinel-recordings.sqlite3")) as db:
        db.execute("UPDATE recordings SET completed=0")
    cfg = {**DEFAULT_CONFIG, "out_root": str(root.parent), "record_cleanup_enabled": True}
    return cfg, root, files


def test_retention_preserves_active_and_unregistered(tmp_path):
    cfg, root, files = setup_storage(tmp_path)
    unknown = root / "20260101" / "personal.mp4"
    unknown.write_bytes(b"private")
    result = maintain_storage(cfg, active_path=str(files[0]))
    assert result["removed"] == 2
    assert files[0].exists() and unknown.exists()
    assert not files[1].exists()


def test_cleanup_disabled_and_disk_minimum(tmp_path, monkeypatch):
    cfg, _, files = setup_storage(tmp_path)
    cfg["record_cleanup_enabled"] = False
    monkeypatch.setattr("app.recorder.storage.shutil.disk_usage", lambda _: SimpleNamespace(free=0))
    result = maintain_storage(cfg)
    assert not result["can_record"] and result["removed"] == 0
    assert all(path.exists() for path in files)


def test_quota_removes_oldest_registered_recording(tmp_path):
    cfg, root, files = setup_storage(tmp_path)
    import time
    with sqlite3.connect(str(root / ".sentinel-recordings.sqlite3")) as db:
        for i, path in enumerate(files):
            db.execute("UPDATE recordings SET completed=? WHERE path=?", (time.time() - 100 + i, path.relative_to(root).as_posix()))
    cfg["record_max_storage_gb"] = 11 / GIB
    result = maintain_storage(cfg)
    assert result["removed"] == 1
    assert not files[0].exists() and files[1].exists() and files[2].exists()


def test_tampered_index_cannot_escape_root(tmp_path):
    cfg, root, _ = setup_storage(tmp_path)
    outside = tmp_path / "keep.mp4"
    outside.write_bytes(b"keep")
    with sqlite3.connect(str(root / ".sentinel-recordings.sqlite3")) as db:
        db.execute("INSERT INTO recordings VALUES ('../../keep.mp4', 0)")
    maintain_storage(cfg)
    assert outside.read_bytes() == b"keep"


@pytest.mark.parametrize("patch", [
    {"out_root": os.path.abspath(os.sep)}, {"cam_name": "../escape"},
    {"record_min_free_gb": float("nan")}, {"record_retention_days": 0},
    {"record_cleanup_enabled": "maybe"},
])
def test_invalid_storage_settings_rejected(patch):
    assert not validate_and_normalize(patch)[0]


def test_no_space_rejects_record_start_but_preview_status_survives(system, monkeypatch):
    app, auth, token, cfg, _, runtime = system
    monkeypatch.setattr("app.recorder.storage.shutil.disk_usage", lambda _: SimpleNamespace(free=0))
    client = authenticate(app.test_client(), auth, token)
    assert client.post("/api/record/start").status_code == 409
    assert not cfg.get_copy()["recording"]
    assert runtime.rec is None
    assert client.get("/api/status").status_code == 200


def test_active_recording_keeps_disk_checks_on_original_output(system, tmp_path, monkeypatch):
    from app.recorder.recorder_worker import record_loop
    import numpy as np
    _, _, _, cfg, frame, runtime = system
    original = tmp_path / "original"
    cfg.set_key("out_root", str(tmp_path / "changed"))
    cfg.set_key("recording", True)
    frame.set(np.zeros((16, 16, 3), dtype=np.uint8))
    stop = threading.Event()
    runtime.rec = SimpleNamespace(out_root=str(original / "videos"), current_path=None,
                                  write=lambda _: stop.set(), stop=lambda: None)
    checked = []
    def inspect(storage_cfg, *args):
        checked.append(storage_cfg["out_root"])
        return {"can_record": True, "free_gb": 20, "removed": 0}
    monkeypatch.setattr("app.recorder.recorder_worker.maintain_storage", inspect)
    record_loop(cfg, frame, runtime, logging.getLogger("storage-test"), stop)
    assert checked == [str(original)]
