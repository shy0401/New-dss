"""계획 v3 단계 F(2026-11-25): 감축 제안에 추정 범위(L2) — 단열·창호(가스) · 승강기 회생제동 · 옥상녹화
(기록 2026-11-25-estimated-ranges.md).

규칙(구현 · 결과 보기 전에 정함):
- 단열·창호(envelope): 신축 주거 연면적 × 구역 가스 원단위 × 도시가스 계수 × [9.8, 17.3]%(MEASURES의 범위). 가스 원단위가 없으면 값 없이 이유
- 승강기 회생제동(elevator_regeneration): [세대 수 ÷ 57, 세대 수 ÷ 21.2]대 × [0.39, 0.57] t. 세대 수가 없으면 값 없이 이유("세대 수")
- 옥상녹화(building_greening): 설계 지역 구분 중부2만. 냉방 = 주거 연면적 × 전력 원단위 × 냉방 몫 ÷ 층수 × [2.35, 3.97]% × 전력 계수,
  난방 = 주거 연면적 × 가스 원단위 ÷ 층수 × [6.81, 9.42]% × 가스 계수. 없는 쪽만 비우고, 범위는 있는 쪽의 합
- 추정은 어떤 합계에도 넣지 않음: 개발 증가분(plan_added)의 단열·창호 · 승강기 줄에 estimate 칸만 더하고 level만 RANGE로.
  구역 전체(area_total) 줄 · 다른 칸 · 목표 · 추천 방안은 그대로
"""
import copy

import pytest

import app.reduction_measures as rm   # 모듈로 가져와 이름이 없을 때 시험마다 따로 실패하게 함
from app.area import target_bases
from app.reduction_measures import applicable_measures
from tests.test_u4_targets import _result

ADDED_M2 = 50000.0
RES_M2 = 60000.0        # 사례 대상지 세 곳: 신축 주거 60,000 m²(+ 상업 20,000)
H = 600                 # 세대 수
FLOORS = 20.0
GAS = 100.0             # kWh/m² (구역 가스 원단위, 시험용 값)
ELEC = 50.0             # kWh/m² (구역 전력 원단위, 시험용 값)
COOL = 0.3              # 지역 냉방 몫
FE = 0.433              # kgCO2eq/kWh 전력
FG = 0.1819             # kgCO2eq/kWh 도시가스 = app.emissions.GAS_FACTOR(test_emissions_rule에서 확인). 가져오면 읽기 전용 실행에서 data/raw를 만들려다 실패해 값으로 둠
KEYS = ("envelope", "elevator_regeneration", "building_greening")


def _est(**kw):
    args = dict(residential_m2=RES_M2, households=H, floors=FLOORS, gas_kwh_per_m2=GAS, elec_kwh_per_m2=ELEC,
                cooling_share=COOL, design_zone="중부2", fe=FE, fg=FG)
    args.update(kw)
    return rm.estimated_ranges(**args)


def _targets():
    return target_bases(_result(plan_roof_m2=2500.0, basis="footprint"))


def _lines(targets=None, **kw):
    """단계 B · D · E 시험과 같은 계획(지붕 2,500 m², 연면적 50,000 m²)의 감축 제안 줄."""
    return applicable_measures(targets if targets is not None else _targets(), ADDED_M2,
                               district_share_pct=30.0, cooling_reading="냉방도일 0.9배", **kw)


def _is_1dp(x):
    return isinstance(x, float) and round(x, 1) == x


def _check_shape(e):
    """추정 한 줄의 공통 꼴: 추정 표시 · 범위 또는 이유 · 곱한 양 · 근거 · 조건."""
    assert e["data_class"] == "ESTIMATED"
    assert isinstance(e["basis"], str) and e["basis"].strip()
    assert e["condition"] is None or isinstance(e["condition"], str)
    assert isinstance(e["chain"], list) and all(isinstance(s, str) and s.strip() for s in e["chain"])
    r = e["kgco2eq_range"] if e.get("kgco2eq_range") is not None else e.get("kgco2_range")   # 승강기는 CO2 칸(검토 반영)
    if r is None:
        assert isinstance(e["reason"], str) and e["reason"].strip()   # 0으로 채우지 않고 이유
    else:
        assert isinstance(r, list) and len(r) == 2 and all(_is_1dp(v) for v in r)
        assert r[0] <= r[1]
        assert e["chain"], "범위가 있으면 곱한 양을 적어야 함"
        assert e["reason"] is None


# ---------------------------------------------------------------- 상수: 기록의 표와 같은 값
def test_the_constants_are_the_recorded_ranges():
    assert tuple(rm.ELEVATOR_HOUSEHOLDS_PER_UNIT) == (21.2, 57.0)   # K-apt 2015년 이후 준공 5,763단지 10~90% 구간
    assert tuple(rm.ELEVATOR_T_PER_UNIT) == (0.39, 0.57)           # 서울시 전망 계수 · 배출권 승인 168 t ÷ 117대 ÷ 2.5년
    assert tuple(rm.GREEN_ROOF_COOLING) == (0.0235, 0.0397)        # 김지현 외 2016 표 7, 냉방
    assert tuple(rm.GREEN_ROOF_HEATING) == (0.0681, 0.0942)        # 같은 표, 난방


def test_the_envelope_range_is_the_measures_table_range():
    env = next(m for m in rm.MEASURES if m["key"] == "envelope")
    assert tuple(env["range"]) == (0.098, 0.173)                     # 117쌍 짝 비교 −9.8~−17.3%


# ---------------------------------------------------------------- 공통 꼴
def test_the_result_has_the_three_keys():
    out = _est()
    assert set(KEYS) <= set(out)


@pytest.mark.parametrize("key", KEYS)
def test_each_estimate_has_the_common_shape(key):
    _check_shape(_est()[key])


@pytest.mark.parametrize("key", KEYS)
def test_with_all_inputs_each_estimate_has_a_range(key):
    e = _est()[key]
    assert (e["kgco2eq_range"] if key != "elevator_regeneration" else e["kgco2_range"]) is not None


def test_elevator_is_co2_not_co2eq():
    """원 값이 tCO2(서울시 실적)라 CO2eq 칸에 넣지 않음(기준 문서 1절, 독립 검토 반영)."""
    e = _est()["elevator_regeneration"]
    assert e["kgco2eq_range"] is None and e["kgco2_range"] and "CO2eq 아님" in e["condition"]


# ---------------------------------------------------------------- 단열·창호: 주거 연면적 × 가스 원단위 × 가스 계수 × 9.8~17.3%
def test_envelope_is_residential_area_times_gas_intensity_times_gas_factor_times_range():
    g = RES_M2 * GAS * FG
    assert _est()["envelope"]["kgco2eq_range"] == pytest.approx([round(g * 0.098, 1), round(g * 0.173, 1)], abs=0.051)


@pytest.mark.parametrize("missing", [{"residential_m2": None}, {"residential_m2": 0}, {"gas_kwh_per_m2": None},
                                     {"gas_kwh_per_m2": 0}, {"fg": None}, {"fg": 0}])
def test_envelope_without_area_gas_or_factor_is_empty_with_a_reason(missing):
    e = _est(**missing)["envelope"]
    assert e["kgco2eq_range"] is None
    _check_shape(e)


def test_envelope_does_not_depend_on_households_floors_or_zone():
    base = _est()["envelope"]["kgco2eq_range"]
    assert _est(households=None)["envelope"]["kgco2eq_range"] == base
    assert _est(floors=None)["envelope"]["kgco2eq_range"] == base
    assert _est(design_zone="남부")["envelope"]["kgco2eq_range"] == base


# ---------------------------------------------------------------- 승강기: [세대 ÷ 57, 세대 ÷ 21.2]대 × [390, 570] kg
def test_elevator_is_units_from_households_times_per_unit_tonnes():
    r = _est()["elevator_regeneration"]["kgco2_range"]
    assert r == pytest.approx([round(H / 57.0 * 390, 1), round(H / 21.2 * 570, 1)], abs=0.051)


def test_600_households_give_the_recorded_4_1_to_16_1_tonnes():
    """기록의 확인 항목: 600세대 → 10.5~28.3대 → 4.1~16.1 t."""
    lo, hi = _est()["elevator_regeneration"]["kgco2_range"]
    assert round(lo / 1000, 1) == 4.1 and round(hi / 1000, 1) == 16.1


@pytest.mark.parametrize("households", [None, 0])
def test_elevator_without_households_is_empty_with_a_reason(households):
    e = _est(households=households)["elevator_regeneration"]
    assert e["kgco2eq_range"] is None and e["kgco2_range"] is None
    assert isinstance(e["reason"], str) and "세대 수" in e["reason"]
    _check_shape(e)


# ---------------------------------------------------------------- 옥상녹화: 중부2만, 최상층 몫(1 ÷ 층수)
def _cool_part(fe=FE, elec=ELEC, share=COOL, floors=FLOORS):
    b = RES_M2 * elec * share / floors
    return [round(b * 0.0235 * fe, 1), round(b * 0.0397 * fe, 1)]


def _heat_part(fg=FG, gas=GAS, floors=FLOORS):
    b = RES_M2 * gas / floors
    return [round(b * 0.0681 * fg, 1), round(b * 0.0942 * fg, 1)]


def test_green_roof_parts_are_cooling_and_heating_over_floors():
    e = _est()["building_greening"]
    assert e["parts"]["cooling"] == pytest.approx(_cool_part(), abs=0.051)
    assert e["parts"]["heating"] == pytest.approx(_heat_part(), abs=0.051)
    assert all(_is_1dp(v) for v in e["parts"]["cooling"] + e["parts"]["heating"])


def test_green_roof_range_is_the_sum_of_the_parts():
    e = _est()["building_greening"]
    c, h = e["parts"]["cooling"], e["parts"]["heating"]
    assert e["kgco2eq_range"] == pytest.approx([round(c[0] + h[0], 1), round(c[1] + h[1], 1)], abs=0.051)


@pytest.mark.parametrize("zone", ["중부1", "남부", "제주", None])
def test_green_roof_outside_central_2_is_empty_with_a_reason(zone):
    e = _est(design_zone=zone)["building_greening"]
    assert e["kgco2eq_range"] is None
    assert isinstance(e["reason"], str) and "중부2" in e["reason"]   # 근거가 서울 기상 계산뿐
    _check_shape(e)


@pytest.mark.parametrize("floors", [None, 0])
def test_green_roof_without_floors_is_empty_with_a_reason(floors):
    e = _est(floors=floors)["building_greening"]
    assert e["kgco2eq_range"] is None
    _check_shape(e)


@pytest.mark.parametrize("missing", [{"elec_kwh_per_m2": None}, {"cooling_share": None}])
def test_green_roof_without_electricity_or_cooling_share_keeps_heating_only(missing):
    e = _est(**missing)["building_greening"]
    assert e["parts"]["cooling"] is None                              # 그 쪽만 비움
    assert e["parts"]["heating"] == pytest.approx(_heat_part(), abs=0.051)
    assert e["kgco2eq_range"] == e["parts"]["heating"]
    _check_shape(e)


@pytest.mark.parametrize("missing", [{"gas_kwh_per_m2": None}, {"fg": None}])
def test_green_roof_without_gas_or_gas_factor_keeps_cooling_only(missing):
    e = _est(**missing)["building_greening"]
    assert e["parts"]["heating"] is None
    assert e["parts"]["cooling"] == pytest.approx(_cool_part(), abs=0.051)
    assert e["kgco2eq_range"] == e["parts"]["cooling"]
    _check_shape(e)


def test_green_roof_without_both_parts_is_empty_with_a_reason():
    e = _est(elec_kwh_per_m2=None, gas_kwh_per_m2=None)["building_greening"]
    assert e["parts"]["cooling"] is None and e["parts"]["heating"] is None
    assert e["kgco2eq_range"] is None
    _check_shape(e)


def test_more_floors_means_a_smaller_green_roof_share():
    lo20 = _est(floors=20.0)["building_greening"]["kgco2eq_range"]
    lo40 = _est(floors=40.0)["building_greening"]["kgco2eq_range"]
    assert lo40[0] < lo20[0] and lo40[1] < lo20[1]


# ---------------------------------------------------------------- 감축 제안 줄: estimate 칸과 level만
ATTACHED = ("envelope", "elevator_regeneration")


def _strip(lines):
    """estimate · level과, 범위가 붙은 줄의 이유 문장(검토 반영: '지표만' 대신 '추정 범위만 따로')만 뺀 나머지."""
    def keep(x):
        ranged = x["target"] == "plan_added" and x["key"] in ATTACHED   # 범위가 붙을 수 있는 줄(앞 · 뒤 같은 기준)
        return {k: v for k, v in x.items() if k not in ("estimate", "level") and not (ranged and k == "no_value_reason")}
    return [keep(x) for x in lines]


def test_a_ranged_line_says_values_are_not_multiplied_and_the_estimate_is_separate():
    lines = _lines(estimates=_est())
    for x in lines:
        if (x.get("estimate") or {}).get("kgco2eq_range") or (x.get("estimate") or {}).get("kgco2_range"):
            assert x["level"] == "RANGE" and "추정 범위" in x["no_value_reason"] and "곱하지 않" in x["no_value_reason"]


def test_estimates_are_attached_only_to_plan_added_envelope_and_elevator_lines():
    est = _est()
    after = _lines(estimates=est)
    for key in ATTACHED:
        hit = [x for x in after if x["target"] == "plan_added" and x["key"] == key]
        assert hit, f"plan_added에 {key} 줄이 있어야 함"
        for x in hit:
            assert x["estimate"] == est[key]
            assert x["level"] == "RANGE"                              # INDICATOR → RANGE
    others = [x for x in after if not (x["target"] == "plan_added" and x["key"] in ATTACHED)]
    assert all("estimate" not in x for x in others)                   # 구역 전체 줄 · 다른 수단 줄에는 없음


def test_area_total_lines_are_unchanged_by_estimates():
    before = [x for x in _lines() if x["target"] == "area_total"]
    after = [x for x in _lines(estimates=_est()) if x["target"] == "area_total"]
    assert after == before                                            # 기존 건물 몫은 근거가 신축 비교라 붙이지 않음


def test_estimates_change_no_other_field_of_any_line():
    before = _lines()
    after = _lines(estimates=_est())
    assert [(x["target"], x["key"]) for x in after] == [(x["target"], x["key"]) for x in before]   # 줄 집합 · 순서 그대로
    assert _strip(after) == _strip(before)                            # value_status · value_kgco2eq · no_value_reason 등 그대로
    for b, a in zip(before, after):
        if not (a["target"] == "plan_added" and a["key"] in ATTACHED):
            assert a["level"] == b["level"]


def test_an_empty_estimate_is_attached_but_keeps_the_level():
    est = _est(gas_kwh_per_m2=None, households=None)                 # 두 범위 모두 없음
    before = _lines()
    after = _lines(estimates=est)
    for key in ATTACHED:
        for b, a in zip(before, after):
            if a["target"] == "plan_added" and a["key"] == key:
                assert a["estimate"] == est[key] and a["estimate"]["kgco2eq_range"] is None and not a["estimate"].get("kgco2_range")
                assert a["level"] == b["level"]                      # 범위가 없으면 수준 그대로
    assert _strip(after) == _strip(before)


def test_estimates_none_is_identical_to_today():
    before = _lines()
    after = _lines(estimates=None)
    assert after == before
    assert all("estimate" not in x for x in after)


def test_estimates_are_never_summed_into_targets_or_recommended():
    targets = _targets()
    frozen = copy.deepcopy(targets)
    _lines(targets=targets, estimates=_est())
    assert targets == frozen                                          # 목표 · 추천 방안 · 남는 양 그대로


def test_the_rooftop_pv_value_line_is_unchanged_by_estimates():
    before = [x for x in _lines() if x["key"] == "rooftop_pv"]
    after = [x for x in _lines(estimates=_est()) if x["key"] == "rooftop_pv"]
    assert after == before


def test_estimates_work_together_with_green_area_and_pv_levels():
    levels = rm.pv_levels(households=H, kwh_per_kw=1160.0, factor_kgco2eq_per_kwh=FE, roof_limit_kw=150.0, region_code="52110")
    before = _lines(green_area_m2=12345.6, pv_levels=levels)
    after = _lines(green_area_m2=12345.6, pv_levels=levels, estimates=_est())
    assert _strip(after) == _strip(before)


# ---------------------------------------------------------------- 지역 계산 연결(2026-11-25, 실행 중 오류에서 더함)
def test_latest_hub_year_reads_the_year_dict_and_takes_the_latest_complete_year_with_gas():
    from app.area import latest_hub_year
    history = {"building_energy": {"years": {
        2022: {"year": 2022, "complete": True, "gas_kwh_per_m2": 90.0, "kwh_per_m2": 40.0},
        2023: {"year": 2023, "complete": True, "gas_kwh_per_m2": 95.0, "kwh_per_m2": 41.0},
        2024: {"year": 2024, "complete": True, "gas_kwh_per_m2": None, "kwh_per_m2": 42.0},
        2025: {"year": 2025, "complete": False, "gas_kwh_per_m2": 99.0, "kwh_per_m2": 43.0}}}}
    assert latest_hub_year(history)["year"] == 2023
    assert latest_hub_year({}) is None and latest_hub_year({"building_energy": {"years": {}}}) is None
