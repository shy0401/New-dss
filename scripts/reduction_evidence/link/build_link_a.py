"""Step A of the complex <-> parcel link (rule v1, complex-parcel-link-2026-11-20.md sections 1-2).

Reads work/e1_parcels.csv, e2_complexes.csv, e3_point.csv (read-only DB exports) and writes
work/link_a.csv (one row = complex x candidate parcel) and work/linked_keys.sql (VALUES list for the year export).
Usage: python build_link_a.py
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
WORK = data("link") / "work"   # DB exports (e1-e4) and step-A outputs, outside Git
csv.field_size_limit(10**9)


def rows(name):
    with open(WORK / name, encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f)


LOT = re.compile(r"(\S+?(?:동|리|가|읍|면))\s+(산\s*)?(\d+)(?:-(\d+))?(?!\d)")
ROAD = re.compile(r"(\S+(?:로|길))\s+(\d+)(?:-(\d+))?(?!\d)")


def road_key(text):
    if not text:
        return None
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"(로)\s+(\d+번?길)", r"\1\2", text)
    m = ROAD.search(text)
    return (m.group(1), int(m.group(2)), int(m.group(3) or 0)) if m else None


# --- parcels of energy_monthly
parcels = {}                      # key -> row
dong_codes = defaultdict(set)     # (sgg, dong name) -> {(bjdong, previous word)}
road_index = defaultdict(set)     # (sgg, road, main, sub) -> {key}
for r in rows("e1_parcels.csv"):
    key = (r["sigungu_code"], r["bjdong_code"], r["lot_type"], r["bun"], r["ji"])
    r["gas_months"], r["elec_hub_months"] = int(r["gas_months"]), int(r["elec_hub_months"])
    r["hub"] = r["gas_months"] > 0 or r["elec_hub_months"] > 0
    parcels[key] = r
    words = [w for w in (r["plat"] or "").split() if w != "산" and not re.fullmatch(r"\d+(-\d+)?", w)]
    if len(words) >= 2:
        dong_codes[(key[0], words[-1])].add((key[1], words[-2]))
    rk = road_key(r["road"])
    if rk and r["hub"]:
        road_index[(key[0], *rk)].add(key)

point = defaultdict(list)
for r in rows("e3_point.csv"):
    p = r["pnu"]
    if len(p) == 19:
        point[r["kapt_code"]].append((p[:5], p[5:10], "0" if p[10] == "1" else "1", p[11:15], p[15:19]))


def addr_b_candidates(sgg, addr):
    m = LOT.search(addr or "")
    if not m:
        return [], "NO_LOT_IN_ADDRESS"
    name, mountain, bun, ji = m.group(1), bool(m.group(2)), int(m.group(3)), int(m.group(4) or 0)
    codes = dong_codes.get((sgg, name), set())
    if len({c for c, _ in codes}) > 1:
        before = (addr[: m.start()].split() or [""])[-1]
        codes = {(c, prev) for c, prev in codes if prev == before}
    bj = {c for c, _ in codes}
    if len(bj) != 1:
        return [], "DONG_NAME_NOT_FOUND" if not bj else "DONG_NAME_AMBIGUOUS"
    return [(sgg, next(iter(bj)), "1" if mountain else "0", f"{bun:04d}", f"{ji:04d}")], None


out, stats, complexes = [], Counter(), []
for c in rows("e2_complexes.csv"):
    complexes.append(c)
    sgg = (c["bjd_code"] or "")[:5]
    cand = {}                                      # key -> first method

    def add(key, method):
        cand.setdefault(key, method)

    if c["bjd_code"] and c["bun"]:
        add((sgg, c["bjd_code"][5:], "0", c["bun"].zfill(4), (c["ji"] or "0").zfill(4)), "REP")
    addr_list = json.loads(c["addr_list"]) if c["addr_list"] and c["addr_list"] != "null" else []
    addr_list = addr_list if isinstance(addr_list, list) else []
    notes = []
    for a in addr_list:
        if a.get("addrGbn") == "B":
            got, why = addr_b_candidates(sgg, a.get("addr"))
            for k in got:
                add(k, "ADDR_B")
            if why:
                notes.append(why)
    roads = [a.get("addr") for a in addr_list if a.get("addrGbn") == "R"] + [c["road_address"]]
    for text in roads:
        rk = road_key(text)
        if rk:
            for k in sorted(road_index.get((sgg, *rk), ())):
                add(k, "ROAD")
    linked = [k for k in cand if k in parcels and parcels[k]["hub"]]
    if not linked:
        for k in point.get(c["kapt_code"], []):
            add(k, "POINT")
        linked = [k for k in cand if k in parcels and parcels[k]["hub"]]
    c["_notes"] = ";".join(sorted(set(notes)))
    c["_linked"] = linked
    for k, method in cand.items():
        p = parcels.get(k)
        out.append({
            "kapt_code": c["kapt_code"], "sigungu_code": k[0], "bjdong_code": k[1], "lot_type": k[2], "bun": k[3], "ji": k[4],
            "pnu": f"{k[0]}{k[1]}{'2' if k[2] == '1' else '1'}{k[3]}{k[4]}", "method": method,
            "has_hub_rows": int(bool(p and p["hub"])),
            "gas_months": p["gas_months"] if p else 0, "elec_hub_months": p["elec_hub_months"] if p else 0,
            "parcel_address": (p or {}).get("plat", ""),
        })
    stats["complexes"] += 1
    stats["linked_complexes"] += bool(linked)

with open(WORK / "link_a.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0]))
    w.writeheader()
    w.writerows(out)
with open(WORK / "complex_notes.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["kapt_code", "notes", "n_linked"])
    for c in complexes:
        w.writerow([c["kapt_code"], c["_notes"], len(c["_linked"])])

keys = sorted({(r["sigungu_code"], r["bjdong_code"], r["lot_type"], r["bun"], r["ji"]) for r in out if r["has_hub_rows"]})
(WORK / "linked_keys.txt").write_text("\n".join(",".join(k) for k in keys), encoding="utf-8")
print(json.dumps({"complexes": stats["complexes"], "linked_complexes": stats["linked_complexes"],
                  "candidate_rows": len(out), "linked_rows": sum(r["has_hub_rows"] for r in out), "linked_parcels": len(keys),
                  "by_method_linked": Counter(r["method"] for r in out if r["has_hub_rows"]),
                  "by_method_all": Counter(r["method"] for r in out)}, ensure_ascii=False))
