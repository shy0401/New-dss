"""POST-HOC (added after seeing the G1 result; not used for the gate): the same 117 pairs with other denominators.

Reads pairs.csv (gas per K-apt gross floor area) and areas.csv (read-only DB export)."""
import csv
import random
import statistics
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _paths import data  # noqa: E402

HERE = Path(__file__).parent
rows = lambda n: list(csv.DictReader(open(data("pair") / n, encoding="utf-8-sig", newline="")))
num = lambda v: float(v) if v not in ("", None) else None
area = {r["kapt_code"]: r for r in rows("areas.csv")}
pairs = rows("pairs.csv")


def summary(diffs):
    rng = random.Random(20261120)
    meds = sorted(statistics.median(rng.choices(diffs, k=len(diffs))) for _ in range(10000))
    return f"n={len(diffs)} median={statistics.median(diffs):.2f}% ci95=({meds[250]:.2f}, {meds[9749]:.2f}) mean={statistics.mean(diffs):.2f}% lower={100 * sum(d < 0 for d in diffs) / len(diffs):.1f}%"


for label, key in (("per gross floor area (rule v1)", "gross_floor_area_m2"), ("per management area", "management_area_m2"), ("per household", "households")):
    diffs, share_new, share_old = [], [], []
    for p in pairs:
        n, o = area[p["new_kapt"]], area[p["old_kapt"]]
        dn, do, gn, go = num(n[key]), num(o[key]), num(n["gross_floor_area_m2"]), num(o["gross_floor_area_m2"])
        if not dn or not do:
            continue
        new, old = float(p["gas_new_kwh_m2"]) * gn / dn, float(p["gas_old_kwh_m2"]) * go / do
        diffs.append((new / old - 1) * 100)
    print(label, "|", summary(diffs))
ratio = lambda r: num(r["management_area_m2"]) / num(r["gross_floor_area_m2"]) if num(r["management_area_m2"]) and num(r["gross_floor_area_m2"]) else None
rn = [ratio(area[p["new_kapt"]]) for p in pairs if ratio(area[p["new_kapt"]])]
ro = [ratio(area[p["old_kapt"]]) for p in pairs if ratio(area[p["old_kapt"]])]
print("management area / gross floor area: new median", round(statistics.median(rn), 3), "old median", round(statistics.median(ro), 3))
an = [num(area[p["new_kapt"]]["gross_floor_area_m2"]) / num(area[p["new_kapt"]]["households"]) for p in pairs]
ao = [num(area[p["old_kapt"]]["gross_floor_area_m2"]) / num(area[p["old_kapt"]]["households"]) for p in pairs]
print("gross floor area per household: new median", round(statistics.median(an), 1), "old median", round(statistics.median(ao), 1))
mn = [num(area[p["new_kapt"]]["management_area_m2"]) / num(area[p["new_kapt"]]["households"]) for p in pairs if num(area[p["new_kapt"]]["management_area_m2"])]
mo = [num(area[p["old_kapt"]]["management_area_m2"]) / num(area[p["old_kapt"]]["households"]) for p in pairs if num(area[p["old_kapt"]]["management_area_m2"])]
print("management area per household: new median", round(statistics.median(mn), 1), "old median", round(statistics.median(mo), 1))
