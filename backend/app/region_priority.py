"""Region priority for the national collection (2026-11-21, user: "핵심 지역부터 받되 범위는 그대로").

The scope stays every region × every site × every step of the analysis year; only the order changes, so whenever the
user stops the run, the regions at the top of ``backend/reference/region_priority.csv`` are complete.

* ``rank_of(code)``: rank in the table (regions not in it come after every listed one).
* Lane order (``my_turn`` / ``leave``): a lane (basic · K-apt · VWorld · 건축HUB) runs one region at a time under a Redis
  lock. Before, a task that found the lock taken asked again 30 s later and whoever asked first won, so the queue
  order was not kept. Now each waiting task puts its region in a sorted set per lane (score = rank) and takes the lock
  only when it is the first live entry. Entries whose task has not asked for ``STALE_S`` (a worker restart lost it)
  are dropped so they never block the lane.
* Stopping (``cancel``): regions queued but not started are skipped when their task comes up.
"""
from __future__ import annotations

import csv
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

TABLE = Path(__file__).resolve().parents[1] / "reference" / "region_priority.csv"
UNLISTED_RANK = 100_000
STALE_S = 120          # a waiting task asks again every LOCK_RETRY_SECONDS (30 s); four misses = gone
WAIT_KEY = "carbon:lane-wait:{lane}"
SEEN_KEY = "carbon:lane-seen:{lane}"
CANCEL_KEY = "carbon:region-cancelled"


@lru_cache(maxsize=1)
def table(path: str | None = None) -> list[dict[str, str]]:
    with open(path or TABLE, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return sorted(rows, key=lambda r: int(r["rank"]))


def rank_of(code: str) -> int:
    for row in table():
        if row["region_code"] == str(code):
            return int(row["rank"])
    return UNLISTED_RANK


def _text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def my_turn(conn: Any, lane: str, code: str, *, now: float | None = None) -> bool:
    """Register ``code`` as waiting for ``lane`` and say whether it is first in rank order."""
    now = time.time() if now is None else now
    wait, seen = WAIT_KEY.format(lane=lane), SEEN_KEY.format(lane=lane)
    conn.zadd(wait, {code: rank_of(code)}, nx=True)
    conn.hset(seen, code, now)
    for member in conn.zrange(wait, 0, -1):
        member = _text(member)
        if member == code:
            return True
        last = conn.hget(seen, member)
        if last is None or now - float(_text(last)) > STALE_S:
            conn.zrem(wait, member)
            conn.hdel(seen, member)
            continue
        return False
    return True


def leave(conn: Any, lane: str, code: str) -> None:
    conn.zrem(WAIT_KEY.format(lane=lane), code)
    conn.hdel(SEEN_KEY.format(lane=lane), code)


def waiting(conn: Any, lane: str) -> list[str]:
    return [_text(m) for m in conn.zrange(WAIT_KEY.format(lane=lane), 0, -1)]


def cancelled(conn: Any, code: str) -> bool:
    """True once for a region whose national-run task should not start (the mark is consumed)."""
    return bool(conn.srem(CANCEL_KEY, code))


def plan(db: Any, until: int, *, start: int = 1) -> list[dict[str, Any]]:
    """Rows of the table from ``start`` to ``until`` with the region's current state."""
    from .regions import StudyRegion
    out = []
    for row in table():
        rank = int(row["rank"])
        if rank < start or rank > until:
            continue
        region = db.get(StudyRegion, row["region_code"])
        out.append(dict(row, rank=rank, status=region.status if region else "NOT_CREATED"))
    return out


def queue_national(db: Any, until: int, *, start: int = 1, dry_run: bool = False, log=print) -> dict[str, Any]:
    """Queue the regions ranked ``start``..``until`` that are not ready or already queued, in rank order."""
    from .region_prepare import create_region
    from .tasks import queue_region_prepare
    stats: dict[str, Any] = {"queued": [], "ready": [], "busy": [], "missing": []}
    for row in plan(db, until, start=start):
        code = row["region_code"]
        if row["status"] == "READY":
            stats["ready"].append(code)
            continue
        if row["status"] == "PREPARING":
            stats["busy"].append(code)
            continue
        if dry_run:
            stats["queued"].append(code)
            continue
        try:
            region = create_region(db, code)
        except LookupError as exc:
            stats["missing"].append(code)
            log(f"{row['rank']} {code}: {exc}")
            continue
        queue_region_prepare(db, region)
        stats["queued"].append(code)
        log(f"{row['rank']} {code} {row.get('name') or ''}: 넣음")
    return stats


def cancel_queued(db: Any, conn: Any, *, log=print) -> list[str]:
    """Stop the national run: regions whose steps are all still QUEUED (none started) go back to waiting state.

    Their queued task finds the cancel mark and returns without running. Regions already running keep going and
    finish, so every region that started ends complete."""
    from .region_prepare import LANES, STEPS, _mark, overall_status
    from .regions import StudyRegion
    stopped = []
    for row in table():
        region = db.get(StudyRegion, row["region_code"])
        if region is None or region.status != "PREPARING":
            continue
        datasets = region.datasets or {}
        state = lambda step: (datasets.get(step) or {}).get("status")
        # not started = nothing running and the basic lane (first in every region) still waiting
        if any(state(s) == "RUNNING" for s in STEPS) or not any(state(s) == "QUEUED" for s in LANES["basic"]):
            continue
        conn.sadd(CANCEL_KEY, region.code)
        for step in STEPS:
            if state(step) == "QUEUED":
                _mark(db, region, step, "PENDING", "전국 수집 멈춤 — 다시 시작하면 이어 받음")
        region.status = overall_status(region.datasets or {})
        region.message = "전국 수집 멈춤 (순위대로 다시 시작하면 이어 받음)"
        db.commit()
        stopped.append(region.code)
        log(f"{row['rank']} {region.code}: 멈춤")
    return stopped
