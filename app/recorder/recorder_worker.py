# pc/app/recorder/recorder_worker.py
import os
import threading
import time
import sqlite3

from .recorder import SegmentRecorder
from .storage import maintain_storage


def stop_recorder(rec_rt, logger) -> None:
    with rec_rt.lock:
        if rec_rt.rec is not None:
            try:
                rec_rt.rec.stop()
            except Exception as e:
                logger.error(f"rec.stop error: {e}")
            rec_rt.rec = None


def record_loop(cfg_store, frame_buf, rec_rt, logger, stop_event) -> None:
    last_write = 0.0
    last_storage_check = 0.0

    def check_before_segment(base_root):
        storage_cfg = {**cfg_store.get_copy(), "out_root": base_root}
        report = maintain_storage(storage_cfg, logger=logger)
        rec_rt.storage = report
        if not report["can_record"]:
            raise OSError("Disk free space below configured minimum; recording stopped")

    while not stop_event.is_set():
        cfg = cfg_store.get_copy()
        if time.monotonic() - last_storage_check >= 5:
            last_storage_check = time.monotonic()
            try:
                with rec_rt.lock:
                    active = rec_rt.rec.current_path if rec_rt.rec else None
                    storage_cfg = dict(cfg)
                    if rec_rt.rec:
                        storage_cfg["out_root"] = os.path.dirname(rec_rt.rec.out_root)
                    rec_rt.storage = maintain_storage(storage_cfg, active, logger)
                    can_record = rec_rt.storage["can_record"]
                if not can_record:
                    raise OSError("Disk free space below configured minimum; recording stopped")
            except (OSError, ValueError, sqlite3.Error) as exc:
                with rec_rt.lock:
                    changed = rec_rt.last_error != str(exc)
                    rec_rt.last_error = str(exc)
                if changed:
                    logger.error("storage protection: %s", exc)
                cfg_store.set_key("recording", False)
                stop_recorder(rec_rt, logger)
                stop_event.wait(0.2)
                continue

        is_recording = bool(cfg.get("recording", False))
        if not is_recording:
            stop_recorder(rec_rt, logger)
            time.sleep(0.05)
            continue

        record_fps = int(cfg.get("record_fps", 10))
        segment_seconds = int(cfg.get("segment_seconds", 60))
        base_root = str(cfg.get("out_root", "recordings"))
        out_root = os.path.join(base_root, "videos")
        cam_name = str(cfg.get("cam_name", "phone1"))
        codec = str(cfg.get("codec", "avc1"))

        interval = 1.0 / max(1, record_fps)

        frame = frame_buf.get_copy()
        if frame is None:
            time.sleep(0.01)
            continue

        now = time.time()
        if (now - last_write) < interval:
            time.sleep(0.001)
            continue
        last_write = now

        # Ensure recorder instance exists.
        with rec_rt.lock:
            need_create = (rec_rt.rec is None)

        if need_create:
            try:
                r = SegmentRecorder(
                    out_root=out_root,
                    fps=record_fps,
                    segment_seconds=segment_seconds,
                    codec=codec,
                    cam_name=cam_name,
                    before_open=lambda root=base_root: check_before_segment(root),
                )
                with rec_rt.lock:
                    if cfg_store.get_copy().get("recording"):
                        rec_rt.rec = r
                logger.info("SegmentRecorder created")
            except Exception as e:
                logger.error(f"create SegmentRecorder failed: {e}")
                time.sleep(0.5)
                continue

        try:
            with rec_rt.lock:
                r = rec_rt.rec
                if r is not None:
                    r.write(frame)
        except Exception as e:
            with rec_rt.lock:
                rec_rt.last_error = "Recording write failed: " + str(e)
            cfg_store.set_key("recording", False)
            logger.error(f"rec.write error: {e}")
            stop_recorder(rec_rt, logger)
            time.sleep(0.2)
    stop_recorder(rec_rt, logger)


_record_thread = None


def start_record_thread(cfg_store, frame_buf, rec_rt, logger, stop_event):
    """
    Start recorder thread once. If already running, return the existing thread.

    Note: server.py may call this twice; we keep a guard here to preserve original behavior safely.
    """
    global _record_thread
    if _record_thread is not None and _record_thread.is_alive():
        logger.warning("record thread already running; skip starting a second one")
        return _record_thread

    t = threading.Thread(
        target=record_loop,
        args=(cfg_store, frame_buf, rec_rt, logger, stop_event),
        daemon=True,
        name="record-worker",
    )
    t.start()
    _record_thread = t
    return t
