"""팀 변화 모델 연결: 공개 주소 거부, 서비스가 꺼졌을 때의 안내, 칸 좌표 전달과 추정 표시."""
from pathlib import Path
from typing import Any

import pytest


def _client():
    from fastapi.testclient import TestClient

    from app.main import app
    return TestClient(app)


def test_the_public_gateway_never_reaches_the_team_model():
    c = _client()
    public = {"X-Public-Gateway": "1"}
    assert c.get("/api/team-model/status", headers=public).json()["status"] == "restricted"
    r = c.post("/api/team-model/predict", json={"region": "52110", "plans": [{"grid": "cell_959500_1760500", "new": [{"floor_area_m2": 1000}]}]},
               headers=public)
    assert r.status_code == 403 and "공개 시연 주소" in r.json()["detail"]
    assert c.get("/api/team-model/cell", params={"grid": "cell_959500_1760500"}, headers=public).status_code == 403


def test_status_says_the_service_is_off_when_it_does_not_answer(monkeypatch):
    from app import team_model
    monkeypatch.setattr(team_model, "_call", lambda path, body=None, timeout=5.0: (0, None))
    body = _client().get("/api/team-model/status").json()
    assert body["status"] == "off" and "profile team-model" in body["reason"]
    assert body["accuracy"]["test"][1]["band"] == "1천~1만" and body["accuracy"]["test"][1]["median_error"] == 0.27


def test_predict_sends_the_cell_corner_and_marks_the_answer_as_a_scenario(monkeypatch):
    from app import team_model
    sent: dict[str, Any] = {}

    def fake(path, body=None, timeout=5.0):
        sent.update(path=path, body=body)
        return 200, {"dataset": "52110_전주시", "results": [{"change_tco2e": 2500.0, "band": {"q10": 900.0}}], "combined": None}
    monkeypatch.setattr(team_model, "_call", fake)
    monkeypatch.setattr(team_model, "_model_region", lambda db, code, cells: None)   # 팀 표를 못 찾으면 지역 코드 그대로
    r = _client().post("/api/team-model/predict", json={"region": "52110", "plans": [
        {"grid": "cell_959500_1760500", "new": [{"use": "residential", "floor_area_m2": 120000, "dwellings": 1200}], "years_after": 3}]})
    assert r.status_code == 200
    plan = sent["body"]["plans"][0]
    assert sent["path"] == "/predict" and sent["body"]["region"] == "52110" and (plan["x"], plan["y"]) == (959500, 1760500)
    assert plan["new"] == [{"use": "residential", "floor_area_m2": 120000.0, "dwellings": 1200.0}] and plan["removed"] == []
    body = r.json()
    assert body["data_class"] == "SCENARIO" and body["results"][0]["grid"] == "cell_959500_1760500" and "방향만" in body["note"]


@pytest.mark.parametrize("payload,code", [
    ({"region": "52110", "plans": [{"grid": "cell_1_2"}]}, 422),                                               # nothing built or removed
    ({"region": "52110", "plans": [{"grid": "cell_1_2", "new": [{"use": "factory", "floor_area_m2": 10}]}]}, 422),  # unknown use
    ({"region": "52110", "plans": [{"grid": "x", "new": [{"floor_area_m2": 10}]}]}, 422),
])
def test_predict_rejects_plans_the_model_cannot_read(monkeypatch, payload, code):
    from app import team_model
    monkeypatch.setattr(team_model, "_call", lambda *a, **k: pytest.fail("the service must not be asked"))
    assert _client().post("/api/team-model/predict", json=payload).status_code == code


def test_predict_passes_the_reason_when_the_model_is_off_or_still_training(monkeypatch):
    from app import team_model
    plan = {"region": "52110", "plans": [{"grid": "cell_959500_1760500", "new": [{"floor_area_m2": 5000}]}]}
    monkeypatch.setattr(team_model, "_call", lambda *a, **k: (0, None))
    r = _client().post("/api/team-model/predict", json=plan)
    assert r.status_code == 503 and "꺼져" in r.json()["detail"]
    monkeypatch.setattr(team_model, "_call", lambda *a, **k: (503, {"detail": "변화 모델을 학습하는 중입니다(1~3분)", "status": "training"}))
    r = _client().post("/api/team-model/predict", json=plan)
    assert r.status_code == 503 and "학습하는 중" in r.json()["detail"]


def test_area_predict_sends_cell_corners_and_totals_and_names_the_cells_back(monkeypatch):
    from app import team_model
    sent: dict[str, Any] = {}

    def fake(path, body=None, timeout=5.0):
        sent.update(path=path, body=body)
        return 200, {"dataset": "52110_전주시", "results": [{"change_tco2e": 1200.0}],
                     "combined": {"change_tco2e": 1200.0, "band": {"q10": 500.0, "q90": 1900.0}},
                     "area": {"split": "equal", "cells_total": 2, "cells_used": [{"x": 959500, "y": 1760500, "grid_id": "g1"}],
                              "cells_skipped": [{"x": 960000, "y": 1760500, "reason": "쓸 수 있는 해가 없는 칸(결측·결함 표시)"}]}}
    monkeypatch.setattr(team_model, "_call", fake)
    monkeypatch.setattr(team_model, "_model_region", lambda db, code, cells: "52113" if len(cells) == 2 else None)
    r = _client().post("/api/team-model/predict-area", json={
        "region": "52110", "grids": ["cell_959500_1760500", "cell_960000_1760500", "cell_959500_1760500"],
        "new": [{"use": "residential", "floor_area_m2": 200000, "dwellings": 2000}, {"use": "commercial", "floor_area_m2": 30000}],
        "years_after": 7})
    assert r.status_code == 200
    assert sent["path"] == "/predict-area" and sent["body"]["region"] == "52113"  # the team region holding the cells
    assert sent["body"]["cells"] == [{"x": 959500, "y": 1760500}, {"x": 960000, "y": 1760500}]  # duplicates dropped, order kept
    assert sent["body"]["new"][0] == {"use": "residential", "floor_area_m2": 200000.0, "dwellings": 2000.0} and sent["body"]["removed"] == []
    body = r.json()
    assert body["data_class"] == "SCENARIO" and "같게 나눠" in body["note"]
    assert body["results"][0]["grid"] == "cell_959500_1760500"
    assert body["area"]["cells_skipped"][0]["grid"] == "cell_960000_1760500"


@pytest.mark.parametrize("payload", [
    {"region": "52110", "grids": ["cell_959500_1760500"]},                                                  # nothing built or removed
    {"region": "52110", "grids": [f"cell_{959500 + 500 * i}_1760500" for i in range(65)], "new": [{"floor_area_m2": 10}]},  # > 64 cells
    {"region": "52110", "grids": ["x"], "new": [{"floor_area_m2": 10}]},
    {"region": "52110", "grids": ["cell_1_2"], "new": [{"floor_area_m2": 10}] * 5},                            # > 4 use rows
])
def test_area_predict_rejects_what_the_model_cannot_read(monkeypatch, payload):
    from app import team_model
    monkeypatch.setattr(team_model, "_call", lambda *a, **k: pytest.fail("the service must not be asked"))
    assert _client().post("/api/team-model/predict-area", json=payload).status_code == 422


def test_area_predict_is_closed_on_the_public_gateway():
    r = _client().post("/api/team-model/predict-area", json={"region": "52110", "grids": ["cell_959500_1760500"], "new": [{"floor_area_m2": 1000}]},
                       headers={"X-Public-Gateway": "1"})
    assert r.status_code == 403


# The api image holds only backend/, so inside the Compose container deploy/ is not there.
# GitHub CI and a pytest run from the repo checkout (docs/TEAM_SETUP.md 4절) do run it.
TEAM_SERVER = Path(__file__).resolve().parents[2] / "deploy" / "team-model" / "server.py"


@pytest.mark.skipif(not TEAM_SERVER.exists(),
                    reason="deploy/team-model/server.py가 없음(api 컨테이너에는 backend/만 들어 있음). 저장소 폴더에서 돌리면 확인됨")
def test_service_splits_a_development_equally_over_its_cells():
    import importlib.util
    spec = importlib.util.spec_from_file_location("team_server", TEAM_SERVER)
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    got = server.split_equal([{"use": "residential", "floor_area_m2": 90000, "dwellings": 900}, {"use": "office", "floor_area_m2": 30000}], 3)
    assert got == [{"use": "residential", "floor_area_m2": 30000.0, "dwellings": 300.0}, {"use": "office", "floor_area_m2": 10000.0}]
    assert server.MAX_PLANS == 64
    # every cell of the development starts from the same year: the latest year at least half of the cells can use
    assert server.common_year([{2016, 2021}, {2021}, {2014, 2021}, {2024}]) == 2021
    assert server.common_year([{2018, 2024}, {2018, 2024}, {2018}, {2018}]) == 2024
    assert server.common_year([{2016}, {2021}]) == 2021
    assert server.common_year([{2014}, {2016}, {2018}]) == 2018  # no year with half: the most cells, the later on a tie
    assert server.common_year([set(), set()]) is None
    assert server.nearest_year({2014, 2018, 2021}, 2019) == 2018 and server.nearest_year({2017, 2021}, 2019) == 2017


def test_cell_predict_asks_the_team_table_of_the_gu_like_the_area_predict(monkeypatch):
    """2026-11-23: 수원(41110)처럼 팀 데이터셋이 구 단위 표인 시는 칸이 든 구 표(예: 41117)로 묻는다(전에는 시 코드로 물어 404)."""
    from app import team_model
    sent: dict[str, Any] = {}

    def fake(path, body=None, timeout=5.0):
        sent.update(body=body)
        return 200, {"results": [{"change_tco2e": 10.0}], "combined": None}
    monkeypatch.setattr(team_model, "_call", fake)
    monkeypatch.setattr(team_model, "_model_region", lambda db, code, cells: "41117" if code == "41110" and len(cells) == 1 else None)
    r = _client().post("/api/team-model/predict", json={"region": "41110", "plans": [{"grid": "cell_961000_1916500", "new": [{"floor_area_m2": 1000}]}]})
    assert r.status_code == 200 and sent["body"]["region"] == "41117"
    def broken(db, code, cells):
        raise OSError("팀 격자 자료 없음")
    monkeypatch.setattr(team_model, "_model_region", broken)
    assert _client().post("/api/team-model/predict", json={"region": "41110", "plans": [{"grid": "cell_961000_1916500", "new": [{"floor_area_m2": 1000}]}]}).status_code == 200
    assert sent["body"]["region"] == "41110"
