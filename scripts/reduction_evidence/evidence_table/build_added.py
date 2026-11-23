"""Rows added to the evidence table after the survey sheet (A1): UK NEED 2026 tables, this project's own measured comparisons
(pair comparison rerun, certified vs non-certified complexes) and the literature rows found for A8 (rows_*.csv, when present).

Writes evidence_added.csv here and ../a1/evidence_table_all.csv (survey 543 rows + added rows, extra column `쓰임`).
Rules: scripts/reduction_evidence/rules/reduction-evidence-table-2026-11-20.md (sections 2-5 and 8). Usage: python build_added.py
"""
import csv
import json
from collections import Counter
from pathlib import Path

import sys as _out
_out.stdout.reconfigure(encoding="utf-8")   # Korean and − in the printed summary
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _paths import data  # noqa: E402

HERE = Path(__file__).parent
ROOT = HERE.parent
NEED = data("evidence_table") / "need"   # UK NEED 2026 table exports (data, outside Git)
COLUMNS = ["번호", "조사표", "분류", "수단_ID", "층", "상위_수단", "도구_수단", "전략_비교", "주체", "줄이는_용도",
           "효과_낮은값_pct", "효과_높은값_pct", "대표값_pct", "근거_등급", "근거_유형", "같은_조건_비교", "검증", "국가", "지역", "난방_방식",
           "효과_원문", "출처_주소", "출처_키", "추천_제외", "제외_까닭", "도구_지표_행", "원문_대조", "비고", "쓰임"]
PLAN, PLAN_ENV, EQUIP, BEHAV = "계획", "계획(외피 기준의 구성 요소)", "설비", "행동 · 교체"
LAYER = {   # 수단_ID -> (분류, 층, 상위_수단, 도구_수단, 추천_제외, 제외_까닭)
    "envelope": ("단열·창호 기준 강화(준공 시기)", PLAN, "", "envelope", "아니오", ""),
    "new_build_package": ("신축 통합 패키지(ZEB·인증·기준 강화)", PLAN, "", "new_build_package", "아니오", ""),
    "insulation": ("단열 강화", PLAN_ENV, "envelope", "envelope", "아니오", ""),
    "window": ("고성능 창호·유리", PLAN_ENV, "envelope", "envelope;window_retrofit", "아니오", ""),
    "airtightness": ("기밀·열교 차단", PLAN_ENV, "envelope", "", "아니오", ""),
    "rooftop_pv": ("태양광", PLAN, "", "rooftop_pv", "아니오", ""),
    "greenery": ("녹지·조경 흡수", PLAN, "", "greenery", "아니오", ""),
    "heat_recovery_ventilation": ("열회수 환기", EQUIP, "new_build_package", "heat_recovery_ventilation", "따로 추천 안 함", "설비 사양(단지 시공 세부). 상위 수단의 구성 요소로만"),
    "boiler_heating_control": ("보일러·난방 제어·배관", EQUIP, "new_build_package", "condensing_boiler;district_heating_control", "따로 추천 안 함", "설비 사양(단지 시공 세부). 상위 수단의 구성 요소로만"),
    "lighting_appliance_elevator": ("조명·가전·승강기·공용부", BEHAV, "", "", "예", "계획 단계 밖(입주 뒤 행동 · 교체)"),
}
rows = []


def add(prefix, measure, compare, use, value, low, high, grade, kind, country, text, url, role, note, same="예", region="", heating="", check="안 함"):
    cls, layer, parent, tool, excl, why = LAYER[measure]
    rows.append({"번호": f"{prefix}-{len([r for r in rows if r['번호'].startswith(prefix)]) + 1:03d}", "조사표": {"N": "추가_영국 NEED 2026", "P": "추가_이 도구 실측 비교", "L": "추가_문헌 보강(A8)"}[prefix],
                 "분류": cls, "수단_ID": measure, "층": layer, "상위_수단": parent, "도구_수단": tool, "전략_비교": compare, "주체": "",
                 "줄이는_용도": use, "효과_낮은값_pct": low, "효과_높은값_pct": high, "대표값_pct": value, "근거_등급": grade, "근거_유형": kind,
                 "같은_조건_비교": same, "검증": "확인", "국가": country, "지역": region, "난방_방식": heating, "효과_원문": text, "출처_주소": url,
                 "출처_키": "", "추천_제외": excl, "제외_까닭": why, "도구_지표_행": "", "원문_대조": check, "비고": note, "쓰임": role})


# ---------------------------------------------------------------- UK NEED 2026 (installed mid-May 2023 to mid-May 2024, England and Wales)
NEED_URL = "https://www.gov.uk/government/statistics/national-energy-efficiency-data-framework-need-impact-of-measures-data-tables-2026"
NEED_MEASURE = {"Condensing Boiler": "boiler_heating_control", "Solid Wall Insulation": "insulation", "Cavity Wall Insulation": "insulation",
                "Loft Insulation": "insulation", "Solar PV": "rooftop_pv"}
KOREAN = {"Condensing Boiler": "콘덴싱 보일러 교체", "Solid Wall Insulation": "외벽(속찬 벽) 단열", "Cavity Wall Insulation": "중공벽 단열",
          "Loft Insulation": "지붕 · 다락 단열", "Solar PV": "지붕 태양광", "Heat Controls": "난방 제어"}


def need_table(book, name):
    return list(csv.reader(open(NEED / book / f"{name}.csv", encoding="utf-8", newline="")))


def pct(v):
    return round(-100 * float(v), 2)      # NEED writes positive savings; the table writes reductions as negative


dist = {}
for name in ("Table_3", "Table_4"):
    for r in need_table("headline_EW_2023", name):
        r = [c for c in r if c != "" and not c.startswith("[Note")]
        if len(r) >= 9 and r[2] == "Savings estimate":
            dist[r[0].strip()] = {"n": int(r[3]), "mean": pct(r[4]), "q1": pct(r[6]), "median": pct(r[7]), "q3": pct(r[8])}
for name in ("Table_1", "Table_2"):
    for r in need_table("headline_EW_2023", name):
        r = [c for c in r if c != "" and not c.startswith("[Note")]
        if len(r) < 7 or r[1] not in ("Gas savings", "Electricity savings"):
            continue
        label, d = r[0].strip(), dist[r[0].strip()]
        parts = [p.strip() for p in label.replace(" and ", ", ").split(",") if p.strip()]
        measure = "insulation" if any("Insulation" in p for p in parts) else NEED_MEASURE[parts[0]]
        gas = r[1] == "Gas savings"
        device = measure in ("boiler_heating_control", "rooftop_pv")
        note = ["주택 유형별 표에 아파트(flat)가 없음(단독 · 반단독 · 연립 · 단층뿐)", "잉글랜드 · 웨일스, 가스 2,500~50,000 kWh 가구만"]
        if device:
            grade, role = "실측_국외_조건맞음", "범위 참고(단독 · 연립 주택 기준)"
            note.append("장치 효율 수단이라 국외 실측을 쓸 수 있는 등급이나, 대상이 공동주택이 아니고 교체 전 보일러 사양을 모름")
        else:
            grade, role = "실측_국외_참고", "범위 참고"
            note.append("외피 수단: 공동주택 조건이 안 맞음 → 범위 참고로만(수집 계획 3.1.1절)")
        if measure == "rooftop_pv":
            note.append("발전량이 아니라 계량 전기(한전에서 받는 전기) 감소율 = 자가소비분. 도구의 발전량 계산에는 쓰지 못함")
        add("N", measure, " + ".join(KOREAN[p] for p in parts) + " 설치 전후(대조군 대비)", "가스" if gas else "전기",
            d["median"], "", "", grade, "실측", "영국",
            f"절감률 중앙값 {-d['median']}%, 평균 {-d['mean']}%, 사분위 {-d['q1']}~{-d['q3']}%(음수는 늘어난 가구). 중앙값 {float(r[-2]):,.0f} kWh, 표본 {d['n']:,}가구",
            NEED_URL, role, " / ".join(note), heating="개별 가스보일러(가스 계량 가구)" if gas else "")

# ---------------------------------------------------------------- this project's measured comparisons
pair = json.loads((data("pair") / "pair_result.json").read_text(encoding="utf-8"))
g, e = pair["main"]["gas"], pair["main"]["electricity_household"]
PAIR_DOC = "project/working/methods/pair-comparison-rerun-2026-11-20.md"   # kept as written in the evidence table (source column); the rules now live in scripts/reduction_evidence/rules/
add("P", "envelope", "준공 2017년 이후 대 2008년 이전 개별난방 단지 짝 비교(다시 계산, 규칙 v1)", "가스", g["median_pct"], g["median_ci95"][0], g["median_ci95"][1],
    "실측_국내", "실측", "한국",
    f"{g['pairs']}쌍, 연면적당 가스 짝별 차이 중앙값 {g['median_pct']}%(95% 구간 {g['median_ci95'][0]}~{g['median_ci95'][1]}%), 평균 {g['mean_pct']}%, 새 단지가 낮은 짝 {g['share_new_lower_pct']}%. 새 {g['median_new']} · 옛 {g['median_old']} kWh/m²·년",
    PAIR_DOC, "연면적당, 면적 구성 차이 섞임 — 지표로 안 씀(사용자 결정 2026-11-20)", "관측 비교(준공 시기에 따라). 분모가 K-apt 연면적이라 새 단지의 지하주차장 등 면적 구성 차이가 섞임 / 전북 101쌍 · 전북 밖 16쌍 / 건축HUB 가스 2021~2025",
    region="전북 15개 시군구;서울 강동;수원;세종;부산 강서;가평", heating="개별난방", check="이 세션 계산")
add("P", "envelope", "같은 117쌍, 분모를 관리비 부과 면적으로(결과를 본 뒤 더한 참고)", "가스", -13.69, -17.25, -9.77, "실측_국내", "실측", "한국",
    "117쌍, 관리비 부과 면적당 가스 짝별 차이 중앙값 −13.69%(95% 구간 −17.25~−9.77%), 새 단지가 낮은 짝 79.5%. 세대당으로는 −19.09%(−27.06~−13.71%)",
    PAIR_DOC, "도구 지표(사후 분모, 기록에 명시. 사용자 결정 2026-11-20, 병합 전)", "G1 판정에 쓰지 않은 사후 계산을 사용자 결정으로 사다리 1단계 값으로 채택. 세대당 연면적 새 144.2 · 옛 107.6 m², 관리비 부과 면적 새 78.9 · 옛 75.1 m²", heating="개별난방", check="이 세션 계산")
add("P", "envelope", "같은 짝의 세대 전기(K-apt)", "전기", e["median_pct"], e["median_ci95"][0], e["median_ci95"][1], "실측_국내", "실측", "한국",
    f"{e['pairs']}쌍, 연면적당 세대 전기 짝별 차이 중앙값 {e['median_pct']}%(95% 구간 {e['median_ci95'][0]}~{e['median_ci95'][1]}%), 평균 {e['mean_pct']}%(구간 {e['mean_ci95'][0]}~{e['mean_ci95'][1]}%), 새 단지가 낮은 짝 {e['share_new_lower_pct']}%",
    PAIR_DOC, "차이 확인 못 함(값으로 쓰지 않음)", "중앙값은 줄고 평균은 늘어 방향을 말할 수 없음. K-apt 전기는 세대 사용분(공용 전기 없음)", heating="개별난방", check="이 세션 계산")
add("P", "envelope", "지금 도구 값: 준공 2017년 이후 대 2008년 이전 78쌍(원래 계산)", "가스", -23.6, -25.8, -20.5, "실측_국내", "실측", "한국",
    "78쌍, 가스 −23.6%(95% 구간 −25.8~−20.5%), 93.6%의 쌍에서 새 단지가 낮음. 전기 +5.2%, 탄소 −6.9%",
    "Carbon-Urban-DSS/docs/REDUCTION_INDICATORS.md", "재현 안 됨, 폐기(사용자 결정 2026-11-20)", "원래 스크립트와 2,385단지 표가 없어 규칙 · 분모를 확인하지 못함. 다시 계산한 값과 95% 구간이 겹치지 않음", heating="개별난방", check="이 세션 계산(재현 안 됨)")
KEA_DOC = "project/working/methods/kea-grade-real-use-rule-2026-11-20.md"   # same
add("P", "new_build_package", "효율등급 본인증 단지 대 비인증 단지(메인 세션 계산)", "전기", 0.6, -4.4, 5.0, "실측_국내", "실측", "한국",
    "인증 138곳 · 비교 252곳, 25개 층. K-apt 단지 전기(세대 쪽 일부) 원단위 차이 +0.6%(95% 구간 −4.4~+5.0%). 세대당 −2.2%(−4.9~+11.9%)",
    KEA_DOC, "차이 확인 못 함(값으로 쓰지 않음)", "구간이 0을 걸침 → 국내 실측으로 전기 차이를 확인하지 못함. 주소 맞춤이 안 된 인증 단지가 비교 무리에 섞였을 수 있음(차이를 0 쪽으로)", check="메인 세션 계산(문서 6절)")
add("P", "new_build_package", "효율등급 본인증 단지 대 비인증 단지, 가스(메인 세션 계산)", "가스", "", "", "", "실측_국내", "실측", "한국",
    "개별난방 · 단지 하나 묶음 · 가스 완비 해 조건의 인증 단지 24곳 · 비교 74곳, 11개 층. 참고 −9.8%(95% 구간 −18.4~+2,403%)",
    KEA_DOC, "차이 확인 못 함(값으로 쓰지 않음)", "인증 단지 24곳 < 기준 30곳 → 확인 못 함. −9.8%는 판정에 쓰지 않는 참고라 대표값을 비워 둠. 구간 위쪽은 가스가 0에 가까운 비교 단지 때문", heating="개별난방", check="메인 세션 계산(문서 8절)")

# ---------------------------------------------------------------- A8 literature rows (written by the search tasks)
GRADES = {"실측_국내", "실측_국외_조건맞음", "문헌_계산", "실측_국외_참고", "가정"}
FULL_TEXT_CHECKS = {
    "JAKO202025863869023": "본문 확인(2026-11-20): 0.65 t/ha/yr의 분모는 녹지 면적이 아니라 공공용지 **부지 면적**(표 머리 'Per land area'), 탄소(C) 기준. "
                           "같은 표의 수관 면적당 값은 0.47 kg/m²/yr(탄소). 부지 중 녹지 면적 점유비 14.6~23.1%, 수목 피도 평균 13.2%. "
                           "도구 가정(녹지 면적당 1.0 kgCO2/m²)과 바로 견줄 수 없음",
}
for name in ("rows_envelope.csv", "rows_pv_green.csv"):
    path = HERE / name
    if not path.exists():
        print("없음:", name)
        continue
    for r in csv.DictReader(open(path, encoding="utf-8-sig", newline="")):
        measure = r["수단_ID"].strip()
        grade = r["근거_등급"].strip()
        if measure not in LAYER or grade not in GRADES:
            print("건너뜀(수단 · 등급 값이 표에 없음):", name, measure, grade, r.get("전략_비교", "")[:40])
            continue
        if "대표값_pct" in r:          # envelope file: percentages
            value, low, high, text = r["대표값_pct"], r["효과_낮은값_pct"], r["효과_높은값_pct"], r["효과_원문"]
        else:                          # pv / greenery file: values with units, not percentages
            value, low, high = "", "", ""
            text = f'{r["지표_이름"]} {r["대표값"]} {r["단위"]}(범위 {r["값_낮은"]}~{r["값_높은"]}). {r["효과_원문"]}'
        note = " / ".join(x for x in (r.get("대상", ""), f'본 범위: {r.get("본_범위", "")}', r.get("비고", "")) if x)
        for key, extra in FULL_TEXT_CHECKS.items():       # this session read the full text afterwards (2026-11-20)
            if key in r["출처_주소"]:
                note = f"{extra} / {note}"
        add("L", measure, r["전략_비교"], r["줄이는_용도"], value, low, high, grade, r["근거_유형"], r["국가"], f'{text} [{r["출처_제목"]}]',
            r["출처_주소"], "지표 후보" if grade in ("실측_국내", "실측_국외_조건맞음", "문헌_계산") else "범위 참고", note,
            same=r.get("같은_조건_비교", ""), region=r.get("지역", ""), heating=r.get("난방_방식", ""),
            check="이 세션이 본문 확인" if any(k in r["출처_주소"] for k in FULL_TEXT_CHECKS) else f'보조 작업이 열람({r.get("본_범위", "")})')

# rows this session read itself (full text, 2026-11-20)
add("L", "greenery", "공동주택 단지(다세대 주거 부지) 식재수목의 부지 면적당 · 수관 면적당 연 탄소흡수량", "흡수(상쇄)", "", "", "", "실측_국내", "실측", "한국",
    "110개 공동주택 단지(서울 36 · 대전 38 · 대구 36, 조사 면적 422.3 ha) 현장 전수 조사. 부지 면적당 연 직접 탄소 저감 평균 1.1±0.1 t/ha/year(범위 0.3~2.9), "
    "수관 면적당 평균 0.5±0.0 kg/m2/year(0.2~0.9). 토지 피복: 포장 · 시설 57.7%, 건물 23.7%, 교목 · 관목 17.9%, 잔디 · 나지 0.7%. 교목 밀도 2.5±0.1주/100 m2, "
    "교목 피도 19.2%, 흉고직경 평균 13.6 cm "
    "[Carbon Offset Service and Design Guideline of Tree Planting for Multifamily Residential Sites in Korea, Sustainability 11(13) 3543, 2019]",
    "https://www.mdpi.com/2071-1050/11/13/3543", "지표 후보",
    "분모 확인(본문): 부지(단지) 면적당과 수관 면적당 두 값. 녹지 면적당 값은 논문에 없음. 환산(× 44/12, 탄소 기준으로 볼 때): 부지당 0.40 kgCO2/m²·년, 수관 면적당 1.83 kgCO2/m²·년. "
    "원문 표기는 carbon이고 CO2 기준이 아니라는 문장은 따로 확인하지 못함(확인 필요). 흡수량은 직경으로 계산하는 계량모델(계절별 CO2 교환 측정 · 직접 수확에서 만든 식) 값",
    same="아니오", region="서울;대전;대구", check="이 세션이 본문 열람(HTML)")

# full-text checks of rows first read from abstracts (fulltext_checks.csv, 2026-11-20): status, denominator / method, and the
# grade or use changes the full text requires. Row values are not rewritten; the full-text values go into 비고.
GRADE_AFTER_FULL_TEXT = {"L-015": "문헌_계산", "L-016": "문헌_계산", "L-047": "문헌_계산"}
ROLE_AFTER_FULL_TEXT = {
    "L-015": "범위 참고(성능비는 PVsyst 해석값. 실측은 실증주택 2014년 1,395 kWh/kWp)",
    "L-016": "범위 참고(성능비는 PVsyst 해석값. 76.1%는 실측 발전량으로 검증한 계산)",
    "L-017": "범위 참고(수직 설치 1.1 kW, L-018과 같은 설비 — 근거 1건으로 셈)",
    "L-018": "지표 후보(수직 · 발코니 설치의 실측 성능비, L-017과 같은 설비)",
    "L-046": "범위 참고(복원지 2.33은 세 군락 값을 더한 것. 본문 값은 0.50~1.19 tC/ha/yr = 0.18~0.44 kgCO2/m²·년)",
    "L-047": "범위 참고(분모가 서울시 전체 토지 면적. 도시숲 구역만은 6.84 tC/ha/yr)",
    "L-045": "범위 참고(공원 전체 면적당, 종속영양 호흡 비율은 가정)",
    "L-031": "범위 참고(서울 구 단위의 건물에 의한 일사 감소 계산값, 구별 9~30%. 한 단지 옥상의 그림자 손실률이 아님)",
}
ft = {}
for ft_path in (HERE / "fulltext_checks.csv", HERE / "fulltext_checks2.csv"):
    if ft_path.exists():
        ft.update({r["번호"]: r for r in csv.DictReader(open(ft_path, encoding="utf-8-sig", newline=""))})
if ft:
    for r in rows:
        c = ft.get(r["번호"])
        if not c:
            continue
        r["원문_대조"] = "본문 " + c["본문_확인"] if c["본문_확인"].startswith("확인") else "본문 못 봄(초록만)"
        if c["본문_확인"].startswith("확인"):
            r["비고"] = " / ".join(x for x in (f'본문 확인(2026-11-20): {c["분모_또는_측정방법"]}', f'원문 값: {c["원문_값"]}',
                                              f'탄소 기준: {c["탄소_기준"]}' if c["탄소_기준"] not in ("", "해당 없음") else "", c["비고"], r["비고"]) if x)
        if r["번호"] in GRADE_AFTER_FULL_TEXT and r["근거_등급"] != GRADE_AFTER_FULL_TEXT[r["번호"]]:
            r["비고"] = f'본문 확인으로 등급 바꿈({r["근거_등급"]} → {GRADE_AFTER_FULL_TEXT[r["번호"]]}) / ' + r["비고"]
            r["근거_등급"] = GRADE_AFTER_FULL_TEXT[r["번호"]]
        if r["번호"] in ROLE_AFTER_FULL_TEXT:
            r["쓰임"] = ROLE_AFTER_FULL_TEXT[r["번호"]]

add("L", "rooftop_pv", "공동주택 옥상 태양광 실측 발전량(광주, 22개 동 단지, 2012년, 경사 22°)", "발전량 · 자립률", "", "", "", "실측_국내", "실측", "한국",
    "실측 연 발전량(설치용량 1 kWp로 환산): 남향 1,255.6, 동쪽 30° 1,249.3, 서쪽 45° 1,222.5 kWh/kWp·yr. 같은 조건의 예측(PVpro) 1,286.0 · 1,262.2 · 1,239.3, 연 오차 2.4 · 1.0 · 1.4% "
    "[건물적용 태양광 수평면 · 방위별 발전량 예측 논문(L-026과 같은 논문)의 검증용 실측 표, 2014]",
    "https://koreascience.kr/article/JAKO201417638007229.page", "지표 후보",
    "논문의 주제는 시뮬레이션이고 이 값은 그 검증에 쓴 실측(표의 kWh/kWp.yr 줄에서 이 세션이 직접 확인: 1249.3 · 1255.6 · 1222.5). 한 단지 · 한 해 값. 이용률로는 약 14.0~14.3%(÷ 8,760, 계산). "
    "모듈 220 W급. 계측 방식 · 설비 용량 합계는 확인 필요",
    same="아니오", region="광주", check="이 세션이 본문 확인(검증 표)")

with open(data("evidence_table") / "evidence_added.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=COLUMNS)
    w.writeheader()
    w.writerows(rows)
base = list(csv.DictReader(open(data("evidence_table") / "evidence_table.csv", encoding="utf-8-sig", newline="")))
with open(data("evidence_table") / "evidence_table_all.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=COLUMNS)
    w.writeheader()
    w.writerows([{**r, "쓰임": ""} for r in base] + rows)
print("added", len(rows), "total", len(base) + len(rows))
print(Counter(r["조사표"] for r in rows))
print(Counter((r["수단_ID"], r["근거_등급"]) for r in rows))
for r in rows:
    if r["번호"].startswith(("N", "P")):
        print(r["번호"], r["수단_ID"], r["줄이는_용도"], r["대표값_pct"], r["근거_등급"], "|", r["쓰임"], "|", r["전략_비교"][:60])
