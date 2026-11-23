"""Read-only: certified vs non-certified K-apt complexes, electricity per m2 (rule fixed 2026-11-20 before results:
scripts/reduction_evidence/rules/kea-grade-real-use-rule-2026-11-20.md). Changes no table.

Usage (inside api container):
  python kea_grade_real_use.py /data/raw/kea_building_rating/<date> /data/ops/20261120-kea-match-v2 /data/ops/<run>
"""
import csv
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import text

from app.db import Session

raw_dir, match_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
out_dir.mkdir(parents=True, exist_ok=True)
YEARS = range(2021, 2025)
SEED, BOOT = 20261120, 2000

items = {}
for f in sorted((raw_dir / "pages").glob("page-*.json")):
    got = json.loads(f.read_text(encoding="utf-8"))["response"]["body"]["items"]["item"]
    for it in got if isinstance(got, list) else [got]:
        items[it["RQID"]] = it

with Session() as db:
    cx = {r[0]: r for r in db.execute(text(
        "select kapt_code, gross_floor_area_m2, households, approval_date, heating_type, bjd_code from apartment_complexes"))}
    months = db.execute(text(
        "select complex_code, year_month, electricity_quantity from apartment_energy_monthly "
        "where quality_status = 'SUCCESS' and electricity_quantity is not null")).all()

# certified group: one match, main cert, households within 10%; latest cert date per complex
cert = {}
for row in csv.DictReader((match_dir / "matches.csv").open(encoding="utf-8")):
    if row["CRTIF_KIND"] != "본인증" or row["in_energy_table"] != "True":
        continue
    it, c = items[row["RQID"]], cx.get(row["kapt_code"])
    hh = it.get("HSHLD_NUMB")
    if not c or hh in (None, "NULL", "0") or not c[2] or abs(int(float(hh)) - c[2]) / c[2] > 0.10:
        continue
    prev = cert.get(row["kapt_code"])
    if prev is None or (it.get("CRTIF_ISU_DD") or "") > (prev[1] or ""):
        cert[row["kapt_code"]] = (it.get("GRD_NAME"), it.get("CRTIF_ISU_DD"))

by_year = defaultdict(lambda: defaultdict(dict))
for code, ym, kwh in months:
    digits = "".join(ch for ch in ym if ch.isdigit())
    y, m = int(digits[:4]), int(digits[4:6])
    if y in YEARS:
        by_year[code][y][m] = kwh


def approval_year(c):
    d = "".join(ch for ch in (c[3] or "") if ch.isdigit())
    return int(d[:4]) if len(d) >= 4 else None


def band(y):
    if y is None:
        return None
    if y <= 2000:
        return "~2000"
    for lo in (2001, 2006, 2011, 2016):
        if y <= lo + 4:
            return f"{lo}-{lo + 4}"
    return "2021~"


excluded = defaultdict(int)
units = {}
for code, c in cx.items():
    ay = approval_year(c)
    if not c[1] or c[1] <= 0:
        excluded["연면적 없음"] += 1
        continue
    if ay is None or not c[4] or not c[5]:
        excluded["사용승인 · 난방 · 시군구 없음"] += 1
        continue
    per_m2, per_hh = [], []
    for y in YEARS:
        if y <= ay:
            continue
        ms = by_year[code].get(y, {})
        if len(ms) == 12:
            total = sum(ms.values())
            per_m2.append(total / c[1])
            if c[2]:
                per_hh.append(total / c[2])
    if not per_m2:
        excluded["12개월 다 있는 해 없음"] += 1
        continue
    units[code] = {"stratum": (c[5][:5], c[4], band(ay)), "kwh_m2": statistics.median(per_m2),
                   "kwh_hh": statistics.median(per_hh) if per_hh else None, "certified": code in cert,
                   "grade": cert.get(code, (None,))[0]}


def grade_group(g):
    if g in ("1+등급", "1++등급", "1+++등급"):
        return "상위(1+ 이상)"
    if g == "1등급":
        return "1등급"
    return "2등급 이하" if g else None


def estimate(rows, key, cert_filter=lambda u: True):
    strata = defaultdict(lambda: ([], []))
    for u in rows:
        if u[key] is None:
            continue
        if u["certified"]:
            if cert_filter(u):
                strata[u["stratum"]][0].append(u[key])
        else:
            strata[u["stratum"]][1].append(u[key])
    used = {s: v for s, v in strata.items() if v[0] and v[1]}
    n_cert = sum(len(v[0]) for v in used.values())
    if not n_cert:
        return None, used
    return sum(len(c) * (statistics.median(c) - statistics.median(n)) / statistics.median(n) for c, n in used.values()) / n_cert, used


def boot(rows, key, cert_filter=lambda u: True):
    point, used = estimate(rows, key, cert_filter)
    if point is None:
        return None
    rng = random.Random(SEED)
    sims = []
    for _ in range(BOOT):
        total, n_all = 0.0, 0
        for c, n in used.values():
            cs = [rng.choice(c) for _ in c]
            ns = [rng.choice(n) for _ in n]
            total += len(cs) * (statistics.median(cs) - statistics.median(ns)) / statistics.median(ns)
            n_all += len(cs)
        sims.append(total / n_all)
    sims.sort()
    return {"diff": round(point, 4), "ci95": [round(sims[int(0.025 * BOOT)], 4), round(sims[int(0.975 * BOOT) - 1], 4)],
            "strata": len(used), "certified": sum(len(v[0]) for v in used.values()),
            "comparison": sum(len(v[1]) for v in used.values())}


rows = list(units.values())
cert_rows = [u for u in rows if u["certified"]]
in_strata = estimate(rows, "kwh_m2")[1]
result = {
    "certified_group_complexes": len(cert), "certified_with_usable_years": len(cert_rows),
    "certified_left_out_no_comparison_stratum": len(cert_rows) - sum(len(v[0]) for v in in_strata.values()),
    "excluded_complexes": dict(excluded), "usable_complexes": len(rows),
    "electricity_kwh_per_m2": boot(rows, "kwh_m2"),
    "electricity_kwh_per_household": boot(rows, "kwh_hh"),
    "by_grade_kwh_per_m2": {},
}
for g in ("상위(1+ 이상)", "1등급", "2등급 이하"):
    r = boot(rows, "kwh_m2", lambda u, g=g: grade_group(u["grade"]) == g)
    result["by_grade_kwh_per_m2"][g] = r if r and r["certified"] >= 10 else {"보고 안 함": "인증 단지 10곳 미만", "n": r["certified"] if r else 0}
(out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
