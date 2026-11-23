"""D5(2026-11-23): 기본 대상지는 전력 · 가스가 모두 관측된 격자 중 세대수가 가장 많은 곳. 없으면 전처럼 세대수 최다."""
from types import SimpleNamespace


class _Db:
    def scalars(self, _query):
        return []


def _patch(monkeypatch, complete: set[str]):
    from app import grid_metrics, service
    monkeypatch.setattr(grid_metrics, "validated_complex_areas", lambda rows: ({}, {}))
    monkeypatch.setattr(service, "baseline_has_total", lambda db, grid, year, clause, areas, hh: grid in complete)


def test_the_largest_cell_with_a_complete_baseline_is_chosen(monkeypatch):
    from app.region_prepare import pick_default_grid
    _patch(monkeypatch, {"g3", "g2"})
    grid, reason = pick_default_grid(_Db(), SimpleNamespace(code="11680"), {"g1": 900, "g2": 500, "g3": 700}, 2025)
    assert grid == "g3" and "세대수 2위" in reason and "가스 관측이 없음" in reason


def test_the_largest_cell_stays_when_it_is_complete(monkeypatch):
    from app.region_prepare import pick_default_grid
    _patch(monkeypatch, {"g1", "g2"})
    grid, reason = pick_default_grid(_Db(), SimpleNamespace(code="11680"), {"g1": 900, "g2": 500}, 2025)
    assert grid == "g1" and "위" not in reason.split("(")[1]


def test_without_any_complete_cell_the_most_households_win_as_before(monkeypatch):
    from app.region_prepare import pick_default_grid
    _patch(monkeypatch, set())
    grid, reason = pick_default_grid(_Db(), SimpleNamespace(code="52740"), {"a": 10, "b": 378}, 2025)
    assert grid == "b" and "모두 전력 · 가스 12개월 관측이 없음" in reason


def test_baseline_has_total_needs_gas_in_every_month(monkeypatch):
    from app import service
    months = [f"2025{m:02d}" for m in range(1, 13)]
    rows = [{"grid_id": "g", "energy_type": t, "use_ym": m, "usage_kwh": 3000.0, "kapt_code": "K1", "matched_gross_floor_area_m2": 100.0}
            for m in months for t in ("ELECTRICITY", "GAS")]
    monkeypatch.setattr(service, "grid_observed_rows", lambda db, grid, within: rows)
    assert service.baseline_has_total(None, "g", 2025, None, {"K1": 100.0}, {"K1": 10})
    monkeypatch.setattr(service, "grid_observed_rows", lambda db, grid, within: [r for r in rows if r["energy_type"] == "ELECTRICITY"])
    assert not service.baseline_has_total(None, "g", 2025, None, {"K1": 100.0}, {"K1": 10})


def test_only_this_regions_rows_count_and_only_the_top_ten_cells(monkeypatch):
    """대시보드처럼 그 지역(법정 시군구) 행만 봄 — 경계 격자의 이웃 지역 단지로 '관측 있음'이 되지 않게. 상위 10곳만."""
    from app import grid_metrics, service
    from app.region_prepare import DEFAULT_GRID_CANDIDATES, pick_default_grid
    seen = []
    monkeypatch.setattr(grid_metrics, "validated_complex_areas", lambda rows: ({}, {}))

    def fake(db, grid, year, clause, areas, hh):
        seen.append((grid, str(clause.compile(compile_kwargs={"literal_binds": True})) if clause is not None else None))
        return grid == "g11"
    monkeypatch.setattr(service, "baseline_has_total", fake)
    hh = {f"g{i}": 1000 - i for i in range(1, 12)}
    grid, reason = pick_default_grid(_Db(), SimpleNamespace(code="11680", legal_codes=["11680"]), hh, 2025, complexes=[])
    assert len(seen) == DEFAULT_GRID_CANDIDATES == 10 and "g11" not in [g for g, _ in seen]
    assert grid == "g1" and "상위 10곳 모두" in reason          # the 11th cell is not looked at
    assert all("sigungu_code IN ('11680')" in c for _, c in seen)
