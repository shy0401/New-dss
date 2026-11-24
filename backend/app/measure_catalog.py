"""감축 수단 묶음(근거표 ``수단_ID``)마다 지금 도구에서 쓰는 수준과 목표 수준 (2026-11-25, 실행 계획 v3 단계 A).

근거표의 묶음 32개를 빠짐없이 한 줄로 둔다. 수준은 "지금 이 도구가 그 묶음을 어떻게 쓰는가"이고, 값을 새로 만들지 않는다.
목표 수준은 계획(PC ``project/working/methods/reduction-measures-plan-v3-2026-11-25.md``)의 단계를 가리킬 뿐이며, 그 단계가
끝나기 전에는 계산에 영향이 없다. 지역마다 감축률을 바꾸지 않는다(2026-11-20 지역 보정 관문 G2).
"""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
from typing import Any

LEVEL_LABEL = {
    "VALUE": "값(지역 감축 제안 · 3D 계획안)",
    "VALUE_3D": "값(3D 계획안 사다리만, 지역 감축 제안은 지표)",
    "RANGE": "범위(추정, 따로 표시)",
    "INDICATOR": "지표(감축 제안 목록)",
    "TABLE_ONLY": "근거표에만(감축 제안 목록에 없음)",
    "EXCLUDED": "기본 방안에서 제외",
    "EMBODIED": "시공 단계(3D 내재탄소 참고 계산)",
    "OUT": "운영탄소 범위 밖",
}
LEVEL_ORDER = tuple(LEVEL_LABEL)

# 묶음 → (지금 수준, 목표 수준, 계획 단계, 메모). 지금 수준은 코드에서 확인한 것만(2026-11-25):
# 지붕 태양광 = 지역 감축 제안 · 3D 사다리의 값, 녹지 · 단열·창호 = 3D 사다리의 값(지역 감축 제안은 지표),
# 도구 수단 목록(reduction_measures.MEASURES)의 지표 = INDICATOR, 근거표 화면의 '도구 수단에 없는 묶음' = TABLE_ONLY.
GROUP_LEVELS: dict[str, tuple[str, str, str, str]] = {
    "rooftop_pv": ("VALUE", "VALUE", "E", "지붕 최대 · 인증 수준 · 실제 사례 수준 세 줄"),
    "greenery": ("VALUE_3D", "VALUE", "D", "상수 판정(단지 110곳 실측, 단위 확인) 뒤 지역 시뮬레이션에도 녹지 입력"),
    "envelope": ("VALUE_3D", "VALUE", "F", "지역 시뮬레이션에서는 가스 범위(구역 가스 원단위 × 연면적)"),
    "new_build_package": ("INDICATOR", "INDICATOR", "B", "추가성(2025-06-30 이후 법정 기준) 문장과 함께"),
    "passive_package": ("INDICATOR", "INDICATOR", "B", "근거 대부분 국외 실측"),
    "window": ("INDICATOR", "INDICATOR", "B", "기존 건물 창호 교체(도구 수단 window_retrofit)"),
    "insulation": ("INDICATOR", "INDICATOR", "B", "도구 수단 envelope(단열·창호 기준 강화)의 근거로 함께 보임"),
    "airtightness": ("TABLE_ONLY", "INDICATOR", "B", ""),
    "shading": ("INDICATOR", "RANGE", "F", "원문 대조(C) 뒤"),
    "heat_recovery_ventilation": ("INDICATOR", "INDICATOR", "B", ""),
    "lighting_appliance_elevator": ("INDICATOR", "RANGE", "F", "승강기 대수 비(K-apt) · 공용 전기 몫으로 곱할 양"),
    "bems_metering": ("INDICATOR", "INDICATOR", "B", "세대 표시장치(도구 수단 home_energy_display)"),
    "boiler_heating_control": ("INDICATOR", "RANGE", "F", "개별난방 가스 범위"),
    "operation": ("INDICATOR", "INDICATOR", "B", "입주 뒤 행동이라 계획 단계 밖(2026-11-20)"),
    "layout_form": ("TABLE_ONLY", "RANGE", "G", "원문 대조(C) · 우리 자료 판정(관문 G4) 뒤 3D 구조 범위"),
    "cool_roof": ("TABLE_ONLY", "RANGE", "F", "지붕 면적 × 냉방 몫"),
    "building_greening": ("TABLE_ONLY", "RANGE", "D", "옥상녹화: 지역별 냉난방 문헌값"),
    "facade_pv": ("TABLE_ONLY", "RANGE", "F", "3D 입면 면적 × 입면 1 m²당 연 발전량"),
    "heat_source_district": ("TABLE_ONLY", "INDICATOR", "B", "원문 대조(C) 필요"),
    "heat_source_choice": ("TABLE_ONLY", "INDICATOR", "B", ""),
    "cooling_efficiency": ("TABLE_ONLY", "INDICATOR", "B", ""),
    "district_cooling": ("TABLE_ONLY", "INDICATOR", "B", ""),
    "cooling_hvac": ("TABLE_ONLY", "INDICATOR", "B", ""),
    "ess_demand_response": ("TABLE_ONLY", "INDICATOR", "B", ""),
    "retrofit_package": ("TABLE_ONLY", "INDICATOR", "B", "기존 건물(구역 전체 목표)"),
    "heat_pump": ("EXCLUDED", "EXCLUDED", "-", "2026-11-11 전문가 자문으로 기본 방안 제외"),
    "solar_thermal_geothermal_fuelcell": ("TABLE_ONLY", "EXCLUDED", "-", "근거가 절감률이 아닌 비용 위주(추천 제외 행 다수)"),
    "frame_system": ("EMBODIED", "EMBODIED", "-", ""),
    "low_carbon_concrete": ("EMBODIED", "EMBODIED", "-", ""),
    "materials_other": ("EMBODIED", "EMBODIED", "-", ""),
    "construction_site": ("EMBODIED", "EMBODIED", "-", ""),
    "corporate_target": ("OUT", "OUT", "-", "기업 목표 · 조달"),
}


def _checked(row: dict[str, str]) -> bool:
    text = (row.get("원문_대조") or "").strip()
    return bool(text) and text != "안 함"


@lru_cache(maxsize=1)
def group_status() -> tuple[dict[str, Any], ...]:
    """근거표 묶음마다 수준 · 근거 상태 · 도구 수단 · 지자체 과제 수. 근거표에 있는데 GROUP_LEVELS에 없는 묶음은 TABLE_ONLY로 둔다."""
    from .reference_tables import GROUP_LABEL, _rows
    rows = _rows("reduction_evidence.csv")
    plans = _rows("local_plans_building.csv")
    by_group: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        for gid in [k for k in (r["수단_ID"] or "").split(";") if k]:
            by_group.setdefault(gid, []).append(r)
    plan_tasks = Counter(k for p in plans for k in (p["수단_ID"] or "").split(";") if k)
    out = []
    for gid, rs in by_group.items():
        level, target, step, note = GROUP_LEVELS.get(gid, ("TABLE_ONLY", "TABLE_ONLY", "-", "수준 미정"))
        tools = sorted({k for r in rs for k in (r["도구_수단"] or "").split(";") if k})
        out.append({"group": gid, "label": GROUP_LABEL.get(gid, gid), "level": level, "level_label": LEVEL_LABEL[level],
                    "target": target, "target_label": LEVEL_LABEL[target], "plan_step": step, "note": note or None,
                    "evidence": {"rows": len(rs), "domestic_measured": sum(r["근거_등급"] == "실측_국내" for r in rs),
                                 "checked": sum(_checked(r) for r in rs), "same_condition": sum(r["같은_조건_비교"] == "예" for r in rs),
                                 "excluded": sum(r["추천_제외"] == "예" for r in rs)},
                    "tool_measures": tools, "local_plan_tasks": plan_tasks.get(gid, 0)})
    out.sort(key=lambda g: (LEVEL_ORDER.index(g["level"]), -g["evidence"]["rows"]))
    return tuple(out)


def cooling_share(code: str | None) -> float | None:
    """세대 전기 중 냉방 몫(월 분해 중앙값, ``regional_conditions_sigungu.csv`` 23개 시군구). 시 코드는 그 시 구 값의 중앙값, 없으면 None."""
    from statistics import median
    from .reference_tables import _rows
    code = str(code or "")
    rows = [r for r in _rows("regional_conditions_sigungu.csv") if r["sigungu_code"] == code]
    if not rows and code.endswith("0"):
        rows = [r for r in _rows("regional_conditions_sigungu.csv") if r["sigungu_code"][:4] == code[:4] and r["sigungu_code"] != code]
    vals = [float(r["elec_share_cool_median"]) for r in rows if r.get("elec_share_cool_median")]
    return round(median(vals), 4) if vals else None


def region_context(guide: dict[str, Any] | None) -> dict[str, Any] | None:
    """감축 수단을 지역에 맞춰 고를 때 쓰는 지역 값(지역 가이드에서 그대로 읽음, 새 값 없음). 단계 B의 순서 규칙이 이 값을 쓴다."""
    if not guide:
        return None
    climate = guide.get("climate") or {}
    kinds = (guide.get("heating") or {}).get("kinds") or []
    district = next((k.get("household_share_pct") for k in kinds if k.get("kind") == "지역난방"), None)
    solar = guide.get("solar") or {}
    pv = solar.get("pv_yield") if isinstance(solar.get("pv_yield"), dict) else solar
    plan_groups: Counter[str] = Counter()
    for p in guide.get("plans") or []:
        for g in p.get("groups") or []:
            plan_groups[g["group"]] += g["tasks"]
    return {"code": guide.get("code"), "name": guide.get("name"), "design_zone": guide.get("design_zone"),
            "hdd_ratio_vs_jeonju": climate.get("hdd_ratio"), "cdd_ratio_vs_jeonju": climate.get("cdd_ratio"),
            "elec_cooling_share": cooling_share(guide.get("code")),
            "district_heating_household_pct": district,
            "district_heat_stats_pct": (guide.get("heat_stats") or {}).get("district_heat_share_pct"),
            "pv_kwh_per_kw": (pv or {}).get("kwh_per_kw"),
            "local_plan_tasks_by_group": dict(plan_groups.most_common()),
            "note": "지역 가이드 값(평년 기후 비 · 난방 구성 · 일사 · 지자체 과제)을 그대로 모은 것. 감축률은 지역마다 바꾸지 않음"}


# 단계 B 순서 규칙(기록 docs/records/2026-11-25-measure-region-order.md, 결과 보기 전에 정함). 감축률은 그대로, 순서 · 이유만
COOLING_KEYS = frozenset({"shading"})
HEATING_KEYS = frozenset({"envelope", "passive_package", "window_retrofit", "heat_recovery_ventilation", "condensing_boiler",
                          "district_heating_control"})
FIXED_KEYS = frozenset({"rooftop_pv", "greenery"})   # 값 · 상쇄 줄: 순서 매김에서 빼고 지금 자리 그대로
CDD_RATIO_OVER = 1.0          # R1: 전주보다 냉방도일이 많음
COOLING_SHARE_MIN = 0.07      # R1: 세대 전기의 냉방 몫(23개 시군구 중앙 5.4%)
HDD_RATIO_MIN = 1.1           # R2: 전주보다 난방도일 10% 이상
DISTRICT_HEATING_MIN = 20.0   # R3: 지역난방 세대 비율(%)


def _line_score(line: dict[str, Any], ctx: dict[str, Any] | None, domestic: dict[str, int]) -> tuple[int, list[str]]:
    if not ctx:
        return 0, ["지역 값을 알 수 없어 기본 순서"]
    key, score, why = line["key"], 0, []
    cdd, share, hdd = ctx.get("cdd_ratio_vs_jeonju"), ctx.get("elec_cooling_share"), ctx.get("hdd_ratio_vs_jeonju")
    dh = ctx.get("district_heating_household_pct")
    if key in COOLING_KEYS:
        if cdd is not None and cdd > CDD_RATIO_OVER:
            score += 10; why.append(f"냉방도일이 전주의 {cdd:.2f}배")
        elif share is not None and share >= COOLING_SHARE_MIN:
            score += 10; why.append(f"세대 전기의 {share * 100:.1f}%가 냉방(23개 시군구 분해, 중앙 5.4%)")
    if key in HEATING_KEYS and hdd is not None and hdd >= HDD_RATIO_MIN:
        score += 10; why.append(f"난방도일이 전주의 {hdd:.2f}배")
    if key == "district_heating_control" and dh is not None and dh >= DISTRICT_HEATING_MIN:
        score += 10; why.append(f"이 지역 공동주택 세대의 {dh:.1f}%가 지역난방")
    if key == "condensing_boiler" and dh is not None and dh < DISTRICT_HEATING_MIN:
        score += 5; why.append(f"개별난방 위주(지역난방 {dh:.1f}%)")
    tasks = sum((ctx.get("local_plan_tasks_by_group") or {}).get(g, 0) for g in line.get("evidence_groups") or [])
    if tasks:
        score += 3; why.append(f"이 지역 지자체 계획 과제 {tasks}개")
    groups = line.get("evidence_groups") or []
    if groups and sum(domestic.get(g, 0) for g in groups) == 0:
        score -= 5; why.append("국내 실측 근거 없음(국외 · 계산 위주)")
    return score, why


def order_lines(lines: list[dict[str, Any]], ctx: dict[str, Any] | None) -> list[dict[str, Any]]:
    """목표 기준마다 지표 줄을 지역 규칙 점수로 다시 놓고(같은 점수는 지금 순서), 줄에 ``priority`` · ``why``를 붙인다.

    값 · 상쇄 줄(지붕 태양광 · 녹지)은 순서 매김에서 빼고 지금 자리 그대로. 줄의 숫자는 건드리지 않는다."""
    domestic = {g["group"]: g["evidence"]["domestic_measured"] for g in group_status()}
    out: list[dict[str, Any]] = []
    targets = list(dict.fromkeys(x["target"] for x in lines))
    for t in targets:
        block = [x for x in lines if x["target"] == t]
        movable = [(i, x) for i, x in enumerate(block) if x["key"] not in FIXED_KEYS]
        scored = []
        for i, x in movable:
            s, why = _line_score(x, ctx, domestic)
            condition = x.get("condition_text")
            if s and why:   # 화면이 이미 그리는 조건 문장 칸에 이유를 붙임(화면 수정 없이)
                condition = (f"{condition} / " if condition else "") + "이 지역: " + ", ".join(why)
            scored.append((-s, i, {**x, "priority": s, "why": why, "condition_text": condition}))
        ranked = [x for _, _, x in sorted(scored, key=lambda z: (z[0], z[1]))]
        slots = iter(ranked)
        out += [next(slots) if x["key"] not in FIXED_KEYS else {**x, "priority": None, "why": []} for x in block]
    return out


def measure_level(key: str, quantified: bool) -> str:
    """감축 제안 한 줄(도구 수단 ``key``)의 수준: 이 계산이 값을 낸 줄만 VALUE, 나머지는 지표."""
    return "VALUE" if quantified else "INDICATOR"
