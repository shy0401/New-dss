"""지역 화면의 지역 가이드에 그 지역 자체의 난방 방식 · 태양광 발전량 (2026-11-22, 수집을 핵심 34위에서 멈춘 뒤)."""
from types import SimpleNamespace

import pytest

from app import region_prepare, regions, regions_api, solar


class FakeDb:
    def __init__(self, rows):
        self.rows = rows
        self.rolled_back = False

    def execute(self, _query):
        return iter(self.rows)

    def rollback(self):
        self.rolled_back = True


@pytest.fixture
def owns_41(monkeypatch):
    monkeypatch.setattr(regions, "scope", lambda db, code: SimpleNamespace(owns_complex=lambda bjd, grid: str(bjd).startswith("41")))


def test_heating_counts_only_the_regions_complexes_and_solar_comes_from_its_own_irradiation(monkeypatch, owns_41):
    monkeypatch.setattr(solar, "regional_pv_yield", lambda db, code, up_to=None: {"code": code, "up_to": up_to, "yield_kwh_per_kw": 1300})
    db = FakeDb([("4111010100", None, "지역난방", 100), ("4111010100", None, "개별난방", 300), ("2611010100", None, "중앙난방", 999)])
    guide = regions_api.with_region_data(db, "41110", {"code": "41110"})
    kinds = {k["kind"]: k for k in guide["heating"]["kinds"]}
    assert guide["heating"]["complexes"] == 2                        # 26… 단지는 이 지역이 아님
    assert kinds["지역난방"]["household_share_pct"] == 25.0 and kinds["개별난방"]["household_share_pct"] == 75.0
    assert guide["solar"]["code"] == "41110" and guide["solar"]["up_to"] == region_prepare.analysis_year()


def test_no_irradiation_is_none_not_zero_and_a_region_without_grid_has_no_heating_row(monkeypatch):
    def not_ready(db, code):
        raise regions.RegionNotReady("no grid")
    monkeypatch.setattr(regions, "scope", not_ready)
    monkeypatch.setattr(solar, "regional_pv_yield", lambda db, code, up_to=None: None)
    guide = regions_api.with_region_data(FakeDb([]), "28275", {"code": "28275"})
    assert "heating" not in guide and guide["solar"] is None


def test_no_guide_stays_none(owns_41):
    assert regions_api.with_region_data(FakeDb([]), "99999", None) is None
