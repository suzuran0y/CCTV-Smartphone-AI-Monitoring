"""Share one JPEG of the latest frame across viewers without blocking uploads."""
import threading

import cv2
import numpy as np


def frame_state(enabled, age, threshold):
    if not enabled:
        return "disabled"
    if age is None:
        return "waiting"
    return "stale" if age >= threshold else "live"


class SharedJpegRenderer:
    def __init__(self, frame_buffer):
        self.frames = frame_buffer
        self.lock = threading.Lock()
        self.key = None
        self.jpeg = None
        self.encode_count = 0

    def render(self, cfg):
        # Uploads take only the frame-buffer lock; JPEG encoding has its own lock.
        with self.lock:
            frame, age, sequence = self.frames.snapshot(copy=False)
            state = frame_state(cfg["ingest_enabled"], age, cfg.get("frame_stale_seconds", 5))
            quality = int(cfg["jpeg_quality"])
            key = (sequence, state, quality)
            if key == self.key:
                return self.jpeg
            if state in ("disabled", "waiting"):
                frame = np.zeros((360, 640, 3), dtype=np.uint8)
                message = "Ingest OFF - enable in dashboard" if state == "disabled" else "Waiting for frames..."
            elif state == "stale":
                frame = frame.copy()
                message = "STALE - no recent frames"
            else:
                message = None
            if message:
                # A banner is part of the JPEG, so direct /stream viewers also see stale state.
                cv2.rectangle(frame, (0, 0), (frame.shape[1], 48), (0, 0, 0), -1)
                cv2.putText(frame, message, (8, 30), cv2.FONT_HERSHEY_SIMPLEX,
                            0.65, (0, 200, 255), 2)
            ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
            if not ok:
                return None
            self.key, self.jpeg = key, encoded.tobytes()
            self.encode_count += 1
            return self.jpeg
