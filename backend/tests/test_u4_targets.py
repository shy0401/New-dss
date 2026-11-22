"""U4(2026-11-23): 목표 기준 둘 · 지붕 한도까지만 태양광 · 남는 양 · 추천 줄의 수단 연결 (DATA_STANDARD 5.9 · 5.15)."""
from pathlib import Path

import pytest

from app.area import onsite_plan, recommended_mix, target_bases
from app.reduction_measures import applicable_measures
from app.reduction_plan import ROOF_M2_PER_KW, ROOF_USABLE_RATIO

F = 0.433


def _result(added=50000.0, removed=0.0, target=40.0, base_kwh=11_227_619.0, intensity=27.0066532, kwh_per_kw=1160.0,
            plan_roof_m2=None, basis=None):
    new_kwh, rem_kwh = intensity * added, intensity * removed
    base_c = base_kwh * F
    bau_c = (base_kwh + new_kwh - rem_kwh) * F
    need = bau_c - base_c * (1 - target / 100)
    return {"factor_kgco2eq_per_kwh": F, "new_load_kwh": new_kwh, "removed_load_kwh": rem_kwh, "baseline_kwh": base_kwh,
            "baseline_kgco2eq": base_c, "bau_kgco2eq": bau_c, "required_reduction_kgco2eq": need, "intensity_kwh_per_m2": intensity,
            "added_floor_area_m2": added, "removed_floor_area_m2": removed, "target_pct": target, "baseline_mode": "OBSERVED",
            "baseline_year": 2025, "pv_yield": {"kwh_per_kw": kwh_per_kw} if kwh_per_kw else None, "options": {},
            "plan_roof_m2": plan_roof_m2, "plan_roof_basis": basis}


def _t(result, key):
    return next(t for t in target_bases(result) if t["key"] == key)


@pytest.mark.parametrize("target", [0.0, 40.0, 100.0])
def test_the_plans_own_increase_does_not_depend_on_the_target(target):
    r = _result(removed=10000.0, target=target)
    added = _t(r, "plan_added")
    assert added["required_reduction_kgco2eq"] == pytest.approx((r["new_load_kwh"] - r["removed_load_kwh"]) * F, abs=0.1)


def test_the_area_target_is_the_increase_plus_the_existing_share():
    r = _result()
    a, b = _t(r, "area_total"), _t(r, "plan_added")
    assert a["required_reduction_kgco2eq"] == pytest.approx(b["required_reduction_kgco2eq"] + a["existing_share_kgco2eq"], abs=0.2)


def test_more_demolished_than_built_is_no_increase_and_leaves_the_need_empty():
    b = _t(_result(added=1000.0, removed=5000.0), "plan_added")
    assert b["required_reduction_kgco2eq"] is None and b["net_added_kgco2eq"] < 0 and b["already_met"]
    assert b["recommended"]["onsite_status"] == "NO_INCREASE" and b["recommended"]["pv_kw"] is None


def test_pv_never_exceeds_the_roof_limit_and_pv_plus_remaining_is_the_need():
    r = _result(plan_roof_m2=2500.0, basis="footprint")
    for t in target_bases(r):
        rec = t["recommended"]
        assert rec["pv_kw"] <= 2500 * ROOF_USABLE_RATIO / ROOF_M2_PER_KW == 150 and rec["capped"]
        assert rec["onsite_status"] == "PARTIAL" and rec["remaining_kgco2eq"] > 0
        assert rec["pv_kgco2eq"] + rec["remaining_kgco2eq"] == pytest.approx(t["required_reduction_kgco2eq"], abs=0.2)


def test_remaining_is_never_zero_or_negative_a_covered_need_gives_a_margin():
    r = _result(added=1000.0, plan_roof_m2=100000.0, basis="footprint")   # a huge roof for a small plan
    rec = _t(r, "plan_added")["recommended"]
    assert rec["onsite_status"] == "MET" and rec["remaining_kgco2eq"] is None and rec["margin_kgco2eq"] >= 0


def test_floor_area_only_is_an_upper_bound_never_a_yes():
    small = _t(_result(), "plan_added")["recommended"]            # 50,000 m² → roof at most 30,000 m² → 3,000 kW
    assert small["roof_limit_basis"] == "floor_area_upper_bound" and small["onsite_status"] == "UPPER_BOUND_ONLY"
    assert small["remaining_kgco2eq"] is None
    big = _t(_result(), "area_total")["recommended"]               # 40 % of the whole area cannot fit even the upper bound
    assert big["onsite_status"] == "PARTIAL" and big["remaining_is_minimum"] and big["pv_kw"] == 3000


def test_without_a_yield_the_pv_value_stays_empty_and_only_kwh_is_given():
    rec = _t(_result(kwh_per_kw=None), "plan_added")["recommended"]
    assert rec["onsite_status"] == "NO_YIELD" and rec["pv_kw"] is None and rec["offset_kwh"] > 0


def test_the_recommended_mix_keeps_its_fields_and_counts_only_roof_pv():
    r = _result(plan_roof_m2=2500.0, basis="footprint")
    rec = recommended_mix(r)
    assert rec["pv_kw"] == 150 and rec["roof_over_plan"] and rec["steps"][0]["key"] == "pv"
    assert rec["remaining_kgco2eq"] > 0 and rec["pv_needed_kw"] > 150


def test_only_the_roof_pv_line_has_a_value_and_conditions_hold():
    r = _result(plan_roof_m2=2500.0, basis="footprint")
    links = applicable_measures(target_bases(r), 50000.0, district_share_pct=None, cooling_reading="냉방도일 0.9배")
    valued = [x for x in links if x["value_status"] == "QUANTIFIED"]
    assert {x["key"] for x in valued} == {"rooftop_pv"} and all(x["value_kgco2eq"] for x in valued)
    assert all(x["value_kgco2eq"] is None and x["no_value_reason"] for x in links if x["value_status"] != "QUANTIFIED")
    added = {x["key"] for x in links if x["target"] == "plan_added"}
    assert "window_retrofit" not in added and "condensing_boiler" not in added      # existing-building measures
    assert "district_heating_control" not in {x["key"] for x in links}             # no district-heated households
    with_dh = applicable_measures(target_bases(r), 50000.0, district_share_pct=86.7, cooling_reading=None)
    assert "district_heating_control" in {x["key"] for x in with_dh}
    assert any("개별난방" in (x["condition_text"] or "") for x in with_dh if x["key"] == "envelope")


def test_the_evidence_rows_come_from_the_summary_not_a_recount():
    from app.reference_tables import evidence_summary
    links = applicable_measures(target_bases(_result()), 50000.0, None, None)
    ev = evidence_summary()["by_measure"]
    for x in links:
        assert x["evidence_table"] == ev.get(x["key"])


STANDARD = Path(__file__).resolve().parents[2] / "docs" / "DATA_STANDARD.md"


@pytest.mark.skipif(not STANDARD.exists() and not Path("/docs/DATA_STANDARD.md").exists(), reason="기준 문서가 없는 실행 환경")
def test_the_roof_rule_in_the_standard_matches_the_constants():
    text = (STANDARD if STANDARD.exists() else Path("/docs/DATA_STANDARD.md")).read_text(encoding="utf-8")
    assert "계획 건물 지붕 한도까지만" in text and f"**{ROOF_USABLE_RATIO:.2f}**" in text and f"**{ROOF_M2_PER_KW:g} m²/kW**" in text


def test_the_new_sentences_belong_to_report_sections_4_and_5_not_the_limits():
    from app.area_report import HTML_SECTIONS as SECTIONS
    by_title = {title: prefixes for title, prefixes in SECTIONS}
    four = next(p for t, p in by_title.items() if t.startswith("4."))
    five = next(p for t, p in by_title.items() if t.startswith("5."))
    assert {"effort_added", "effort_added_none", "effort_split"} <= set(four) and "effort_rec_added" in five


def test_capping_is_judged_before_the_10_kw_rounding():
    """375.0 kW 필요 · 한도 375.5 kW: 한도에 걸리지 않음(검토 지적 1). 위 한계 기준이면 '충족'이라 하지 않음."""
    need_kwh = 375.0 * 1000.0
    r = _result(kwh_per_kw=1000.0, plan_roof_m2=6258.4, basis="footprint")     # 6,258.4 × 0.6 ÷ 10 = 375.5 kW
    rec = onsite_plan(r, need_kwh * F)
    assert not rec["capped"] and rec["onsite_status"] == "MET" and rec["pv_kw"] == 375.5
    up = onsite_plan(_result(kwh_per_kw=1000.0, added=6258.4), need_kwh * F)
    assert up["onsite_status"] == "UPPER_BOUND_ONLY" and up["remaining_kgco2eq"] is None


def test_a_plan_without_its_own_roof_keeps_the_need_as_remaining():
    r = _result(added=0.0, removed=1000.0)
    rec = onsite_plan(r, 100_000.0)
    assert rec["onsite_status"] == "NO_ROOF" and rec["pv_kw"] is None and rec["remaining_kgco2eq"] == 100_000.0
    mix = recommended_mix(r)
    assert mix["pv_kw"] is None and mix["steps"] == [] and mix["remaining_kgco2eq"] > 0


def test_explicit_footprints_win_over_floor_area_per_floors_and_never_exceed_the_floor_area():
    from app.area import _effort_result
    args = dict(history={}, target_pct=40.0, pv_yield_kwh_per_kw=1200.0, factor=F, base_year=2025, baseline_mode="OBSERVED",
                intensity=27.0, base_kwh=10_000_000.0, basis_area=100_000.0, basis="apartments", load_text="")
    e = _effort_result(plan={"added_floor_area_m2": 50000, "floors": 20, "building_count": 5, "footprint_per_building": 500}, **args)
    assert e["plan_roof_m2"] == 2500 and e["plan_roof_basis"] == "footprint"
    e = _effort_result(plan={"added_floor_area_m2": 50000, "floors": 20}, **args)
    assert e["plan_roof_m2"] == 2500 and e["plan_roof_basis"] == "floor_area_per_floors"
    e = _effort_result(plan={"added_floor_area_m2": 50000, "floors": 0.5}, **args)
    assert e["plan_roof_m2"] is None                       # floors below 1 are not read as a wider roof
    e = _effort_result(plan={"added_floor_area_m2": 1000, "building_count": 5, "footprint_per_building": 500}, **args)
    assert e["plan_roof_m2"] == 1000                       # never above the floor area


def test_the_area_target_already_met_has_its_own_status():
    a = _t(_result(added=0.0, target=0.0), "area_total")
    assert a["already_met"] and a["recommended"]["onsite_status"] == "ALREADY_MET"
