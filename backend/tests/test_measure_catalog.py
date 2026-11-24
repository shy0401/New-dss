"""계획 v3 단계 A(2026-11-25): 근거표 묶음 32개의 수준 표 · 감축 제안 줄의 수준 · 지역 맥락. 값은 바뀌지 않는다."""
from app.area import target_bases
from app.measure_catalog import GROUP_LEVELS, LEVEL_LABEL, group_status, region_context
from app.reduction_measures import MEASURES, applicable_measures, catalog
from app.reference_tables import _rows
from tests.test_u4_targets import _result

LINKED_LEVELS = {"VALUE", "VALUE_3D", "INDICATOR"}


def test_every_evidence_group_has_a_known_level_and_no_stale_entry():
    groups = {k for r in _rows("reduction_evidence.csv") for k in (r["수단_ID"] or "").split(";") if k}
    status = {g["group"]: g for g in group_status()}
    assert set(status) == groups == set(GROUP_LEVELS)
    for g in status.values():
        assert g["level"] in LEVEL_LABEL and g["target"] in LEVEL_LABEL and g["evidence"]["rows"] > 0
        assert g["evidence"]["checked"] <= g["evidence"]["rows"] and g["evidence"]["domestic_measured"] <= g["evidence"]["rows"]


def test_level_agrees_with_the_evidence_table_links():
    for g in group_status():
        if g["level"] == "TABLE_ONLY":
            assert not g["tool_measures"], g["group"]          # shown only in the evidence table
        if g["level"] in LINKED_LEVELS:
            assert g["tool_measures"], g["group"]              # a tool measure carries this group's evidence
    tool_keys = {m["key"] for m in MEASURES}
    for g in group_status():
        if g["level"] in LINKED_LEVELS:
            assert set(g["tool_measures"]) & tool_keys, g["group"]


def test_lines_carry_their_level_and_groups_without_changing_values():
    r = _result(plan_roof_m2=2500.0, basis="footprint")
    links = applicable_measures(target_bases(r), 50000.0, district_share_pct=None, cooling_reading=None)
    for x in links:
        assert x["level"] == ("VALUE" if x["value_status"] == "QUANTIFIED" else "INDICATOR")
        assert isinstance(x["evidence_groups"], list)
    pv = next(x for x in links if x["key"] == "rooftop_pv")
    assert pv["level"] == "VALUE" and "rooftop_pv" in pv["evidence_groups"]


def test_catalog_lists_all_groups_with_labels():
    c = catalog()
    assert len(c["groups"]) == len(GROUP_LEVELS) and c["level_labels"] == LEVEL_LABEL
    assert "checked_rows" in c["measures"][0]["evidence_table"]


def test_region_context_only_reads_the_region_guide():
    guide = {"code": "26440", "name": "부산 강서구", "design_zone": "남부",
             "climate": {"hdd_ratio": 0.8, "cdd_ratio": 1.1},
             "heating": {"kinds": [{"kind": "지역난방", "household_share_pct": 42.0}, {"kind": "개별난방", "household_share_pct": 58.0}]},
             "heat_stats": {"district_heat_share_pct": 30.5}, "solar": {"kwh_per_kw": 1294.0},
             "plans": [{"groups": [{"group": "rooftop_pv", "tasks": 3}, {"group": "operation", "tasks": 1}]},
                       {"groups": [{"group": "rooftop_pv", "tasks": 2}]}]}
    ctx = region_context(guide)
    assert ctx["cdd_ratio_vs_jeonju"] == 1.1 and ctx["district_heating_household_pct"] == 42.0
    assert ctx["pv_kwh_per_kw"] == 1294.0 and ctx["local_plan_tasks_by_group"] == {"rooftop_pv": 5, "operation": 1}
    assert region_context(None) is None
    empty = region_context({"code": "x"})
    assert empty["hdd_ratio_vs_jeonju"] is None and empty["district_heating_household_pct"] is None   # unknown stays None, never 0
