from pathlib import Path

import pytest

from app.recorder import recorder as recorder_module
from app.recorder.recorder import SegmentRecorder


class FakeWriter:
    def __init__(self, opened: bool):
        self._opened = opened
        self.released = False

    def isOpened(self):
        return self._opened

    def release(self):
        self.released = True


def install_fake_video_writer(monkeypatch, supported_codecs):
    attempts = []

    monkeypatch.setattr(
        recorder_module.cv2,
        "VideoWriter_fourcc",
        lambda *characters: "".join(characters),
    )

    def create_writer(path, codec, fps, size):
        attempts.append((codec, Path(path).suffix, fps, size))
        return FakeWriter(codec in supported_codecs)

    monkeypatch.setattr(recorder_module.cv2, "VideoWriter", create_writer)
    return attempts


def test_recorder_falls_back_and_reuses_working_codec(tmp_path, monkeypatch):
    attempts = install_fake_video_writer(monkeypatch, {"mp4v"})
    recorder = SegmentRecorder(out_root=str(tmp_path), codec="avc1")

    first_path = recorder._open_writer(640, 480)

    assert [item[0] for item in attempts] == ["avc1", "mp4v"]
    assert recorder.active_codec == "mp4v"
    assert first_path.endswith(".mp4")

    recorder._close_writer()
    attempts.clear()
    recorder._open_writer(640, 480)

    assert attempts[0][0] == "mp4v"
    assert all(item[0] != "avc1" for item in attempts)


def test_recorder_uses_avi_for_xvid(tmp_path, monkeypatch):
    attempts = install_fake_video_writer(monkeypatch, {"XVID"})
    recorder = SegmentRecorder(out_root=str(tmp_path), codec="XVID")

    path = recorder._open_writer(320, 240)

    assert attempts == [("XVID", ".avi", 10, (320, 240))]
    assert path.endswith(".avi")
    assert recorder.active_codec == "XVID"


def test_recorder_reports_all_codec_failures(tmp_path, monkeypatch):
    attempts = install_fake_video_writer(monkeypatch, set())
    recorder = SegmentRecorder(out_root=str(tmp_path), codec="avc1")

    with pytest.raises(RuntimeError, match="VideoWriter open failed for all codecs"):
        recorder._open_writer(640, 480)

    assert [item[0] for item in attempts] == ["avc1", "mp4v", "XVID", "MJPG"]
    assert recorder.writer is None
    assert recorder.current_path is None
