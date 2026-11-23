"""B4: parse the screen transcription (greentogether_apt_2025_screen.txt), check it against the on-screen totals,
join the design zone (design_zone_sigungu.csv) and write greentogether_apt_2025.csv + a zone summary.

No value is filled in: "-" on screen -> empty (NULL). TOE -> kWh uses 1 TOE = 10^7 kcal, 1 kWh = 860 kcal
(= 11,627.9 kWh/TOE, final energy). That basis is NOT stated on the screen (확인 필요); ratios between regions do
not depend on it as long as one factor is used for all regions.
Run: python greentogether_parse.py
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _paths import REPO, data  # noqa: E402
_sys.path.insert(0, str(Path(__file__).resolve().parent))   # design_zone next to this script

from design_zone import classify

HERE = Path(__file__).parent
KWH_PER_TOE = 1e7 / 860.0  # assumption, see docstring
SIDO_TO_DB = {"광주광역시": "전남광주통합특별시", "전라남도": "전남광주통합특별시"}


def num(s: str) -> float | None:
    return None if s == "-" else float(s)


def main() -> None:
    zone_rows = list(csv.DictReader((REPO / "backend" / "reference" / "design_zone_sigungu.csv").open(encoding="utf-8-sig")))
    by_name = {r["sigungu_name"]: r for r in zone_rows}
    rows, problems, sido = [], [], None
    sums: dict[str, list[float]] = defaultdict(lambda: [0.0] * 6)
    for line in (HERE / "inputs" / "greentogether_apt_2025_screen.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("# ") or not line.strip():
            continue
        if line.startswith("#"):
            sido = line[1:].strip()
            continue
        parts = line.lstrip("=").split("|")
        vals = [num(x) for x in parts[1:]]
        if line.startswith("="):
            for i, (got, want) in enumerate(zip(sums[sido], vals)):
                tol = 0 if i == 0 else (5 if i == 1 else 30)  # counts exact; areas and TOE cells are rounded on screen
                if abs(got - (want or 0)) > tol:
                    problems.append(f"{sido} col{i}: rows {got:.0f} vs total {want}")
            continue
        for i, v in enumerate(vals):
            sums[sido][i] += v or 0.0
        name = parts[0]
        db_sido = SIDO_TO_DB.get(sido, sido)
        full = db_sido if name == sido else f"{db_sido} {name}"
        z = by_name.get(full)
        if z is None:
            # the statistics keep district names the DB list no longer has (인천 2026 개편 전 구 이름).
            # The zone still follows from the 비고 rule by name; the code stays empty.
            problems.append(f"no code for: {full} (zone by rule: {classify(full)[2]})")
            z = {"sigungu_code": "", "design_zone": classify(full)[2]}
        bldg, area, e, g, h, tot = vals
        rows.append({
            "stat_sido": sido, "stat_sigungu": name, "sigungu_code": z["sigungu_code"] if z else "",
            "design_zone": z["design_zone"] if z else "", "year": 2025, "use": "아파트",
            "buildings": int(bldg), "floor_area_m2": int(area),
            "electricity_toe": e, "citygas_toe": g, "district_heat_toe": h, "total_toe": tot,
            "electricity_kwh_per_m2": round(e * KWH_PER_TOE / area, 2) if e is not None else None,
            "citygas_kwh_per_m2": round(g * KWH_PER_TOE / area, 2) if g is not None else None,
            "district_heat_kwh_per_m2": round(h * KWH_PER_TOE / area, 2) if h is not None else None,
            "total_kwh_per_m2": round(tot * KWH_PER_TOE / area, 2) if tot is not None else None,
        })
    with (data("regional_guide") / "greentogether_apt_2025.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # zone summary: area-weighted intensity (sum TOE / sum area), "-" counted as no supply (not as zero use of a meter)
    zones: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        z = zones[r["design_zone"] or "(코드 없음)"]
        z["n"] += 1
        z["area"] += r["floor_area_m2"]
        for k in ("electricity_toe", "citygas_toe", "district_heat_toe", "total_toe"):
            z[k] += r[k] or 0.0
    summary = {"rows": len(rows), "problems": problems, "kwh_per_toe_assumed": round(KWH_PER_TOE, 1), "zones": {}}
    for name, z in zones.items():
        summary["zones"][name] = {
            "sigungu": int(z["n"]), "floor_area_m2": int(z["area"]),
            "electricity_kwh_per_m2": round(z["electricity_toe"] * KWH_PER_TOE / z["area"], 1),
            "citygas_kwh_per_m2": round(z["citygas_toe"] * KWH_PER_TOE / z["area"], 1),
            "district_heat_kwh_per_m2": round(z["district_heat_toe"] * KWH_PER_TOE / z["area"], 1),
            "total_kwh_per_m2": round(z["total_toe"] * KWH_PER_TOE / z["area"], 1),
        }
    base = summary["zones"].get("중부2", {}).get("total_kwh_per_m2")
    if base:
        summary["total_ratio_to_jungbu2"] = {k: round(v["total_kwh_per_m2"] / base, 3) for k, v in summary["zones"].items()}
    (data("regional_guide") / "greentogether_apt_2025_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
