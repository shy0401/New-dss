"""냉방 쪽 보강 35행(a10/cooling_rows.csv)을 근거표 열로 맞춰 기존 610행 뒤에 붙인다(2026-11-20).
층 · 추천 제외 · 쓰임은 근거표 2 · 5절 규칙을 그대로 적용. 값 · 원문은 고치지 않는다.
usage: python -E -P merge_a10.py <evidence_table_all.csv> <cooling_rows.csv> <out merged csv>
"""
import csv
import sys

base_p, add_p, out_p = sys.argv[1:4]
base = list(csv.DictReader(open(base_p, encoding="utf-8-sig")))
cols = list(base[0].keys())
add = list(csv.DictReader(open(add_p, encoding="utf-8-sig")))

EXC_SPEC = "설비 사양(단지 시공 세부). 상위 수단의 구성 요소로만"          # 근거표 5절의 같은 문장
EXC_HP = "적용이 거의 불가능(면담: 실제 COP가 3.0에 못 미침, 초기 비용)"   # 히트펌프 행의 같은 문장
LAYER = {"cool_roof": "계획(외피 기준의 구성 요소)", "building_greening": "계획", "cooling_efficiency": "설비",
         "district_cooling": "계획(열원)", "heat_source_choice": "계획(열원)"}
HEAT_PUMP = {"A10-031", "A10-032", "A10-033", "A10-034", "A10-035"}

rows = []
for a in add:
    mid, no = a["수단_ID"], a["번호"]
    if mid == "cooling_efficiency":
        exc, why = "따로 추천 안 함", EXC_SPEC
    elif no in HEAT_PUMP:
        exc, why = "예", EXC_HP
    else:
        exc, why = "아니오", ""
    if not a["대표값_pct"]:
        use = "범위 참고(% 없음, 온도 등만)"
    elif mid == "cool_roof" and a["근거_등급"] == "실측_국내":
        use = "범위 참고(최상층 세대 기준일 가능성, 동 전체에 곱하지 않음)"
    elif mid == "building_greening":
        use = "범위 참고(최상층 세대 · 저층 모형 값, 5층 이상 주거는 효과가 작다는 연구 있음)"
    elif mid == "heat_source_choice" and no in ("A10-025", "A10-026"):
        use = "범위 참고(탄소는 기준 문서 5절 계수로 다시 계산해야 함)"
    elif a["근거_등급"] == "가정":
        use = "범위 참고(가정 · 기관 추정)"
    else:
        use = "범위 참고"
    r = {c: "" for c in cols}
    r.update({"번호": no, "조사표": "추가_냉방 쪽 보강(A10)", "분류": a["분류"], "수단_ID": mid, "층": LAYER[mid],
              "전략_비교": a["전략_비교"], "줄이는_용도": a["줄이는_용도"], "효과_낮은값_pct": a["효과_낮은값_pct"],
              "효과_높은값_pct": a["효과_높은값_pct"], "대표값_pct": a["대표값_pct"], "근거_등급": a["근거_등급"],
              "근거_유형": a["근거_유형"], "국가": a["국가"], "지역": a["지역"], "난방_방식": a["난방_방식"],
              "효과_원문": a["효과_원문"], "출처_주소": a["출처_주소"], "추천_제외": exc, "제외_까닭": why,
              "원문_대조": a["원문_대조"], "비고": (f"건물 유형: {a['건물_유형']}. " if a["건물_유형"] else "") + a["비고"],
              "쓰임": use})
    rows.append(r)
with open(out_p, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    w.writerows(base + rows)
print("base", len(base), "added", len(rows), "total", len(base) + len(rows))
