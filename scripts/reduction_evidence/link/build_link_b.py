"""Step B of the complex <-> parcel link: groups, year sums and the checks fixed in
complex-parcel-link-2026-11-20.md section 3 (electricity 0.80-1.25, floor area 0.80-1.25, gas presence).

Reads work/link_a.csv and the read-only exports e2/e4/e5/e6; writes the final files next to this script:
complex_parcel_link.csv, link_groups.csv, link_group_year.csv, complex_link_summary.csv, link_summary.json.
Usage: python build_link_b.py
"""
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _paths import data  # noqa: E402

HERE = Path(__file__).parent
WORK = data("link") / "work"
OUT = data("link")   # results outside Git
csv.field_size_limit(10**9)
YEARS = ["2021", "2022", "2023", "2024", "2025"]   # 2020 has provider gaps (DATA_STANDARD section 4)
LOW, HIGH = 0.80, 1.25


def rows(path):
    with open(path, encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f)


def num(v):
    return float(v) if v not in (None, "") else None


complexes = {c["kapt_code"]: c for c in rows(WORK / "e2_complexes.csv")}
notes = {r["kapt_code"]: r["notes"] for r in rows(WORK / "complex_notes.csv")}
link = list(rows(WORK / "link_a.csv"))
register = {r["pnu"]: r for r in rows(WORK / "e4_register.csv")}

parcel_year = defaultdict(dict)        # key -> {(year, kind): (months, kwh)}  kind: GAS / ELEC_HUB
for r in rows(WORK / "e5_parcel_year.csv"):
    key = (r["sigungu_code"], r["bjdong_code"], r["lot_type"], r["bun"], r["ji"])
    kind = "GAS" if r["energy_type"] == "GAS" else ("ELEC_HUB" if r["source"] != "K-apt" else "ELEC_KAPT")
    parcel_year[key][(r["y"], kind)] = (int(r["months"]), num(r["kwh"]))
kapt_year = {(r["complex_code"], r["y"]): (int(r["elec_months"]), num(r["elec_kwh"])) for r in rows(WORK / "e6_kapt_year.csv")}


def key_of(r):
    return (r["sigungu_code"], r["bjdong_code"], r["lot_type"], r["bun"], r["ji"])


# --- groups: connected components over linked rows
parent = {}


def find(x):
    while parent.setdefault(x, x) != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


linked = [r for r in link if r["has_hub_rows"] == "1"]
for r in linked:
    parent[find(("c", r["kapt_code"]))] = find(("p", key_of(r)))
members = defaultdict(lambda: {"c": set(), "p": set()})
for node in list(parent):
    members[find(node)][node[0]].add(node[1])
groups = {}
for i, (_, m) in enumerate(sorted(members.items(), key=lambda kv: min(kv[1]["c"])), 1):
    groups[f"G{i:04d}"] = m
group_of_complex = {c: g for g, m in groups.items() for c in m["c"]}
complexes_on_parcel = Counter(key_of(r) for r in linked)
parcels_of_complex = Counter(r["kapt_code"] for r in linked)


def full_years(key, kind):
    return [y for y in YEARS if parcel_year[key].get((y, kind), (0, None))[0] == 12]


def year_of(c):
    d = (c["approval_date"] or "")[:4]
    return int(d) if d.isdigit() else None


# --- per group-year sums
group_year, group_rows = [], []
for g, m in groups.items():
    cs = [complexes[c] for c in sorted(m["c"])]
    ps = sorted(m["p"])
    gas_any = [p for p in ps if any(parcel_year[p].get((y, "GAS"), (0, 0))[0] for y in ["2020", *YEARS])]
    per_year = {}
    for y in YEARS:
        row = {"group_id": g, "year": y}
        for kind, label in (("GAS", "gas"), ("ELEC_HUB", "elec_hub")):
            have = [p for p in ps if parcel_year[p].get((y, kind), (0, None))[0] > 0]
            full = [p for p in have if parcel_year[p][(y, kind)][0] == 12]
            row[f"{label}_parcels_with_rows"], row[f"{label}_parcels_12m"] = len(have), len(full)
            row[f"{label}_kwh"] = sum(parcel_year[p][(y, kind)][1] for p in full) if have and len(have) == len(full) else None
        k = [kapt_year.get((c["kapt_code"], y), (0, None)) for c in cs]
        row["kapt_elec_complexes_12m"] = sum(1 for months, _ in k if months == 12)
        row["kapt_elec_kwh"] = sum(v for _, v in k) if all(months == 12 for months, _ in k) else None
        row["gas_parcels_any_year"] = len(gas_any)
        per_year[y] = row
        group_year.append(row)
    # checks
    elec_year = next((y for y in reversed(YEARS) if per_year[y]["elec_hub_kwh"] and per_year[y]["kapt_elec_kwh"]), None)
    elec_ratio = per_year[elec_year]["elec_hub_kwh"] / per_year[elec_year]["kapt_elec_kwh"] if elec_year else None
    gfa_kapt = [num(c["gross_floor_area_m2"]) for c in cs]
    gfa_kapt = sum(gfa_kapt) if all(gfa_kapt) else None
    pnus = [f"{p[0]}{p[1]}{'2' if p[2] == '1' else '1'}{p[3]}{p[4]}" for p in ps]
    reg = [num(register[x]["gfa_m2"]) for x in pnus if x in register and num(register[x]["gfa_m2"])]
    gfa_reg = sum(reg) if reg else None
    area_ratio = gfa_reg / gfa_kapt if gfa_reg and gfa_kapt else None
    heats = sorted({c["heating_type"] or "" for c in cs})
    ys = [year_of(c) for c in cs if year_of(c)]
    has_gas = bool(gas_any)
    individual = any("개별" in h for h in heats)
    group_rows.append({
        "group_id": g, "group_type": f"{'1' if len(cs) == 1 else 'N'}:{'1' if len(ps) == 1 else 'N'}",
        "sigungu_code": ps[0][0], "kapt_codes": "+".join(c["kapt_code"] for c in cs), "n_complexes": len(cs), "n_parcels": len(ps),
        "n_gas_parcels": len(gas_any), "methods": "+".join(sorted({r["method"] for r in linked if r["kapt_code"] in m["c"]})),
        "heating_types": "|".join(heats), "approval_year_min": min(ys) if ys else None, "approval_year_max": max(ys) if ys else None,
        "mixed": int(len(heats) > 1 or (bool(ys) and max(ys) - min(ys) > 4)),
        "households": sum(int(c["households"]) for c in cs) if all(c["households"] for c in cs) else None,
        "gfa_kapt_m2": gfa_kapt, "gfa_register_m2": round(gfa_reg, 2) if gfa_reg else None,
        "area_ratio": round(area_ratio, 4) if area_ratio else None,
        "check_area": "NO_BASIS" if area_ratio is None else ("OK" if LOW <= area_ratio <= HIGH else "SUSPECT"),
        "elec_check_year": elec_year, "elec_ratio": round(elec_ratio, 4) if elec_ratio else None,
        "check_elec": "NO_BASIS" if elec_ratio is None else ("OK" if LOW <= elec_ratio <= HIGH else "SUSPECT"),
        "check_gas": ("INDIVIDUAL_NO_GAS" if individual and not has_gas else "NON_INDIVIDUAL_WITH_GAS" if not individual and has_gas else "OK"),
        "gas_full_years": ";".join(y for y in YEARS if per_year[y]["gas_kwh"] is not None),
    })


# check v2 (2026-11-20, after v1 failed: K-apt electricity is the households' own use, so 건축HUB / K-apt centres on ~1.3).
# Lower bound of v1 kept (0.80); upper bound = median ratio x 1.25. v1 column is kept as it was.
_ratios = [g["elec_ratio"] for g in group_rows if g["elec_ratio"]]
ELEC_MEDIAN = statistics.median(_ratios)
for g in group_rows:
    r = g["elec_ratio"]
    g["check_elec_v2"] = "NO_BASIS" if not r else ("LOW" if r < LOW else "HIGH" if r > ELEC_MEDIAN * HIGH else "OK")


def write(name, data, fields=None):
    with open(OUT / name, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields or list(data[0]))
        w.writeheader()
        w.writerows(data)


final = []
for r in link:
    k, c = key_of(r), complexes[r["kapt_code"]]
    is_linked = r["has_hub_rows"] == "1"
    final.append({
        "kapt_code": r["kapt_code"], "complex_name": c["name"], "sigungu_code": k[0], "bjdong_code": k[1], "lot_type": k[2], "bun": k[3], "ji": k[4],
        "pnu": r["pnu"], "method": r["method"], "linked": r["has_hub_rows"],
        "gas_months": r["gas_months"], "elec_hub_months": r["elec_hub_months"],
        "gas_full_years": ";".join(full_years(k, "GAS")) if is_linked else "", "elec_hub_full_years": ";".join(full_years(k, "ELEC_HUB")) if is_linked else "",
        "n_complexes_on_parcel": complexes_on_parcel[k] if is_linked else "", "n_linked_parcels_of_complex": parcels_of_complex[r["kapt_code"]],
        "group_id": group_of_complex.get(r["kapt_code"], "") if is_linked else "", "parcel_address": r["parcel_address"],
    })
write("complex_parcel_link.csv", final)
write("link_groups.csv", group_rows)
write("link_group_year.csv", group_year)

group_by_id = {g["group_id"]: g for g in group_rows}
cand_by_complex = defaultdict(list)
for r in link:
    cand_by_complex[r["kapt_code"]].append(r)
summary = []
for code, c in complexes.items():
    g = group_of_complex.get(code)
    hh = int(c["households"]) if c["households"] else None
    if g:
        why = ""
    elif hh is not None and hh < 200:
        why = "UNDER_200_HOUSEHOLDS"
    elif cand_by_complex[code]:
        why = "CANDIDATE_WITHOUT_HUB_ROWS"
    else:
        why = "NO_CANDIDATE"
    summary.append({
        "kapt_code": code, "complex_name": c["name"], "sigungu_code": (c["bjd_code"] or "")[:5], "heating_type": c["heating_type"],
        "approval_year": year_of(c), "households": hh, "gross_floor_area_m2": c["gross_floor_area_m2"],
        "linked": int(bool(g)), "n_linked_parcels": parcels_of_complex[code], "group_id": g or "",
        "group_type": group_by_id[g]["group_type"] if g else "", "methods": "+".join(sorted({r["method"] for r in cand_by_complex[code] if r["has_hub_rows"] == "1"})),
        "unlinked_reason": why, "address_notes": notes.get(code, ""),
        "check_elec": group_by_id[g]["check_elec"] if g else "", "check_elec_v2": group_by_id[g]["check_elec_v2"] if g else "", "check_area": group_by_id[g]["check_area"] if g else "",
        "check_gas": group_by_id[g]["check_gas"] if g else "", "gas_full_years": group_by_id[g]["gas_full_years"] if g else "",
    })
write("complex_link_summary.csv", summary)

ok = [g for g in group_rows if g["elec_ratio"]]
indiv = [s for s in summary if "개별" in (s["heating_type"] or "")]
by_sgg = defaultdict(Counter)
for s in summary:
    by_sgg[s["sigungu_code"]]["complexes"] += 1
    by_sgg[s["sigungu_code"]]["linked"] += s["linked"]
    if "개별" in (s["heating_type"] or ""):
        by_sgg[s["sigungu_code"]]["individual"] += 1
        by_sgg[s["sigungu_code"]]["individual_gas_year"] += bool(s["gas_full_years"])
result = {
    "complexes": len(summary), "linked_complexes": sum(s["linked"] for s in summary),
    "unlinked_reason": Counter(s["unlinked_reason"] for s in summary if not s["linked"]),
    "unlinked_200plus": sum(1 for s in summary if not s["linked"] and (s["households"] or 0) >= 200),
    "linked_rows_by_method": Counter(r["method"] for r in final if r["linked"] == "1"),
    "complexes_by_first_method": Counter(s["methods"] for s in summary if s["linked"]),
    "linked_parcels": len({r["pnu"] for r in final if r["linked"] == "1"}),
    "groups": len(group_rows), "group_types": Counter(g["group_type"] for g in group_rows),
    "groups_mixed": sum(g["mixed"] for g in group_rows),
    "check_elec": Counter(g["check_elec"] for g in group_rows), "elec_ratio_median": round(ELEC_MEDIAN, 4),
    "check_elec_v2": Counter(g["check_elec_v2"] for g in group_rows),
    "check_elec_v2_by_method": {m: Counter(g["check_elec_v2"] for g in group_rows if g["methods"] == m) for m in sorted({g["methods"] for g in group_rows})},
    "check_elec_v2_x_area": Counter(f'{g["check_elec_v2"]}/{g["check_area"]}' for g in group_rows),
    "individual_gas_year_by_v2": Counter(group_by_id[s["group_id"]]["check_elec_v2"] for s in summary if s["gas_full_years"] and "개별" in (s["heating_type"] or "")),
    "check_area": Counter(g["check_area"] for g in group_rows),
    "check_gas": Counter(g["check_gas"] for g in group_rows),
    "check_elec_by_method": {m: Counter(g["check_elec"] for g in group_rows if g["methods"] == m) for m in sorted({g["methods"] for g in group_rows})},
    "elec_ratio_quantiles": [round(q, 4) for q in statistics.quantiles([g["elec_ratio"] for g in ok], n=20)] if len(ok) > 20 else None,
    "individual_complexes": len(indiv), "individual_linked": sum(s["linked"] for s in indiv),
    "individual_with_gas_full_year": sum(1 for s in indiv if s["gas_full_years"]),
    "individual_gas_year_new_2017": sum(1 for s in indiv if s["gas_full_years"] and (s["approval_year"] or 0) >= 2017),
    "individual_gas_year_old_2008": sum(1 for s in indiv if s["gas_full_years"] and s["approval_year"] and s["approval_year"] <= 2008),
    "by_sigungu": {k: dict(v) for k, v in sorted(by_sgg.items())},
}
(OUT / "link_summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=1))
