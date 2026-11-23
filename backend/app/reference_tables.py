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


USE_INTENSITY_FILE = "use_intensity_2025.csv"
USE_INTENSITY_MIN_PARCELS = 30   # fewer parcels of that use in the region → the value of all READY regions


def use_intensity(region_code: str | None, use_class: str) -> dict[str, Any] | None:
    """Observed electricity intensity (kWh/m²·년) of a plan use (2026-11-23, 기준 문서 5.9): the region's own when it has at
    least USE_INTENSITY_MIN_PARCELS parcels of that use, else all READY regions. None for uses without a row (residential,
    officetel, knowledge industry, industrial, other keep the area's own intensity)."""
    rows = [r for r in _rows(USE_INTENSITY_FILE) if r["use_class"] == use_class]
    own = next((r for r in rows if region_code and r["region_code"] == str(region_code) and int(r["parcels"]) >= USE_INTENSITY_MIN_PARCELS), None)
    row = own or next((r for r in rows if r["region_code"] == "ALL"), None)
    if not row:
        return None
    return {"kwh_per_m2": float(row["kwh_per_m2"]), "scope": "REGION" if own else "READY_ALL", "parcels": int(row["parcels"]),
            "year": int(row["year"]), "register_uses": row["register_uses"].replace("+", " · ")}


# 기후 가이드 표의 지점 연결 중 같은 시 · 군(광역시는 시 안)인 것만. '같은 시도 · 같은 지역 구분 대표 지점'은 다른 도시라 쓰지 않음.
ASOS_MAPPINGS = ("지점 있음", "광역시 지점")


def asos_station(code: str | None) -> tuple[str, str] | None:
    """(ASOS 지점 번호, 지점 이름) of the region's own city (regional_climate_guide.csv, 기상청 평년값 지점 연결), or None.

    Only ASOS stations: 평년값 지점 번호 300 이상(방재 AWS 등)은 ASOS 일자료 API가 0행을 줌(2026-11-21 시험: 541 남양주 · 572 성남 ·
    571 화성 · 712 순천 · 860 대구 0행, 108 서울 · 184 제주 · 257 양산시 31행). A city with 일반구(41110 등) uses its own row, else
    the station most of its 구 rows name."""
    from collections import Counter
    if not code:
        return None
    code = str(code)
    row = _by_code("regional_climate_guide.csv", code)
    rows = [row] if row else [r for r in _rows("regional_climate_guide.csv")
                              if code.endswith("0") and r["sigungu_code"][:4] == code[:4] and r["sigungu_code"] != code]
    picks = [(r["station_id"], r["station_name"]) for r in rows
             if r["mapping"] in ASOS_MAPPINGS and r["station_id"].isdigit() and int(r["station_id"]) < 300]
    return Counter(picks).most_common(1)[0][0] if picks else None


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


# 감축률의 지역 차이(지역 보정 관문 G2, docs/records/2026-11-20-regional-adjustment-gates.md). 숫자는 그 기록 그대로
RATE_NOTE = ("감축률은 지역에 따라 크게 다르지 않다고 봅니다: 단열·창호 가스 절감률이 기후에 따라 달라지는 폭이 2.21 · 2.72%p로, "
             "보정할 기준(지표 범위 폭의 절반 3.75%p)에 못 미쳤습니다. 다만 근거 단지가 모두 중부2(13개 시군구)라 남부 · 제주는 확인하지 못했습니다")
# 전주 단지 공동주택 전기 중 냉방 몫(지역 기후 가이드 표 README, 추정)
COOLING_SHARE_NOTE = "냉방 수단의 효과는 냉방 에너지에 대한 %라 냉방이 적은 지역일수록 작게 나타납니다(전주 공동주택 전기 중 냉방 몫 약 6%, 추정)"
COOLING_GROUPS = ("cool_roof", "building_greening", "cooling_efficiency")   # 근거표의 냉방 쪽 묶음(도구 수단 아님)


def cooling_measures(cdd_ratio: float | None) -> dict[str, Any]:
    """냉방 쪽 수단 목록과 그 지역에서의 읽는 법. 수단의 쓰임은 서비스 수단 목록(차양)과 근거표 판단에서 가져온다(새 값 없음)."""
    from .reduction_measures import MEASURES, USE_LABEL
    shading = next(m for m in MEASURES if m["key"] == "shading")
    groups = {g["group"]: g for g in evidence_summary()["unlinked_groups"]}
    items = [{"label": shading["title"], "use": USE_LABEL[shading["use"]], "indicator": shading["indicator"]}]
    for gid in COOLING_GROUPS:
        g = groups.get(gid)
        if g:
            top = g["exclusion"][0]["value"]
            items.append({"label": g["label"], "use": "설비 사양(따로 추천 안 함)" if top == "따로 추천 안 함" else "범위 참고(근거표, 값으로 쓰지 않음)",
                          "indicator": None})
    if cdd_ratio is None:
        where = "이 지역은 냉방도일이 없어(기상 지점 연결 안 됨) 전주와 견주지 못합니다"
    elif cdd_ratio > 1:
        where = f"냉방도일이 전주의 {cdd_ratio:.2f}배로 냉방이 전주보다 더 필요한 지역입니다"
    else:
        where = f"냉방도일이 전주의 {cdd_ratio:.2f}배입니다"
    return {"items": items, "reading": f"{where}. {COOLING_SHARE_NOTE}"}


HEAT_STATS_SOURCE = "건물에너지사용량통계(국가승인통계 제408003호, 그린투게더) 2025 아파트"


def heat_stats(code: str | None) -> dict[str, Any] | None:
    """시군구 아파트 에너지 중 지역난방 열 비중(통계, TOE끼리 나눔). 구가 있는 시 코드는 그 시의 구를 더한다. 표에 없으면 None.

    지역난방 TOE가 통계에 없으면(화면 "-") 비중도 None — 0 %로 쓰지 않는다(2026-11-20)."""
    code = str(code or "")
    rows = [r for r in _rows("apartment_energy_stats_2025.csv") if r["sigungu_code"] == code]
    if not rows and code.endswith("0"):
        rows = [r for r in _rows("apartment_energy_stats_2025.csv") if r["sigungu_code"][:4] == code[:4] and r["sigungu_code"] != code]
    if not rows:
        return None
    total = sum(float(r["total_toe"]) for r in rows if r["total_toe"])
    heat_rows = [r for r in rows if r["district_heat_toe"]]
    heat = sum(float(r["district_heat_toe"]) for r in heat_rows) if heat_rows else None
    return {"year": int(rows[0]["year"]), "parts": [r["sigungu_name"] for r in rows] if len(rows) > 1 else None,
            "total_toe": round(total, 1) if total else None, "district_heat_toe": round(heat, 1) if heat is not None else None,
            "district_heat_share_pct": round(heat / total * 100, 1) if heat is not None and total else None, "source": HEAT_STATS_SOURCE}


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
    ref = _by_code("regional_climate_guide.csv", "52110") or {}
    return {"code": code, "name": zone_row["sigungu_name"], "design_zone": zone_row["design_zone"], "standard_zone": STANDARD_ZONE.get(zone_row["design_zone"]),
            "climate": climate, "plans": [p for p in (city_plans, sido_plans) if p],
            "reference": {"station": ref.get("station_name"), "sunshine_hours_year": _num(ref.get("sunshine_hours_year"))},
            "cooling": cooling_measures(climate["cdd_ratio"] if climate else None), "rate_note": RATE_NOTE,
            "heat_stats": heat_stats(code),
            "sources": {"zone": DESIGN_ZONE_SOURCE, "climate": CLIMATE_SOURCE, "plans": PLAN_SOURCE},
            "value_kinds": "지역 구분 = 고시, 기후 = 평년값, 배출 방향 = 추정 가이드(예측 아님), 과제 = 지자체 계획값(자체 평가)",
            "check": "정부 표준베이스라인의 남부 ÷ 중부2 차이(−11.9%)보다 이 가이드의 남부 중앙값(에너지 −4.3%)이 작아, 미리 정한 점검에서 '맞지 않음'이었습니다. 방향만 참고하세요."}
