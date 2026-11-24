"""계획 v3 단계 B(2026-11-25): 지역 규칙으로 지표 줄 순서 · 이유. 값 · 줄 집합은 그대로(기록 2026-11-25-measure-region-order.md)."""
from app.area import target_bases
from app.measure_catalog import FIXED_KEYS, cooling_share, order_lines
from app.reduction_measures import applicable_measures
from tests.test_u4_targets import _result


def _lines(district=None):
    r = _result(plan_roof_m2=2500.0, basis="footprint")
    return applicable_measures(target_bases(r), 50000.0, district_share_pct=district, cooling_reading=None)


def _ctx(**kw):
    base = {"cdd_ratio_vs_jeonju": 1.0, "hdd_ratio_vs_jeonju": 1.0, "elec_cooling_share": 0.055,
            "district_heating_household_pct": 5.0, "local_plan_tasks_by_group": {}}
    return {**base, **kw}


def _order(lines, target="plan_added"):
    return [x["key"] for x in lines if x["target"] == target]


def _numbers(lines):
    keep = ("value_status", "value_kgco2eq", "indicator_text", "evidence_table", "level", "evidence_groups", "attach_to")
    return sorted((x["target"], x["key"], repr([x.get(k) for k in keep])) for x in lines)


def test_values_and_line_set_never_change_only_order_and_reasons():
    lines = _lines(district=30.0)
    for ctx in (None, _ctx(), _ctx(hdd_ratio_vs_jeonju=1.3), _ctx(cdd_ratio_vs_jeonju=1.2, district_heating_household_pct=60.0)):
        out = order_lines(lines, ctx)
        assert _numbers(out) == _numbers(lines)
        for t in ("plan_added", "area_total"):   # value / offset lines keep their place
            before, after = _order(lines, t), _order(out, t)
            assert [i for i, k in enumerate(before) if k in FIXED_KEYS] == [i for i, k in enumerate(after) if k in FIXED_KEYS]


def test_without_region_values_the_order_stays():
    lines = _lines()
    out = order_lines(lines, None)
    assert _order(out) == _order(lines) and all(x["why"] == ["지역 값을 알 수 없어 기본 순서"] for x in out if x["key"] not in FIXED_KEYS)


def test_colder_region_puts_heating_before_cooling():
    out = order_lines(_lines(), _ctx(hdd_ratio_vs_jeonju=1.256, cdd_ratio_vs_jeonju=0.333))
    order = _order(out)
    assert order.index("envelope") < order.index("shading")
    env = next(x for x in out if x["key"] == "envelope" and x["target"] == "plan_added")
    assert "난방도일이 전주의 1.26배" in env["why"] and "이 지역: " in env["condition_text"]


def test_hotter_region_or_large_cooling_share_puts_shading_first():
    by_cdd = _order(order_lines(_lines(), _ctx(cdd_ratio_vs_jeonju=1.063, hdd_ratio_vs_jeonju=0.894)))
    by_share = _order(order_lines(_lines(), _ctx(cdd_ratio_vs_jeonju=0.618, elec_cooling_share=0.0795, hdd_ratio_vs_jeonju=0.765)))
    for order in (by_cdd, by_share):
        assert order.index("shading") < order.index("envelope")


def test_district_heating_region_lifts_district_control():
    out = order_lines(_lines(district=87.9), _ctx(hdd_ratio_vs_jeonju=1.207, district_heating_household_pct=87.9))
    movable = [k for k in _order(out) if k not in FIXED_KEYS]
    assert movable[0] == "district_heating_control"
    line = next(x for x in out if x["key"] == "district_heating_control")
    assert any("87.9%가 지역난방" in w for w in line["why"]) and line["priority"] == 20


def test_local_plan_and_evidence_rules():
    lines = _lines()
    out = order_lines(lines, _ctx(local_plan_tasks_by_group={"operation": 4}))
    op = next(x for x in out if x["key"] == "operation" and x["target"] == "plan_added")
    assert "지자체 계획 과제 4개" in op["why"]
    hrv = next(x for x in out if x["key"] == "heat_recovery_ventilation" and x["target"] == "plan_added")
    assert "국내 실측 근거 없음(국외 · 계산 위주)" in hrv["why"] and hrv["priority"] < 0


def test_cooling_share_reads_the_table_and_uses_district_median():
    assert cooling_share("26440") == 0.0795
    assert cooling_share("41110") is not None      # 수원: 구 값의 중앙값
    assert cooling_share("99999") is None           # unknown stays None, never 0
