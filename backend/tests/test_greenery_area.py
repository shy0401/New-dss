"""계획 v3 단계 D2(2026-11-25): 지역 계획의 녹지 면적 입력(기록 2026-11-25-greenery-area-input.md).

규칙(결과 보기 전에 정함):
- 녹지 면적이 있고 0보다 크면 감축 제안의 녹지 줄만 상쇄 값: value_status OFFSET, offset_kgco2 = 면적 × 1.0 kg,
  offset_range_kgco2 = 면적 × [0.88, 1.59] kg. 감축 칸(value_kgco2eq)은 비움(CO2와 CO2eq를 섞지 않음, 독립 검토 반영)
- 녹지 값은 어떤 합계에도 넣지 않음: 다른 줄(태양광 포함) · 목표 값은 그대로
- 값이 없거나 0이면 지금과 같음
- 녹지 줄은 단계 B의 고정 줄(순서 매김 밖) 그대로, 수단 묶음 수준은 VALUE_3D → VALUE
"""
import copy

import pytest
from pydantic import ValidationError

from app.area import PlanInput, target_bases
from app.measure_catalog import FIXED_KEYS, GROUP_LEVELS, group_status, order_lines
from app.reduction_measures import applicable_measures
from app.reduction_plan import GREEN_UPTAKE_KG_PER_M2, GREEN_UPTAKE_RANGE_T_PER_HA
from tests.test_u4_targets import _result

ADDED_M2 = 50000.0
GREEN_M2 = 12345.6   # 경계(…5)에 걸리지 않는 면적: 12,345.6 / 10,864.1 / 19,629.5


def _targets():
    return target_bases(_result(plan_roof_m2=2500.0, basis="footprint"))


def _lines(targets=None, **kw):
    """단계 B 시험과 같은 계획(지붕 2,500 m², 연면적 50,000 m²)의 감축 제안 줄."""
    return applicable_measures(targets if targets is not None else _targets(), ADDED_M2,
                               district_share_pct=30.0, cooling_reading="냉방도일 0.9배", **kw)


def _green(lines):
    return [x for x in lines if x["key"] == "greenery"]


def _others(lines):
    return [x for x in lines if x["key"] != "greenery"]


# ---------------------------------------------------------------- 상수: 3D 계획안 검토와 같은 값
def test_the_constants_are_the_3d_ones_1_kg_and_8_8_to_15_9_t_per_ha():
    assert GREEN_UPTAKE_KG_PER_M2 == 1.0
    assert tuple(GREEN_UPTAKE_RANGE_T_PER_HA) == (8.8, 15.9)   # t/ha ÷ 10 = kg/m² → 0.88 ~ 1.59


# ---------------------------------------------------------------- 녹지 면적을 넣은 평가
def test_with_green_area_every_greenery_line_becomes_an_offset_line():
    lines = _lines(green_area_m2=GREEN_M2)
    green = _green(lines)
    assert {x["target"] for x in green} == {"plan_added", "area_total"}   # 두 목표 기준 모두에 녹지 줄
    for x in green:
        assert x["value_status"] == "OFFSET"             # 감축 값 줄(QUANTIFIED)과 구별
        assert x["value_kgco2eq"] is None               # 감축(CO2eq) 칸은 비움
        assert x["offset_kgco2"] == round(GREEN_M2 * GREEN_UPTAKE_KG_PER_M2, 1)
        assert x["offset_range_kgco2"] == [round(GREEN_M2 * t / 10, 1) for t in GREEN_UPTAKE_RANGE_T_PER_HA]
        lo, hi = x["offset_range_kgco2"]
        assert lo < x["offset_kgco2"] < hi
        assert "상쇄" in x["offset_text"] and "kgCO2/m²" in x["offset_text"]
        assert x["level"] == "VALUE"


@pytest.mark.parametrize("area", [1.0, 800.0, 250000.0])
def test_the_greenery_value_is_area_times_one_kg_for_any_size(area):
    for x in _green(_lines(green_area_m2=area)):
        assert x["value_status"] == "OFFSET" and x["offset_kgco2"] == round(area * 1.0, 1)
        assert x["offset_range_kgco2"] == [round(area * t / 10, 1) for t in GREEN_UPTAKE_RANGE_T_PER_HA]


def test_green_area_never_changes_any_other_line_field_by_field():
    """녹지 값은 어떤 합계에도 넣지 않음: 태양광 줄을 포함한 다른 줄은 칸별로 같다."""
    before = _lines()
    after = _lines(green_area_m2=GREEN_M2)
    assert _others(after) == _others(before)
    assert [(x["target"], x["key"]) for x in after] == [(x["target"], x["key"]) for x in before]   # 줄 집합 · 순서 그대로


def test_green_area_does_not_touch_the_targets_or_the_recommended_mix():
    targets = _targets()
    frozen = copy.deepcopy(targets)
    _lines(targets=targets, green_area_m2=GREEN_M2)
    assert targets == frozen                            # 목표 필요 감축량 · 추천 방안 · 태양광 그대로


def test_only_pv_carries_a_reduction_value_and_only_greenery_an_offset():
    lines = _lines(green_area_m2=GREEN_M2)
    assert {x["key"] for x in lines if x["value_status"] == "QUANTIFIED"} == {"rooftop_pv"}
    assert {x["key"] for x in lines if x["value_status"] == "OFFSET"} == {"greenery"}
    assert all(x["value_kgco2eq"] is None for x in lines if x["value_status"] != "QUANTIFIED")
    assert all("offset_kgco2" not in x for x in lines if x["key"] != "greenery")


@pytest.mark.parametrize("tiny", [0.01, 0.04])
def test_a_tiny_area_that_rounds_to_zero_is_not_a_value(tiny):
    assert _lines(green_area_m2=tiny) == _lines()      # 0.0 kg 값을 만들지 않음


# ---------------------------------------------------------------- 녹지 면적이 없거나 0: 지금과 같음
@pytest.mark.parametrize("area", [None, 0, 0.0])
def test_without_green_area_the_output_is_identical_to_today(area):
    before = _lines()
    after = _lines(green_area_m2=area)
    assert after == before
    for x in _green(after):
        assert x["value_status"] == "INDICATOR_ONLY" and x["value_kgco2eq"] is None
        assert "offset_kgco2" not in x and "offset_range_kgco2" not in x
        assert x["no_value_reason"]                    # 값이 없는 이유 문장 그대로


def test_without_new_floor_area_there_is_no_greenery_line_even_with_green_area():
    """녹지 줄은 신축 · 재개발 몫(연면적이 늘 때)에만 붙는 지금 규칙 그대로."""
    targets = target_bases(_result(added=0.0, removed=1000.0))
    before = applicable_measures(targets, 0.0, None, None)
    after = applicable_measures(targets, 0.0, None, None, green_area_m2=GREEN_M2)
    assert not _green(before) and not _green(after) and after == before


# ---------------------------------------------------------------- 단계 B 고정 줄 그대로
def test_greenery_stays_a_fixed_line_outside_the_region_order():
    assert "greenery" in FIXED_KEYS
    lines = _lines(green_area_m2=GREEN_M2)
    ctx = {"cdd_ratio_vs_jeonju": 1.2, "hdd_ratio_vs_jeonju": 1.3, "elec_cooling_share": 0.08,
           "district_heating_household_pct": 60.0, "local_plan_tasks_by_group": {"operation": 4}}
    out = order_lines(lines, ctx)
    for t in ("plan_added", "area_total"):
        before = [x["key"] for x in lines if x["target"] == t]
        after = [x["key"] for x in out if x["target"] == t]
        assert before.index("greenery") == after.index("greenery")     # 자리 그대로
    keep = ("value_status", "value_kgco2eq", "offset_kgco2", "offset_range_kgco2", "level")
    assert [[x.get(k) for k in keep] for x in _green(out)] == [[x.get(k) for k in keep] for x in _green(lines)]


# ---------------------------------------------------------------- 입력: PlanInput.green_area_m2
def test_plan_input_takes_green_area_and_defaults_to_none():
    assert PlanInput().green_area_m2 is None           # 없으면 None(0으로 채우지 않음)
    assert PlanInput(green_area_m2=0).green_area_m2 == 0
    assert PlanInput(added_floor_area_m2=50000, green_area_m2=12345.6).green_area_m2 == pytest.approx(12345.6)


@pytest.mark.parametrize("bad", [-0.1, -1, -12345.6, 10_000_001, float("inf"), float("nan")])
def test_plan_input_rejects_negative_huge_or_non_finite_green_area(bad):
    with pytest.raises(ValidationError):
        PlanInput(green_area_m2=bad)


# ---------------------------------------------------------------- 수단 묶음 수준: VALUE_3D → VALUE
def test_greenery_group_level_is_value_in_the_regional_plan_too():
    assert GROUP_LEVELS["greenery"][0] == "VALUE"
    row = next(g for g in group_status() if g["group"] == "greenery")
    assert row["level"] == "VALUE"
