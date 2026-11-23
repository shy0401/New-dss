"""Read-only: address-matching rule v2 (fixed 2026-11-20 from v1 failure samples, before running).

Usage (inside api container): python kea_match_v2.py /data/raw/kea_building_rating/<date> /data/ops/<run>
Writes summary.json, samples.json and matches.csv (cert row -> kapt_code, step). Changes no table.
"""
import csv
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


SIDO = {"서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구", "인천광역시": "인천", "광주광역시": "광주",
        "대전광역시": "대전", "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기", "강원특별자치도": "강원",
        "강원도": "강원", "충청북도": "충북", "충청남도": "충남", "전북특별자치도": "전북", "전라북도": "전북",
        "전라남도": "전남", "경상북도": "경북", "경상남도": "경남", "제주특별자치도": "제주"}
SHORT = set(SIDO.values())
PARCEL = re.compile(r"(\S+?(?:동|리|가))\s*(산\s*)?(\d+)(?:-(\d+))?")
ROAD = re.compile(r"(\S+?(?:로|길))\s*(\d+(?:번?길))?\s+(\d+)(?:-(\d+))?")
BLOCK = re.compile(r"\S*(?:블럭|블록|BL|로트|생활권)\S*", re.I)
ADMIN_DONG = re.compile(r"^(.+?)\d+동$")


def sido_and_rest(addr, fallback):
    first, _, rest = addr.partition(" ")
    if first in SIDO:
        return SIDO[first], rest
    if first in SHORT:
        return first, rest
    return val(fallback), addr


def clean(addr):
    addr = re.sub(r"\([^)]*\)", " ", addr)
    addr = BLOCK.sub(" ", addr)
    addr = re.sub(r"외\s*\d+\s*필지", " ", addr)
    return addr.replace("번지", " ").replace("일대", " ").replace("일원", " ")


def parcel(addr):
    m = PARCEL.search(clean(addr))
    if not m:
        return None
    return (m.group(1), "산" if m.group(2) else "", int(m.group(3)), int(m.group(4) or 0)), clean(addr)[: m.start()]


def road(addr):
    m = ROAD.search(clean(addr))
    if not m:
        return None
    return (m.group(1) + (m.group(2) or ""), int(m.group(3)), int(m.group(4) or 0))


def norm_sgg(s):
    return re.sub(r"\s|시", "", s or "")


with Session() as db:
    nat = db.execute(text("select kapt_code, address from national_complexes")).all()
    apt = db.execute(text("select kapt_code, road_address from apartment_complexes")).all()
energy_codes = {r[0] for r in apt}

pidx = defaultdict(list)
for code, address in nat:
    if not address:
        continue
    sido, rest = sido_and_rest(address, None)
    p = parcel(rest)
    if sido and p:
        pidx[(sido,) + p[0]].append((code, p[1]))
ridx = defaultdict(list)
for code, address in apt:
    if not address:
        continue
    sido, rest = sido_and_rest(address, None)
    r = road(rest)
    if sido and r:
        ridx[(sido,) + r].append(code)


def pick(cands, prefix):
    if len(cands) > 1:
        a = norm_sgg(prefix)
        cands = [c for c in cands if a and (a in norm_sgg(c[1]) or norm_sgg(c[1]) in a)] or cands
    return cands


outcome, by_kind, samples, rows = Counter(), defaultdict(Counter), defaultdict(list), []
for it in items:
    if it.get("PURPOSE_KIND_NAME") != "주거용":
        continue
    kind = it.get("CRTIF_KIND")
    addr = val(it.get("LOC_ADDR")) or ""
    sido, rest = sido_and_rest(addr, it.get("RGN_SCT_NAME"))
    res, code = None, None
    p = parcel(rest)
    if p:
        cands = pick(pidx.get((sido,) + p[0], []), p[1])
        if not cands:
            m = ADMIN_DONG.match(p[0][0])
            if m:
                cands = pick(pidx.get((sido, m.group(1) + "동") + p[0][1:], []), p[1])
                if len(cands) == 1:
                    res, code = "행정동→법정동 일치", cands[0][0]
        elif len(cands) == 1:
            res, code = "지번 일치", cands[0][0]
        if res is None and len(cands) > 1:
            res = "여러 후보"
    if res is None:
        r = road(rest)
        if r:
            c = ridx.get((sido,) + r, [])
            if len(c) == 1:
                res, code = "도로명 일치", c[0]
            elif len(c) > 1:
                res = "여러 후보"
    if res is None:
        res = "불일치" if (p or road(rest)) else "지번 · 도로명 아님"
    outcome[res] += 1
    by_kind[kind][res] += 1
    if len(samples[res]) < 10:
        samples[res].append({"addr": addr, "sido": it.get("RGN_SCT_NAME"), "kind": kind})
    if code:
        rows.append({"RQID": it.get("RQID"), "CRTIF_NO": it.get("CRTIF_NO"), "CRTIF_KIND": kind, "GRD_NAME": it.get("GRD_NAME"),
                     "kapt_code": code, "step": res, "in_energy_table": code in energy_codes})

with (out_dir / "matches.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
main_energy = {r["kapt_code"] for r in rows if r["CRTIF_KIND"] == "본인증" and r["in_energy_table"]}
summary = {
    "residential": sum(outcome.values()), "outcome": dict(outcome), "by_kind": {k: dict(v) for k, v in by_kind.items()},
    "matched_distinct_complexes": len({r["kapt_code"] for r in rows}),
    "matched_in_energy_table": len({r["kapt_code"] for r in rows if r["in_energy_table"]}),
    "main_cert_in_energy_table": len(main_energy),
    "main_cert_in_energy_by_grade": dict(Counter(r["GRD_NAME"] for r in rows if r["CRTIF_KIND"] == "본인증" and r["in_energy_table"])),
}
(out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
(out_dir / "samples.json").write_text(json.dumps(samples, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False))
