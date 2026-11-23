"""POST-HOC (not for the gate): underground parking per household of the paired new / old complexes (areas.csv, pairs.csv)."""
import csv
import statistics
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _paths import data  # noqa: E402

HERE = Path(__file__).parent
rows = lambda n: list(csv.DictReader(open(data("pair") / n, encoding="utf-8-sig", newline="")))
area = {r["kapt_code"]: r for r in rows("areas.csv")}
pairs = rows("pairs.csv")
for side in ("new", "old"):
    under = [float(area[p[f"{side}_kapt"]]["parking_under"] or 0) / float(area[p[f"{side}_kapt"]]["households"]) for p in pairs]
    ground = [float(area[p[f"{side}_kapt"]]["parking_ground"] or 0) / float(area[p[f"{side}_kapt"]]["households"]) for p in pairs]
    print(side, "underground parking per household: median", round(statistics.median(under), 2), "share with none", round(100 * sum(u == 0 for u in under) / len(under), 1), "% | ground median", round(statistics.median(ground), 2))
