"""Gas decomposition v2 (regional-conditions-2026-11-20.md 5절, fixed before this ran):
  y = a*days + h0*HDD(month) + h1*HDD(previous month),  a,h0,h1 >= 0   — no lag choice
Everything else (units, years, zero-month merge, 2025 hold-out, G3/G2 thresholds, gate set) as in v1 (decompose.py).
Outputs: decomp_gas_units_v2.csv, decomp_summary_v2.json
Run: python decompose_v2.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import decompose as D

HERE = Path(__file__).parent
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _paths import REPO, data  # noqa: E402  (2026-11-24: data and results live outside Git)
OUT = data("regional_conditions")          # DB exports (extract/), results
GUIDE = data("regional_guide")            # design_zone_sigungu.csv, greentogether_apt_2025.csv (regional_guide/)


def design2(periods, wx):
    rows, ys = [], []
    for months, v in periods:
        d = h0 = h1 = 0.0
        ok = True
        for ym in months:
            a, b = wx.get(ym, (None, None))[0], wx.get(D.prev_ym(ym, 1), (None, None))[0]
            if a is None or b is None:
                ok = False
                break
            d += D.days_in(ym)
            h0 += a
            h1 += b
        if ok:
            rows.append([d, h0, h1])
            ys.append(v)
    return np.array(rows, dtype=float), np.array(ys, dtype=float)


def fit(obs, wx, years):
    X, y = design2([p for yr in years for p in obs[yr]], wx)
    if len(y) < 12 * len(years) * 0.75 or len(y) < 6:
        return None
    return D.nnls_small(X, y)


def main() -> None:
    weather, normal = D.load_weather()
    units = D.load_gas_units()
    rows = []
    for uid, u in units.items():
        obs = D.observations(u["months"], u["years"], True)
        train = sorted(y for y in obs if y < D.HOLDOUT)
        if D.HOLDOUT not in obs or len(train) < D.MIN_TRAIN_YEARS:
            continue
        wx = weather[u["region"]]
        b = fit(obs, wx, train)
        if b is None:
            continue
        Xh, yh = design2(obs[D.HOLDOUT], wx)
        if len(yh) < 9 or yh.sum() <= 0:
            continue
        pred = Xh @ b
        bf = fit(obs, wx, train + [D.HOLDOUT])
        hn, cn = normal[u["region"]]
        h = float(bf[1] + bf[2])
        base, heat = float(bf[0]) * 365.25, h * hn
        tot = base + heat
        rows.append({
            "unit": uid, **{k: v for k, v in u.items() if k not in ("months", "years")},
            "train_years": len(train), "merged_billing": int(any(len(m) > 1 for y in obs for m, _ in obs[y])),
            "cvrmse_holdout": D.cvrmse(yh, pred), "bias_holdout": float((pred.sum() - yh.sum()) / yh.sum()),
            "pred_holdout_kwh": float(pred.sum()), "actual_holdout_kwh": float(yh.sum()),
            "a_kwh_per_day": float(bf[0]), "h_kwh_per_hdd": h, "h0_share": float(bf[1] / h) if h > 0 else None,
            "c_kwh_per_cdd": None, "normal_hdd": float(hn), "normal_cdd": float(cn), "normal_total_kwh": tot,
            "share_base": base / tot if tot > 0 else None, "share_heat": heat / tot if tot > 0 else None, "share_cool": 0.0,
        })
    D.write_units("decomp_gas_units_v2.csv", rows)
    gate = [r for r in rows if r["heating"] == "개별난방" and r["mixed"] == 0]
    clean = [r for r in gate if r["methods"] != "POINT" and r["check_area"] != "SUSPECT" and r["check_gas"] == "OK"]
    h0 = [r["h0_share"] for r in gate if r["h0_share"] is not None]
    out = {
        "model": "a*days + h0*HDD(m) + h1*HDD(m-1)", "units_decomposed": len(rows),
        "G3_gate_individual": D.g3(gate), "G3_gate_clean_sensitivity": D.g3(clean),
        "G3_by_weather": {k: D.g3([r for r in gate if D.region_kind(r) == k]) for k in sorted({D.region_kind(r) for r in gate})},
        "h0_share_of_heating_slope_median": round(float(np.median(h0)), 3),
        "share_heat_by_heating": D.share_table(rows, lambda r: r["heating"]),
        "share_heat_by_era_gate": D.share_table(gate, lambda r: r["era"]),
        "G2": D.g2(gate), "G2_clean_sensitivity": D.g2(clean),
    }
    (OUT / "decomp_summary_v2.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
