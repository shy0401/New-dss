"""탄소 감축 방안 (기준 문서 5.15): 다른 안과 견주지 않고 같은 계획을 대책 없음에서 수단을 하나씩 더해 줄인다. 절감률은 실측 지표."""
import pytest

from app.area import recommended_mix
from app.reduction_plan import building_plan, plan_text, roof_pv, zeb_grade

FACTORS = {"ELECTRICITY": {"factor": 0.4}, "GAS": {"factor": 0.2}}


def test_ladder_from_no_measures_through_envelope_rooftop_pv_and_greenery():
    p = building_plan({"electricity_kwh": 1_000_000, "gas_kwh": 500_000}, 1000, FACTORS, {"kwh_per_kw": 1200, "label": "추정"}, plan_carbon_kg=450_000, green_area_m2=3000)
    assert p["available"] and p["start"]["carbon_kg"] == 500_000
    keys = [s["key"] for s in p["steps"]]
    # 히트펌프 단계는 2026-11-11, 에너지 절약 운영(입주 뒤 행동)은 2026-11-20부터 기본에서 뺌
    assert keys == ["envelope", "rooftop_pv", "greenery"]
    env, pv, green = p["steps"]
    # 단열·창호: 가스 500,000 × (1 − 0.137) = 431,500 kWh, 전력은 그대로
    assert env["electricity_kwh"] == 1_000_000 and env["gas_kwh"] == 431_500 and env["carbon_kg"] == 486_300 and env["cumulative_pct"] == 2.7
    # 옥상 1,000 × 0.6 = 600 m² → 60 kW × 1,200 = 72,000 kWh
    assert p["pv"]["roof_m2"] == 600 and p["pv"]["kw"] == 60 and p["pv"]["kwh"] == 72_000
    # 전력 1,000,000 − 72,000 = 928,000 kWh → 371,200 + 가스 86,300 = 457,500 kg
    assert pv["carbon_kg"] == 457_500 and pv["cumulative_pct"] == 8.5
    # 녹지 3,000 m² × 1.0 kg = 3,000 kg 흡수(상쇄): 전력·가스는 그대로, 탄소만 줄어든다
    assert green["electricity_kwh"] == 928_000 and green["carbon_kg"] == 454_500 and green["reduction_kg"] == 3000
    assert p["green"] == {"area_m2": 3000, "uptake_kg": 3000, "range_kg": [2640.0, 4770.0]}
    # 지표의 실측 범위: 계산은 중앙값, 범위는 그 단계 감축량이 움직일 수 있는 폭 (가스 500,000 × 9.8~17.3% × 0.2)
    assert env["range_pct"] == [9.8, 17.3] and env["reduction_range_kg"] == [9_800, 17_300]
    assert pv["range_pct"] is None and pv["reduction_range_kg"] is None
    assert green["range_pct"] is None and green["reduction_range_kg"] == [2640.0, 4770.0]
    assert p["final_carbon_kg"] == 454_500 and p["final_pct"] == 9.1
    assert p["self_sufficiency_pct"] == 6.1 and p["zeb_grade"] is None
    assert p["residual"]["electricity_kwh"] == 928_000 and p["residual"]["offsite_pv_kw"] == 773.3
    assert p["plan"] == {"carbon_kg": 450_000, "pct": 10.0}
    assert "454.5 t" in plan_text(p) and "구역 밖 재생에너지" in plan_text(p)
    # 녹지 흡수는 상쇄라 감축 수단만의 비율을 따로 둔다: (500,000 − 457,500) ÷ 500,000 = 8.5%
    assert p["reduction_pct"] == 8.5 and "감축 수단만으로는 −8.5%" in plan_text(p)
    # 남는 454,500 kg = 전력 928,000 × 0.4 + 가스 431,500 × 0.2 − 녹지 3,000. 구역 밖 태양광 773.3 kW는 전력분(371.2 t)만 덮는다
    r = p["residual"]
    assert r["electricity_carbon_kg"] == 371_200 and r["gas_carbon_kg"] == 86_300 and r["offset_kg"] == 3000
    assert r["electricity_carbon_kg"] + r["gas_carbon_kg"] - r["offset_kg"] == r["carbon_kg"]
    assert "전력분은 구역 밖 재생에너지" in plan_text(p) and "가스분은 전력 조달로 줄지 않습니다" in plan_text(p)
    assert "는 구역 밖 재생에너지(태양광 약 773 kW 상당) 조달로 채웁니다" not in plan_text(p)
    assert any("117쌍" in a for a in p["assumptions"]) and any("히트펌프" in a and "넣지 않았습니다" in a for a in p["assumptions"])
    assert any("에너지 절약 운영" in a and "넣지 않았습니다" in a for a in p["assumptions"])


def test_missing_inputs_drop_the_step_instead_of_using_zero():
    assert building_plan({"electricity_kwh": None, "gas_kwh": 1}, 1000, FACTORS)["available"] is False
    assert building_plan({"electricity_kwh": 1, "gas_kwh": 1}, 1000, {"ELECTRICITY": {"factor": None}})["available"] is False
    no_gas = building_plan({"electricity_kwh": 100_000, "gas_kwh": None}, 500, FACTORS, None)
    assert no_gas["steps"] == [] and no_gas["start"]["gas_kwh"] is None   # 가스도 발전량 근거도 없으면 단계가 없다(0 % 단계를 만들지 않음)
    assert any("가스 사용량이 없어" in a for a in no_gas["assumptions"])
    no_yield = building_plan({"electricity_kwh": 100_000, "gas_kwh": 50_000}, 500, FACTORS, None)
    assert [s["key"] for s in no_yield["steps"]] == ["envelope"] and no_yield["pv"]["kwh"] is None
    assert no_yield["residual"]["offsite_pv_kw"] is None
    assert no_yield["reduction_pct"] == no_yield["final_pct"] and no_yield["residual"]["offset_kg"] == 0   # 상쇄가 없으면 두 비율이 같다
    assert no_gas["residual"]["gas_carbon_kg"] is None and plan_text(no_gas) is None   # 더할 수단이 없으면 요약 문장도 없다
    assert no_yield["green"] is None and any("녹지 면적이 없어" in a for a in no_yield["assumptions"])


def test_rooftop_pv_beyond_own_use_is_not_counted_and_zeb_band_is_reference_only():
    p = building_plan({"electricity_kwh": 10_000, "gas_kwh": 0}, 2000, FACTORS, {"kwh_per_kw": 1200, "label": "추정"})
    # 자체 소비 전력 10,000 kWh까지만 태양광으로 셈
    assert p["pv"]["kwh"] == 144_000 and p["pv"]["used_kwh"] == 10_000 and p["pv"]["surplus_kwh"] == 134_000
    assert p["final_carbon_kg"] == 0 and p["final_pct"] == 100.0 and p["residual"]["offsite_pv_kw"] is None
    assert zeb_grade(19.9) is None and zeb_grade(20) == "5등급" and zeb_grade(45) == "4등급" and zeb_grade(120) == "1등급"
    assert roof_pv(0, 1200) is None and roof_pv(100, None) == {"roof_m2": 60.0, "kw": 6.0, "kwh": None}


def _effort(**kw):
    base = {"available": True, "factor_kgco2eq_per_kwh": 0.433, "new_load_kwh": 5_331_000.0, "baseline_kwh": 101_269_161.0, "removed_floor_area_m2": 0,
            "intensity_kwh_per_m2": 53.31, "required_reduction_kgco2eq": 11_078_232.3, "pv_yield": {"kwh_per_kw": 1199.9}}
    base.update(kw)
    return base


def test_recommended_mix_is_solar_only_in_10_kw_steps():
    """2026-11-20부터 자동 방안에 신축 전력 −11.3% · 기존 운영 −4.8%를 넣지 않는다(전력 절감 근거 없음 · 입주 뒤 행동).
    2026-11-23(U4): 지붕 한도 안이면 필요 용량을 10 kW 단위로 올린 값 그대로(건축면적 400,000 m² → 한도 24,000 kW)."""
    roomy = {"added_floor_area_m2": 2_000_000.0, "plan_roof_m2": 400_000.0, "plan_roof_basis": "footprint"}
    rec = recommended_mix(_effort(**roomy))
    assert [s["key"] for s in rec["steps"]] == ["pv"]
    assert rec["new_efficiency_pct"] == 0 and rec["existing_efficiency_pct"] == 0 and rec["new_kwh"] == 0 and rec["existing_kwh"] == 0
    assert rec["pv_kw"] % 10 == 0 and rec["met"] and rec["roof_m2"] == rec["pv_kw"] * 10 and not rec["capped"]
    # 필요 감축 11,078,232.3 kg ÷ 0.433 ÷ 1,199.9 = 21,322.5 kW → 10 kW 단위 올림 21,330
    assert rec["pv_kw"] == 21330 and rec["remaining_kgco2eq"] is None and rec["margin_kgco2eq"] >= 0


def test_recommended_mix_without_yield_states_the_offset_kwh_only():
    rec = recommended_mix(_effort(pv_yield=None))
    assert rec["steps"] == [] and not rec["met"] and rec["offset_kwh"] == pytest.approx(11_078_232.3 / 0.433, abs=0.1)
    assert recommended_mix({"available": True, "factor_kgco2eq_per_kwh": None}) is None


def test_recommended_roof_is_compared_with_the_plan_roof():
    """2026-11-20 점검 A → 2026-11-23 U4: 태양광은 계획 지붕 한도(건축면적 합 × 0.60 ÷ 10 m²/kW)까지만, 넘는 몫은 남는 양.
    건축면적 합을 모르면 연면적이 지붕의 위 한계."""
    rec = recommended_mix(_effort(added_floor_area_m2=100_000.0, plan_roof_m2=None))      # 위 한계 6,000 kW < 필요 21,330 kW
    assert rec["pv_kw"] == 6000 and rec["roof_m2"] == 60_000 and rec["plan_roof_m2"] == 100_000 and rec["plan_roof_basis"] == "floor_area"
    assert rec["roof_over_plan"] and rec["remaining_is_minimum"] and rec["remaining_kgco2eq"] > 0 and rec["pv_needed_kw"] == 21330
    rec = recommended_mix(_effort(added_floor_area_m2=2_000_000.0, plan_roof_m2=None))
    assert not rec["roof_over_plan"] and rec["onsite_status"] == "UPPER_BOUND_ONLY"   # 위 한계 안: 모자란다고도 된다고도 단정하지 않음
    rec = recommended_mix(_effort(added_floor_area_m2=2_000_000.0, plan_roof_m2=150_000.0, plan_roof_basis="footprint"))
    assert rec["plan_roof_basis"] == "footprint" and rec["plan_roof_m2"] == 150_000 and rec["roof_over_plan"] and rec["pv_kw"] == 9000
    assert recommended_mix(_effort(pv_yield=None))["roof_over_plan"] is False   # 태양광 용량이 없으면 견주지 않음


def test_the_base_year_of_the_reference_is_written_with_the_reductions():
    """감축량에는 기준 연도를 함께 적는다(AGENTS.md): 기준안을 만든 관측 연도를 결과와 가정 문장에 둔다."""
    p = building_plan({"electricity_kwh": 1_000_000, "gas_kwh": 500_000}, 1000, FACTORS, None, base_year=2024)
    assert p["base_year"] == 2024 and any("2024년 기준안에 대한 값" in a for a in p["assumptions"])
    assert building_plan({"electricity_kwh": 1_000_000, "gas_kwh": 500_000}, 1000, FACTORS, None)["base_year"] is None
