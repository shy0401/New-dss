"""계획 v3 단계 E(2026-11-25): 지붕 태양광을 세 수준으로(기록 2026-11-25-pv-three-levels.md).

규칙(구현 · 결과 보기 전에 정함):
- 지붕 최대(지금 값) 그대로. 인증 수준 = 세대 수 × 0.20~0.61 kW/세대(공식 자료), 사례 수준 = 세대 수 × 0.13~0.64 kW/세대(기사)
- 두 수준의 kW는 지붕 한도(roof_limit_kw)를 넘지 않게 자름(자르면 capped)
- 연 발전량 = kW × 지역 발전량(kWh/kW), 감축 = 발전량 × 전력 계수. 발전량 근거가 없으면 kW만
- 세대 수가 없으면 두 수준은 값 없이 이유 문장("세대 수")
- 지역 규칙(문장만): 서울(11xxx) · 제주(50xxx), 그 밖은 없음
- 세 수준은 더하지 않음: 목표 · 추천 방안 · 다른 줄 · 지붕 태양광 줄의 기존 칸 그대로, 새 칸 pv_levels만 더해짐
"""
import copy

import pytest

import app.reduction_measures as rm   # 모듈로 가져와 이름이 없을 때 시험마다 따로 실패하게 함
from app.area import target_bases
from app.reduction_measures import applicable_measures
from tests.test_u4_targets import _result

ADDED_M2 = 50000.0
H = 600                 # 사례 대상지 세 곳의 계획 세대 수
YIELD = 1160.0          # kWh/kW (test_u4_targets 기본값)
F = 0.433               # kgCO2eq/kWh
LEVELS = ("certified", "cases")
RANGES = {"certified": (0.20, 0.61), "cases": (0.13, 0.64)}


def _levels(households=H, kwh_per_kw=YIELD, factor=F, roof_limit_kw=None, region_code="52110"):
    return rm.pv_levels(households=households, kwh_per_kw=kwh_per_kw, factor_kgco2eq_per_kwh=factor,
                     roof_limit_kw=roof_limit_kw, region_code=region_code)


def _targets():
    return target_bases(_result(plan_roof_m2=2500.0, basis="footprint"))   # 지붕 한도 2,500 × 0.6 ÷ 10 = 150 kW


def _lines(targets=None, **kw):
    """단계 B · D 시험과 같은 계획(지붕 2,500 m², 연면적 50,000 m²)의 감축 제안 줄."""
    return applicable_measures(targets if targets is not None else _targets(), ADDED_M2,
                               district_share_pct=30.0, cooling_reading="냉방도일 0.9배", **kw)


# ---------------------------------------------------------------- 상수: 기록의 표와 같은 값
def test_the_constants_are_the_recorded_per_household_ranges():
    assert tuple(rm.PV_KW_PER_HOUSEHOLD_CERTIFIED) == (0.20, 0.61)   # 공식 자료(ZEB 인증사례집 · LH)
    assert tuple(rm.PV_KW_PER_HOUSEHOLD_CASES) == (0.13, 0.64)     # 기사(포레온 0.128 · 웰카운티 0.639)


# ---------------------------------------------------------------- 세대 수 × 범위(지붕 한도 없음)
def test_600_households_give_the_recorded_kw_ranges():
    """기록의 확인 항목: 600세대 → 인증 120~366 kW, 사례 78~384 kW."""
    out = _levels()
    assert out["certified"]["kw_range"] == [120.0, 366.0]
    assert out["cases"]["kw_range"] == [78.0, 384.0]


@pytest.mark.parametrize("level", LEVELS)
def test_each_level_is_households_times_range_then_yield_then_factor(level):
    out = _levels()[level]
    lo_k, hi_k = RANGES[level]
    kw = [round(H * lo_k, 1), round(H * hi_k, 1)]
    kwh = [round(k * YIELD, 1) for k in kw]
    kg = [round(e * F, 1) for e in kwh]
    assert out["kw_range"] == kw
    assert out["kwh_range"] == pytest.approx(kwh, abs=0.051)
    assert out["kgco2eq_range"] == pytest.approx(kg, abs=0.051)
    assert out["capped"] is False                       # 한도가 없으면 자르지 않음
    assert out["data_class"] == "ESTIMATED"             # 추정 범위
    assert isinstance(out["basis"], str) and out["basis"].strip()
    assert out["reason"] is None


def test_source_types_are_official_for_certified_and_article_for_cases():
    out = _levels()
    assert out["certified"]["source_type"] == "공식 자료"
    assert out["cases"]["source_type"] == "기사"          # 공식 자료로 교차 확인 안 됨


# ---------------------------------------------------------------- 지붕 한도로 자름
def test_the_roof_limit_caps_each_end_and_says_so():
    out = _levels(roof_limit_kw=150.0)                  # 단계 B 계획의 지붕 한도
    assert out["certified"]["kw_range"] == [120.0, 150.0] and out["certified"]["capped"] is True
    assert out["cases"]["kw_range"] == [78.0, 150.0] and out["cases"]["capped"] is True
    for level in LEVELS:                                # 발전량 · 감축은 자른 kW로
        o = out[level]
        assert o["kwh_range"] == pytest.approx([round(k * YIELD, 1) for k in o["kw_range"]], abs=0.051)
        assert o["kgco2eq_range"] == pytest.approx([round(e * F, 1) for e in o["kwh_range"]], abs=0.051)


def test_a_roof_limit_below_both_ends_caps_both_ends():
    out = _levels(roof_limit_kw=50.0)
    for level in LEVELS:
        assert out[level]["kw_range"] == [50.0, 50.0] and out[level]["capped"] is True


def test_a_roof_limit_above_the_range_changes_nothing():
    a, b = _levels(roof_limit_kw=1000.0), _levels(roof_limit_kw=None)
    assert all(a[k] == b[k] for k in LEVELS) and a["region_rule"] == b["region_rule"]   # 되돌려 적는 한도 칸만 다름
    for level in LEVELS:
        assert _levels(roof_limit_kw=1000.0)[level]["capped"] is False


# ---------------------------------------------------------------- 발전량 근거 없음: kW만
@pytest.mark.parametrize("level", LEVELS)
def test_without_a_yield_only_kw_is_given(level):
    out = _levels(kwh_per_kw=None)[level]
    assert out["kw_range"] == [round(H * RANGES[level][0], 1), round(H * RANGES[level][1], 1)]
    assert out["kwh_range"] is None
    assert out["kgco2eq_range"] is None                 # 0으로 채우지 않음


# ---------------------------------------------------------------- 세대 수 없음: 값 없이 이유
@pytest.mark.parametrize("households", [None, 0])
def test_without_households_both_levels_are_empty_with_a_reason(households):
    out = _levels(households=households, roof_limit_kw=150.0)
    for level in LEVELS:
        o = out[level]
        assert o["kw_range"] is None and o["kwh_range"] is None and o["kgco2eq_range"] is None
        assert isinstance(o["reason"], str) and "세대 수" in o["reason"]


# ---------------------------------------------------------------- 지역 규칙(문장만, 값에 안 씀)
@pytest.mark.parametrize("code, word", [("11680", "서울"), ("11", "서울"), ("50110", "제주"), ("50130", "제주")])
def test_region_rule_names_seoul_and_jeju(code, word):
    rule = _levels(region_code=code)["region_rule"]
    assert isinstance(rule, str) and word in rule


@pytest.mark.parametrize("code", ["52110", "26110", None])
def test_no_region_rule_elsewhere(code):
    assert _levels(region_code=code)["region_rule"] is None


def test_the_region_rule_does_not_change_the_values():
    seoul, other = _levels(region_code="11680"), _levels(region_code="52110")
    for level in LEVELS:
        assert seoul[level] == other[level]


# ---------------------------------------------------------------- 감축 제안 줄: 새 칸만 더함
def test_pv_levels_is_added_only_to_rooftop_pv_lines_and_nothing_else_changes():
    levels = _levels(roof_limit_kw=150.0, region_code="11680")
    before = _lines()
    after = _lines(pv_levels=levels)
    pv = [x for x in after if x["key"] == "rooftop_pv"]
    assert pv, "지붕 태양광 줄이 있어야 함"
    assert all(x["pv_levels"] == levels for x in pv)
    assert all("pv_levels" not in x for x in after if x["key"] != "rooftop_pv")
    stripped = [{k: v for k, v in x.items() if k != "pv_levels"} for x in after]
    assert stripped == before                            # 줄 집합 · 순서 · 기존 칸(값 포함) 그대로


def test_pv_levels_none_is_identical_to_today():
    before = _lines()
    after = _lines(pv_levels=None)
    assert after == before
    assert all("pv_levels" not in x for x in after)


def test_pv_levels_without_households_still_changes_nothing_else():
    levels = _levels(households=None, roof_limit_kw=150.0)
    before = _lines()
    after = _lines(pv_levels=levels)
    assert [{k: v for k, v in x.items() if k != "pv_levels"} for x in after] == before


def test_the_three_levels_are_never_summed_into_targets_or_recommended():
    targets = _targets()
    frozen = copy.deepcopy(targets)
    _lines(targets=targets, pv_levels=_levels(roof_limit_kw=150.0))
    assert targets == frozen                             # 목표 · 추천 방안 · 남는 양은 지붕 최대(지금 값) 그대로


def test_pv_levels_works_together_with_green_area():
    levels = _levels(roof_limit_kw=150.0)
    before = _lines(green_area_m2=12345.6)
    after = _lines(green_area_m2=12345.6, pv_levels=levels)
    assert [{k: v for k, v in x.items() if k != "pv_levels"} for x in after] == before


# ---------------------------------------------------------------- 세대 수: 주거 용도 줄의 dwellings 합
BASE = {"area": {"type": "admin", "code": "x"}}


def test_normalize_plan_sums_residential_dwellings_into_households():
    from app.plan_bundle import BundleIn, normalize_plan
    body = BundleIn(**BASE, uses_new=[{"use": "residential", "floor_area_m2": 60000, "dwellings": 600},
                                      {"use": "commercial", "floor_area_m2": 20000}])
    assert normalize_plan(body)["households"] == 600


def test_normalize_plan_adds_several_residential_lines_and_ignores_other_uses():
    from app.plan_bundle import BundleIn, normalize_plan
    body = BundleIn(**BASE, uses_new=[{"use": "residential", "floor_area_m2": 60000, "dwellings": 600},
                                      {"use": "residential", "floor_area_m2": 30000, "dwellings": 250},
                                      {"use": "commercial", "floor_area_m2": 20000, "dwellings": 40}])
    assert normalize_plan(body)["households"] == 850


@pytest.mark.parametrize("uses_new", [
    [{"use": "residential", "floor_area_m2": 60000}, {"use": "commercial", "floor_area_m2": 20000}],
    [{"use": "commercial", "floor_area_m2": 20000}],
    [],
])
def test_normalize_plan_has_no_households_key_without_residential_dwellings(uses_new):
    from app.plan_bundle import BundleIn, normalize_plan
    plan = normalize_plan(BundleIn(**BASE, uses_new=uses_new))
    assert "households" not in plan                      # 0으로 채우지 않음


def test_normalize_plan_keeps_the_other_fields_with_households():
    from app.plan_bundle import BundleIn, normalize_plan
    body = BundleIn(**BASE, uses_new=[{"use": "residential", "floor_area_m2": 60000, "dwellings": 600},
                                      {"use": "commercial", "floor_area_m2": 20000}])
    plan = normalize_plan(body)
    assert plan["added_floor_area_m2"] == 80000
    assert plan["uses_new"] == [{"use": "residential", "floor_area_m2": 60000.0},
                                {"use": "commercial", "floor_area_m2": 20000.0}]


# ---------------------------------------------------------------- 독립 검토 반영(2026-11-25)
def test_the_inputs_are_given_back_so_the_numbers_can_be_traced():
    out = rm.pv_levels(600, 1160.0, 0.433, 240.0, "52110", "footprint")
    assert (out["households"], out["kwh_per_kw"], out["roof_limit_kw"], out["roof_limit_basis"]) == (600, 1160.0, 240.0, "footprint")


def test_an_upper_bound_roof_gives_kw_only_and_says_why():
    """지붕을 연면적(위 한계)으로만 알면 지붕 최대 줄처럼 감축량을 확정하지 않는다."""
    out = rm.pv_levels(600, 1160.0, 0.433, 3600.0, "52110", "floor_area_upper_bound")
    for level in ("certified", "cases"):
        row = out[level]
        assert row["kw_range"] == [round(600 * k, 1) for k in getattr(rm, "PV_KW_PER_HOUSEHOLD_" + ("CERTIFIED" if level == "certified" else "CASES"))]
        assert row["kwh_range"] is None and row["kgco2eq_range"] is None and row["capped"] is False
        assert "위 한계" in row["reason"]


def test_a_zero_roof_limit_is_not_a_zero_value():
    out = rm.pv_levels(600, 1160.0, 0.433, 0.0, "52110", "footprint")
    for level in ("certified", "cases"):
        assert out[level]["kw_range"] is None and out[level]["kgco2eq_range"] is None and out[level]["reason"]


def test_each_rooftop_line_gets_its_own_copy():
    levels = rm.pv_levels(600, 1160.0, 0.433, 150.0, "52110", "footprint")
    lines = [x for x in _lines(pv_levels=levels) if x["key"] == "rooftop_pv"]
    assert len(lines) >= 2
    lines[0]["pv_levels"]["certified"]["kw_range"] = [0, 0]
    assert lines[1]["pv_levels"]["certified"]["kw_range"] != [0, 0]
