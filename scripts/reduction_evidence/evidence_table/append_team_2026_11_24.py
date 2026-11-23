"""Append the 2026-11-24 team-survey literature rows (rows_team_2026-11-24.csv) to the evidence table as T-001.. rows.

The rows were checked against the original papers on 2026-11-24 (records/2026-11-24-team-reduction-evidence.md): values
come only from text that was read; abstract-only rows say so in 원문_대조. Same value layout as the A8 literature rows
(build_added.py): values with units go into 효과_원문, the % columns stay empty.
usage: python scripts/reduction_evidence/evidence_table/append_team_2026_11_24.py [table csv]   (default backend/reference/reduction_evidence.csv)
Runs once: refuses when T- rows are already in the table.
"""
import csv
import sys
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parents[2]
TABLE = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "backend" / "reference" / "reduction_evidence.csv"
SURVEY = "추가_팀 감축 방안 조사(2026-11-24)"
PLAN = "계획"
LAYER = {   # 수단_ID -> (분류, 층, 상위_수단, 도구_수단, 추천_제외, 제외_까닭); facade_pv is not linked to a tool measure yet
    "facade_pv": ("입면·발코니 태양광", PLAN, "", "", "아니오", ""),
    "rooftop_pv": ("태양광", PLAN, "", "rooftop_pv", "아니오", ""),
    "layout_form": ("배치·형태·향·밀도·세대 규모", PLAN, "", "", "아니오", ""),
}
CHECK = {"본문": "본문 확인(2026-11-24)", "초록만": "초록만"}

with open(TABLE, encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    columns = reader.fieldnames
    table = list(reader)
if any(r["번호"].startswith("T-") for r in table):
    sys.exit(f"{TABLE}: T- 행이 이미 있음, 그대로 둠")

new = []
for r in csv.DictReader(open(HERE / "rows_team_2026-11-24.csv", encoding="utf-8-sig", newline="")):
    cls, layer, parent, tool, excl, why = LAYER[r["수단_ID"]]
    if not r["지표_이름"]:
        value = ""
    elif r["대표값"]:
        value = f'{r["지표_이름"]} {r["대표값"]} {r["단위"]}(범위 {r["값_낮은"]}~{r["값_높은"]}). '
    else:
        value = f'{r["지표_이름"]} {r["값_낮은"]}~{r["값_높은"]} {r["단위"]}. '
    scope = r["본_범위"]
    new.append({**{c: "" for c in columns},
                "번호": f"T-{len(new) + 1:03d}", "조사표": SURVEY, "분류": cls, "수단_ID": r["수단_ID"], "층": layer, "상위_수단": parent,
                "도구_수단": tool, "전략_비교": r["전략_비교"], "줄이는_용도": r["줄이는_용도"], "근거_등급": r["근거_등급"],
                "근거_유형": r["근거_유형"], "검증": "확인", "국가": r["국가"], "지역": r["지역"],
                "효과_원문": f'{value}{r["효과_원문"]} [{r["출처_제목"]}]', "출처_주소": r["출처_주소"], "추천_제외": excl, "제외_까닭": why,
                "원문_대조": CHECK.get(scope, f"본문 확인(2026-11-24, {scope.removeprefix('본문').strip('()')})"),
                "비고": " / ".join(x for x in (r["대상"], r["비고"]) if x), "쓰임": r["쓰임"]})

raw = TABLE.read_bytes()   # append only: the existing rows stay byte for byte
eol = "\r\n" if b"\r\n" in raw[:4096] else "\n"
with open(TABLE, "a", encoding="utf-8", newline="") as f:
    if not raw.endswith(b"\n"):
        f.write(eol)
    csv.DictWriter(f, fieldnames=columns, lineterminator=eol).writerows(new)
print(f"{TABLE}: {len(table)} → {len(table) + len(new)}행 (T-001~T-{len(new):03d})")
