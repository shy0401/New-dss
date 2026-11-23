"""Give freed heap memory back to the operating system after heavy work (2026-11-24).

glibc keeps memory that Python has already freed and does not hand it back on its own. Measured in the api container
(three plan evaluations + two dashboards, docs/records/2026-11-24-docker-memory-trim.md): RSS 1,098 MB, of which
``malloc_trim(0)`` returned 406 MB at once; the named caches held about 18 MB. Trimming changes no value, only which
pages the process keeps. No glibc (tests on Windows/macOS): nothing happens."""
from __future__ import annotations

import ctypes
import threading
import time

HEAVY_S = 1.0  # trim after a request or task that ran at least this long (light ones barely grow the heap)

try:
    _LIBC = ctypes.CDLL("libc.so.6")
    _LIBC.malloc_trim.argtypes = [ctypes.c_size_t]
    _LIBC.malloc_trim.restype = ctypes.c_int
except (OSError, AttributeError):
    _LIBC = None

_RUNNING = threading.Lock()


def available() -> bool:
    return _LIBC is not None


def release() -> bool:
    """One ``malloc_trim(0)``; skipped while another call is running. True when it ran."""
    if _LIBC is None or not _RUNNING.acquire(blocking=False):
        return False
    try:
        _LIBC.malloc_trim(0)
        return True
    finally:
        _RUNNING.release()


def release_if_heavy(started: float) -> bool:
    """``release`` when the work that began at ``started`` (``time.monotonic()``) took HEAVY_S or more."""
    return release() if time.monotonic() - started >= HEAVY_S else False
