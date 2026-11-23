"""Read-only: count fields and apply address-matching rule v1 (fixed 2026-11-20 before fetching).

Usage (inside api container): python kea_match_v1.py /data/raw/kea_building_rating/<date> /data/ops/<run>
Writes summary.json and samples.json to the output folder. Changes no table.
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import text

from app.db import Session

raw_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
out_dir.mkdir(parents=True, exist_ok=True)

items = []
for f in sorted((raw_dir / "pages").glob("page-*.json")):
    got = json.loads(f.read_text(encoding="utf-8"))["response"]["body"]["items"]["item"]
    items.extend(got if isinstance(got, list) else [got])

def val(v):
    return None if v is None or str(v).strip() in ("", "NULL") else str(v).strip()

fields = sorted({k for it in items for k in it})
missing = {k: sum(1 for it in items if val(it.get(k)) is None) for k in fields}
kinds = Counter((it.get("PURPOSE_KIND_NAME"), it.get("CRTIF_KIND")) for it in items)
years = Counter(it.get("CRTIF_ISU_DD_YEAR") for it in items)

SIDO = {"서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주",
        "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기", "강원특별자치도": "강원",
        "강원도": "강원", "충청북도": "충북", "충청남도": "충남", "전북특별자치도": "전북", "전라북도": "전북",
        "전라남도": "전남", "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주"}
PARCEL = re.compile(r"(\S+?(?:동|리|가|로\d*가))\s*(산\s*)?(\d+)(?:-(\d+))?")

def clean(addr):
    addr = re.sub(r"외\s*\d+\s*필지", " ", addr)
    return addr.replace("번지", " ").replace("일대", " ")

def parcel(addr):
    m = PARCEL.search(clean(addr))
    if not m:
        return None
    return (m.group(1), "산" if m.group(2) else "", int(m.group(3)), int(m.group(4) or 0)), addr[: m.start()]

def norm_sgg(s):
    return re.sub(r"\s|시", "", s or "")

with Session() as db:
    rows = db.execute(text("select kapt_code, address, name from national_complexes")).all()
    energy_codes = {r[0] for r in db.execute(text("select kapt_code from apartment_complexes"))}
index = defaultdict(list)
nat_unparsed = 0
for code, address, name in rows:
    if not address:
        nat_unparsed += 1
        continue
    parts = address.split(" ", 1)
    sido = SIDO.get(parts[0])
    p = parcel(parts[1] if len(parts) > 1 else "")
    if not sido or not p:
        nat_unparsed += 1
        continue
    index[(sido,) + p[0]].append((code, p[1], name))

outcome = Counter()
by_kind = defaultdict(Counter)
samples = defaultdict(list)
matched = []
for it in items:
    if it.get("PURPOSE_KIND_NAME") != "주거용":
        continue
    kind = it.get("CRTIF_KIND")
    addr = val(it.get("LOC_ADDR")) or ""
    p = parcel(addr)
    if not p:
        res = "지번 아님"
    else:
        cands = index.get((val(it.get("RGN_SCT_NAME")),) + p[0], [])
        if len(cands) > 1:
            a = norm_sgg(p[1])
            cands = [c for c in cands if a and (a in norm_sgg(c[1]) or norm_sgg(c[1]) in a)] or cands
        res = "하나 일치" if len(cands) == 1 else ("여러 후보" if cands else "불일치")
        if res == "하나 일치":
            matched.append((it, cands[0][0]))
    outcome[res] += 1
    by_kind[kind][res] += 1
    if len(samples[res]) < 15:
        samples[res].append({"addr": addr, "sido": it.get("RGN_SCT_NAME"), "name": it.get("BLD_NM"), "kind": kind})

matched_codes = {code for _, code in matched}
summary = {
    "items": len(items), "fields_missing_as_null": missing,
    "purpose_x_kind": {f"{a}|{b}": n for (a, b), n in kinds.items()},
    "cert_years": dict(sorted(years.items(), key=lambda kv: str(kv[0]))),
    "national_complexes": len(rows), "national_unparsed": nat_unparsed,
    "residential_outcome": dict(outcome), "residential_outcome_by_kind": {k: dict(v) for k, v in by_kind.items()},
    "matched_distinct_complexes": len(matched_codes),
    "matched_complexes_with_energy_rows_table": len(matched_codes & energy_codes),
    "matched_main_cert_complexes_with_energy_table": len({c for it, c in matched if it.get("CRTIF_KIND") == "본인증"} & energy_codes),
}
(out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
(out_dir / "samples.json").write_text(json.dumps(samples, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False))
