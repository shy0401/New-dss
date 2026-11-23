"""A2 pair comparison rerun (gate G1), rules fixed in scripts/reduction_evidence/rules/pair-comparison-rerun-2026-11-20.md sections 1-4.

Reads ../link/link_groups.csv and ../link/link_group_year.csv (built from read-only DB exports); writes pairs.csv, strata.csv
and pair_result.json next to this script. Usage: python pair_compare.py
"""
import csv
import json
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _paths import data  # noqa: E402

HERE = Path(__file__).parent
LINK = data("link")
OUT = data("pair")   # results outside Git
YEARS = [2021, 2022, 2023, 2024, 2025]
GAS_FACTOR, ELEC_FACTOR = 0.1819, 0.4330          # DATA_STANDARD 5.5, 5.6 (fixed factor for comparisons)
G1_LOW, G1_HIGH = -25.8, -20.5
SEED, DRAWS = 20261120, 10000
CITY = {"52111": "52110", "52113": "52110", "41111": "41110", "41113": "41110", "41115": "41110", "41117": "41110"}


def rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def num(v):
    return float(v) if v not in ("", None) else None


groups = {g["group_id"]: g for g in rows(LINK / "link_groups.csv")}
year_rows = defaultdict(dict)
for r in rows(LINK / "link_group_year.csv"):
    year_rows[r["group_id"]][int(r["year"])] = r


def band(households):
    return "~299" if households < 300 else "300~499" if households < 500 else "500~999" if households < 1000 else "1000~"


def build(city=False, no_band=False, area_ok_only=False, with_point=False, limit=(20.0, 200.0), lag=2, region=None):
    """Eligible complexes with their usable years. Returns (units, dropped counters)."""
    units, dropped = [], Counter()
    for g in groups.values():
        if g["heating_types"] != "개별난방" or g["n_complexes"] != "1":
            continue
        year, gfa, hh = num(g["approval_year_min"]), num(g["gfa_kapt_m2"]), num(g["households"])
        if not year or not gfa or not hh:
            dropped["no_year_area_households"] += 1
            continue
        era = "new" if year >= 2017 else "old" if year <= 2008 else None
        if era is None:
            continue
        if "POINT" in g["methods"] and not with_point:
            dropped["point_link"] += 1
            continue
        if g["check_area"] == "SUSPECT" or (area_ok_only and g["check_area"] != "OK"):
            dropped["area_check"] += 1
            continue
        if region == "jeonbuk" and not g["sigungu_code"].startswith("52"):
            continue
        if region == "other" and g["sigungu_code"].startswith("52"):
            continue
        gas, elec = {}, {}
        for y in YEARS:
            r = year_rows[g["group_id"]].get(y)
            if y < year + lag or not r or num(r["gas_kwh"]) is None:
                continue
            value = num(r["gas_kwh"]) / gfa
            if limit and not (limit[0] <= value <= limit[1]):
                dropped["gas_out_of_range_years"] += 1
                continue
            gas[y] = value
            if num(r["kapt_elec_kwh"]) is not None:
                elec[y] = num(r["kapt_elec_kwh"]) / gfa
        if not gas:
            dropped[f"no_usable_gas_year_{era}"] += 1
            continue
        sgg = CITY.get(g["sigungu_code"], g["sigungu_code"]) if city else g["sigungu_code"]
        units.append({"id": g["group_id"], "kapt": g["kapt_codes"], "era": era, "sgg": g["sigungu_code"],
                      "stratum": (sgg, "all" if no_band else band(hh)), "households": hh, "year": int(year), "gas": gas, "elec": elec})
    return units, dropped


def pair_value(new, old, latest_only=False):
    common = sorted(set(new["gas"]) & set(old["gas"]))
    if not common:
        return None
    if latest_only:
        common = common[-1:]
    out = {"years": common, "gas_new": statistics.mean(new["gas"][y] for y in common), "gas_old": statistics.mean(old["gas"][y] for y in common)}
    both = [y for y in common if y in new["elec"] and y in old["elec"]]
    if both:
        out["elec_new"] = statistics.mean(new["elec"][y] for y in both)
        out["elec_old"] = statistics.mean(old["elec"][y] for y in both)
        out["carbon_new"] = statistics.mean(new["gas"][y] * GAS_FACTOR + new["elec"][y] * ELEC_FACTOR for y in both)
        out["carbon_old"] = statistics.mean(old["gas"][y] * GAS_FACTOR + old["elec"][y] * ELEC_FACTOR for y in both)
    return out


def match(units, latest_only=False):
    strata = defaultdict(lambda: {"new": [], "old": []})
    for u in units:
        strata[u["stratum"]][u["era"]].append(u)
    pairs = []
    for key in sorted(strata):
        used = set()
        for new in sorted(strata[key]["new"], key=lambda u: u["kapt"]):
            for old in sorted(strata[key]["old"], key=lambda u: (abs(u["households"] - new["households"]), u["kapt"])):
                if old["id"] in used:
                    continue
                value = pair_value(new, old, latest_only)
                if value is None:
                    continue
                used.add(old["id"])
                pairs.append({"stratum": key, "new": new, "old": old, **value})
                break
    return pairs, strata


def match_all_old(units):
    """S3: each new complex against the median of every old complex of its stratum, year by year."""
    strata = defaultdict(lambda: {"new": [], "old": []})
    for u in units:
        strata[u["stratum"]][u["era"]].append(u)
    pairs = []
    for key in sorted(strata):
        for new in strata[key]["new"]:
            years = [y for y in sorted(new["gas"]) if any(y in o["gas"] for o in strata[key]["old"])]
            if not years:
                continue
            ref = {y: statistics.median(o["gas"][y] for o in strata[key]["old"] if y in o["gas"]) for y in years}
            pairs.append({"stratum": key, "new": new, "old": None, "years": years,
                          "gas_new": statistics.mean(new["gas"][y] for y in years), "gas_old": statistics.mean(ref[y] for y in years)})
    return pairs, strata


def stats(pairs, what="gas", boot=True):
    sel = [p for p in pairs if f"{what}_new" in p]
    diffs = [(p[f"{what}_new"] / p[f"{what}_old"] - 1) * 100 for p in sel]
    if not diffs:
        return {"pairs": 0}
    out = {"pairs": len(diffs), "median_pct": round(statistics.median(diffs), 2), "mean_pct": round(statistics.mean(diffs), 2),
           "ratio_of_sums_pct": round((sum(p[f"{what}_new"] for p in sel) / sum(p[f"{what}_old"] for p in sel) - 1) * 100, 2),
           "share_new_lower_pct": round(100 * sum(1 for d in diffs if d < 0) / len(diffs), 1),
           "median_new": round(statistics.median(p[f"{what}_new"] for p in sel), 2), "median_old": round(statistics.median(p[f"{what}_old"] for p in sel), 2)}
    if boot and len(diffs) >= 5:
        rng = random.Random(SEED)
        meds = sorted(statistics.median(rng.choices(diffs, k=len(diffs))) for _ in range(DRAWS))
        out["median_ci95"] = [round(meds[int(DRAWS * 0.025)], 2), round(meds[int(DRAWS * 0.975) - 1], 2)]
        means = sorted(statistics.mean(rng.choices(diffs, k=len(diffs))) for _ in range(DRAWS))
        out["mean_ci95"] = [round(means[int(DRAWS * 0.025)], 2), round(means[int(DRAWS * 0.975) - 1], 2)]
    return out


# ---------------------------------------------------------------- main run (rules v1)
units, dropped = build()
pairs, strata = match(units)
main = {"gas": stats(pairs, "gas"), "electricity_household": stats(pairs, "elec"), "carbon_gas_plus_household_elec": stats(pairs, "carbon")}
primary = main["gas"]["median_pct"]
result = {
    "rule": "v1 (pair-comparison-rerun-2026-11-20.md)",
    "eligible": {"new": sum(1 for u in units if u["era"] == "new"), "old": sum(1 for u in units if u["era"] == "old")},
    "dropped": dict(dropped), "strata_with_both": sum(1 for s in strata.values() if s["new"] and s["old"]),
    "new_without_pair": sum(1 for u in units if u["era"] == "new") - len(pairs),
    "pairs_by_sigungu": dict(Counter(p["new"]["sgg"] for p in pairs)),
    "pairs_by_band": dict(Counter(p["stratum"][1] for p in pairs)),
    "years_used": dict(Counter(y for p in pairs for y in p["years"])),
    "main": main, "G1_range": [G1_LOW, G1_HIGH], "G1_primary_median_pct": primary,
    "G1": "PASS" if G1_LOW <= primary <= G1_HIGH else "FAIL",
}

sens = {}
for name, kw, how in (
    ("S1_city", {"city": True}, {}), ("S2_no_band", {"no_band": True}, {}), ("S4_area_ok_only", {"area_ok_only": True}, {}),
    ("S5_with_point", {"with_point": True}, {}), ("S6_latest_year", {}, {"latest_only": True}), ("S7_no_range", {"limit": None}, {}),
    ("S8_lag1", {"lag": 1}, {}), ("S9_jeonbuk", {"region": "jeonbuk"}, {}), ("S9_other", {"region": "other"}, {}),
):
    u, _ = build(**kw)
    p, _ = match(u, **how)
    sens[name] = {"gas": stats(p, "gas"), "electricity_household": stats(p, "elec", boot=False)}
u, _ = build()
p, _ = match_all_old(u)
sens["S3_all_old_median"] = {"gas": stats(p, "gas")}
result["sensitivity"] = sens

with open(OUT / "pairs.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["sigungu_code", "household_band", "new_kapt", "new_group", "new_approval_year", "new_households", "old_kapt", "old_group",
                "old_approval_year", "old_households", "years", "gas_new_kwh_m2", "gas_old_kwh_m2", "gas_diff_pct",
                "elec_new_kwh_m2", "elec_old_kwh_m2", "elec_diff_pct", "carbon_new_kg_m2", "carbon_old_kg_m2", "carbon_diff_pct"])
    for q in pairs:
        n, o = q["new"], q["old"]
        d = lambda k: round((q[f"{k}_new"] / q[f"{k}_old"] - 1) * 100, 2) if f"{k}_new" in q else ""
        v = lambda k: round(q[k], 3) if k in q else ""
        w.writerow([q["stratum"][0], q["stratum"][1], n["kapt"], n["id"], n["year"], int(n["households"]), o["kapt"], o["id"], o["year"], int(o["households"]),
                    ";".join(map(str, q["years"])), v("gas_new"), v("gas_old"), d("gas"), v("elec_new"), v("elec_old"), d("elec"),
                    v("carbon_new"), v("carbon_old"), d("carbon")])
with open(OUT / "strata.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["sigungu_code", "household_band", "new_eligible", "old_eligible", "pairs"])
    count = Counter(q["stratum"] for q in pairs)
    for key in sorted(strata):
        w.writerow([key[0], key[1], len(strata[key]["new"]), len(strata[key]["old"]), count[key]])
(OUT / "pair_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=1))
