"""B8: describe how the 가스공사 file relates to the DB degree days (서울 = ASOS 108, 부산 = ASOS 159), 2015~2024.

The file has ONE value per city-month and no unit (portal page: bases 18/24 °C, daily mean; unit column empty).
So this only reports ratio and correlation; it does not treat the file as a check of the DB values.
Reads the raw file read-only (cp949). Run: python kogas_compare.py -> kogas_compare.json
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _paths import REPO, data  # noqa: E402  (2026-11-24: data and results live outside Git)
OUT = data("regional_conditions")          # DB exports (extract/), results
GUIDE = data("regional_guide")            # design_zone_sigungu.csv, greentogether_apt_2025.csv (regional_guide/)
RAW = REPO / "data" / "raw" / "kogas_degree_days" / "2026-11-20"
CITY = {"서울": "11740", "부산": "26440"}


def main() -> None:
    path = next(RAW.glob("*.csv"))
    rows = list(csv.DictReader(io.StringIO(path.read_bytes().decode("cp949"))))
    kogas = {(r["지역"], y, r["월"]): float(r[y]) for r in rows for y in r if y.isdigit() and r[y] not in ("", None)}
    db = {}
    for line in (OUT / "extract" / "weather.csv").read_text(encoding="utf-8").splitlines():
        rc, ym, hdd, cdd, src = line.split("|")
        if hdd and cdd:
            db[(rc, ym[:4], ym[4:])] = (float(hdd), float(cdd), src)
    out = {"file": path.name, "cities_in_file": sorted({r["지역"] for r in rows}), "years": "2015~2024"}
    for city, rc in CITY.items():
        heat, cool, both = [], [], []
        for y in range(2015, 2025):
            for m in range(1, 13):
                k, d = kogas.get((city, str(y), f"{m:02d}")), db.get((rc, str(y), f"{m:02d}"))
                if k is None or d is None:
                    continue
                hdd, cdd, _ = d
                both.append((k, hdd, cdd))
                if cdd == 0 and hdd >= 100:
                    heat.append((k, hdd))
                if hdd == 0 and cdd >= 10:
                    cool.append((k, cdd))
        b = np.array(both)
        # least squares k ≈ p*HDD + q*CDD + r  (how the single series maps onto our two series)
        X = np.column_stack([b[:, 1], b[:, 2], np.ones(len(b))])
        coef, *_ = np.linalg.lstsq(X, b[:, 0], rcond=None)
        res = b[:, 0] - X @ coef
        h, c = np.array(heat), np.array(cool)
        out[city] = {
            "db_region": rc, "months_compared": len(b),
            "heating_only_months": len(h),
            "ratio_file_over_hdd_median_p10_p90": [round(float(np.percentile(h[:, 0] / h[:, 1], q)), 2) for q in (50, 10, 90)],
            "corr_file_vs_hdd_heating_months": round(float(np.corrcoef(h[:, 0], h[:, 1])[0, 1]), 4),
            "cooling_only_months": len(c),
            "ratio_file_over_cdd_median_p10_p90": [round(float(np.percentile(c[:, 0] / c[:, 1], q)), 2) for q in (50, 10, 90)] if len(c) else None,
            "corr_file_vs_cdd_cooling_months": round(float(np.corrcoef(c[:, 0], c[:, 1])[0, 1]), 4) if len(c) > 2 else None,
            "fit_file = p*HDD + q*CDD + r": {"p": round(float(coef[0]), 2), "q": round(float(coef[1]), 2), "r": round(float(coef[2]), 1),
                                              "r2": round(float(1 - (res @ res) / ((b[:, 0] - b[:, 0].mean()) ** 2).sum()), 4)},
        }
    (OUT / "kogas_compare.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
