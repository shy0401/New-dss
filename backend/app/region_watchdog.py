"""Region collection watchdog (2026-11-21, user: "문제 발생 시 답변 없이도 자동적으로 문제를 해결하고 다시 수집을 이어나가는 로직").

A worker task that runs every ``INTERVAL_S`` and keeps a long (national) collection going without anyone watching:

* WAITING steps whose quota reset passed → queued again (``tasks.resume_overdue_regions``; before, only the region
  screens' reads did this, so a run nobody looked at stayed waiting).
* Orphaned steps → queued again. A lane's steps are orphaned when nothing works on them: RUNNING while the region does
  not hold that lane (``tasks.LANE_HOLDER_KEY``, set with the lane lock; the worker was restarted or killed mid-run and
  another region may hold the lane by now), or QUEUED with their lane's turn come (the earlier lane of the
  region is done) and no live waiting task for that lane (``region_priority`` wait list), both only after
  ``ORPHAN_AFTER_S`` without any change to the region, so a task that was just queued is never doubled.
* FAILED steps (not BLOCKED: a key or credential problem needs a person) → asked again after ``RETRY_AFTER_S``, at most
  ``MAX_AUTO_RETRIES`` times per step (provider bursts of 503 / empty answers usually pass).
* A report of what it saw and did → ``DATA_DIR/ops/watchdog.json`` (the session and the screens can read it).

A region requeued twice by mistake is harmless: lanes take one region at a time and finished steps are skipped.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

INTERVAL_S = 600
ORPHAN_AFTER_S = 900
RETRY_AFTER_S = 1200
MAX_AUTO_RETRIES = 2
RUN_KEY = "carbon:watchdog-run"
# The lane that must be done before a lane's steps are queued (tasks.run_prepare_region / run_region_lane).
LANE_AFTER = {"basic": None, "kapt": "basic", "vworld": "basic", "bldhub": "vworld"}


def _age_s(value: Any, now: float) -> float:
    if not value:
        return float("inf")
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return float("inf")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return now - value.timestamp()


def _text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def live_waiters(conn: Any, lane: str, now: float) -> set[str]:
    """Regions whose task for ``lane`` asked for its turn within ``region_priority.STALE_S``."""
    from .region_priority import SEEN_KEY, STALE_S
    seen = conn.hgetall(SEEN_KEY.format(lane=lane)) or {}
    return {_text(code) for code, at in seen.items() if now - float(_text(at)) <= STALE_S}


def check(db: Any, conn: Any, *, now: float | None = None, queue: Callable[..., Any] | None = None,
          resume: Callable[[Any], list[str]] | None = None) -> dict[str, Any]:
    """One watchdog pass. Returns what it found and queued."""
    from sqlalchemy import select
    from .region_prepare import DONE_STATES, LANES, _mark
    from .regions import StudyRegion
    from .tasks import LANE_HOLDER_KEY, queue_region_prepare, resume_overdue_regions
    now = time.time() if now is None else now
    queue = queue or queue_region_prepare
    report: dict[str, Any] = {"at": datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="seconds"),
                              "resumed": [], "orphans": {}, "retried": {}, "blocked": {}, "preparing": 0}
    try:
        report["resumed"] = list((resume or resume_overdue_regions)(db))
    except Exception as exc:  # noqa: BLE001 - one failed part must not stop the others
        db.rollback()
        report["resume_error"] = str(exc)[:200]
    holder = {lane: _text(conn.get(LANE_HOLDER_KEY.format(lane=lane)) or "") for lane in LANES}
    waiting = {lane: live_waiters(conn, lane, now) for lane in LANES}
    for region in db.scalars(select(StudyRegion).where(StudyRegion.status.in_(("PREPARING", "PARTIAL")))).all():
        datasets = dict(region.datasets or {})
        state = lambda step: (datasets.get(step) or {}).get("status")
        quiet = _age_s(region.updated_at, now) >= ORPHAN_AFTER_S
        report["preparing"] += region.status == "PREPARING"
        again: list[str] = []
        for lane, steps in LANES.items():
            states = [state(s) for s in steps]
            before = LANE_AFTER[lane]
            turn = before is None or all(state(s) in DONE_STATES for s in LANES[before])
            if not quiet or region.code in waiting[lane]:
                continue
            if "RUNNING" in states and holder[lane] != region.code:
                again += [s for s in steps if state(s) in ("RUNNING", "QUEUED")]
            elif "QUEUED" in states and "RUNNING" not in states and turn:
                again += [s for s in steps if state(s) == "QUEUED"]
        # finalize left behind (the worker stopped between the last lane and finalize)
        if not again and quiet and state("finalize") in ("QUEUED", "RUNNING") and holder["kapt"] != region.code \
                and not any(state(s) in ("QUEUED", "RUNNING") for lane_steps in LANES.values() for s in lane_steps):
            again = ["finalize"]
        if again:
            queue(db, region, again if again == ["finalize"] else again + ["finalize"])
            report["orphans"][region.code] = again
            continue
        retry = []
        for step, item in datasets.items():
            item = item or {}
            if item.get("status") == "BLOCKED":
                report["blocked"][region.code] = report["blocked"].get(region.code, []) + [step]
            if item.get("status") != "FAILED" or step == "finalize":
                continue
            if int(item.get("auto_retries") or 0) >= MAX_AUTO_RETRIES or _age_s(item.get("at"), now) < RETRY_AFTER_S:
                continue
            retry.append(step)
        if retry:
            counts = {step: int((datasets.get(step) or {}).get("auto_retries") or 0) + 1 for step in retry}
            queue(db, region, retry + ["finalize"])
            for step, count in counts.items():
                _mark(db, region, step, "QUEUED", f"자동 재시도 {count}/{MAX_AUTO_RETRIES} (감시 작업)", auto_retries=count)
            report["retried"][region.code] = retry
    return report


def write_report(report: dict[str, Any]) -> None:
    path = Path(os.getenv("DATA_DIR", "data")) / "ops" / "watchdog.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
