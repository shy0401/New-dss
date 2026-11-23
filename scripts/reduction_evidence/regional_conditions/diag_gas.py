"""Why gas failed G3 (v1 rules unchanged): where the 2025 error sits.

For the gate set (individual heating, not mixed), with the v1 fit on the training years:
  - predicted vs actual by calendar month of 2025 (pooled)
  - pooled bias when each year in turn is held out (needs >= 2 other years) -> is 2025 special or is there a trend?
  - CV-RMSE by number of training years and by unit size
Run: python diag_gas.py   -> diag_gas.json
"""
from __future__ import annotations

import json
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


def main() -> None:
    weather, normal = D.load_weather()
    units = {k: u for k, u in D.load_gas_units().items() if u["heating"] == "개별난방" and u["mixed"] == 0}
    lag = 0
    by_month = defaultdict(lambda: [0.0, 0.0])
    by_hold = defaultdict(lambda: [0.0, 0.0, 0])
    cv_by_train, cv_by_size = defaultdict(list), defaultdict(list)
    worst = []
    for uid, u in units.items():
        obs = D.observations(u["months"], u["years"], True)
        wx = weather[u["region"]]
        years = sorted(obs)
        for hold in years:
            train = [y for y in years if y != hold]
            if len(train) < 2:
                continue
            f = D.fit_unit(obs, wx, lag, False, train)
            if not f:
                continue
            Xh, yh = D.design(obs[hold], wx, lag, False)
            if len(yh) < 9 or yh.sum() <= 0:
                continue
            pred = Xh @ f[0]
            by_hold[hold][0] += pred.sum()
            by_hold[hold][1] += yh.sum()
            by_hold[hold][2] += 1
            if hold == D.HOLDOUT and all(y < hold for y in train):
                for (months, v), p in zip(obs[hold], pred):
                    by_month[months[-1][4:]][0] += p
                    by_month[months[-1][4:]][1] += v
                cv = D.cvrmse(yh, pred)
                cv_by_train[len(train)].append(cv)
                size = u["households"] or 0
                cv_by_size["<300" if size < 300 else ("300~999" if size < 1000 else "1000+")].append(cv)
                worst.append((cv, uid, u["sigungu"], size, round(float(pred.sum() / yh.sum() - 1), 3),
                              [round(float(x)) for x in yh], [round(float(x)) for x in pred]))
    worst.sort(reverse=True)
    out = {
        "units": len(units),
        "holdout_2025_by_month_pred_over_actual": {m: round(p / a, 3) for m, (p, a) in sorted(by_month.items())},
        "holdout_2025_month_share_of_actual": {m: round(a / sum(v[1] for v in by_month.values()), 3) for m, (p, a) in sorted(by_month.items())},
        "leave_one_year_out_pooled_bias": {str(y): {"units": n, "bias": round(p / a - 1, 4)} for y, (p, a, n) in sorted(by_hold.items())},
        "cvrmse_median_by_train_years": {str(k): {"n": len(v), "median": round(float(np.median(v)), 4)} for k, v in sorted(cv_by_train.items())},
        "cvrmse_median_by_households": {k: {"n": len(v), "median": round(float(np.median(v)), 4)} for k, v in cv_by_size.items()},
        "worst_12": [{"cvrmse": round(c, 3), "unit": u, "sigungu": s, "households": h, "bias": b, "actual_2025": a, "pred_2025": p}
                     for c, u, s, h, b, a, p in worst[:12]],
        "median_12_sample": [{"cvrmse": round(c, 3), "unit": u, "sigungu": s, "households": h, "bias": b, "actual_2025": a, "pred_2025": p}
                             for c, u, s, h, b, a, p in worst[len(worst) // 2 - 2: len(worst) // 2 + 2]],
    }
    (OUT / "diag_gas.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k not in ("worst_12", "median_12_sample")}, ensure_ascii=False))
    for w in out["worst_12"][:5] + out["median_12_sample"]:
        print(json.dumps(w, ensure_ascii=False))


if __name__ == "__main__":
    main()
