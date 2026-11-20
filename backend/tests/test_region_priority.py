"""전국 수집 지역 순위 (2026-11-21): 순위 표, 차선마다 순위대로 잠금, 멈춤."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import region_priority


class FakeRedis:
    """The few Redis calls the lane order and the lock use."""

    def __init__(self):
        self.z, self.h, self.s, self.locks = {}, {}, {}, set()

    def zadd(self, key, mapping, nx=False):
        z = self.z.setdefault(key, {})
        for member, score in mapping.items():
            if not (nx and member in z):
                z[member] = score

    def zrange(self, key, start, end):
        items = sorted(self.z.get(key, {}).items(), key=lambda kv: (kv[1], kv[0]))
        return [m.encode() for m, _ in items]

    def zrem(self, key, member):
        self.z.get(key, {}).pop(member, None)

    def hset(self, key, field, value):
        self.h.setdefault(key, {})[field] = str(value).encode()

    def hget(self, key, field):
        return self.h.get(key, {}).get(field)

    def hdel(self, key, field):
        self.h.get(key, {}).pop(field, None)

    def sadd(self, key, member):
        self.s.setdefault(key, set()).add(member)

    def srem(self, key, member):
        present = member in self.s.get(key, set())
        self.s.get(key, set()).discard(member)
        return int(present)

    def lock(self, name, **kw):
        redis = self

        class Lock:
            def acquire(self, blocking=True):
                if name in redis.locks:
                    return False
                redis.locks.add(name)
                return True

            def release(self):
                redis.locks.discard(name)

            def reacquire(self):
                pass

        return Lock()


def test_priority_table_is_complete_and_in_tier_order():
    rows = region_priority.table()
    ranks = [int(r["rank"]) for r in rows]
    assert ranks == list(range(1, len(rows) + 1)) and len(rows) == 207
    codes = [r["region_code"] for r in rows]
    assert len(set(codes)) == len(codes) and all(len(c) == 5 and c.isdigit() for c in codes)
    tiers = [int(r["tier"]) for r in rows]
    assert tiers == sorted(tiers)                                         # 1 → 4
    for tier in set(tiers):                                               # inside a tier: more complexes first
        counts = [int(r["complexes"]) for r in rows if int(r["tier"]) == tier]
        assert counts == sorted(counts, reverse=True)
    assert region_priority.rank_of("41130") == 1 and region_priority.rank_of("27260") == 4
    assert region_priority.rank_of("52110") == region_priority.UNLISTED_RANK   # 전주: ready, not in the table


def test_lane_goes_to_the_highest_ranked_live_waiter():
    conn = FakeRedis()
    low, high = "41190", "27260"                                          # ranks 20 and 4
    assert region_priority.my_turn(conn, "kapt", low, now=0)              # alone: its turn
    assert region_priority.my_turn(conn, "kapt", high, now=1)             # the higher rank is first now
    assert not region_priority.my_turn(conn, "kapt", low, now=2)          # the lower rank waits
    region_priority.leave(conn, "kapt", high)                             # the higher one took the lock
    assert region_priority.my_turn(conn, "kapt", low, now=3)
    assert region_priority.waiting(conn, "vworld") == []                  # lanes are separate


def test_a_lost_waiter_does_not_block_the_lane():
    conn = FakeRedis()
    region_priority.my_turn(conn, "vworld", "27260", now=0)               # its task was lost (worker rebuilt)
    assert not region_priority.my_turn(conn, "vworld", "41190", now=60)
    assert region_priority.my_turn(conn, "vworld", "41190", now=0 + region_priority.STALE_S + 1)
    assert region_priority.waiting(conn, "vworld") == ["41190"]


def test_locked_run_waits_for_its_rank_and_finalize_does_not(monkeypatch):
    import redis
    from app import region_prepare, tasks
    conn = FakeRedis()
    monkeypatch.setattr(redis.Redis, "from_url", lambda url: conn)
    ran = []
    monkeypatch.setattr(region_prepare, "prepare_region", lambda db, code, steps, log=None, force=False: ran.append((code, steps)) or {"datasets": {}})

    class Retry(Exception):
        pass

    class Task:
        def retry(self, countdown):
            return Retry(countdown)

    region_priority.my_turn(conn, "kapt", "27260")                        # rank 4 is waiting for the K-apt lane
    with pytest.raises(Retry):
        tasks._run_region_locked(Task(), tasks.LANE_LOCKS["kapt"], "41190", ["kapt_energy"], False)
    assert ran == [] and region_priority.waiting(conn, "kapt") == ["27260", "41190"]
    tasks._run_region_locked(Task(), tasks.LANE_LOCKS["kapt"], "41190", ["finalize"], False, ordered=False)
    assert ran == [("41190", ["finalize"])]                                # finalize skips the order
    tasks._run_region_locked(Task(), tasks.LANE_LOCKS["kapt"], "27260", ["kapt_energy"], False)
    assert ran[-1] == ("27260", ["kapt_energy"]) and region_priority.waiting(conn, "kapt") == ["41190"]
    assert conn.locks == set()                                            # released after the run


def test_cancelled_region_task_does_not_run(monkeypatch):
    import redis
    from app import tasks
    conn = FakeRedis()
    monkeypatch.setattr(redis.Redis, "from_url", lambda url: conn)
    runs = []
    monkeypatch.setattr(tasks, "_run_region_locked", lambda *a, **k: runs.append(a))
    conn.sadd(region_priority.CANCEL_KEY, "27260")
    tasks.run_prepare_region.run("27260", None, False)
    assert runs == [] and region_priority.cancelled(conn, "27260") is False   # the mark is used once
    tasks.run_prepare_region.run("27260", ["grid"], False)
    assert len(runs) == 1


def test_cancel_stops_only_regions_that_have_not_started():
    from app.region_prepare import STEPS
    from app.regions import StudyRegion
    engine = create_engine("sqlite+pysqlite:///:memory:")
    StudyRegion.__table__.create(engine)
    db = sessionmaker(engine)()
    queued = {s: {"status": "QUEUED"} for s in STEPS}
    started = dict({s: {"status": "DONE"} for s in ("grid", "sgis_admin", "complexes", "weather", "ordinance")},
                   kapt_energy={"status": "QUEUED"}, zoning={"status": "QUEUED"})
    running = dict(queued, grid={"status": "RUNNING"})
    for code, datasets in (("27260", queued), ("48250", started), ("27230", running)):
        db.add(StudyRegion(code=code, name=code, sido_name="", legal_codes=[], sgis_codes=[], datasets=datasets, status="PREPARING"))
    db.commit()
    conn = FakeRedis()
    assert region_priority.cancel_queued(db, conn, log=lambda m: None) == ["27260"]
    stopped = db.get(StudyRegion, "27260")
    assert stopped.status == "NOT_PREPARED" and all(v["status"] == "PENDING" for v in stopped.datasets.values())
    assert db.get(StudyRegion, "48250").status == "PREPARING"             # basic lane done: it finishes
    assert conn.s[region_priority.CANCEL_KEY] == {"27260"}


def test_queue_national_follows_the_table_and_skips_ready_or_busy(monkeypatch):
    from app import region_prepare, tasks
    from app.regions import StudyRegion
    engine = create_engine("sqlite+pysqlite:///:memory:")
    StudyRegion.__table__.create(engine)
    db = sessionmaker(engine)()
    db.add(StudyRegion(code="41130", name="성남", sido_name="", legal_codes=[], sgis_codes=[], datasets={}, status="PREPARING"))
    db.add(StudyRegion(code="41360", name="남양주", sido_name="", legal_codes=[], sgis_codes=[], datasets={}, status="READY"))
    db.commit()

    def create(db, code):
        if code == "48250":
            raise LookupError("없음")
        region = db.get(StudyRegion, code) or StudyRegion(code=code, name=code, sido_name="", legal_codes=[], sgis_codes=[], datasets={}, status="NOT_PREPARED")
        db.add(region); db.commit()
        return region

    queued = []
    monkeypatch.setattr(region_prepare, "create_region", create)
    monkeypatch.setattr(tasks, "queue_region_prepare", lambda db, region: queued.append(region.code))
    result = region_priority.queue_national(db, 6, log=lambda m: None)
    assert queued == ["44230", "27260", "27230"]                          # ranks 3, 4, 6 in order
    assert result["busy"] == ["41130"] and result["ready"] == ["41360"] and result["missing"] == ["48250"]
    assert region_priority.queue_national(db, 6, dry_run=True, log=lambda m: None)["queued"] == ["44230", "27260", "48250", "27230"]
