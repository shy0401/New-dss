"""G2 re-judgement with the new envelope indicator (regional-conditions-2026-11-20.md 11절, written before this ran).

New indicator: -13.7 % (95 % range 9.8~17.3 %, width 7.5 %p) -> threshold 3.75 %p.
Nothing is refitted: the unit results of decompose.py / decompose_v2.py are read as they are and D.g2 is called
with the new constants (same formula, same verdict table, same seed). Old-indicator results are recomputed from
the same files as a check that W scales by 13.7/23.6.
Run: python g2_rejudge.py -> g2_rejudge.json
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import decompose as D

HERE = Path(__file__).parent
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _paths import REPO, data  # noqa: E402  (2026-11-24: data and results live outside Git)
OUT = data("regional_conditions")          # DB exports (extract/), results
GUIDE = data("regional_guide")            # design_zone_sigungu.csv, greentogether_apt_2025.csv (regional_guide/)
OLD = (23.6, (20.5, 25.8))
NEW = (13.7, (9.8, 17.3))
FLOATS = ("share_heat", "a_kwh_per_day", "h_kwh_per_hdd", "normal_hdd")


def load(name: str) -> list[dict]:
    rows = []
    with (OUT / name).open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["heating"] != "개별난방" or r["mixed"] != "0":
                continue
            for k in FLOATS:
                r[k] = float(r[k]) if r[k] != "" else None
            rows.append(r)
    return rows


def run(rows: list[dict], saving: float, rng: tuple[float, float]) -> dict:
    D.ENVELOPE_SAVING, D.ENVELOPE_RANGE = saving, rng
    D.G2_THRESHOLD = (rng[1] - rng[0]) / 2
    return D.g2(rows)


def main() -> None:
    out = {"new_indicator_pct": NEW[0], "new_range_pct": NEW[1], "new_threshold_pp": (NEW[1][1] - NEW[1][0]) / 2}
    for ver, name in (("v1", "decomp_gas_units.csv"), ("v2", "decomp_gas_units_v2.csv")):
        gate = load(name)
        clean = [r for r in gate if r["methods"] != "POINT" and r["check_area"] != "SUSPECT" and r["check_gas"] == "OK"]
        old, new, new_clean = run(gate, *OLD), run(gate, *NEW), run(clean, *NEW)
        out[ver] = {
            "old_indicator_check": {"W_obs_pp": old["W_obs_pp"], "W_clim_pp": old["W_clim_pp"], "verdict": old["verdict"]},
            "new": new, "new_clean_sensitivity": {k: new_clean[k] for k in ("units", "W_obs_pp", "W_obs_boot_p05_p95", "W_clim_pp", "verdict")},
            "scale_check_W_obs_new_over_old": round(new["W_obs_pp"] / old["W_obs_pp"], 4),
        }
    out["expected_scale"] = round(NEW[0] / OLD[0], 4)
    (OUT / "g2_rejudge.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for ver in ("v1", "v2"):
        n = out[ver]["new"]
        print(ver, json.dumps({k: n[k] for k in ("units", "s_ref_median_heat_share", "k_pct_of_heating_gas", "threshold_pp", "W_obs_pp",
                                                  "W_obs_boot_p05_p95", "adjusted_saving_pct_at_hdd", "W_clim_pp", "verdict")}, ensure_ascii=False))
        print("  by sigungu", json.dumps(n["adjusted_saving_pct_by_sigungu"], ensure_ascii=False))
        print("  old check", out[ver]["old_indicator_check"], "scale", out[ver]["scale_check_W_obs_new_over_old"], "clean", out[ver]["new_clean_sensitivity"])
    print("expected scale", out["expected_scale"])


if __name__ == "__main__":
    main()
