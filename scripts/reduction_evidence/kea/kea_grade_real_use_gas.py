"""Read-only: certified vs non-certified complexes, gas (건축HUB, kWh) per m2. Rule fixed 2026-11-20 before results:
scripts/reduction_evidence/rules/kea-grade-real-use-rule-2026-11-20.md section 7. Uses files only (no DB).

Usage: python kea_grade_real_use_gas.py <raw kea dir> <match v2 dir> <link dir> <out dir>
"""
import csv
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

raw_dir, match_dir, link_dir, out_dir = (Path(a) for a in sys.argv[1:5])
out_dir.mkdir(parents=True, exist_ok=True)
YEARS = ("2021", "2022", "2023", "2024")
SEED, BOOT = 20261120, 2000


def read(path):
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


items = {}
for f in sorted((raw_dir / "pages").glob("page-*.json")):
    got = json.loads(f.read_text(encoding="utf-8"))["response"]["body"]["items"]["item"]
    for it in got if isinstance(got, list) else [got]:
        items[it["RQID"]] = it

summary = {r["kapt_code"]: r for r in read(link_dir / "complex_link_summary.csv")}
groups = {r["group_id"]: r for r in read(link_dir / "link_groups.csv")}
gy = defaultdict(dict)
for r in read(link_dir / "link_group_year.csv"):
    gy[r["group_id"]][r["year"]] = r

# certified group: same rule as the electricity comparison (main cert, households within 10%, latest cert)
cert = {}
for row in read(match_dir / "matches.csv"):
    if row["CRTIF_KIND"] != "본인증" or row["in_energy_table"] != "True":
        continue
    it, s = items[row["RQID"]], summary.get(row["kapt_code"])
    hh = it.get("HSHLD_NUMB")
    if not s or hh in (None, "NULL", "0") or not s["households"] or abs(int(float(hh)) - int(float(s["households"]))) / float(s["households"]) > 0.10:
        continue
    prev = cert.get(row["kapt_code"])
    if prev is None or (it.get("CRTIF_ISU_DD") or "") > (prev[1] or ""):
        cert[row["kapt_code"]] = (it.get("GRD_NAME"), it.get("CRTIF_ISU_DD"))


def band(y):
    if y <= 2000:
        return "~2000"
    for lo in (2001, 2006, 2011, 2016):
        if y <= lo + 4:
            return f"{lo}-{lo + 4}"
    return "2021~"


excluded = defaultdict(int)
units = {}
for code, s in summary.items():
    g = groups.get(s["group_id"]) if s["group_id"] else None
    if not g:
        excluded["연결 안 됨"] += 1
        continue
    if g["n_complexes"] != "1" or g["mixed"] != "0" or g["check_area"] != "OK":
        excluded["묶음 조건(단지 하나 · 섞임 없음 · 연면적 맞음) 아님"] += 1
        continue
    if "개별" not in (s["heating_type"] or ""):
        excluded["개별난방 아님"] += 1
        continue
    ay = int(s["approval_year"]) if s["approval_year"] else None
    area = float(s["gross_floor_area_m2"]) if s["gross_floor_area_m2"] else 0
    if ay is None or area <= 0:
        excluded["사용승인 · 연면적 없음"] += 1
        continue
    vals = []
    for y in YEARS:
        r = gy[g["group_id"]].get(y)
        if not r or int(y) <= ay or not r["gas_kwh"]:
            continue
        if int(r["gas_parcels_12m"]) == int(r["gas_parcels_any_year"]) > 0:
            vals.append(float(r["gas_kwh"]) / area)
    if not vals:
        excluded["가스 지번 전부 12개월인 해 없음"] += 1
        continue
    units[code] = {"stratum": (s["sigungu_code"], band(ay)), "v": statistics.median(vals),
                   "certified": code in cert, "grade": cert.get(code, (None,))[0]}


def grade_group(gr):
    if gr in ("1+등급", "1++등급", "1+++등급"):
        return "상위(1+ 이상)"
    if gr == "1등급":
        return "1등급"
    return "2등급 이하" if gr else None


def strata_of(rows, keep):
    st = defaultdict(lambda: ([], []))
    for u in rows:
        if u["certified"]:
            if keep(u):
                st[u["stratum"]][0].append(u["v"])
        else:
            st[u["stratum"]][1].append(u["v"])
    return {k: v for k, v in st.items() if v[0] and v[1]}


def weighted(used, pick=lambda xs, rng: xs, rng=None):
    total = n_all = 0
    for c, n in used.values():
        c2, n2 = pick(c, rng), pick(n, rng)
        total += len(c2) * (statistics.median(c2) - statistics.median(n2)) / statistics.median(n2)
        n_all += len(c2)
    return total / n_all


def boot(rows, keep=lambda u: True):
    used = strata_of(rows, keep)
    if not used:
        return None
    point = weighted(used)
    rng = random.Random(SEED)
    sims = sorted(weighted(used, lambda xs, r: [r.choice(xs) for _ in xs], rng) for _ in range(BOOT))
    return {"diff": round(point, 4), "ci95": [round(sims[int(0.025 * BOOT)], 4), round(sims[int(0.975 * BOOT) - 1], 4)],
            "strata": len(used), "certified": sum(len(v[0]) for v in used.values()),
            "comparison": sum(len(v[1]) for v in used.values())}


rows = list(units.values())
result = {"certified_group_complexes": len(cert), "certified_usable": sum(u["certified"] for u in rows),
          "usable_complexes": len(rows), "excluded": dict(excluded), "gas_kwh_per_m2": boot(rows), "by_grade": {}}
for gname in ("상위(1+ 이상)", "1등급", "2등급 이하"):
    r = boot(rows, lambda u, gname=gname: grade_group(u["grade"]) == gname)
    result["by_grade"][gname] = r if r and r["certified"] >= 10 else {"보고 안 함": "인증 단지 10곳 미만", "n": r["certified"] if r else 0}
(out_dir / "result_gas.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
