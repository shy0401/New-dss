"""참조 표(backend/reference) 읽기: 감축 근거표 요약 · 설계기준 지역 구분 · 지역 기후 가이드 · 지자체 계획 과제 (2026-11-20).

표는 손정리 · 계산 결과이고 원본 경로 · 해시는 ``backend/reference/README.md``와 기준 문서 2절에 있다. 여기서는 값을 고치거나
새로 계산하지 않고 그대로 읽어 화면 · 계산이 쓰는 모양으로만 묶는다. 빈칸은 None(0으로 채우지 않음).
"""
from __future__ import annotations

import csv
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

REF = Path(__file__).resolve().parent.parent / "reference"

# 근거 등급(근거표 README) → 화면 이름. 순서가 화면 순서다
GRADE_LABEL = {"실측_국내": "국내 실측", "실측_국외_조건맞음": "국외 실측(조건 맞음)", "문헌_계산": "계산", "실측_국외_참고": "국외 실측(참고)",
               "가정": "가정", "해당_없음": "효과 값 아님"}
# 근거표 수단 묶음(수단_ID) → 이름. 조사표 분류 이름(방법 문서 2절)과 보강 묶음
GROUP_LABEL = {
    "layout_form": "배치·형태·향·밀도·세대 규모", "new_build_package": "신축 통합 기준(ZEB·인증·기준 강화)", "passive_package": "패시브 패키지",
    "insulation": "단열 강화", "window": "고성능 창호·유리", "airtightness": "기밀·열교 차단", "shading": "차양·일사 조절", "envelope": "단열·창호 기준(짝 비교)",
    "heat_source_district": "지역난방·열병합", "heat_pump": "히트펌프·난방 전기화", "solar_thermal_geothermal_fuelcell": "태양열·지열·연료전지",
    "rooftop_pv": "태양광", "retrofit_package": "리모델링 통합", "heat_recovery_ventilation": "열회수 환기", "boiler_heating_control": "보일러·난방 제어·배관",
    "lighting_appliance_elevator": "조명·가전·승강기·공용부", "bems_metering": "BEMS·HEMS·계량·자동제어", "cooling_hvac": "냉방·공조",
    "ess_demand_response": "ESS·수요관리", "operation": "운영·행동", "frame_system": "구조 방식", "low_carbon_concrete": "저탄소 콘크리트·시멘트",
    "materials_other": "철강·기타 자재·재활용", "construction_site": "시공 현장", "corporate_target": "기업 목표·조달", "greenery": "녹지·조경 흡수",
    "cool_roof": "쿨루프(고반사 지붕)", "building_greening": "옥상·벽면 녹화", "cooling_efficiency": "냉방기 효율", "district_cooling": "지역냉방",
    "heat_source_choice": "열원 선택 비교(개별·중앙·지역)",
}
# 표준지표(국토교통부 2024)는 중부 · 남부 값만 있다(출처 기사). 설계기준 지역 구분 → 표준지표 지역. 제주는 표준지표 지역이 없어 None(확인 필요)
STANDARD_ZONE = {"중부1": "중부", "중부2": "중부", "남부": "남부"}
DESIGN_ZONE_SOURCE = "국토교통부고시 제2026-360호(건축물의 에너지절약설계기준) 별표 1 비고"
CLIMATE_SOURCE = "기상청 기후평년값 1991~2020(일별), 이 도구 계산"
PLAN_SOURCE = "지자체 탄소중립·녹색성장 기본계획 건물 부문(원문 대조)"


@lru_cache(maxsize=None)
def _rows(name: str) -> tuple[dict[str, str], ...]:
    with (REF / name).open(encoding="utf-8-sig") as f:
        return tuple(csv.DictReader(f))


def _num(v: str | None) -> float | None:
    return float(v) if v not in (None, "") else None


def _by_code(name: str, code: str | None) -> dict[str, str] | None:
    """시군구 코드로 한 줄. 표에는 구가 있는 시도 시 코드(41110 등)가 함께 있어 정확히 맞는 코드만 쓴다(짐작하지 않음)."""
    if not code:
        return None
    return next((r for r in _rows(name) if r["sigungu_code"] == str(code)), None)


def design_zone(code: str | None) -> str | None:
    """시군구 → 설계기준 지역 구분(중부1 · 중부2 · 남부 · 제주). 표에 없는 코드는 None."""
    r = _by_code("design_zone_sigungu.csv", code)
    return r["design_zone"] if r else None


def standard_zone(code: str | None) -> str | None:
    """표준지표 지역(중부 · 남부). 지역 구분이 없거나 제주면 None."""
    return STANDARD_ZONE.get(design_zone(code) or "")


# ---- (가) 감축 근거표 요약 ----------------------------------------------------------------

def _summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    grades = Counter(r["근거_등급"] for r in rows)
    exc = Counter(r["추천_제외"] for r in rows)
    reasons = Counter(r["제외_까닭"] for r in rows if r["제외_까닭"])
    return {"rows": len(rows), "sources": len({r["출처_주소"].strip() for r in rows if r["출처_주소"].strip()}),
            "grades": [{"grade": g, "label": GRADE_LABEL[g], "rows": grades[g]} for g in GRADE_LABEL if grades.get(g)],
            "exclusion": [{"value": k, "rows": n} for k, n in exc.most_common()],
            "reasons": [{"reason": k, "rows": n} for k, n in reasons.most_common()]}


@lru_cache(maxsize=1)
def evidence_summary() -> dict[str, Any]:
    """도구 수단(``reduction_measures`` 키)마다 근거표 행 요약, 그리고 도구 수단에 연결되지 않은 근거 묶음 목록.

    행 수는 독립된 근거의 수가 아니다(같은 출처 · 수단이 여러 행). 그래서 출처 수(출처 주소 기준)를 함께 낸다.
    """
    rows = _rows("reduction_evidence.csv")
    by_tool: dict[str, list[dict[str, str]]] = {}
    unlinked: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        keys = [k for k in r["도구_수단"].split(";") if k]
        for k in keys:
            by_tool.setdefault(k, []).append(r)
        if not keys:
            unlinked.setdefault(r["수단_ID"], []).append(r)
    groups = []
    for mid, rs in unlinked.items():
        s = _summary(rs)
        layer = Counter(r["층"] for r in rs).most_common(1)[0][0]
        groups.append({"group": mid, "label": GROUP_LABEL.get(mid, mid), "layer": layer, **s})
    order = {"아니오": 0, "따로 추천 안 함": 1, "예": 2, "해당 없음": 3}
    groups.sort(key=lambda g: (order.get(g["exclusion"][0]["value"], 9), -g["rows"]))
    return {"rows": len(rows), "by_measure": {k: _summary(v) for k, v in by_tool.items()}, "unlinked_groups": groups,
            "grade_labels": GRADE_LABEL,
            "note": "행 수는 독립된 근거 수가 아닙니다(같은 출처가 여러 행). 출처 수는 출처 주소가 다른 것만 셉니다. 근거표는 감축 수단을 고르는 판단 근거이고, 행의 값을 계획안에 곱하지 않습니다."}


# ---- (나) 지역 기후 · 계획 가이드 ------------------------------------------------------------

def _plans(code: str) -> list[dict[str, str]]:
    return [r for r in _rows("local_plans_building.csv") if r["지역_코드"] == code]


def _plan_block(code: str, rows: list[dict[str, str]]) -> dict[str, Any] | None:
    if not rows:
        return None
    groups = Counter(r["수단_ID"].split(";")[0] for r in rows)
    return {"code": code, "region": rows[0]["지역"], "plan": rows[0]["계획_이름"], "tasks": len(rows),
            "groups": [{"group": g, "label": GROUP_LABEL.get(g, "그 밖"), "tasks": n} for g, n in groups.most_common()],
            "task_names": [r["과제_이름"] for r in rows]}


def region_guide(code: str | None) -> dict[str, Any] | None:
    """한 시군구의 지역 구분 · 평년 기후(전주 대비) · 기준 배출 방향 가이드(추정) · 지자체 계획 건물 과제. 표에 없으면 None."""
    code = str(code or "")
    zone_row = _by_code("design_zone_sigungu.csv", code)
    if zone_row is None:
        return None
    c = _by_code("regional_climate_guide.csv", code) or {}
    sido_plans = _plan_block(code[:2], _plans(code[:2]))
    city_plans = _plan_block(code, _plans(code))
    climate = None
    if c.get("mapping"):
        climate = {"station": c["station_name"], "mapping": c["mapping"],
                   "summer_mean_c": _num(c["summer_mean_c"]), "winter_mean_c": _num(c["winter_mean_c"]),
                   "hdd_ratio": _num(c["hdd_ratio_vs_jeonju"]), "cdd_ratio": _num(c["cdd_ratio_vs_jeonju"]),
                   "sunshine_hours_year": _num(c["sunshine_hours_year"]),
                   "guide_emission_change_pct": _num(c["guide_emission_change_pct"]),
                   "guide_electricity_change_pct": _num(c["guide_electricity_change_pct"]),
                   "guide_gas_change_pct": _num(c["guide_gas_change_pct"]),
                   "within_our_data": c.get("within_our_data_hdd_range") == "예"}
    return {"code": code, "name": zone_row["sigungu_name"], "design_zone": zone_row["design_zone"], "standard_zone": STANDARD_ZONE.get(zone_row["design_zone"]),
            "climate": climate, "plans": [p for p in (city_plans, sido_plans) if p],
            "sources": {"zone": DESIGN_ZONE_SOURCE, "climate": CLIMATE_SOURCE, "plans": PLAN_SOURCE},
            "value_kinds": "지역 구분 = 고시, 기후 = 평년값, 배출 방향 = 추정 가이드(예측 아님), 과제 = 지자체 계획값(자체 평가)",
            "check": "정부 표준베이스라인의 남부 ÷ 중부2 차이(−11.9%)보다 이 가이드의 남부 중앙값(에너지 −4.3%)이 작아, 미리 정한 점검에서 '맞지 않음'이었습니다. 방향만 참고하세요."}
