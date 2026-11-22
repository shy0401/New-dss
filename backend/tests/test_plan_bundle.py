"""U3 S1(2026-11-23): 계획 하나 → 답 하나(POST /api/plans/evaluate). 값은 기존 계산에서 꺼내기만 하고, 블록이 OK가 아니면 숫자는 null."""
import pytest

from app.area import target_bases

F = 0.433


def _client():
    from fastapi.testclient import TestClient

    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


def _effort(added=50000.0, removed=0.0, target=40.0):
    base_kwh, intensity = 11_227_619.0, 27.0
    new_kwh, rem_kwh = intensity * added, intensity * removed
    base_c, bau_c = base_kwh * F, (base_kwh + new_kwh - rem_kwh) * F
    e = {"available": True, "baseline_mode": "OBSERVED", "baseline_year": 2025, "basis": "apartments", "basis_label": "공동주택(K-apt)",
         "scope": "전력 운영탄소 기준 (가스는 이 계산에 넣지 않음)", "factor_kgco2eq_per_kwh": F, "baseline_kwh": base_kwh, "baseline_kgco2eq": base_c,
         "intensity_kwh_per_m2": intensity, "intensity_area_m2": 100000.0, "new_load_kwh": new_kwh, "removed_load_kwh": rem_kwh,
         "bau_kgco2eq": bau_c, "required_reduction_kgco2eq": bau_c - base_c * (1 - target / 100), "target_pct": target,
         "added_floor_area_m2": added, "removed_floor_area_m2": removed, "pv_yield": {"kwh_per_kw": 1200.0}, "options": {},
         "plan_roof_m2": None, "plan_roof_basis": None}
    e["targets"] = target_bases(e)
    return e


@pytest.fixture
def fake_analyze(monkeypatch):
    from app import area
    seen = {}

    def fake(db, spec, from_year, to_year, event_year=None, window=3, plan=None, target_pct=None, pv_yield=None, **kw):
        seen.update(plan=plan, target_pct=target_pct, spec=spec)
        e = _effort(added=(plan or {}).get("added_floor_area_m2") or 0.0, removed=(plan or {}).get("removed_floor_area_m2") or 0.0,
                    target=target_pct or 0.0)
        return {"effort": e, "facts": [{"id": "effort_added", "text": "이 계획으로 전력 운영탄소가 연간 … 늘어납니다", "numbers": []}],
                "history": {"area": {"grid_ids": ["cell_959500_1760500", "cell_960000_1760500"]}}, "region": {"code": "52110"}}
    monkeypatch.setattr(area, "analyze", fake)
    return seen


BODY = {"region": "52110", "area": {"type": "admin", "code": "x"}, "target_pct": 40,
        "uses_new": [{"use": "residential", "floor_area_m2": 40000, "dwellings": 400}, {"use": "commercial", "floor_area_m2": 10000}],
        "include": ["baseline", "plan_emission", "reduction"]}


def test_the_uses_are_the_floor_area_and_the_blocks_only_read_existing_results(fake_analyze):
    r = _client().post("/api/plans/evaluate", json=BODY)
    assert r.status_code == 200, r.text
    d = r.json()
    assert fake_analyze["plan"]["added_floor_area_m2"] == 50000 and d["plan"]["added_floor_area_m2"] == 50000
    pe = d["blocks"]["plan_emission"]
    added = next(t for t in d["analysis"]["effort"]["targets"] if t["key"] == "plan_added")
    assert pe["status"] == "OK" and pe["net_added_kgco2eq"] == added["net_added_kgco2eq"]      # one field, not recomputed
    assert d["blocks"]["baseline"]["data_class"] == "OBSERVED" and d["blocks"]["reduction"]["targets"]
    assert d["blocks"]["change_model"]["status"] == "NOT_REQUESTED" and d["blocks"]["ordinance"]["status"] == "NOT_REQUESTED"
    assert {s["key"] for s in d["scopes"]} >= {"plan_emission", "change_model", "district_heat"}


def test_two_different_floor_areas_in_one_plan_are_refused(fake_analyze):
    body = dict(BODY, plan={"added_floor_area_m2": 30000})
    assert _client().post("/api/plans/evaluate", json=body).status_code == 422
    body = dict(BODY, plan={"floors": 20, "building_count": 5, "footprint_per_building": 400})   # 40,000 ≠ 50,000
    r = _client().post("/api/plans/evaluate", json=body)
    assert r.status_code == 422 and "층수 × 동수" in r.json()["detail"]
    body = dict(BODY, plan={"floors": 20, "building_count": 5, "footprint_per_building": 500})   # 50,000 = 50,000
    assert _client().post("/api/plans/evaluate", json=body).status_code == 200


def test_without_a_target_only_the_plans_own_increase_is_given(fake_analyze):
    body = {k: v for k, v in BODY.items() if k != "target_pct"}
    d = _client().post("/api/plans/evaluate", json=body).json()
    red = d["blocks"]["reduction"]
    assert red["target_pct"] is None and [t["key"] for t in red["targets"]] == ["plan_added"] and "목표 %" in red["note"]


def test_the_change_model_is_not_run_on_the_public_gateway_and_points_to_the_intensity_value(fake_analyze):
    body = dict(BODY, include=["plan_emission", "change_model"])
    d = _client().post("/api/plans/evaluate", json=body, headers={"X-Public-Gateway": "1"}).json()
    cm = d["blocks"]["change_model"]
    assert cm["status"] == "RESTRICTED" and cm["change_tco2e"] is None
    assert cm["fallback"]["block"] == "plan_emission" and "늘어납니다" in cm["fallback"]["text"]


def test_no_uses_means_no_change_model_never_a_guessed_use(fake_analyze):
    body = {k: v for k, v in BODY.items() if k != "uses_new"} | {"plan": {"added_floor_area_m2": 50000}, "include": ["change_model"]}
    cm = _client().post("/api/plans/evaluate", json=body).json()["blocks"]["change_model"]
    assert cm["status"] == "NO_USES" and cm["change_tco2e"] is None


def test_a_region_without_a_team_table_says_so_before_asking_the_service(fake_analyze, monkeypatch):
    from app import team_grid, team_model
    monkeypatch.setattr(team_grid, "region_datasets", lambda db, code: [])
    monkeypatch.setattr(team_model, "predict_area", lambda *a, **k: pytest.fail("the service must not be asked"))
    cm = _client().post("/api/plans/evaluate", json=dict(BODY, include=["change_model"])).json()["blocks"]["change_model"]
    assert cm["status"] == "NO_TEAM_TABLE_REGION" and "준비 중" in cm["reason"]


def test_a_change_below_1000_t_is_read_for_direction_only(fake_analyze, monkeypatch):
    from app import team_grid, team_model
    monkeypatch.setattr(team_grid, "region_datasets", lambda db, code: ["52110_전주시"])
    monkeypatch.setattr(team_model, "cell_dataset", lambda db, code, x, y: "52110_전주시")
    monkeypatch.setattr(team_model, "service_status", lambda: {"status": "ready"})
    monkeypatch.setattr(team_model, "predict_area", lambda body, request: {
        "combined": {"change_tco2e": 640.0, "band": {"q10": 200.0, "q90": 1100.0}}, "results": [{"emission_before_tco2e": 100.0}, {"emission_before_tco2e": 50.0}],
        "area": {"cells_used": [{"x": 1, "y": 2}, {"x": 3, "y": 4}], "cells_skipped": [], "cells_total": 2, "year": 2024}, "train": "00_합본_7차"})
    cm = _client().post("/api/plans/evaluate", json=dict(BODY, include=["change_model"])).json()["blocks"]["change_model"]
    assert cm["status"] == "OK" and cm["reading"] == "direction" and cm["change_tco2e"] == 640.0 and cm["band_q90_tco2e"] == 1100.0
    assert cm["emission_before_tco2e"] == 150.0 and cm["accuracy_row"]["band"].startswith("교차검증 2~9칸")
    assert "floors" in cm["not_used"]


def test_district_heat_needs_one_cell():
    from app.plan_bundle import district_heat_block
    b = district_heat_block(None, _effort(), None, "52110")
    assert b["status"] == "NEEDS_CELL" and b["heat_kwh"] is None


def test_coverage_ratio_is_the_one_cell_formula():
    from app.domain import coverage_ratio_pct
    assert coverage_ratio_pct(2500, 10000) == 25.0 and coverage_ratio_pct(None, 10000) is None and coverage_ratio_pct(100, 0) is None
