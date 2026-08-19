# pc/app/recorder/recorder.py
import os
import time
from datetime import datetime

import cv2


CODEC_EXTENSIONS = {
    "avc1": ".mp4",
    "H264": ".mp4",
    "mp4v": ".mp4",
    "XVID": ".avi",
    "MJPG": ".avi",
}
SAFE_FALLBACK_CODECS = ("mp4v", "XVID", "MJPG")


class SegmentRecorder:
    """
    Continuously writes video and rotates files by fixed duration.

    Output example:
      recordings/videos/YYYYMMDD/phone1_YYYYMMDD_HHMMSS.mp4
    """
    def __init__(self, out_root: str = "recordings", fps: int = 10, segment_seconds: int = 60,
                 codec: str = "mp4v", cam_name: str = "cam1"):
        self.out_root = out_root
        self.fps = fps
        self.segment_seconds = segment_seconds
        self.requested_codec = codec
        self.active_codec = None
        self.cam_name = cam_name

        self.writer = None
        self.segment_start_ts = None
        self.current_path = None
        os.makedirs(self.out_root, exist_ok=True)

    def _codec_candidates(self):
        primary = self.active_codec or self.requested_codec
        candidates = [primary, *SAFE_FALLBACK_CODECS]
        return list(dict.fromkeys(candidates))

    def _make_path(self, codec: str) -> str:
        now = datetime.now()
        day_dir = os.path.join(self.out_root, now.strftime("%Y%m%d"))
        os.makedirs(day_dir, exist_ok=True)
        extension = CODEC_EXTENSIONS.get(codec, ".mp4")
        stem = f"{self.cam_name}_{now.strftime('%Y%m%d_%H%M%S')}"
        path = os.path.join(day_dir, f"{stem}{extension}")
        suffix = 1
        while os.path.exists(path):
            path = os.path.join(day_dir, f"{stem}_{suffix:03d}{extension}")
            suffix += 1
        return path

    def _open_writer(self, frame_w: int, frame_h: int) -> str:
        failures = []
        for codec in self._codec_candidates():
            if len(codec) != 4:
                failures.append(f"{codec!r}: FourCC must contain exactly 4 characters")
                continue

            path = self._make_path(codec)
            writer = None
            try:
                fourcc = cv2.VideoWriter_fourcc(*codec)
                writer = cv2.VideoWriter(path, fourcc, self.fps, (frame_w, frame_h))
                if writer.isOpened():
                    self.writer = writer
                    self.current_path = path
                    self.segment_start_ts = time.time()
                    previous_codec = self.active_codec or self.requested_codec
                    self.active_codec = codec
                    if codec != previous_codec:
                        print(f"[REC] codec fallback {previous_codec} -> {codec}")
                    return path
                failures.append(f"{codec}: writer did not open")
            except Exception as exc:
                failures.append(f"{codec}: {exc}")
            finally:
                if writer is not None and writer is not self.writer:
                    writer.release()
                if writer is not self.writer and os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass

        self.writer = None
        self.current_path = None
        self.segment_start_ts = None
        detail = "; ".join(failures)
        raise RuntimeError(f"VideoWriter open failed for all codecs ({detail})")

    def _close_writer(self) -> None:
        if self.writer is not None:
            self.writer.release()
        self.writer = None
        self.segment_start_ts = None
        self.current_path = None

    def write(self, frame_bgr) -> None:
        """Write one frame; auto-open and auto-rotate by time."""
        h, w = frame_bgr.shape[:2]
        now = time.time()

        if self.writer is None:
            path = self._open_writer(w, h)
            print(f"[REC] start {path}")

        if self.segment_start_ts is not None and (now - self.segment_start_ts) >= self.segment_seconds:
            old = self.current_path
            self._close_writer()
            path = self._open_writer(w, h)
            print(f"[REC] rotate {old} -> {path}")

        self.writer.write(frame_bgr)

    def stop(self) -> None:
        if self.writer is not None:
            print(f"[REC] stop {self.current_path}")
        self._close_writer()
