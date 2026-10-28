import logging
import threading

import numpy as np
import pytest

from app.recorder import recorder_worker


@pytest.mark.parametrize('auto_resume', [True, False])
def test_gap_closes_segment_and_obeys_resume_policy(system, monkeypatch, auto_resume):
    _, _, _, cfg, frames, runtime = system
    cfg.set_many({'recording': True, 'ingest_enabled': True, 'record_auto_resume': auto_resume})
    pixels = np.zeros((24, 32, 3), np.uint8)
    frames.set(pixels)
    stop = threading.Event()
    segments = []

    class Recorder:
        current_path = None
        def __init__(self, **kwargs):
            self.out_root = kwargs['out_root']
            self.writes = 0
            self.closed = False
            segments.append(self)
        def write(self, frame):
            self.writes += 1
            if len(segments) == 1:
                frames.ts -= 10
            else:
                stop.set()
        def stop(self):
            self.closed = True
            if auto_resume and len(segments) == 1:
                frames.set(pixels)
            elif not auto_resume:
                stop.set()

    monkeypatch.setattr(recorder_worker, 'SegmentRecorder', Recorder)
    monkeypatch.setattr(recorder_worker, 'maintain_storage', lambda *_: {'can_record': True})
    worker = threading.Thread(target=recorder_worker.record_loop,
                              args=(cfg, frames, runtime, logging.getLogger('gap-test'), stop), daemon=True)
    worker.start()
    try:
        worker.join(2)
        assert not worker.is_alive()
    finally:
        stop.set()
        worker.join(1)
    assert len(segments) == (2 if auto_resume else 1)
    assert all(s.closed and s.writes == 1 for s in segments)
    assert cfg.get_copy()['recording'] is auto_resume


def test_waiting_before_first_frame_can_be_manually_stopped(system, monkeypatch):
    _, _, _, cfg, frames, runtime = system
    cfg.set_many({'recording': True, 'ingest_enabled': True})
    stop = threading.Event()
    monkeypatch.setattr(recorder_worker, 'maintain_storage', lambda *_: {'can_record': True})
    worker = threading.Thread(target=recorder_worker.record_loop,
                              args=(cfg, frames, runtime, logging.getLogger('gap-test'), stop), daemon=True)
    worker.start()
    try:
        import time
        deadline = time.monotonic() + 1
        while not runtime.waiting_for_frames and time.monotonic() < deadline:
            time.sleep(0.01)
        assert runtime.waiting_for_frames and runtime.rec is None
        cfg.set_key('recording', False)
        frames.set(np.zeros((24, 32, 3), np.uint8))
        deadline = time.monotonic() + 1
        while runtime.waiting_for_frames and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not runtime.waiting_for_frames and runtime.rec is None
    finally:
        stop.set()
        worker.join(1)
