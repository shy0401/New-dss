"""이행 사업 표의 목표 감축량을 tCO2eq 한 단위로 옮기고 한 해 · 누적을 가른다(2026-11-20 점검 8번).

규칙(값을 보기 전에 정함):
- 배율: 단위 글의 괄호 앞부분에 '천'이 있으면 1000, 없으면 1(톤 · t · ton). 원래 값 · 단위 글은 그대로 둔다.
- 목표_감축량_tco2eq: 원래 값이 숫자 하나일 때만 값 × 배율. 비었거나 여러 값이 한 칸에 적힌 줄은 NULL(0 아님).
- 목표_기준: 단위 글이 한 해(당해 · 그해 · 연도별 값 · /년)나 누적을 분명히 말할 때만 적고,
  둘이 어긋나거나(예: '/년'인데 '누적 줄과 같은 값') 아무 말이 없으면 '확인 필요'.
  목표_연도 칸이 '(총계)' · '(소계)'로 기간 합을 밝힌 줄은 '누적'.
- 결과는 지역 · 문서마다 기준이 달라 더하거나 견주지 않는다(제안 목록 · 적용 가능성에만).

쓰는 법: python -I normalize_units.py local_plans_building.csv local_plans_building_units.csv
"""
import csv
import sys

# 단위 글 → 목표_기준. 표에 있는 25가지를 하나씩 읽고 적음. 없는 글이 나오면 멈춘다.
BASIS = {
    "천tCO2eq.": "확인 필요",
    "톤CO2eq": "확인 필요",
    "tCO2eq": "확인 필요",
    "천톤CO2eq": "확인 필요",
    "tCO2eq(누적감축량)": "누적",
    "천 톤CO2eq.(본문 '2030년까지', 2024~2030년 누적)": "누적",
    "tCO2eq('연차별 온실가스 감축량' 표의 '감축잠재량(tCO2eq, 누적)' 줄의 2030년 칸. 2019~2024년 기존 실적분을 포함한 누적)": "누적",
    "천톤/년(표 머리 그대로. 부록 관리카드의 '누적' 줄과 같은 값)": "확인 필요",   # '/년'과 '누적'이 어긋남
    "톤CO₂eq.(표 107 '2030년 온실가스 감축량'. 과제카드의 2025~2030년 누적 값과 같은 자리)": "확인 필요",   # 2030년 값과 누적이 어긋남
    "tCO2eq./년": "한 해",
    "천톤CO2eq.(표 '연도별 감축계획'의 ’30년 칸, 연도별 값)": "한 해",
    "천 톤CO2eq": "확인 필요",
    "천 tonCO2eq": "확인 필요",
    "tCO2eq(그해 감축량. 표 4.2-5 · 4.2-6은 같은 값을 천톤CO2eq./년으로 적음)": "한 해",
    "천tCO2eq": "확인 필요",
    "tCO2eq/년(누적 감축 잠재량)": "확인 필요",   # '/년'과 '누적'이 어긋남
    "천tCO2eq(과제 카드 표기 '누적감축량'. 부록 355쪽 표는 같은 값을 '감축 잠재량(천tCO2eq/yr)'으로 적음)": "확인 필요",   # 누적과 /yr가 어긋남
    "톤CO2eq.(연차별 감축목표량, 누적 사업량으로 산출)": "한 해",   # 그해 목표량, 누적은 사업량을 말함
    "tCO2eq('연차별 온실가스 감축량' 표의 '감축잠재량(tCO2eq, 누적)' 줄의 2030년 칸. 2019~2024년 기존 실적분을 포함한 누적). 세부 줄마다 적힘(과제 합계 줄은 문서에 없음)": "누적",
    "톤CO₂eq.(표 107 '2030년 온실가스 감축량'. 과제카드에서는 2030년 한 해 값이고 누적 줄은 '-')": "한 해",
    "tCO2eq('연차별 온실가스 감축량' 표의 '감축잠재량(tCO2eq, 당해)' 줄의 2030년 칸. 그해 값이고 누적 줄은 없음)": "한 해",
    "tCO2eq('연차별 온실가스 감축량' 표의 '감축잠재량(tCO2eq, 당해)' 줄의 2030년 칸. 그해 값이고 누적 줄은 없음). 세부 줄마다 적힘(과제 합계 줄은 문서에 없음)": "한 해",
    "천 톤CO2eq.(본문 '사업 종료하는 ’25년까지', 2024~2025년 누적)": "누적",
    "톤CO2eq.(연차별 감축목표량, 단발 사업: 당해연도 사업량으로 산출)": "한 해",
}


def number(text: str) -> float | None:
    try:
        return float(text.replace(",", "").strip())
    except ValueError:
        return None


def main(src: str, dst: str) -> None:
    rows = list(csv.DictReader(open(src, encoding="utf-8-sig")))
    out_rows = []
    for r in rows:
        unit, raw = r["목표_단위"], r["목표_감축량"].strip()
        if not raw:
            scale, tco2e, basis = None, None, None
        else:
            if unit not in BASIS:
                raise SystemExit(f"규칙에 없는 단위 글: {unit!r}")
            scale = 1000 if "천" in unit.split("(")[0] else 1   # 괄호 안 설명의 '천'(전북)은 보지 않음
            value = number(raw)
            tco2e = round(value * scale, 1) if value is not None else None
            basis = BASIS[unit]
            year = r["목표_연도"]
            if basis == "확인 필요" and ("(총계)" in year or "(소계)" in year):
                basis = "누적"
        out_rows.append(dict(r, 목표_배율=scale if scale is not None else "",
                             목표_감축량_tco2eq="" if tco2e is None else f"{tco2e:g}",
                             목표_기준=basis or ""))
    fields = list(rows[0].keys())
    i = fields.index("목표_연도") + 1
    fields = fields[:i] + ["목표_배율", "목표_감축량_tco2eq", "목표_기준"] + fields[i:]
    with open(dst, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)
    from collections import Counter
    filled = [x for x in out_rows if x["목표_감축량"].strip()]
    print("rows", len(out_rows), "with target", len(filled),
          "numeric", sum(1 for x in filled if x["목표_감축량_tco2eq"]),
          "multi-value NULL", sum(1 for x in filled if not x["목표_감축량_tco2eq"]))
    print("basis", dict(Counter(x["목표_기준"] for x in filled)))
    print("scale", dict(Counter(x["목표_배율"] for x in filled)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
