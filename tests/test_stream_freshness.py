import concurrent.futures
import threading
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.config.config_store import DEFAULT_CONFIG, validate_and_normalize
from app.core.frame_buffer import FrameBuffer
from app.web.stream_renderer import SharedJpegRenderer
from conftest import authenticate


def test_frame_status_transition_and_snapshot_rejects_stale(system):
    app, auth, token, cfg, frame, _ = system
    visitor = app.test_client()
    admin = authenticate(app.test_client(), auth, token)
    assert visitor.get('/api/status').json['frame_state'] == 'disabled'
    cfg.set_key('ingest_enabled', True)
    assert visitor.get('/api/status').json['frame_state'] == 'waiting'
    frame.set(np.zeros((64, 96, 3), np.uint8))
    assert visitor.get('/api/status').json['frame_state'] == 'live'
    frame.ts -= 6
    assert visitor.get('/api/status').json['frame_state'] == 'stale'
    assert admin.post('/api/snapshot').status_code == 409
    frame.set(np.zeros((64, 96, 3), np.uint8))
    assert visitor.get('/api/status').json['frame_state'] == 'live'
    assert admin.post('/api/snapshot').status_code == 200
    assert admin.post('/api/snapshot').status_code == 200
    assert len(list(Path(cfg.get_copy()['out_root']).glob('snapshots/*/*.jpg'))) == 2


def test_shared_jpeg_invalidates_on_new_frame_quality_clear_and_staleness():
    frames = FrameBuffer()
    cfg = {**DEFAULT_CONFIG, 'ingest_enabled': True}
    renderer = SharedJpegRenderer(frames)
    pixels = np.zeros((80, 320, 3), np.uint8)
    frames.set(pixels)
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        jpegs = list(pool.map(lambda _: renderer.render(cfg), range(32)))
    assert len(set(jpegs)) == 1
    assert renderer.encode_count == 1
    cfg['jpeg_quality'] = 55
    renderer.render(cfg)
    assert renderer.encode_count == 2
    frames.ts -= 6
    stale = renderer.render(cfg)
    assert stale != jpegs[0]
    renderer.render(cfg)
    assert renderer.encode_count == 3
    assert not pixels.any()  # Overlay must never alter the shared camera frame.
    frames.set(pixels)
    renderer.render(cfg)
    frames.clear()
    renderer.render(cfg)
    assert renderer.encode_count == 5


def test_upload_is_not_blocked_by_jpeg_encoding(monkeypatch):
    frames = FrameBuffer()
    pixels = np.zeros((24, 32, 3), np.uint8)
    frames.set(pixels)
    renderer = SharedJpegRenderer(frames)
    started, release, uploaded = threading.Event(), threading.Event(), threading.Event()
    encode = cv2.imencode

    def slow_encode(*args):
        started.set()
        assert release.wait(2)
        return encode(*args)

    monkeypatch.setattr(cv2, 'imencode', slow_encode)
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        drawing = pool.submit(renderer.render, {**DEFAULT_CONFIG, 'ingest_enabled': True})
        try:
            assert started.wait(1)
            def upload():
                frames.set(pixels)
                uploaded.set()
            writing = pool.submit(upload)
            assert uploaded.wait(1)
        finally:
            release.set()
        assert drawing.result() is not None
        writing.result()


@pytest.mark.parametrize('patch', [
    {'frame_stale_seconds': 0}, {'record_gap_seconds': float('nan')},
    {'record_gap_seconds': 301}, {'record_auto_resume': 'invalid'},
])
def test_invalid_freshness_config(patch):
    assert not validate_and_normalize(patch)[0]
