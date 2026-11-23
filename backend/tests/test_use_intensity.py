"""Per-use intensity of the plan lines (2026-11-23, 기준 문서 5.9): non-residential lines use their observed intensity."""
import pytest

from app import area
from app.reference_tables import USE_INTENSITY_MIN_PARCELS, use_intensity


def test_reference_rows_region_then_all():
    allc = use_intensity(None, "commercial")
    assert allc["scope"] == "READY_ALL" and allc["kwh_per_m2"] > 50
    assert use_intensity(None, "residential") is None          # residential keeps the area's own intensity
    assert use_intensity(None, "officetel") is None
    assert use_intensity("99999", "office")["scope"] == "READY_ALL"   # unknown region → all READY regions
    assert USE_INTENSITY_MIN_PARCELS == 30


def test_line_loads_mix_area_and_use_intensities():
    total, lines = area.line_loads([{"use": "residential", "floor_area_m2": 60000}, {"use": "commercial", "floor_area_m2": 20000}],
                                   80000, 40.0, None)
    com = use_intensity(None, "commercial")["kwh_per_m2"]
    assert total == pytest.approx(60000 * 40.0 + 20000 * com)
    assert [x["basis"] for x in lines] == ["AREA", "READY_ALL"]
    same, none = area.line_loads(None, 80000, 40.0, None)
    assert same == pytest.approx(80000 * 40.0) and none == []          # no use lines: as before


def _result(plan, basis="apartments"):
    return area._effort_result({}, plan, 30.0, None, 0.4594, 2025, "OBSERVED", 40.0, 1_000_000.0, 25_000.0, basis, "신축 부하 = 계획 연면적 × 원단위 40")


def test_effort_uses_lines_only_with_use_lines_and_not_on_kcsm():
    lines = [{"use": "residential", "floor_area_m2": 60000}, {"use": "commercial", "floor_area_m2": 20000}]
    plain = _result({"added_floor_area_m2": 80000})
    mixed = _result({"added_floor_area_m2": 80000, "uses_new": lines})
    kcsm = _result({"added_floor_area_m2": 80000, "uses_new": lines}, basis="kcsm")
    assert plain["new_load_kwh"] == pytest.approx(3_200_000.0)
    assert mixed["new_load_kwh"] > plain["new_load_kwh"]           # commercial is above the residential 40
    assert kcsm["new_load_kwh"] == plain["new_load_kwh"] and kcsm["new_load_lines"] == []
    assert "용도별" in mixed["assumptions"][0]
    only_res = _result({"added_floor_area_m2": 80000, "uses_new": [{"use": "residential", "floor_area_m2": 80000}]})
    assert only_res["new_load_kwh"] == pytest.approx(plain["new_load_kwh"])   # residential-only plans do not change


def test_removed_lines_feed_the_mix_and_the_demolition_check():
    res = _result({"added_floor_area_m2": 10000, "removed_floor_area_m2": 2000,
                   "uses_new": [{"use": "residential", "floor_area_m2": 10000}], "uses_removed": [{"use": "commercial", "floor_area_m2": 2000}]})
    com = use_intensity(None, "commercial")["kwh_per_m2"]
    assert res["removed_load_kwh"] == pytest.approx(2000 * com, rel=1e-6)
    assert area.measure_mix(res, {"existing_efficiency_pct": 10})["existing_kwh"] == pytest.approx((1_000_000 - 2000 * com) * 0.1, rel=1e-6)
    with pytest.raises(ValueError):
        _result({"added_floor_area_m2": 0, "removed_floor_area_m2": 20000, "uses_removed": [{"use": "commercial", "floor_area_m2": 20000}]})
