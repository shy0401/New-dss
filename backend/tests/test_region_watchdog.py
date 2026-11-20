"""지역 수집 감시 작업 (2026-11-21): 끊긴 단계 · 한도 뒤 · 실패 단계를 사람 없이 다시 넣음."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import region_watchdog
from app.region_prepare import LANES, STEPS
from app.regions import StudyRegion

NOW = datetime(2026, 11, 21, 3, 0, tzinfo=timezone.utc)


class FakeRedis:
    def __init__(self):
        self.kv, self.h = {}, {}

    def get(self, key):
        return self.kv.get(key)

    def hgetall(self, key):
        return self.h.get(key, {})


def db_with(*regions):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    StudyRegion.__table__.create(engine)
    db = sessionmaker(engine)()
    for code, status, datasets, minutes_ago in regions:
        db.add(StudyRegion(code=code, name=code, sido_name="", legal_codes=[], sgis_codes=[], datasets=datasets, status=status,
                           updated_at=NOW - timedelta(minutes=minutes_ago)))
    db.commit()
    return db


def steps(**states):
    done = {s: {"status": "DONE", "at": (NOW - timedelta(hours=2)).isoformat()} for s in STEPS}
    for step, value in states.items():
        done[step] = value if isinstance(value, dict) else {"status": value, "at": (NOW - timedelta(minutes=40)).isoformat()}
    return done


def run(db, conn):
    queued = []
    report = region_watchdog.check(db, conn, now=NOW.timestamp(), queue=lambda db, region, s: queued.append((region.code, list(s))),
                                   resume=lambda db: [])
    return report, queued


def test_running_step_of_a_region_that_does_not_hold_its_lane_is_queued_again():
    db = db_with(("27260", "PREPARING", steps(kapt_energy="RUNNING", finalize="QUEUED"), 40),     # worker died mid-run
                 ("48250", "PREPARING", steps(zoning="RUNNING", finalize="QUEUED"), 40))          # still running
    conn = FakeRedis()
    conn.kv["carbon:lane-holder:kapt"] = b"41190"          # another region took the K-apt lane after the restart
    conn.kv["carbon:lane-holder:vworld"] = b"48250"
    report, queued = run(db, conn)
    assert queued == [("27260", ["kapt_energy", "finalize"])] and report["orphans"] == {"27260": ["kapt_energy"]}


def test_queued_steps_wait_for_their_turn_and_for_a_live_task():
    vworld_queued = {s: "QUEUED" for s in LANES["vworld"]}
    db = db_with(("27260", "PREPARING", steps(**vworld_queued, register="QUEUED", building_energy="QUEUED", finalize="QUEUED"), 40),  # no task
                 ("48250", "PREPARING", steps(**vworld_queued, finalize="QUEUED"), 40),                        # its task waits (live)
                 ("27230", "PREPARING", steps(grid="RUNNING", kapt_energy="QUEUED", finalize="QUEUED"), 40),    # basic still running
                 ("41190", "PREPARING", steps(kapt_energy="QUEUED", finalize="QUEUED"), 5))                   # just queued
    conn = FakeRedis()
    conn.kv["carbon:lane-holder:basic"] = b"27230"
    conn.h["carbon:lane-seen:vworld"] = {b"48250": str(NOW.timestamp() - 20).encode()}
    report, queued = run(db, conn)
    # 27260: VWorld's turn has come and nobody works on it; 건축HUB waits for VWorld, so only the VWorld steps
    assert queued == [("27260", list(LANES["vworld"]) + ["finalize"])]


def test_failed_steps_are_retried_twice_then_left_and_blocked_ones_are_reported():
    db = db_with(("27260", "PARTIAL", steps(register="FAILED"), 40),
                 ("48250", "PARTIAL", steps(register={"status": "FAILED", "auto_retries": 2, "at": (NOW - timedelta(hours=1)).isoformat()}), 40),
                 ("27230", "PARTIAL", steps(kapt_energy="BLOCKED"), 40),
                 ("41190", "PARTIAL", steps(zoning={"status": "FAILED", "at": (NOW - timedelta(minutes=5)).isoformat()}), 40))  # too soon
    report, queued = run(db, FakeRedis())
    assert queued == [("27260", ["register", "finalize"])]
    assert report["retried"] == {"27260": ["register"]} and report["blocked"] == {"27230": ["kapt_energy"]}
    retried = db.get(StudyRegion, "27260").datasets["register"]
    assert retried["auto_retries"] == 1 and retried["status"] == "QUEUED"


def test_finalize_left_behind_is_queued_alone():
    db = db_with(("27260", "PREPARING", steps(finalize="QUEUED"), 40),
                 ("44230", "PREPARING", steps(finalize="RUNNING"), 40))   # finalize running under its 건축HUB lane lock
    conn = FakeRedis()
    conn.kv["carbon:lane-holder:bldhub"] = b"44230"
    report, queued = run(db, conn)
    assert queued == [("27260", ["finalize"])]


def test_ready_regions_and_live_runs_are_left_alone():
    db = db_with(("27260", "READY", steps(), 600), ("48250", "PREPARING", steps(kapt_energy="RUNNING", finalize="QUEUED"), 40))
    conn = FakeRedis()
    conn.kv["carbon:lane-holder:kapt"] = b"48250"
    report, queued = run(db, conn)
    assert queued == [] and report["preparing"] == 1


def test_worker_start_puts_back_only_the_stopped_workers_unfinished_tasks():
    """2026-11-21: a rebuild left 267 taken-but-unfinished tasks (acks_late) waiting for the 26 h visibility timeout."""
    from app.tasks import restore_stale_unacked

    class Client:
        def zrangebyscore(self, key, low, high):
            assert key == "unacked_index"
            return [tag for tag, at in ((b"old-1", 100.0), (b"old-2", 150.0), (b"mine", 300.0)) if low <= at <= high]

    class Qos:
        def __init__(self):
            self.restored = []

        def restore_by_tag(self, tag):
            self.restored.append(tag)

    class Channel:
        unacked_index_key = "unacked_index"

        def __init__(self):
            self.client, self.qos = Client(), Qos()

    channel = Channel()
    assert restore_stale_unacked(channel, 200.0) == 2
    assert channel.qos.restored == ["old-1", "old-2"]          # the one taken after the start stays with this worker
