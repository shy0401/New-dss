from app.region_prepare import STEPS, _classify, overall_status
from app.vworld import tiles_for


def test_tiles_group_four_cells_per_km():
    tiles = tiles_for(["cell_968500_1762000", "cell_968000_1762000", "cell_968000_1762500", "cell_969000_1762000", "bad"])
    assert tiles == {(968000, 1762000): ["cell_968000_1762000", "cell_968000_1762500", "cell_968500_1762000"],
                     (969000, 1762000): ["cell_969000_1762000"]}


def test_overall_status_needs_every_step():
    done = {step: {"status": "DONE"} for step in STEPS}
    assert overall_status(done) == "READY"
    assert overall_status(dict(done, weather={"status": "SKIPPED"})) == "READY"
    assert overall_status(dict(done, kapt_energy={"status": "WAITING"})) == "PARTIAL"
    assert overall_status(dict(done, zoning={"status": "RUNNING"})) == "PREPARING"
    assert overall_status({"grid": {"status": "FAILED"}}) == "NOT_PREPARED"


def test_quota_and_credentials_are_told_apart():
    from app.cache import ExternalError
    assert _classify(ExternalError("건축HUB 일일 호출 한도 초과(22): 받은 페이지는 저장되므로 다음 날 이어서 받습니다"))[0] == "WAITING"
    assert _classify(ExternalError("공공데이터 호출 제한"))[0] == "WAITING"
    assert _classify(ExternalError("API 인증 실패: DATA_GO_KR_SERVICE_KEY 미설정"))[0] == "BLOCKED"
    assert _classify(ExternalError("SGIS 격자 API 오류: provider_code=-200"))[0] == "FAILED"
    status, message = _classify(KeyError("x"))
    assert status == "FAILED" and message == "처리 실패: KeyError"


def test_collect_energy_years_runs_newest_first_and_stops_at_the_daily_quota(monkeypatch):
    from app import energy_parcels, region_prepare
    from app.cache import ExternalError

    class Region:
        legal_codes = ["1174010100"]
        datasets = {"building_energy": {"status": "DONE", "year": 2025}}

    region = Region()

    class Db:
        def get(self, model, code):
            return region

        def rollback(self):
            pass

        def refresh(self, obj, **kw):
            pass

        def commit(self):
            pass

    calls = []

    def collect(db, year, progress, regions):
        calls.append(year)
        if year == 2022:
            raise ExternalError("공공데이터 호출 제한 (22)")
        return {"requests": 10, "inserted": 5, "updated": 0}

    monkeypatch.setattr(region_prepare, "legal_leaves", lambda db, codes: [{"sigunguCd": "11740", "bjdongCd": "10100"}])
    monkeypatch.setattr(energy_parcels, "collect_energy_all", collect)
    monkeypatch.setattr(energy_parcels, "build_parcel_grid", lambda db, codes=None: 0)
    result = region_prepare.collect_energy_years(Db(), "11740", [2019, 2022, 2024, 2023, 2021], log=lambda m: None)
    assert calls == [2024, 2023, 2022]                      # newest first; 2021 not asked after the quota answer
    assert sorted(result["done"]) == [2023, 2024] and result["left"] == [2021, 2022]
    assert result["years_before_hub"] == [2019]              # 건축HUB starts 2020: never requested
    # each year's own state: the quota-cut year is not DONE, so it reads as 잠정값 (energy_parcels.region_year_complete)
    assert region.datasets["energy_years"] == {"2024": "DONE", "2023": "DONE", "2022": "WAITING"}
    assert region.datasets["building_energy"] == {"status": "DONE", "year": 2025}


def test_region_year_complete_uses_the_region_record_not_the_city_wide_file(tmp_path, monkeypatch):
    """The progress file speaks for 전주 only. A prepared region counts its analysis year (지역 준비) and the
    years region-energy-history finished; a year the daily quota cut half way stays 잠정값."""
    import json
    from app.energy_parcels import region_year_complete
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops" / "history-progress.json").write_text(
        json.dumps({"items": {f"energy:{y}": {"status": "DONE", "scope": "all_parcels"} for y in range(2020, 2026)}}), encoding="utf-8")

    class Study:
        def __init__(self, datasets):
            self.datasets = datasets

    regions = {
        "26440": Study({"building_energy": {"status": "DONE", "year": 2025},
                        "energy_years": {"2024": "DONE", "2021": "DONE", "2020": "WAITING"}}),
        "41110": Study({"building_energy": {"status": "DONE", "message": "2025년 법정동·리 4곳, 요청 1회, 새 행 1"}}),  # older record: no year key
        "36110": Study({"building_energy": {"status": "WAITING", "year": 2025}}),
    }

    class Db:
        def get(self, model, code):
            return regions.get(code)

        def rollback(self):
            pass

    db = Db()
    assert region_year_complete(db, "52110", 2020) and region_year_complete(db, None, 2023)   # 전주: the city-wide file
    assert region_year_complete(db, "26440", 2025) and region_year_complete(db, "26440", 2024)
    assert not region_year_complete(db, "26440", 2020)      # quota stopped it half way
    assert not region_year_complete(db, "26440", 2022)      # never collected for this region
    assert region_year_complete(db, "41110", 2025) and not region_year_complete(db, "41110", 2024)
    assert not region_year_complete(db, "36110", 2025)      # the step itself is still waiting
    assert not region_year_complete(db, "99999", 2025)      # not a prepared region


def test_weather_moves_to_where_people_live_when_the_region_centre_is_at_sea(monkeypatch, tmp_path):
    """군산 (2026-10-10): the bbox centre (35.904, 126.4445) lies at sea because of 고군산군도; ERA5-Land has no cell there and
    answered null for every day (0 complete months). The step then asks at the median position of the region's K-apt complexes."""
    import json as _json
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app import collectors, region_prepare, solar
    from app.kapt import ApartmentComplex
    from app.regions import RegionWeatherMonthly

    engine = create_engine("sqlite+pysqlite:///:memory:")
    ApartmentComplex.__table__.create(engine)
    RegionWeatherMonthly.__table__.create(engine)
    db = sessionmaker(engine)()
    for code, bjd, lat, lon in (("A1", "5213010100", 35.97, 126.70), ("A2", "5213010200", 35.96, 126.72),
                                ("A3", "5213010300", 35.98, 126.74), ("X9", "5211110100", 35.82, 127.10)):
        db.add(ApartmentComplex(kapt_code=code, snapshot_month="202609", name=code, bjd_code=bjd, latitude=lat, longitude=lon, summary_json={}))
    db.commit()

    def payload(value):
        days = ["2025-01-%02d" % d for d in range(1, 32)]
        return _json.dumps({"daily": {"time": days, "temperature_2m_mean": [value] * 31, "temperature_2m_min": [value] * 31,
                                      "temperature_2m_max": [value] * 31, "precipitation_sum": [0.0 if value is not None else None] * 31}}).encode()

    asked = []

    class Client:
        def get(self, provider, operation, url, params):
            asked.append((params["latitude"], params["longitude"]))
            at_sea = params["longitude"] < 126.6
            return {"body": payload(None if at_sea else 1.5)}

    monkeypatch.setattr(collectors, "client", Client())
    monkeypatch.setattr(solar, "fetch_region", lambda *a, **k: 0)
    monkeypatch.setattr(region_prepare, "analysis_year", lambda: 2025)
    monkeypatch.setattr(region_prepare, "_root", lambda: tmp_path)
    # 군산에는 ASOS 관측소(140)가 있어, 공공데이터포털 키가 있는 PC에서는 ERA5-Land 뒤에 ASOS 덮어쓰기(_asos_overlay)가 이 가짜 client를
    # ASOS 인자(latitude 없음)로 부름. 이 시험은 ERA5-Land 지점 이동만 보므로 키를 지워 덮어쓰기를 건너뜀(키 없는 PC와 같은 결과)
    monkeypatch.delenv("DATA_GO_KR_SERVICE_KEY", raising=False)

    class Region:
        code, legal_codes, center_lat, center_lon = "52130", ["52130"], 35.904, 126.4445

    result = region_prepare.step_weather(db, Region(), print)
    assert asked == [(35.904, 126.4445), (35.97, 126.72)]  # centre first, then the median complex position (X9 is another city)
    row = db.get(RegionWeatherMonthly, ("52130", "202501"))
    assert row.days_observed == 31 and row.mean_temperature == 1.5 and (row.latitude, row.longitude) == (35.97, 126.72)
    assert "완전월 1개월" in result["message"] and "바다" in result["message"]


def test_collect_kapt_years_records_each_year_skips_done_ones_and_stops_at_the_daily_quota(monkeypatch):
    """K-apt past years of a prepared region (지역 준비 takes only the analysis year). Daily quota 5,000 calls: a year cut by the
    quota is WAITING (asked again next night, answered months are not asked again), and no further year is asked."""
    from app import kapt_energy, region_prepare
    from app.cache import ExternalError

    class Region:
        code = "52710"
        legal_codes = ["52710"]
        datasets = {"complexes": {"status": "DONE"}, "kapt_energy": {"status": "DONE", "year": 2025}, "kapt_years": {"2024": "DONE"}}

    region = Region()

    class Db:
        def get(self, model, code):
            return region

        def rollback(self):
            pass

        def refresh(self, obj, **kw):
            pass

        def commit(self):
            pass

    calls = []

    def collect(db, year, scope, **kw):
        calls.append((year, scope, kw["history"], kw["region"]))
        if year == 2022:
            raise ExternalError("공공데이터 호출 제한")
        return {"requested": 500, "normalized": 480, "failed": 0}

    monkeypatch.setattr(kapt_energy, "collect_kapt_energy", collect)
    monkeypatch.setattr(region_prepare, "_kapt_failed_months", lambda db, legal, year: 3 if year == 2023 else 0)
    result = region_prepare.collect_kapt_years(Db(), "52710", [2021, 2022, 2023, 2024], log=lambda m: None)
    assert calls == [(2023, "full", True, "52710"), (2022, "full", True, "52710")]   # 2024 already DONE; newest first
    assert result["stopped"] == "WAITING" and result["left"] == [2021, 2022, 2023]
    # 2023 has 3 months still failing at the gateway for this region: PARTIAL (asked again), never 0
    assert region.datasets["kapt_years"] == {"2024": "DONE", "2023": "PARTIAL", "2022": "WAITING"}
    assert region.datasets["kapt_energy"] == {"status": "DONE", "year": 2025}


def test_kapt_step_of_region_prepare_rides_out_a_gateway_burst_and_counts_only_its_own_region(monkeypatch):
    """10/13: two short "04" bursts left 1,086 군산 complex-months FAILED with no pause and no retry.
    The step now pauses and retries like the back-fill, and another region's failures do not fail it."""
    import pytest
    from app import kapt_energy, region_prepare
    from app.cache import ExternalError

    class Region:
        code = "52130"
        legal_codes = ["52130"]

    seen = {}

    def collect(db, year, scope, **kw):
        seen.update(kw)
        return {"requested": 1896, "normalized": 1500, "failed": 199, "not_reported": 300, "suspect": 10}  # 199 = 가평's, not this region's

    monkeypatch.setattr(kapt_energy, "collect_kapt_energy", collect)
    monkeypatch.setattr(region_prepare, "_kapt_failed_months", lambda db, legal, year: 0 if legal == ["52130"] else 199)
    result = region_prepare.step_kapt_energy(None, Region(), print)
    assert seen["region"] == "52130" and seen["retry_rounds"] == 1 and seen["outage_pause_s"] == 300 and seen["max_outage_pauses"] == 6
    assert result["rows"] == 1500

    monkeypatch.setattr(region_prepare, "_kapt_failed_months", lambda db, legal, year: 12)
    with pytest.raises(ExternalError, match="12개 단지·월"):
        region_prepare.step_kapt_energy(None, Region(), print)


def test_collect_kapt_years_needs_the_region_complexes_first():
    from app import region_prepare

    class Region:
        code = "41820"
        legal_codes = ["41820"]
        datasets = {"grid": {"status": "DONE"}}

    class Db:
        def get(self, model, code):
            return Region()

    result = region_prepare.collect_kapt_years(Db(), "41820", [2024], log=lambda m: None)
    assert result["stopped"] == "NO_COMPLEXES" and result["left"] == [2024]


def test_collect_sgis_years_resolves_each_years_codes_by_name_and_marks_unpublished_years(monkeypatch):
    """SGIS 행정동 history of a prepared region: the 시·도 list of each year names that year's 시군구 codes (they change,
    e.g. 전라북도 → 전북특별자치도), 2016 is not published (errCd -100 → no rows) and stays absent, never 0."""
    from app import region_prepare

    class Region:
        code = "52130"
        name = "전북특별자치도 군산시"
        sido_name = "전북특별자치도"
        datasets = {"sgis_years": {"2024": "DONE"}}

    region = Region()
    store: dict[str, object] = {}

    class Db:
        def get(self, model, key):
            if model is region_prepare.StudyRegion:
                return region
            return store.get(f"{model.__name__}:{key}")

        def add(self, obj):
            store[f"{type(obj).__name__}:{obj.id}"] = obj

        def rollback(self):
            pass

        def refresh(self, obj, **kw):
            pass

        def commit(self):
            pass

    calls = []

    def fetch(name, path, params, parser):
        calls.append(name)
        year = params["year"]
        if name.endswith("-sido"):
            if year == 2016:
                return {"status": "EMPTY_VALID", "rows": []}
            sido_code = "35" if year < 2024 else "52"
            sido_name = "전라북도" if year < 2024 else "전북특별자치도"
            return {"status": "SUCCESS", "rows": [{"adm_code": "31", "adm_name": "경기도", "value": 1, "value_status": "OBSERVED"},
                                                  {"adm_code": sido_code, "adm_name": sido_name, "value": 2, "value_status": "OBSERVED"}]}
        if path == "stats/searchpopulation.json" and params["adm_cd"] in ("31", "35", "52"):
            return {"status": "SUCCESS", "rows": [{"adm_code": params["adm_cd"] + "010", "adm_name": "전주시", "value": 10, "value_status": "OBSERVED"},
                                                  {"adm_code": params["adm_cd"] + "020", "adm_name": "군산시", "value": 20, "value_status": "OBSERVED"}]}
        if path == "stats/household.json" and params["adm_cd"] in ("31", "35", "52"):
            return {"status": "SUCCESS", "rows": [{"adm_code": params["adm_cd"] + "020", "adm_name": "군산시", "value": 9, "value_status": "OBSERVED",
                                                  "family_member_count": None, "average_family_member_count": None}]}
        if path == "stats/searchpopulation.json":
            return {"status": "SUCCESS", "rows": [{"adm_code": params["adm_cd"] + "01", "adm_name": "군산시 해신동", "value": 5, "value_status": "OBSERVED", "raw_record": {}}]}
        if path == "stats/household.json":
            return {"status": "SUCCESS", "rows": [{"adm_code": params["adm_cd"] + "01", "adm_name": "군산시 해신동", "value": 3, "value_status": "OBSERVED",
                                                  "family_member_count": None, "average_family_member_count": None, "raw_record": {}}]}
        return {"features": [], "raw_source_id": None}

    stored_boundaries = []
    monkeypatch.setattr(region_prepare, "_mark_year", lambda db, r, field, year, status: r.datasets.setdefault(field, {}).__setitem__(str(year), status))
    from app import sgis
    monkeypatch.setattr(sgis, "_store_boundaries", lambda db, year, code, parsed: stored_boundaries.append((year, code)) or 0)
    result = region_prepare.collect_sgis_years(Db(), "52130", [2016, 2023, 2024, 2025], log=lambda m: None, fetch=fetch)
    assert region.datasets["sgis_years"] == {"2024": "DONE", "2025": "DONE", "2023": "DONE", "2016": "NOT_PUBLISHED"}
    assert result["left"] == []
    # 2025 used the new 시·도 code 52, 2023 the old one 35: the 군산시 code of each year was asked, 전주시 was not
    assert "population-2025-52020" in calls and "population-2023-35020" in calls and "population-2023-35010" not in calls
    assert (2025, "52020") in stored_boundaries and (2023, "35020") in stored_boundaries
    assert store["SgisPopulationAdmin:2023:3502001"].population_count == 5
    assert store["SgisPopulationAdmin:2023:35020"].population_count == 20 and store["SgisHouseholdAdmin:2023:35020"].household_count == 9
    assert "SgisPopulationAdmin:2016:3502001" not in store


def test_complexes_step_is_failed_when_no_detail_page_could_be_read(monkeypatch, tmp_path):
    """2026-11-20 대구 달서: 단지 252곳 상세가 모두 실패했는데 단계가 DONE으로 끝나 난방 방식 · 주소가 빈 채로 남았다.
    상세가 하나도 없으면 FAILED(다시 실행 필요, 첫 오류를 메시지에), 하나라도 읽히면 지금처럼 DONE(실패 수는 메시지에)."""
    import json as _json
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app import kapt, region_prepare
    from app.kapt import ApartmentComplex

    engine = create_engine("sqlite+pysqlite:///:memory:")
    ApartmentComplex.__table__.create(engine)
    db = sessionmaker(engine)()
    month_dir = tmp_path / "raw" / "kapt-national" / "202610"
    month_dir.mkdir(parents=True)
    rows = [{"kaptCode": c, "kaptName": c, "bjdCode": "2729010100", "bjdName": "대곡동", "addr": "대구광역시 달서구 대곡동 1"} for c in ("A1", "A2")]
    (month_dir / "list-27290.json").write_text(_json.dumps({"resultList": rows}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(region_prepare, "_root", lambda: tmp_path)
    monkeypatch.setattr(region_prepare, "list_codes", lambda codes: ["27290"])

    def broken(client, code):
        raise RuntimeError(f"K-apt returned no detail for {code}")

    monkeypatch.setattr(kapt, "fetch_complex_detail", broken)

    class Region:
        code, legal_codes = "27290", ["27290"]

    result = region_prepare.step_complexes(db, Region(), lambda m: None, delay_s=0)
    assert result["status"] == "FAILED" and result["rows"] == 2 and result["details"] == 0
    assert "상세 실패 2개" in result["message"] and "다시 실행 필요" in result["message"] and "RuntimeError" in result["message"]
    assert db.query(ApartmentComplex).count() == 2   # 목록 값은 저장됨

    # 한 곳이라도 읽히면 DONE(상태 키 없음 = DONE), 실패 수는 메시지에
    detail = {"resultMap_kapt": {"kaptCode": "A1", "codeHeat": "지역난방"}, "resultMap_kapt_addrList": []}
    monkeypatch.setattr(kapt, "fetch_complex_detail", lambda client, code: detail if code == "A1" else broken(client, code))
    result = region_prepare.step_complexes(db, Region(), lambda m: None, delay_s=0)
    assert "status" not in result and result["details"] == 1 and "상세 실패 1개" in result["message"]

def _fake_region_db(monkeypatch):
    """SQLite에 StudyRegion 한 행, 단계 실행기는 가짜(부른 단계만 적음)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app import region_prepare
    from app.regions import StudyRegion
    engine = create_engine("sqlite+pysqlite:///:memory:")
    StudyRegion.__table__.create(engine)
    db = sessionmaker(engine)()
    db.add(StudyRegion(code="48330", name="양산시", sido_name="경상남도", legal_codes=["48330"], sgis_codes=[], datasets={}))
    db.commit()
    called = []
    monkeypatch.setattr(region_prepare, "create_region", lambda db, code: db.get(StudyRegion, code))
    monkeypatch.setattr(region_prepare, "forget_region_cache", lambda code=None: None)
    monkeypatch.setattr(region_prepare, "RUNNERS", {s: (lambda s: (lambda db, r, log: called.append(s) or {"message": "ok"}))(s) for s in region_prepare.STEPS})
    return db, called


def test_a_lane_run_keeps_the_region_preparing_while_other_lanes_are_queued(monkeypatch):
    """2026-11-21 차선 나누기(region_prepare.LANES): 한 차선이 끝나도 다른 차선 단계가 QUEUED/RUNNING이면 지역은 PREPARING."""
    from app import region_prepare
    db, called = _fake_region_db(monkeypatch)
    region = db.get(region_prepare.StudyRegion, "48330")
    for step in ("kapt_energy", "zoning", "register", "finalize"):
        region_prepare._mark(db, region, step, "QUEUED", "대기 중")
    result = region_prepare.prepare_region(db, "48330", list(region_prepare.LANES["basic"]), log=lambda m: None)
    assert called == list(region_prepare.LANES["basic"])
    assert result["status"] == "PREPARING" and result["datasets"]["kapt_energy"]["status"] == "QUEUED"
    assert region_prepare.other_lanes_busy(result["datasets"]) == ["zoning", "register", "kapt_energy"]   # finalize는 세지 않음
    called.clear()
    rest = [s for s in region_prepare.STEPS if s not in region_prepare.LANES["basic"]]
    result = region_prepare.prepare_region(db, "48330", rest, log=lambda m: None)
    assert result["status"] == "READY" and region_prepare.other_lanes_busy(result["datasets"]) == []


def test_lane_plan_and_order(monkeypatch):
    """기본 단계 뒤 K-apt · VWorld 차선을 넣고, 건축HUB는 VWorld 뒤, 정리는 마지막 차선이 함."""
    from app import tasks
    runs, queued = [], []
    monkeypatch.setattr(tasks, "_run_region_locked", lambda task, lock, code, steps, force: runs.append((lock, steps)) or {"datasets": {}})
    monkeypatch.setattr(tasks.run_region_lane, "delay", lambda *a: queued.append(a))
    tasks.run_prepare_region.run("48330", None, False)
    assert runs == [("carbon:region-prepare", ["grid", "sgis_admin", "complexes", "weather", "ordinance"])]
    assert queued == [("kapt", "48330", ["kapt_energy"], False, True, None),
                      ("vworld", "48330", ["zoning", "zoning_other", "special_areas", "buildings", "cadastral"], False, True, ["register", "building_energy"])]
    # VWorld 차선이 끝나면 건축HUB 차선을 넣고 정리는 하지 않음
    runs.clear(); queued.clear()
    tasks.run_region_lane.run("vworld", "48330", ["zoning"], False, True, ["register", "building_energy"])
    assert runs == [("carbon:region-vworld", ["zoning"])] and queued == [("bldhub", "48330", ["register", "building_energy"], False, True, None)]
    # 건축HUB 차선 끝: 다른 차선(K-apt)이 아직 돌면 정리 안 함, 다 끝났으면 정리
    runs.clear()
    monkeypatch.setattr(tasks, "_run_region_locked", lambda task, lock, code, steps, force: runs.append((lock, steps)) or {"datasets": {"kapt_energy": {"status": "RUNNING"}}})
    tasks.run_region_lane.run("bldhub", "48330", ["register"], False, True, None)
    assert runs == [("carbon:region-bldhub", ["register"])]
    runs.clear()
    monkeypatch.setattr(tasks, "_run_region_locked", lambda task, lock, code, steps, force: runs.append((lock, steps)) or {"datasets": {"kapt_energy": {"status": "DONE"}}})
    tasks.run_region_lane.run("kapt", "48330", ["kapt_energy"], False, True, None)
    assert runs == [("carbon:region-kapt", ["kapt_energy"]), ("carbon:region-kapt", ["finalize"])]
    # 일부 단계만 다시: 건축HUB만 → VWorld 없이 바로 건축HUB 차선
    queued.clear(); runs.clear()
    tasks.run_prepare_region.run("27290", ["complexes", "register", "building_energy", "finalize"], True)
    assert runs[0] == ("carbon:region-prepare", ["complexes"]) and queued == [("bldhub", "27290", ["register", "building_energy"], True, True, None)]
    assert tasks.LOCK_RETRY_SECONDS == 30 and set(tasks.LANE_LOCKS) == {"basic", "kapt", "vworld", "bldhub"}


def test_parallel_prefetch_fills_every_page_with_one_session_per_flow(monkeypatch):
    """S1(2026-11-21): 대장 · 건물 에너지 쪽을 여러 흐름으로 미리 받음. 흐름마다 자기 세션, 모든 쪽을 한 번씩."""
    import threading
    from app import energy_parcels, official
    monkeypatch.setenv("DATA_GO_KR_SERVICE_KEY", "k")
    monkeypatch.setattr(official, "official_spec", lambda *a: {})
    monkeypatch.setattr(official, "verified_operation", lambda spec, op: "u")
    seen, sessions, lock = [], [], threading.Lock()

    class Session:
        def __init__(self):
            with lock:
                sessions.append(1)
        def get(self, provider, operation, url, params):
            with lock:
                seen.append((params.get("bjdongCd"), params.get("useYm"), operation, params["pageNo"]))
            total = 250 if params.get("bjdongCd") == "10100" else 50   # 10100 = 3쪽, 나머지 1쪽
            body = ('{"response":{"header":{"resultCode":"00"},"body":{"items":{"item":[{"a":1}]},"totalCount":%d}}}' % total).encode()
            return {"body": body, "status": 200, "id": "x"}
        def forget(self, r): pass
        def reset_connection(self): pass
        def record_error(self, r, m): pass

    regions = [{"sigunguCd": "48330", "bjdongCd": b} for b in ("10100", "10200", "10300", "10400", "10500")]
    done, failed = official.prefetch_register(regions, flows=4, session_factory=Session)
    assert (done, failed) == (3 + 4, 0) and len(sessions) == 4
    assert sorted(p for b, _, _, p in seen if b == "10100") == [1, 2, 3]
    seen.clear(); sessions.clear()
    done, failed = energy_parcels.prefetch_energy(regions[:2], 2025, flows=2, months=["202501", "202502"], session_factory=Session)
    assert (done, failed) == (2 * 2 * (3 + 1), 0) and len(sessions) == 2   # (10100: 3쪽 + 10200: 1쪽) × 2달 × 전기 · 가스
    assert official.prefetch_register(regions, flows=1, session_factory=Session) == (0, 0)   # 1흐름이면 미리 받지 않음(순차 그대로)