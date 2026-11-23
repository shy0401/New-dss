import threading
import time

from app import memtrim


def test_release_runs_where_glibc_exists_and_is_a_no_op_elsewhere():
    assert memtrim.release() is memtrim.available()


def test_light_work_is_not_trimmed():
    assert memtrim.release_if_heavy(time.monotonic()) is False


def test_heavy_work_is_trimmed_once_at_a_time():
    assert memtrim.release_if_heavy(time.monotonic() - memtrim.HEAVY_S - 1) is memtrim.available()
    with memtrim._RUNNING:  # another trim is running: this one is skipped, not queued
        assert memtrim.release() is False


def test_release_from_threads():
    results = []
    threads = [threading.Thread(target=lambda: results.append(memtrim.release())) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 4 and all(isinstance(r, bool) for r in results)
