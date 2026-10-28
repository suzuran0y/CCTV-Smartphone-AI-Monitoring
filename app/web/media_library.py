"""Read-only access to media in the currently configured output directory."""
import heapq
import os
import re
import stat
from pathlib import Path

from app.recorder.storage import safe_root


KINDS = {"videos": {".mp4", ".avi"}, "snapshots": {".jpg"}}
VIDEO = re.compile(r"\d{8}/[A-Za-z0-9_-]+_\d{8}_\d{6}(?:_\d+)?\.(?:mp4|avi)\Z")
SNAPSHOT = re.compile(r"\d{8}/snapshot_\d{8}_\d{6}(?:_\d+)?\.jpg\Z")


def media_path(output, kind, relative):
    if kind not in KINDS:
        raise ValueError("unknown media kind")
    pattern = VIDEO if kind == "videos" else SNAPSHOT
    if not isinstance(relative, str) or not pattern.fullmatch(relative):
        raise ValueError("invalid media path")
    root = safe_root(Path(output) / kind)
    path = safe_root(root / relative)
    path.relative_to(root)
    return path


def list_media(output, kind, active, page=1, page_size=25):
    if kind not in KINDS:
        raise ValueError("unknown media kind")
    root = safe_root(Path(output) / kind)
    active = Path(active).absolute() if active else None

    def entries():
        if not root.exists():
            return
        with os.scandir(root) as days:
            for day in days:
                if not re.fullmatch(r"\d{8}", day.name) or not day.is_dir(follow_symlinks=False):
                    continue
                try:
                    safe_root(day.path)
                    with os.scandir(day.path) as files:
                        for item in files:
                            relative = day.name + "/" + item.name
                            try:
                                path = media_path(output, kind, relative)
                                if path == active or not item.is_file(follow_symlinks=False):
                                    continue
                                info = path.stat()
                            except (OSError, ValueError):
                                continue
                            yield {"path": relative, "name": item.name,
                                   "size_bytes": info.st_size, "modified_at": info.st_mtime}
                except (OSError, ValueError):
                    continue

    # Bound memory even when a deployment has years of segments. Offset is capped by the API.
    end = page * page_size
    newest = heapq.nlargest(end + 1, entries(), key=lambda row: (row["modified_at"], row["path"]))
    return {"items": newest[(page - 1) * page_size:end], "has_more": len(newest) > end,
            "page": page, "page_size": page_size}


def open_media(output, kind, relative, active):
    path = media_path(output, kind, relative)
    if active and path == Path(active).absolute():
        raise PermissionError("recording is still being written")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        # Revalidate after opening; never serve a symlink/junction or a replaced target.
        media_path(output, kind, relative)
        if not stat.S_ISREG(info.st_mode) or not os.path.samestat(info, path.stat()):
            raise ValueError("media changed while opening")
        stream = os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise
    return stream, info, path.name
