"""지역 조건표(지금 DB의 23개 시군구): design zone + normal degree days + decomposition shares + 2025 statistics.
Reads the files this folder already holds; writes regional_conditions_sigungu.csv. Empty = no value (never 0-filled).
Run: python build_conditions.py
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import numpy as np

import decompose as D

HERE = Path(__file__).parent
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _paths import REPO, data  # noqa: E402  (2026-11-24: data and results live outside Git)
OUT = data("regional_conditions")          # DB exports (extract/), results
GUIDE = data("regional_guide")            # design_zone_sigungu.csv, greentogether_apt_2025.csv (regional_guide/)
ENVELOPE_SAVING_NEW = 13.7  # % of gas, new ladder indicator (user decision 2026-11-20); reference only, G2 not passed


def rows_of(name: str) -> list[dict]:
    with ((GUIDE if name in ("design_zone_sigungu.csv", "greentogether_apt_2025.csv") else OUT) / name).open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def med(vals: list[float]) -> str:
    return "" if not vals else f"{float(np.median(vals)):.4f}"


def main() -> None:
    zone = {r["sigungu_code"]: r for r in rows_of("design_zone_sigungu.csv")}
    normal = {}
    for line in (OUT / "weather_normal_2015_2025.txt").read_text(encoding="utf-8").splitlines():
        rc, _yrs, hdd, cdd, _mn, _mx, fb = line.split("|")
        normal[rc] = (hdd, cdd, fb)
    stat = {r["sigungu_code"]: r for r in rows_of("greentogether_apt_2025.csv") if r["sigungu_code"]}
    complexes = defaultdict(lambda: defaultdict(int))
    for line in (OUT / "extract" / "complexes.csv").read_text(encoding="utf-8").splitlines():
        _code, bjd, heat, *_ = line.split("|")
        complexes[bjd[:5]]["all"] += 1
        complexes[bjd[:5]][heat] += 1
    elec = defaultdict(list)
    for r in rows_of("decomp_elec_units.csv"):
        elec[r["sigungu"]].append(r)
    gas = {"v1": defaultdict(list), "v2": defaultdict(list)}
    for ver, name in (("v1", "decomp_gas_units.csv"), ("v2", "decomp_gas_units_v2.csv")):
        for r in rows_of(name):
            if r["heating"] == "개별난방" and r["mixed"] == "0" and r["share_heat"]:
                gas[ver][r["sigungu"]].append(float(r["share_heat"]))
    ref = {ver: float(np.median([v for lst in gas[ver].values() for v in lst])) for ver in gas}
    out = []
    for sg in sorted(complexes):
        wc = D.weather_code(sg)
        hdd, cdd, fb = normal.get(wc, ("", "", ""))
        g1, g2 = gas["v1"].get(sg, []), gas["v2"].get(sg, [])
        s = stat.get(sg, {})
        out.append({
            "sigungu_code": sg, "sigungu_name": zone[sg]["sigungu_name"], "design_zone": zone[sg]["design_zone"],
            "weather_code": wc, "hdd_normal_2015_2025": hdd, "cdd_normal_2015_2025": cdd, "weather_fallback_months_of_132": fb,
            "complexes": complexes[sg]["all"], "complexes_individual_heating": complexes[sg]["개별난방"],
            "complexes_district_heating": complexes[sg]["지역난방"],
            "elec_units_decomposed": len(elec[sg]),
            "elec_share_cool_median": med([float(r["share_cool"]) for r in elec[sg] if r["share_cool"]]),
            "elec_share_heat_median": med([float(r["share_heat"]) for r in elec[sg] if r["share_heat"]]),
            "gas_units_decomposed_individual": len(g2),
            "gas_share_heat_median_v1": med(g1), "gas_share_heat_median_v2": med(g2),
            "envelope_saving_adjusted_ref_pct_v2": f"{ENVELOPE_SAVING_NEW * float(np.median(g2)) / ref['v2']:.2f}" if len(g2) >= D.MIN_UNITS_PER_SIGUNGU else "",
            "stat2025_apt_electricity_kwh_per_m2": s.get("electricity_kwh_per_m2", ""),
            "stat2025_apt_citygas_kwh_per_m2": s.get("citygas_kwh_per_m2", ""),
            "stat2025_apt_district_heat_kwh_per_m2": s.get("district_heat_kwh_per_m2", ""),
            "value_kinds": "zone=OBSERVED(고시); degree days=CALCULATED; shares=CALCULATED(분해, 가스는 G3 못 넘음 → 참고); envelope ref=참고(G2 못 넘음, 계산에 쓰지 않음); stat2025 kWh=ESTIMATED(TOE 환산 가정)",
        })
    with (OUT / "regional_conditions_sigungu.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    for r in out:
        print(r["sigungu_code"], r["design_zone"], r["hdd_normal_2015_2025"], r["complexes"], r["gas_units_decomposed_individual"],
              r["gas_share_heat_median_v2"], r["envelope_saving_adjusted_ref_pct_v2"], r["elec_share_cool_median"])


if __name__ == "__main__":
    main()
