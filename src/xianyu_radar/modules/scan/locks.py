"""Prevent overlapping scans of the same seller."""

from __future__ import annotations

import hashlib
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from xianyu_radar import config as cfg

_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}


@contextmanager
def seller_scan_lock(seller_id: str) -> Iterator[bool]:
    with _guard:
        thread_lock = _locks.setdefault(seller_id, threading.Lock())
    if not thread_lock.acquire(blocking=False):
        yield False
        return

    handle = None
    file_locked = False
    try:
        if os.name == "posix":
            import fcntl

            directory = Path(cfg.DATA_DIR) / "locks"
            directory.mkdir(parents=True, exist_ok=True)
            filename = hashlib.sha256(seller_id.encode("utf-8")).hexdigest() + ".lock"
            handle = (directory / filename).open("a+b")
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
            file_locked = True
        yield True
    finally:
        if handle is not None:
            if file_locked:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
        thread_lock.release()
