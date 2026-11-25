"""계획 v3 단계 I(2026-11-25): 감축 수단 조합 제안 세 가지 — 태양광 수준별, 값과 추정을 섞지 않음
(기록 2026-11-25-measure-combinations.md).

규칙(구현 · 결과 보기 전에 정함):
- 대상: 개발 증가분 기준(plan_added)의 필요 감축량 need. 없으면(None) 조합도 None
- 조합 셋 = 태양광 수준 셋: A 지붕 최대(값, SCENARIO) · B 인증 수준 · C 실제 사례 수준(추정 범위, ESTIMATED)
- 칸을 나눠서 냄: pv · after_pv · electricity_estimates · after_estimates · gas_estimates · co2_estimates · indicators.
  한 칸에 값(SCENARIO)과 추정(ESTIMATED)을 더하지 않음
- after_pv = need − pv. 0 아래는 0이 아니라 "메움"(A: covered + 여유량, B/C: 그 끝을 None + covered_possible)
- 범위 빼기: [a, b] − [c, d] = [a − d, b − c]
- 입력(목표 · 태양광 수준 · 추정 · 줄)은 바꾸지 않음
"""
import copy

import pytest

import app.reduction_measures as rm   # 모듈로 가져와 이름이 없을 때 시험마다 따로 실패하게 함
from app.area import target_bases
from app.measure_catalog import order_lines
from app.reduction_measures import applicable_measures
from tests.test_u4_targets import _result

ADDED_M2 = 50000.0
RES_M2 = 60000.0        # 사례 대상지 세 곳: 신축 주거 60,000 m²
H = 600                 # 세대 수
FLOORS = 20.0
GAS = 100.0             # kWh/m² (시험용 값)
ELEC = 50.0             # kWh/m² (시험용 값)
COOL = 0.3              # 냉방 몫
YIELD = 1160.0          # kWh/kW (test_u4_targets 기본값)
FE = 0.433              # kgCO2eq/kWh 전력
FG = 0.1819             # 도시가스 계수 = app.emissions.GAS_FACTOR. 읽기 전용 실행에서 app.emissions를 가져오면 실패해 값으로 둠
KEYS = ("A", "B", "C")
LEVEL_OF = {"A": "roof_max", "B": "certified", "C": "cases"}
EST_LEVEL = {"B": "certified", "C": "cases"}
CTX = {"cdd_ratio_vs_jeonju": 0.9, "hdd_ratio_vs_jeonju": 1.25, "elec_cooling_share": 0.055,
       "district_heating_household_pct": 30.0, "local_plan_tasks_by_group": {}}   # 추운 지역: 난방 쪽 지표가 앞으로


# ---------------------------------------------------------------- 입력 만들기
def _targets(**kw):
    args = dict(plan_roof_m2=2500.0, basis="footprint")   # 지붕 한도 150 kW → PARTIAL(단계 B · E · F 시험과 같은 계획)
    args.update(kw)
    return target_bases(_result(**args))


def _added(targets):
    return next(t for t in targets if t["key"] == "plan_added")


def _levels(households=H, roof_limit_kw=150.0, kwh_per_kw=YIELD):
    return rm.pv_levels(households, kwh_per_kw, FE, roof_limit_kw, "52110", "footprint")


def _est(**kw):
    args = dict(residential_m2=RES_M2, households=H, floors=FLOORS, gas_kwh_per_m2=GAS, elec_kwh_per_m2=ELEC,
                cooling_share=COOL, design_zone="중부2", fe=FE, fg=FG)
    args.update(kw)
    return rm.estimated_ranges(**args)


def _lines(targets, pv_levels=None, estimates=None, ctx=CTX):
    """화면과 같은 순서의 감축 제안 줄(applicable_measures → order_lines)."""
    lines = applicable_measures(targets, ADDED_M2, district_share_pct=30.0, cooling_reading="냉방도일 0.9배",
                                pv_levels=pv_levels, estimates=estimates)
    return order_lines(lines, ctx)


def _combos(targets=None, pv_levels="default", estimates="default", lines=None):
    targets = targets if targets is not None else _targets()
    pv_levels = _levels() if pv_levels == "default" else pv_levels
    estimates = _est() if estimates == "default" else estimates
    lines = lines if lines is not None else _lines(targets, pv_levels, estimates)
    return rm.combinations(targets, pv_levels, estimates, lines)


def _by_key(out):
    return {c["key"]: c for c in out}


def _numbers(x):
    """칸 안의 숫자를 모두 꺼냄(음수 확인용)."""
    if isinstance(x, bool) or x is None:
        return []
    if isinstance(x, (int, float)):
        return [x]
    if isinstance(x, dict):
        return [n for v in x.values() for n in _numbers(v)]
    if isinstance(x, (list, tuple)):
        return [n for v in x for n in _numbers(v)]
    return []


def _sub(a, b):
    """[a0, a1] − [b0, b1] = [a0 − b1, a1 − b0](가장 넓게)."""
    return [a[0] - b[1], a[1] - b[0]]


# ---------------------------------------------------------------- 대상 없음: None
def test_no_plan_added_target_gives_none():
    only_area = [t for t in _targets() if t["key"] != "plan_added"]
    assert rm.combinations(only_area, _levels(), _est(), []) is None


def test_more_demolished_than_built_has_nothing_to_cover_and_gives_none():
    targets = target_bases(_result(added=1000.0, removed=5000.0))   # plan_added need None(test_u4_targets와 같은 경우)
    assert _added(targets)["required_reduction_kgco2eq"] is None
    assert rm.combinations(targets, _levels(), _est(), _lines(targets)) is None


# ---------------------------------------------------------------- 꼴: 셋, A/B/C, 태양광 수준
def test_exactly_three_combinations_a_b_c_with_their_pv_levels():
    out = _combos()
    assert isinstance(out, list) and len(out) == 3
    assert [c["key"] for c in out] == list(KEYS)
    for c in out:
        assert c["pv_level"] == LEVEL_OF[c["key"]]


def test_each_combination_has_all_fields():
    fields = {"key", "pv_level", "need_kgco2eq", "pv", "after_pv", "electricity_estimates", "after_estimates",
              "gas_estimates", "co2_estimates", "indicators"}
    for c in _combos():
        assert fields <= set(c)


def test_need_is_the_plan_added_required_reduction():
    targets = _targets()
    need = _added(targets)["required_reduction_kgco2eq"]
    for c in _combos(targets=targets):
        assert c["need_kgco2eq"] == need


# ---------------------------------------------------------------- A: 지붕 최대(값)
def test_a_pv_is_the_recommended_roof_max_value():
    targets = _targets()
    rec = _added(targets)["recommended"]
    a = _by_key(_combos(targets=targets))["A"]
    assert a["pv"]["data_class"] == "SCENARIO"
    assert a["pv"]["kgco2eq"] == rec["pv_kgco2eq"]


def test_a_after_pv_is_need_minus_pv():
    targets = _targets()
    need, pv = _added(targets)["required_reduction_kgco2eq"], _added(targets)["recommended"]["pv_kgco2eq"]
    assert pv < need
    a = _by_key(_combos(targets=targets))["A"]
    assert a["after_pv"]["kgco2eq"] == round(need - pv, 1)


@pytest.mark.parametrize("roof", [2500.0, 1000.0, 4000.0])
def test_a_after_pv_equals_the_recommended_remaining_when_partial(roof):
    """기록의 확인 항목: A의 after_pv는 지금 추천 방안의 남는 양과 같음(같은 지붕 최대)."""
    targets = _targets(plan_roof_m2=roof)
    rec = _added(targets)["recommended"]
    assert rec["onsite_status"] == "PARTIAL"
    a = _by_key(_combos(targets=targets, pv_levels=_levels(roof_limit_kw=rec["roof_limit_kw"])))["A"]
    # 추천 방안은 반올림 전 값으로 빼고, 조합은 반올림한 need · pv로 빼서 0.1 안쪽 차이는 허용
    assert a["after_pv"]["kgco2eq"] == pytest.approx(rec["remaining_kgco2eq"], abs=0.11)


def test_a_covered_need_gives_covered_and_margin_not_zero_or_negative():
    targets = target_bases(_result(added=1000.0, plan_roof_m2=100000.0, basis="footprint"))   # 큰 지붕 · 작은 계획 → MET
    added = _added(targets)
    rec = added["recommended"]
    assert rec["onsite_status"] == "MET"
    a = _by_key(_combos(targets=targets, pv_levels=_levels(roof_limit_kw=rec["roof_limit_kw"])))["A"]
    ap = a["after_pv"]
    assert ap["covered"] is True
    assert ap["kgco2eq"] is None                                       # 0으로 채우지 않음
    assert ap["margin_kgco2eq"] == round(rec["pv_kgco2eq"] - added["required_reduction_kgco2eq"], 1)
    assert ap["margin_kgco2eq"] >= 0


def test_a_does_not_depend_on_pv_levels_or_estimates():
    targets = _targets()
    full = _by_key(_combos(targets=targets))["A"]
    bare = _by_key(_combos(targets=targets, pv_levels=None, estimates=None))["A"]
    assert full["pv"] == bare["pv"]
    assert full["after_pv"] == bare["after_pv"]                         # 전력 추정을 after_pv에 빼지 않음


# ---------------------------------------------------------------- B/C: 인증 · 사례 수준(추정 범위)
@pytest.mark.parametrize("key", ["B", "C"])
def test_b_c_pv_is_the_level_range_marked_estimated(key):
    levels = _levels()
    c = _by_key(_combos(pv_levels=levels))[key]
    assert c["pv"]["data_class"] == "ESTIMATED"
    assert c["pv"]["kgco2eq_range"] == levels[EST_LEVEL[key]]["kgco2eq_range"]


@pytest.mark.parametrize("key", ["B", "C"])
def test_b_c_after_pv_is_need_minus_the_range_widest(key):
    targets = _targets()
    levels = _levels()
    need = _added(targets)["required_reduction_kgco2eq"]
    lo, hi = levels[EST_LEVEL[key]]["kgco2eq_range"]
    assert hi < need                                                    # 이 계획은 두 끝 모두 못 메움
    c = _by_key(_combos(targets=targets, pv_levels=levels))[key]
    assert c["after_pv"]["kgco2eq_range"] == [round(need - hi, 1), round(need - lo, 1)]


def test_a_range_end_below_zero_is_none_and_covered_possible():
    """need가 사례 수준 범위 안에 있음: need − 큰 끝은 0 아래 → None + covered_possible, 다른 끝은 값."""
    targets = _targets(added=8000.0, plan_roof_m2=100000.0)
    levels = _levels(roof_limit_kw=None)
    need = _added(targets)["required_reduction_kgco2eq"]
    lo, hi = levels["cases"]["kgco2eq_range"]
    assert lo < need < hi
    c = _by_key(_combos(targets=targets, pv_levels=levels))["C"]
    assert c["after_pv"]["kgco2eq_range"] == [None, round(need - lo, 1)]
    assert c["after_pv"]["covered_possible"] is True


def test_both_range_ends_below_zero_are_none_and_covered_possible():
    targets = target_bases(_result(added=1000.0, plan_roof_m2=100000.0, basis="footprint"))
    levels = _levels(roof_limit_kw=None)
    need = _added(targets)["required_reduction_kgco2eq"]
    assert levels["certified"]["kgco2eq_range"][0] > need
    b = _by_key(_combos(targets=targets, pv_levels=levels))["B"]
    assert b["after_pv"]["kgco2eq_range"] == [None, None]
    assert b["after_pv"]["covered_possible"] is True


@pytest.mark.parametrize("added, roof", [(50000.0, 2500.0), (8000.0, 100000.0), (1000.0, 100000.0)])
def test_never_a_negative_number_in_after_pv_or_after_estimates(added, roof):
    targets = _targets(added=added, plan_roof_m2=roof)
    for c in _combos(targets=targets, pv_levels=_levels(roof_limit_kw=None)):
        assert all(n >= 0 for n in _numbers(c["after_pv"])), c["key"]
        assert all(n >= 0 for n in _numbers(c["after_estimates"])), c["key"]


@pytest.mark.parametrize("key", ["B", "C"])
def test_b_c_without_households_have_no_range_and_a_reason(key):
    c = _by_key(_combos(pv_levels=_levels(households=None)))[key]
    assert c["pv"]["kgco2eq_range"] is None
    assert isinstance(c["pv"]["reason"], str) and c["pv"]["reason"].strip()
    assert (c["after_pv"] or {}).get("kgco2eq_range") is None          # 범위가 없으면 빼지 않음


# ---------------------------------------------------------------- 태양광 수준 · 추정이 모두 없음
def test_without_pv_levels_and_estimates_a_still_computed_and_the_rest_empty():
    targets = _targets()
    rec = _added(targets)["recommended"]
    out = _by_key(_combos(targets=targets, pv_levels=None, estimates=None))
    assert out["A"]["pv"]["data_class"] == "SCENARIO" and out["A"]["pv"]["kgco2eq"] == rec["pv_kgco2eq"]
    assert out["A"]["after_pv"]["kgco2eq"] == rec["remaining_kgco2eq"]   # 검토 반영: 추천 방안의 남는 양을 그대로
    for key in ("B", "C"):
        assert out[key]["pv"]["kgco2eq_range"] is None
        assert isinstance(out[key]["pv"]["reason"], str) and out[key]["pv"]["reason"].strip()
    for c in out.values():
        assert c["electricity_estimates"] == [] and c["co2_estimates"] == [] and c["gas_estimates"] == []
        assert c["after_estimates"] is None


# ---------------------------------------------------------------- 전력 추정: 옥상녹화 냉방 몫만
def test_electricity_estimates_are_the_green_roof_cooling_part_only():
    est = _est()
    cool = est["building_greening"]["parts"]["cooling"]
    assert cool
    for c in _combos(estimates=est):
        assert len(c["electricity_estimates"]) == 1
        assert c["electricity_estimates"][0]["key"] == "building_greening_cooling"
        assert c["electricity_estimates"][0]["kgco2eq_range"] == cool
        keys = {x["key"] for x in c["electricity_estimates"]}
        assert "elevator_regeneration" not in keys and "envelope" not in keys   # 승강기는 CO2, 단열은 가스


@pytest.mark.parametrize("kw", [{"design_zone": "남부"}, {"elec_kwh_per_m2": None}, {"cooling_share": None}, {"floors": None}])
def test_without_a_cooling_part_electricity_estimates_are_empty_and_after_estimates_none(kw):
    est = _est(**kw)
    assert not (est["building_greening"].get("parts") or {}).get("cooling")
    for c in _combos(estimates=est):
        assert c["electricity_estimates"] == []
        assert c["after_estimates"] is None


# ---------------------------------------------------------------- 추정을 반영하면(after_estimates)
def test_a_after_estimates_is_after_pv_minus_the_cooling_range():
    targets = _targets()
    est = _est()
    cool = est["building_greening"]["parts"]["cooling"]
    a = _by_key(_combos(targets=targets, estimates=est))["A"]
    x = a["after_pv"]["kgco2eq"]
    assert a["after_estimates"]["data_class"] == "ESTIMATED"
    assert a["after_estimates"]["kgco2eq_range"] == pytest.approx(_sub([x, x], cool), abs=0.11)


@pytest.mark.parametrize("key", ["B", "C"])
def test_b_c_after_estimates_is_the_after_pv_range_minus_the_cooling_range(key):
    targets = _targets()
    est = _est()
    cool = est["building_greening"]["parts"]["cooling"]
    c = _by_key(_combos(targets=targets, estimates=est))[key]
    rng = c["after_pv"]["kgco2eq_range"]
    assert None not in rng
    assert c["after_estimates"]["data_class"] == "ESTIMATED"
    assert c["after_estimates"]["kgco2eq_range"] == pytest.approx(_sub(rng, cool), abs=0.11)


def test_after_estimates_below_zero_is_none_and_covered_possible():
    """냉방 몫의 큰 끝이 남는 양보다 큰 경우: 0 아래 끝은 None + covered_possible, 다른 끝은 값."""
    targets = _targets()
    est = _est(residential_m2=60_000_000.0)                            # 냉방 몫을 크게(시험용)
    cool = est["building_greening"]["parts"]["cooling"]
    b = _by_key(_combos(targets=targets, estimates=est))["B"]
    lo_after, hi_after = b["after_pv"]["kgco2eq_range"]
    assert lo_after is not None and hi_after is not None
    assert lo_after - cool[1] < 0 < hi_after - cool[0]
    ae = b["after_estimates"]
    assert ae["kgco2eq_range"][0] is None
    assert ae["kgco2eq_range"][1] == pytest.approx(hi_after - cool[0], abs=0.11)
    assert ae["covered_possible"] is True


def test_estimates_appear_only_in_after_estimates_not_in_after_pv():
    """값과 추정을 한 칸에 더하지 않음: after_pv는 추정이 있든 없든 같음."""
    targets = _targets()
    levels = _levels()
    with_est = _by_key(_combos(targets=targets, pv_levels=levels, estimates=_est()))
    without = _by_key(_combos(targets=targets, pv_levels=levels, estimates=None))
    for key in KEYS:
        assert with_est[key]["after_pv"] == without[key]["after_pv"]
        assert with_est[key]["pv"] == without[key]["pv"]


# ---------------------------------------------------------------- 가스 · CO2 추정(나란히, 빼지 않음)
def test_gas_estimates_are_envelope_and_green_roof_heating():
    est = _est()
    heat = est["building_greening"]["parts"]["heating"]
    for c in _combos(estimates=est):
        gas = c["gas_estimates"]
        env = [x for x in gas if x["key"] == "envelope"]
        assert len(env) == 1 and env[0]["kgco2eq_range"] == est["envelope"]["kgco2eq_range"]
        rest = [x for x in gas if x["key"] != "envelope"]
        assert len(rest) == 1 and rest[0]["key"].startswith("building_greening") and rest[0]["kgco2eq_range"] == heat
        assert all("cooling" not in x["key"] for x in gas)


def test_without_gas_intensity_gas_estimates_are_empty():
    est = _est(gas_kwh_per_m2=None)                                     # 단열·창호 · 옥상녹화 난방 모두 없음
    for c in _combos(estimates=est):
        assert c["gas_estimates"] == []


def test_co2_estimates_are_the_elevator_in_co2_not_co2eq():
    est = _est()
    for c in _combos(estimates=est):
        assert len(c["co2_estimates"]) == 1
        item = c["co2_estimates"][0]
        assert item["key"] == "elevator_regeneration"
        assert item["kgco2_range"] == est["elevator_regeneration"]["kgco2_range"]
        assert "kgco2eq_range" not in item or item["kgco2eq_range"] is None


def test_without_households_co2_estimates_are_empty():
    for c in _combos(estimates=_est(households=None)):
        assert c["co2_estimates"] == []


def test_the_estimate_lists_are_the_same_for_a_b_c():
    out = _combos()
    for field in ("electricity_estimates", "gas_estimates", "co2_estimates", "indicators"):
        assert out[0][field] == out[1][field] == out[2][field], field


# ---------------------------------------------------------------- 지표: 주어진 순서의 plan_added INDICATOR 줄 위 3개
def _expected_indicators(lines):
    picked = [x for x in lines if x["target"] == "plan_added" and x["level"] == "INDICATOR"][:3]
    return [{"key": x["key"], "title": x["title"], "why": x["why"]} for x in picked]


def test_indicators_are_the_first_three_plan_added_indicator_lines_with_their_reasons():
    targets = _targets()
    lines = _lines(targets, _levels(), _est())
    exp = _expected_indicators(lines)
    assert len(exp) == 3
    for c in _combos(targets=targets, lines=lines):
        assert [{k: x[k] for k in ("key", "title", "why")} for x in c["indicators"]] == exp


def test_indicators_follow_the_given_order_not_a_new_sort():
    targets = _targets()
    lines = _lines(targets, _levels(), _est())
    added = [x for x in lines if x["target"] == "plan_added"]
    rest = [x for x in lines if x["target"] != "plan_added"]
    flipped = list(reversed(added)) + rest
    exp = _expected_indicators(flipped)
    assert exp != _expected_indicators(lines)                           # 순서를 바꾸면 위 3개가 달라지는 경우
    for c in _combos(targets=targets, lines=flipped):
        assert [x["key"] for x in c["indicators"]] == [x["key"] for x in exp]


def test_indicators_skip_value_range_and_area_total_lines():
    targets = _targets()
    lines = _lines(targets, _levels(), _est())
    for c in _combos(targets=targets, lines=lines):
        keys = [x["key"] for x in c["indicators"]]
        assert "rooftop_pv" not in keys                                 # 값 줄
        assert "envelope" not in keys and "elevator_regeneration" not in keys   # 추정 범위가 붙어 RANGE가 된 줄
    only_area = [x for x in lines if x["target"] != "plan_added"]
    for c in _combos(targets=targets, lines=only_area):
        assert c["indicators"] == []


def test_fewer_than_three_indicator_lines_give_fewer_items():
    targets = _targets()
    lines = _lines(targets, _levels(), _est())
    ind = [x for x in lines if x["target"] == "plan_added" and x["level"] == "INDICATOR"]
    two = [x for x in lines if x not in ind] + ind[:2]
    for c in _combos(targets=targets, lines=two):
        assert [x["key"] for x in c["indicators"]] == [x["key"] for x in ind[:2]]


# ---------------------------------------------------------------- 입력을 바꾸지 않음
def test_inputs_are_never_mutated():
    targets = _targets()
    levels = _levels()
    est = _est()
    lines = _lines(targets, levels, est)
    frozen = copy.deepcopy((targets, levels, est, lines))
    rm.combinations(targets, levels, est, lines)
    assert (targets, levels, est, lines) == frozen


def test_returned_lists_do_not_alias_the_inputs():
    """돌려준 칸을 고쳐도 입력은 그대로(조합은 기존 목표 · 추천 방안 · 줄에 영향 없음)."""
    targets = _targets()
    levels = _levels()
    est = _est()
    lines = _lines(targets, levels, est)
    frozen = copy.deepcopy((targets, levels, est, lines))
    out = rm.combinations(targets, levels, est, lines)
    for c in out:
        for item in c["electricity_estimates"] + c["gas_estimates"] + c["co2_estimates"]:
            for k in ("kgco2eq_range", "kgco2_range"):
                if isinstance(item.get(k), list):
                    item[k].append(-1)
        if isinstance(c["pv"].get("kgco2eq_range"), list):
            c["pv"]["kgco2eq_range"].append(-1)
        for x in c["indicators"]:
            if isinstance(x.get("why"), list):
                x["why"].append("x")
    assert (targets, levels, est, lines) == frozen



# ---------------------------------------------------------------- 독립 검토 반영(2026-11-25): A는 추천 방안의 판정을 따름
def test_a_with_an_upper_bound_roof_is_not_a_value_and_not_covered():
    """층수 · 동 정보가 없어 지붕을 연면적 위 한계로만 알면 A도 값을 확정하지 않는다(지붕 태양광 줄과 같은 판단)."""
    targets = target_bases(_result(added=50000.0))
    rec = _added(targets)["recommended"]
    assert rec["onsite_status"] == "UPPER_BOUND_ONLY"
    a = _by_key(_combos(targets=targets, pv_levels=None, estimates=None))["A"]
    assert a["pv"]["kgco2eq"] is None and a["pv"]["status"] == "UPPER_BOUND_ONLY" and "위 한계" in a["pv"]["reason"]
    assert a["after_pv"] is None and a["after_estimates"] is None


def test_after_range_marks_covered_ends_with_none_and_gives_the_margin():
    out = rm._after([-5.0, 10.0], "ESTIMATED")
    assert out["kgco2eq_range"] == [None, 10.0] and out["covered"] == "possible" and out["margin_kgco2eq_range"] == [5.0, None]
    out = rm._after([-5.0, -1.0], "ESTIMATED")
    assert out["kgco2eq_range"] == [None, None] and out["covered"] == "all" and out["margin_kgco2eq_range"] == [5.0, 1.0]
    out = rm._after([0.04, 5.0], "ESTIMATED")    # 반올림해 0이면 값이 아님
    assert out["kgco2eq_range"] == [None, 5.0] and out["covered"] == "possible"


def test_estimate_items_carry_their_basis_and_condition():
    for c in _combos():
        for item in c["gas_estimates"] + c["electricity_estimates"] + c["co2_estimates"]:
            assert item.get("data_class") == "ESTIMATED" and item.get("basis") and "condition" in item
