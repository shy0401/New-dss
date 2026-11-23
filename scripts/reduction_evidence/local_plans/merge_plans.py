"""A4: merge the building-sector task tables (plans_*.csv) into local_plans_building.csv and check them against the rules in
scripts/reduction_evidence/rules/local-carbon-plans-building-2026-11-20.md (columns, measure IDs, value kind). Nothing is corrected:
problems are listed. Usage: python merge_plans.py
"""
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _paths import data  # noqa: E402

HERE = Path(__file__).parent
INPUTS = HERE / "inputs"   # transcribed tables kept in the repo
OUT = data("local_plans")   # results outside Git
COLUMNS = ["지역_코드", "지역", "계획_이름", "계획_기간", "수립_시기", "부문", "과제_번호", "과제_이름", "과제_내용", "수단_ID", "층", "대상",
           "목표_감축량", "목표_단위", "목표_연도", "실적_2025", "예산", "지원_제도", "출처_주소", "쪽", "본_범위", "값의_종류", "비고"]
MEASURES = {"new_build_package", "retrofit_package", "insulation", "window", "rooftop_pv", "solar_thermal_geothermal_fuelcell", "heat_pump",
            "heat_source_district", "boiler_heating_control", "lighting_appliance_elevator", "bems_metering", "operation", "greenery",
            "materials_other", "other", ""}
KIND = "지자체 계획값(자체 평가)"
rows, problems = [], []
for path in sorted(INPUTS.glob("plans_*.csv")):
    data = list(csv.DictReader(open(path, encoding="utf-8-sig", newline="")))
    if data and list(data[0]) != COLUMNS[:23]:
        problems.append(f"{path.name}: 열이 규칙과 다름 {[c for c in data[0] if c not in COLUMNS]} / 빠짐 {[c for c in COLUMNS if c not in data[0]]}")
    for i, r in enumerate(data, 2):
        r = {c: (r.get(c) or "").strip() for c in COLUMNS}
        r["_file"] = path.name
        unknown = [m for m in re.split(r"[;,]\s*", r["수단_ID"]) if m not in MEASURES]
        if unknown:
            problems.append(f"{path.name}:{i} 수단_ID가 대응표에 없음 {unknown}")
        if r["값의_종류"] != KIND:
            problems.append(f"{path.name}:{i} 값의_종류가 다름: {r['값의_종류']!r}")
        if r["목표_감축량"] and not r["목표_단위"]:
            problems.append(f"{path.name}:{i} 목표 감축량에 단위 없음")
        if r["본_범위"] != "찾지 못함" and not r["출처_주소"]:
            problems.append(f"{path.name}:{i} 출처 주소 없음")
        rows.append(r)

# original-PDF recheck (recheck/plans_<code>.csv): when present, it replaces every earlier row of that region
rechecked = {}
for path in sorted((INPUTS / "recheck").glob("plans_*.csv")):
    data = list(csv.DictReader(open(path, encoding="utf-8-sig", newline="")))
    if data and list(data[0]) != COLUMNS:
        problems.append(f"recheck/{path.name}: 열이 규칙과 다름 {[c for c in data[0] if c not in COLUMNS]} / 빠짐 {[c for c in COLUMNS if c not in data[0]]}")
    code = path.stem.split("_", 1)[1]
    fresh = []
    for i, r in enumerate(data, 2):
        r = {c: (r.get(c) or "").strip() for c in COLUMNS}
        r["_file"], r["_recheck"] = f"recheck/{path.name}", "1"
        if r["지역_코드"] != code:
            problems.append(f"recheck/{path.name}:{i} 지역_코드가 파일 이름과 다름: {r['지역_코드']!r}")
        unknown = [m for m in re.split(r"[;,]\s*", r["수단_ID"]) if m not in MEASURES]
        if unknown:
            problems.append(f"recheck/{path.name}:{i} 수단_ID가 대응표에 없음 {unknown}")
        if r["값의_종류"] != KIND:
            problems.append(f"recheck/{path.name}:{i} 값의_종류가 다름: {r['값의_종류']!r}")
        if r["목표_감축량"] and not r["목표_단위"]:
            problems.append(f"recheck/{path.name}:{i} 목표 감축량에 단위 없음")
        fresh.append(r)
    rechecked[code] = (len([r for r in rows if r["지역_코드"] == code]), len(fresh))
    rows = [r for r in rows if r["지역_코드"] != code] + fresh
changes = []
for path in sorted((INPUTS / "recheck").glob("changes_*.csv")):
    if path.name == "changes_all.csv":      # the merged list written below; reading it back would count every change twice
        continue
    for r in csv.DictReader(open(path, encoding="utf-8-sig", newline="")):
        changes.append({**r, "_file": path.name})
if changes:
    keys = ["지역_코드", "과제_번호", "과제_이름", "열", "앞선_값", "원문_값", "쪽", "종류", "비고"]
    with open(OUT / "changes_all.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(changes)

# a region read later by another file: its earlier "찾지 못함" placeholder row is dropped (counted in the summary)
found = {r["지역_코드"] for r in rows if r["본_범위"] != "찾지 못함"}
replaced = [r for r in rows if r["본_범위"] == "찾지 못함" and r["지역_코드"] in found]
rows = [r for r in rows if r not in replaced]

# 쓰임 (main session's judgement 2026-11-20: rows read from preview page images or from a second-hand summary stay in the table
# as reference until the original document is checked; numbers read from images are flagged). 층 labels: spacing only.
def role(r):
    scope = r["본_범위"]
    if r.get("_recheck"):
        return "문서 글자를 읽음(원문 대조함)"
    if scope == "찾지 못함":
        return "찾지 못함"
    if "pdftotext" in scope:              # the document's own text was read (a preview seen earlier does not matter)
        return "문서 글자를 읽음"
    if "미리보기" in scope or "쪽 그림" in scope:
        return "참고(원문 대조 전)"
    if "2차 인용" in scope:
        return "참고(상위계획 요약 2차 인용)"
    if scope.startswith("요약본") or "보도자료" in scope:
        return "참고(공개 화면 · 보도자료)"
    return "문서 글자를 읽음"


for r in rows:
    r["쓰임"] = role(r)
    if r["쓰임"] == "참고(원문 대조 전)" and any(r[c] for c in ("목표_감축량", "예산", "실적_2025")) and "그림 판독" not in r["비고"]:
        r["비고"] = " / ".join(x for x in (r["비고"], "확인 필요(그림 판독)") if x)
    r["층"] = re.sub(r"\s*·\s*", " · ", r["층"])
COLUMNS = COLUMNS + ["쓰임"]

with open(OUT / "local_plans_building.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)

by_region = defaultdict(list)
for r in rows:
    by_region[(r["지역_코드"], r["지역"])].append(r)
measure_count = Counter(m for r in rows for m in re.split(r"[;,]\s*", r["수단_ID"]) if m)
regions_with = defaultdict(set)
for r in rows:
    for m in re.split(r"[;,]\s*", r["수단_ID"]):
        if m:
            regions_with[m].add(r["지역"])
summary = {
    "rows": len(rows), "regions": len(by_region),
    "by_region": {f"{k[0]} {k[1]}": {"rows": len(v), "본_범위": dict(Counter(x["본_범위"] for x in v)),
                                     "with_target": sum(1 for x in v if x["목표_감축량"]), "with_result_2025": sum(1 for x in v if x["실적_2025"]),
                                     "with_budget": sum(1 for x in v if x["예산"])} for k, v in sorted(by_region.items())},
    "measure_rows": dict(measure_count.most_common()), "measure_regions": {m: len(v) for m, v in sorted(regions_with.items(), key=lambda kv: -len(kv[1]))},
    "layer": dict(Counter(r["층"] for r in rows)), "role": dict(Counter(r["쓰임"] for r in rows)),
    "role_by_region": {f"{k[0]} {k[1]}": dict(Counter(x["쓰임"] for x in v)) for k, v in sorted(by_region.items())}, "not_found": [f"{k[0]} {k[1]}" for k, v in by_region.items() if all(x["본_범위"] == "찾지 못함" for x in v)],
    "rechecked_rows_before_after": rechecked,
    "changes": {"total": len(changes), "by_region": dict(Counter(c.get("지역_코드", "") for c in changes)), "by_kind": dict(Counter(c.get("종류", "") for c in changes))},
    "placeholder_rows_replaced": [f'{r["지역_코드"]} {r["지역"]} ({r["_file"]})' for r in replaced],
    "problems": problems,
}
(OUT / "local_plans_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=1))
