"""A1: survey sheet '근거 행' (543 rows) -> evidence table CSV, by the rules fixed in
scripts/reduction_evidence/rules/reduction-evidence-table-2026-11-20.md (sections 1-6). Values are copied, never edited.

Usage: python build_evidence_table.py   (reads work/근거_행.csv, optional source_checks.csv; writes evidence_table.csv, evidence_summary.json)
"""
import csv
import json
import re
import statistics
from collections import Counter
from pathlib import Path

import sys as _out
_out.stdout.reconfigure(encoding="utf-8")   # Korean and − in the printed summary
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _paths import data  # noqa: E402

HERE = Path(__file__).parent
PLAN, PLAN_ENV, EQUIP, BEHAV, EMBODIED, NOT_MEASURE = "계획", "계획(외피 기준의 구성 요소)", "설비", "행동 · 교체", "자재 · 시공(내재탄소)", "수단 아님"
CLASS = {   # 분류 -> (수단_ID, 층, 상위_수단, 도구_수단)
    "배치·형태·향·밀도·세대 규모": ("layout_form", PLAN, "", ""),
    "신축 통합 패키지(ZEB·인증·기준 강화)": ("new_build_package", PLAN, "", "new_build_package"),
    "패시브 패키지": ("passive_package", PLAN, "", "passive_package"),
    "단열 강화": ("insulation", PLAN_ENV, "envelope", "envelope"),
    "고성능 창호·유리": ("window", PLAN_ENV, "envelope", "envelope;window_retrofit"),
    "기밀·열교 차단": ("airtightness", PLAN_ENV, "envelope", ""),
    "차양·일사 조절": ("shading", PLAN_ENV, "envelope", "shading"),
    "지역난방·열병합": ("heat_source_district", "계획(열원)", "", ""),
    "히트펌프·난방 전기화": ("heat_pump", "계획(열원)", "", ""),
    "태양열·지열·연료전지": ("solar_thermal_geothermal_fuelcell", "계획(열원 · 재생)", "", ""),
    "태양광": ("rooftop_pv", PLAN, "", "rooftop_pv"),
    "리모델링 통합": ("retrofit_package", "계획(기존 건물을 남기는 안에서만)", "", ""),
    "열회수 환기": ("heat_recovery_ventilation", EQUIP, "new_build_package", "heat_recovery_ventilation"),
    "보일러·난방 제어·배관": ("boiler_heating_control", EQUIP, "new_build_package", "condensing_boiler;district_heating_control"),
    "조명·가전·승강기·공용부": ("lighting_appliance_elevator", EQUIP, "new_build_package", "common_lighting;elevator_regeneration"),
    "BEMS·HEMS·계량·자동제어": ("bems_metering", EQUIP, "new_build_package", "home_energy_display"),
    "냉방·공조": ("cooling_hvac", EQUIP, "new_build_package", ""),
    "ESS·수요관리": ("ess_demand_response", EQUIP, "new_build_package", ""),
    "운영·행동": ("operation", BEHAV, "", "operation"),
    "구조 방식": ("frame_system", EMBODIED, "", "frame_system;modular"),
    "저탄소 콘크리트·시멘트": ("low_carbon_concrete", EMBODIED, "", "low_carbon_concrete"),
    "철강·기타 자재·재활용": ("materials_other", EMBODIED, "", ""),
    "시공 현장": ("construction_site", EMBODIED, "", ""),
    "기업 목표·조달": ("corporate_target", NOT_MEASURE, "", ""),
}
USE = {"난방": "난방 열", "가스": "가스", "냉방": "냉방", "전기": "전기", "총에너지": "총에너지", "1차에너지": "1차에너지", "운영탄소": "운영탄소",
       "내재탄소": "내재탄소", "자립률·생산": "발전량 · 자립률", "비용": "비용(절감률 아님)", "기타": "기타"}
ZONE = re.compile(r"중부\s?[12]|중부|남부|제주")
PLACE = re.compile(r"서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|수원|성남|고양|용인|전주|청주|천안|창원|김해|춘천|원주|송도|화성|동탄|판교|노원")
HEAT = re.compile(r"개별난방|지역난방|중앙난방")
LIGHT_EQUIP = re.compile(r"조명|LED|승강기|엘리베이터|공용|주차")


def num(v):
    return float(v) if v not in ("", None) else None


rows = list(csv.DictReader(open(data("evidence_table") / "work" / "근거_행.csv", encoding="utf-8", newline="")))
checks = {}
if (HERE / "source_checks.csv").exists():
    checks = {r["번호"]: r for r in csv.DictReader(open(HERE / "source_checks.csv", encoding="utf-8-sig", newline=""))}


def tool_indicator(r):
    measured, value = r["근거군"] == "실측", num(r["대표값(%)"]) is not None
    if not (measured and value):
        return ""
    if r["분류"] == "운영·행동" and r["지표군"] == "전기":
        return "사다리 2단계 운영 −4.8%"
    if r["분류"].startswith("신축 통합") and r["지표군"] == "총·1차에너지·운영탄소":
        return "따로 본 값 신축 통합 −11.3%(지역 시뮬레이션 신축)"
    if r["분류"] == "열회수 환기" and r["국가"] == "한국":
        return "따로 본 값 열회수 환기 −3.5%"
    if r["분류"].startswith("BEMS") and r["지표군"] == "전기" and r["국가"] == "한국":
        return "따로 본 값 세대 표시장치 −11.7%"
    return ""


out = []
for r in rows:
    text = f'{r["전략·비교"]} {r["효과(원문)"]}'
    measure, layer, parent, tool = CLASS[r["분류"]]
    notes = []
    if r["분류"] == "조명·가전·승강기·공용부" and "가전" in text and not LIGHT_EQUIP.search(text):
        layer, parent = BEHAV, ""
    use = USE[r["지표"]]
    if r["분류"] == "조명·가전·승강기·공용부" and r["지표"] == "전기":
        use = "전기(해당 설비)"
    korea, group = r["국가"] == "한국", r["근거군"]
    device = (r["분류"] in ("태양광", "히트펌프·난방 전기화", "조명·가전·승강기·공용부")
              or (r["분류"] == "보일러·난방 제어·배관" and "보일러" in text))
    if r["지표군"] == "비용" or layer == NOT_MEASURE:
        grade = "해당_없음"
    elif group == "실측":
        grade = "실측_국내" if korea else ("실측_국외_조건맞음" if device else "실측_국외_참고")
    elif group == "설계·계산" and korea:
        grade = "문헌_계산"
    else:
        grade = "가정"
    if grade == "실측_국외_참고":
        notes.append("국외 실측: 공동주택 · 난방 방식 · 난방도일 조건 미확인")
    if r["분류"] in ("보일러·난방 제어·배관", "조명·가전·승강기·공용부", "태양열·지열·연료전지") and not re.search(r"보일러|조명|LED|승강기|엘리베이터|가전|지열|태양열|연료전지|배관|제어", text):
        notes.append("분류 안 세부 수단 확인 필요")
    if layer == BEHAV:
        excl, why = "예", "계획 단계 밖(입주 뒤 행동 · 교체)"
    elif r["분류"] == "히트펌프·난방 전기화":
        excl, why = "예", "적용이 거의 불가능(면담: 실제 COP가 3.0에 못 미침, 초기 비용)"
    elif r["분류"] == "태양열·지열·연료전지" and "지열" in text:
        excl, why = "예", "적용이 거의 불가능(면담: 공사비 약 100억)"
    elif layer == EQUIP:
        excl, why = "따로 추천 안 함", "설비 사양(단지 시공 세부). 상위 수단의 구성 요소로만"
    elif layer == EMBODIED:
        excl, why = "해당 없음", "운영 감축 추천의 대상이 아님(시공 단계 참고 계산)"
    elif layer == NOT_MEASURE:
        excl, why = "해당 없음", "수단이 아님"
    else:
        excl, why = "아니오", ""
    indicator = tool_indicator(r)
    if indicator and excl != "아니오":
        notes.append("도구 사다리 · 따로 본 값에 쓰이는 행(사용자 확인 대기)")
    check = checks.get(r["번호"], {})
    # v1.1 (2026-11-20, after the source check): a row the source shows to be calculated is not graded as measured.
    if check.get("실측_여부") == "계산" and grade.startswith("실측"):
        grade = "문헌_계산" if korea else "가정"
        notes.append("원문 대조로 등급 바꿈(조사표의 근거 유형은 실측)")
    if check.get("비고"):
        notes.append(check["비고"])
    zones, places = sorted(set(z.replace(" ", "") for z in ZONE.findall(text))), sorted(set(PLACE.findall(text)))
    heats = sorted(set(HEAT.findall(text)))
    out.append({
        "번호": r["번호"], "조사표": r["조사표"], "분류": r["분류"], "수단_ID": measure, "층": layer, "상위_수단": parent, "도구_수단": tool,
        "전략_비교": r["전략·비교"], "주체": r["주체(기업·기관)"], "줄이는_용도": use,
        "효과_낮은값_pct": r["효과 낮은값(%)"], "효과_높은값_pct": r["효과 높은값(%)"], "대표값_pct": r["대표값(%)"],
        "근거_등급": grade, "근거_유형": r["근거 유형"], "같은_조건_비교": r["같은 조건 비교"], "검증": r["검증"],
        "국가": r["국가"], "지역": ";".join(zones + places), "난방_방식": ";".join(heats),
        "효과_원문": r["효과(원문)"], "출처_주소": r["출처"], "출처_키": r["출처 키"],
        "추천_제외": excl, "제외_까닭": why, "도구_지표_행": indicator,
        "원문_대조": check.get("원문_대조", "안 함"), "비고": " / ".join(notes),
    })

with open(data("evidence_table") / "evidence_table.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0]))
    w.writeheader()
    w.writerows(out)


def med(sel):
    v = [float(r["대표값_pct"]) for r in sel if r["대표값_pct"] != ""]
    return {"n": len(sel), "n_value": len(v), "median": round(statistics.median(v), 2) if v else None,
            "min": min(v) if v else None, "max": max(v) if v else None}


by_measure = {}
for m in sorted({r["수단_ID"] for r in out}):
    sel = [r for r in out if r["수단_ID"] == m]
    by_measure[m] = {"층": Counter(r["층"] for r in sel).most_common(1)[0][0], "rows": len(sel),
                     "grades": dict(Counter(r["근거_등급"] for r in sel)),
                     "실측_국내_by_use": {u: med([r for r in sel if r["근거_등급"] == "실측_국내" and r["줄이는_용도"] == u])
                                      for u in sorted({r["줄이는_용도"] for r in sel if r["근거_등급"] == "실측_국내"})},
                     "문헌_계산_by_use": {u: med([r for r in sel if r["근거_등급"] == "문헌_계산" and r["줄이는_용도"] == u])
                                      for u in sorted({r["줄이는_용도"] for r in sel if r["근거_등급"] == "문헌_계산"})}}
summary = {
    "rows": len(out), "grade": dict(Counter(r["근거_등급"] for r in out)), "layer": dict(Counter(r["층"] for r in out)),
    "exclude": dict(Counter(r["추천_제외"] for r in out)), "exclude_reason": dict(Counter(r["제외_까닭"] for r in out if r["제외_까닭"])),
    "with_region": sum(1 for r in out if r["지역"]), "with_zone": sum(1 for r in out if re.search("중부|남부|제주", r["지역"])),
    "with_heating": sum(1 for r in out if r["난방_방식"]), "value_null": sum(1 for r in out if r["대표값_pct"] == ""),
    "source_empty": sum(1 for r in out if not r["출처_주소"].strip()),
    "tool_indicator_rows": {k: med([r for r in out if r["도구_지표_행"] == k]) for k in sorted({r["도구_지표_행"] for r in out if r["도구_지표_행"]})},
    "source_check": dict(Counter(r["원문_대조"] for r in out if r["도구_지표_행"])),
    "notes": dict(Counter(n for r in out for n in r["비고"].split(" / ") if n).most_common(8)),
    "by_measure": by_measure,
}
(data("evidence_table") / "evidence_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps({k: v for k, v in summary.items() if k != "by_measure"}, ensure_ascii=False, indent=1))
for m, v in by_measure.items():
    print(m, v["층"], v["rows"], v["grades"])
