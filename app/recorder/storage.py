"""Bounded retention of explicitly registered, completed Sentinel recordings."""
import os
import re
import shutil
import sqlite3
import stat
import time
from pathlib import Path

GIB = 1024 ** 3


def safe_root(value):
    path = Path(os.path.abspath(value))
    if path in (Path(path.anchor), Path.home(), Path.cwd()):
        raise ValueError("choose a dedicated recordings directory")
    for part in (path, *path.parents):
        if part.exists():
            info = part.lstat()
            if part.is_symlink() or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError("recording paths cannot contain links or junctions")
    return path


def register_recording(video_root, filename):
    root = safe_root(video_root)
    path = Path(filename).absolute()
    relative = path.relative_to(root).as_posix()
    if not re.fullmatch(r"\d{8}/[A-Za-z0-9_-]+_\d{8}_\d{6}(?:_\d+)?\.(mp4|avi)", relative):
        raise ValueError("invalid recording filename")
    index = safe_root(root / ".sentinel-recordings.sqlite3")
    db = sqlite3.connect(str(index))
    try:
        with db:
            db.execute("CREATE TABLE IF NOT EXISTS recordings (path TEXT PRIMARY KEY, completed REAL)")
            db.execute("INSERT OR REPLACE INTO recordings VALUES (?, ?)", (relative, time.time()))
    finally:
        db.close()


def maintain_storage(cfg, active_path=None, logger=None):
    root = safe_root(Path(cfg["out_root"]) / "videos")
    root.mkdir(parents=True, exist_ok=True)
    active = Path(active_path).absolute() if active_path else None
    free = shutil.disk_usage(root).free
    min_free = float(cfg.get("record_min_free_gb", 1)) * GIB
    removed = 0
    index = root / ".sentinel-recordings.sqlite3"
    if cfg.get("record_cleanup_enabled") and index.exists():
        safe_root(index)
        db = sqlite3.connect(str(index))
        try:
            rows = db.execute("SELECT path, completed FROM recordings ORDER BY completed").fetchall()
            files = []
            for relative, completed in rows:
                if not re.fullmatch(r"\d{8}/[A-Za-z0-9_-]+_\d{8}_\d{6}(?:_\d+)?\.(mp4|avi)", relative):
                    continue
                path = root / relative
                safe_root(path)
                if path.exists() and path != active:
                    files.append((path, completed, path.stat().st_size, relative))
            total = sum(f[2] for f in files) + (active.stat().st_size if active and active.exists() else 0)
            maximum = float(cfg.get("record_max_storage_gb", 20)) * GIB
            cutoff = time.time() - int(cfg.get("record_retention_days", 7)) * 86400
            for path, completed, size, relative in files:
                if completed >= cutoff and total <= maximum and free >= min_free:
                    continue
                # Validate the exact target again immediately before deletion.
                safe_root(path)
                path.relative_to(root)
                path.unlink()
                with db:
                    db.execute("DELETE FROM recordings WHERE path=?", (relative,))
                total -= size
                free = shutil.disk_usage(root).free
                removed += 1
                if logger:
                    logger.info("retention removed completed recording: %s", path)
        finally:
            db.close()
    return {"free_gb": round(free / GIB, 3), "removed": removed, "can_record": free >= min_free}
