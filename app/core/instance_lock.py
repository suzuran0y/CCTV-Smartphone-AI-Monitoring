"""Lock a data directory for the lifetime of the owning process."""
import os
from contextlib import contextmanager


@contextmanager
def instance_lock(path):
    with open(path, "a+b") as handle:
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError("This Sentinel data directory is already in use.") from error
        yield
