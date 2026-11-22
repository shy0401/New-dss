"""사용자 단계 U0(2026-11-23): 이유 없는 500 대신 404 · 422 · 504, 공개 주소의 쓰기 막기, 지역별 목록, 지우기."""
import urllib.error

import pytest


def _client():
    from fastapi.testclient import TestClient

    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


PUBLIC = {"X-Public-Gateway": "1"}


def test_an_unprepared_region_is_a_404_with_the_reason_on_every_reader(monkeypatch):
    """보고서 만들기가 준비하지 않은 지역에 닿으면 500이 아니라 404와 까닭(전역 처리)."""
    from app import reporting
    from app.regions import RegionNotReady

    def not_ready(*a, **k):
        raise RegionNotReady("인천광역시 제물포구의 분석 격자가 아직 없습니다")
    monkeypatch.setattr(reporting, "create_snapshot", not_ready)
    r = _client().post("/api/reports", json={"year": 2025, "grid_id": None, "scenario_ids": [], "region": "28125"})
    assert r.status_code == 404 and "분석 격자가 아직 없습니다" in r.json()["detail"]


def test_a_radius_area_without_its_centre_is_a_422_not_a_crash():
    from app.area import resolve_area
    with pytest.raises(ValueError, match="중심 좌표"):
        resolve_area({"type": "circle", "radius_m": 1000}, [], [], [], {})


def test_the_public_gateway_cannot_start_collection_change_settings_upload_or_delete():
    c = _client()
    for method, path in (("post", "/api/regions/11110/prepare"), ("post", "/api/regions/national/collect"), ("post", "/api/collections"),
                         ("post", "/api/collection/missing"), ("post", "/api/v1/collection-jobs"), ("post", "/api/system/offline"),
                         ("post", "/api/uploads/preview"), ("delete", "/api/scenarios/x"), ("delete", "/api/reports/x"),
                         ("delete", "/api/area-reports/x")):
        r = getattr(c, method)(path, headers=PUBLIC, **({"json": {}} if method == "post" else {}))
        assert r.status_code == 403 and "공개 시연 주소" in r.json()["detail"], (method, path, r.status_code)


def test_plans_reports_and_analyses_stay_open_on_the_public_gateway():
    from app.main import PUBLIC_BLOCKED_WRITE
    for path in ("/api/scenarios", "/api/optimize", "/api/reports", "/api/area-reports", "/api/areas/analyze", "/api/regions/52110/open",
                 "/api/scenarios/abc/image", "/api/team-model/predict"):
        assert PUBLIC_BLOCKED_WRITE.match(path) is None, path


def test_a_slow_team_model_is_told_apart_from_one_that_is_off(monkeypatch):
    from app import team_model
    plan = {"region": "52110", "plans": [{"grid": "cell_959500_1760500", "new": [{"floor_area_m2": 5000}]}]}
    monkeypatch.setattr(team_model, "_model_region", lambda db, code, cells: None)
    monkeypatch.setattr(team_model, "_call", lambda *a, **k: (team_model.TIMEOUT, None))
    r = _client().post("/api/team-model/predict", json=plan)
    assert r.status_code == 504 and "230초 안에" in r.json()["detail"]
    area = {"region": "52110", "grids": ["cell_959500_1760500"], "new": [{"floor_area_m2": 5000}]}
    r = _client().post("/api/team-model/predict-area", json=area)
    assert r.status_code == 504 and "칸 수를 줄여" in r.json()["detail"]
    monkeypatch.setattr(team_model, "_call", lambda *a, **k: (0, None))
    assert "꺼져" in _client().post("/api/team-model/predict", json=plan).json()["detail"]


def test_call_reports_a_timeout_separately(monkeypatch):
    from app import team_model

    def raiser(exc):
        def f(*a, **k):
            raise exc
        return f
    monkeypatch.setattr(team_model.urllib.request, "urlopen", raiser(TimeoutError("timed out")))
    assert team_model._call("/status") == (team_model.TIMEOUT, None)
    monkeypatch.setattr(team_model.urllib.request, "urlopen", raiser(urllib.error.URLError(TimeoutError("timed out"))))
    assert team_model._call("/status") == (team_model.TIMEOUT, None)
    monkeypatch.setattr(team_model.urllib.request, "urlopen", raiser(urllib.error.URLError(ConnectionRefusedError())))
    assert team_model._call("/status") == (0, None)
    # the area wait stays under the 240 s of nginx in front of the screen (frontend/nginx.conf, deploy/gateway.conf)
    assert team_model.PREDICT_TIMEOUT_S < 240


def test_a_saved_record_without_a_region_is_placed_by_its_grid(monkeypatch):
    from app import regions
    calls = []
    monkeypatch.setattr(regions, "region_for_grid", lambda db, g: calls.append(g) or "52710")
    cache: dict = {}
    assert regions.record_region(None, "41110", "cell_1_2", cache) == "41110"
    assert regions.record_region(None, None, "cell_1_2", cache) == "52710"
    assert regions.record_region(None, None, "cell_1_2", cache) == "52710" and calls == ["cell_1_2"]  # looked up once
    assert regions.record_region(None, None, None, cache) == "52710"  # no grid: region_for_grid's answer, as when saved
    assert calls == ["cell_1_2", None]


def test_analyze_answers_422_for_a_radius_area_without_its_centre():
    r = _client().post("/api/areas/analyze", json={"region": "52110", "area": {"type": "circle", "radius_m": 1000}})
    assert r.status_code == 422 and "중심 좌표" in r.json()["detail"]


def test_deleting_a_plan_removes_its_result_and_image_and_leaves_other_kinds_alone():
    """이 PC(공개 주소 아님)에서는 지울 수 있다. 계획안 지우기는 결과 · 3D 이미지도 함께, 보고서 종류는 서로 못 지움."""
    import uuid

    from app.db import Session
    from app.models import Scenario, ScenarioImage, ScenarioResult
    from app.reporting import DecisionReport
    sid, plan_rid, area_rid = (f"test-u0-{uuid.uuid4()}" for _ in range(3))
    with Session() as db:
        db.add(Scenario(id=sid, inputs={"region": "52110", "grid_id": None}))
        db.flush()
        db.add(ScenarioResult(id=sid, result={}))
        db.add(ScenarioImage(scenario_id=sid, png=b"\x89PNG"))
        db.add(DecisionReport(id=plan_rid, snapshot={"kind": "PLAN", "year": 2025, "grid_id": None, "summary": {"mode": "x"}}))
        db.add(DecisionReport(id=area_rid, snapshot={"kind": "AREA", "region": {"code": "52110"}, "summary": {}}))
        db.commit()
    c = _client()
    try:
        assert sid in [s["id"] for s in c.get("/api/scenarios", params={"region": "52110"}).json()]
        assert sid not in [s["id"] for s in c.get("/api/scenarios", params={"region": "41110"}).json()]
        assert area_rid in [r["id"] for r in c.get("/api/area-reports", params={"region": "52110"}).json()]
        assert c.delete(f"/api/area-reports/{plan_rid}").status_code == 404   # a plan report is not an area report
        assert c.delete(f"/api/reports/{area_rid}").status_code == 404
        assert c.delete(f"/api/scenarios/{sid}").status_code == 204
        assert c.delete(f"/api/reports/{plan_rid}").status_code == 204
        assert c.delete(f"/api/area-reports/{area_rid}").status_code == 204
        assert c.delete(f"/api/scenarios/{sid}").status_code == 404
        with Session() as db:
            assert db.get(ScenarioResult, sid) is None and db.get(ScenarioImage, sid) is None and db.get(DecisionReport, plan_rid) is None
    finally:
        with Session() as db:
            for model, key in ((ScenarioImage, sid), (ScenarioResult, sid), (Scenario, sid), (DecisionReport, plan_rid), (DecisionReport, area_rid)):
                row = db.get(model, key)
                if row is not None:
                    db.delete(row)
                    db.flush()
            db.commit()


def test_a_public_request_to_an_open_path_is_not_stopped_by_the_gateway_rule(monkeypatch):
    from app import team_model
    monkeypatch.setattr(team_model, "_call", lambda *a, **k: (0, None))
    r = _client().post("/api/areas/analyze", json={"region": "52110", "area": {"type": "circle", "radius_m": 1000}}, headers=PUBLIC)
    assert r.status_code == 422  # reached the endpoint (the gateway rule would answer 403)
