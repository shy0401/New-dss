"""End-use decomposition and gates G3 / G2 (rules: project/working/methods/regional-conditions-2026-11-20.md 3절,
written before this script was run on real data).

  y_month = a*days + h*HDD + c*CDD,  a,h,c >= 0   (gas: no CDD term)
  electricity unit = K-apt complex (household electricity), gas unit = link-table group (parcel sum)
  hold out 2025, fit on earlier complete years -> G3;  refit with 2025 -> normal-year shares -> G2

Inputs: extract/*.csv (extract.py), ../reduction_evidence/link/*.csv (read only).
Outputs here: decomp_elec_units.csv, decomp_gas_units.csv, decomp_summary.json
Run: python decompose.py            (real data)
     python decompose.py --selftest (synthetic recovery check, no data read)
"""
from __future__ import annotations

import calendar
import csv
import itertools
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _paths import REPO, data  # noqa: E402  (2026-11-24: data and results live outside Git)
OUT = data("regional_conditions")          # DB exports (extract/), results
GUIDE = data("regional_guide")            # design_zone_sigungu.csv, greentogether_apt_2025.csv (regional_guide/)
EX = OUT / "extract"
LINK = data("link")

HOLDOUT = 2025
MIN_TRAIN_YEARS = 2
G3_CVRMSE = 0.15
G3_BIAS = 0.05
ENVELOPE_SAVING = 23.6          # % of gas, DATA_STANDARD 5.15
ENVELOPE_RANGE = (20.5, 25.8)
G2_THRESHOLD = (ENVELOPE_RANGE[1] - ENVELOPE_RANGE[0]) / 2  # 2.65 %p
MIN_UNITS_PER_SIGUNGU = 20
H_LOW, H_HIGH, H_FALLBACK_MAX = 1869.0, 2767.0, 2923.0     # normal HDD: 부산 강서, 서울 강동, 가평(ERA5)
SEED = 20261120
N_BOOT = 1000
FALLBACK_ALL = {"41820", "52140", "52210", "52710", "52720", "52730"}  # every month ERA5-Land
FALLBACK_PART = {"36110"}


def weather_code(sgg: str) -> str:
    if sgg.startswith("4111"):
        return "41110"
    if sgg in ("52111", "52113"):
        return "52110"
    return sgg


def prev_ym(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[4:])
    idx = y * 12 + (m - 1) - k
    return f"{idx // 12:04d}{idx % 12 + 1:02d}"


def days_in(ym: str) -> int:
    return calendar.monthrange(int(ym[:4]), int(ym[4:]))[1]


def nnls_small(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Exact non-negative least squares for a few columns: best feasible OLS over all column subsets."""
    p = X.shape[1]
    best, best_sse = np.zeros(p), float(np.dot(y, y))
    for r in range(1, p + 1):
        for cols in itertools.combinations(range(p), r):
            b, *_ = np.linalg.lstsq(X[:, cols], y, rcond=None)
            if (b < 0).any():
                continue
            res = y - X[:, cols] @ b
            sse = float(res @ res)
            if sse < best_sse - 1e-9:
                best_sse, best = sse, np.zeros(p)
                best[list(cols)] = b
    return best


def cvrmse(y: np.ndarray, pred: np.ndarray) -> float | None:
    m = float(y.mean())
    return None if m <= 0 else float(np.sqrt(np.mean((pred - y) ** 2)) / m)


# ---------------------------------------------------------------- data
def load_weather() -> tuple[dict, dict]:
    w: dict[str, dict[str, tuple[float | None, float | None]]] = defaultdict(dict)
    for line in (EX / "weather.csv").read_text(encoding="utf-8").splitlines():
        rc, ym, hdd, cdd, _src = line.split("|")
        w[rc][ym] = (float(hdd) if hdd else None, float(cdd) if cdd else None)
    normal = {}
    for rc, months in w.items():
        by_m = defaultdict(lambda: [[], []])
        for ym, (h, c) in months.items():
            if "201501" <= ym <= "202512" and h is not None and c is not None:
                by_m[ym[4:]][0].append(h)
                by_m[ym[4:]][1].append(c)
        normal[rc] = (sum(np.mean(v[0]) for v in by_m.values()), sum(np.mean(v[1]) for v in by_m.values()))
    return w, normal


def observations(months: dict[str, float], years: list[int], merge_zero: bool) -> dict[int, list[tuple[list[str], float]]]:
    """year -> [(months of the period, usage)]. Gas: a run of 1-2 zero months is merged into the next positive
    month of the same year; a longer run, or a run with no following month in that year, drops the year."""
    out = {}
    for yr in years:
        seq = [(f"{yr}{m:02d}", months[f"{yr}{m:02d}"]) for m in range(1, 13)]
        if not merge_zero:
            out[yr] = [([ym], v) for ym, v in seq]
            continue
        periods, pending, ok = [], [], True
        for ym, v in seq:
            if v == 0:
                pending.append(ym)
                if len(pending) > 2:
                    ok = False
                    break
            else:
                periods.append((pending + [ym], v))
                pending = []
        if ok and not pending:
            out[yr] = periods
    return out


def design(periods: list[tuple[list[str], float]], wx: dict, lag: int, use_cdd: bool):
    rows, ys = [], []
    for months, v in periods:
        d = h = c = 0.0
        ok = True
        for ym in months:
            src = prev_ym(ym, lag)
            hd, cd = wx.get(src, (None, None))
            if hd is None or cd is None:
                ok = False
                break
            d += days_in(src)
            h += hd
            c += cd
        if ok:
            rows.append([d, h, c] if use_cdd else [d, h])
            ys.append(v)
    return np.array(rows, dtype=float), np.array(ys, dtype=float)


def fit_unit(obs: dict[int, list], wx: dict, lag: int, use_cdd: bool, years: list[int]):
    periods = [p for y in years for p in obs[y]]
    X, y = design(periods, wx, lag, use_cdd)
    if len(y) < 12 * len(years) * 0.75 or len(y) < 6:
        return None
    return nnls_small(X, y), X, y


def analyse(units: dict[str, dict], weather: dict, normal: dict, use_cdd: bool, merge_zero: bool) -> tuple[list[dict], dict]:
    """units: id -> {months: {ym: kwh}, years: [complete years], region: weather code, ...meta}"""
    prepared = {}
    for uid, u in units.items():
        obs = observations(u["months"], u["years"], merge_zero)
        train = sorted(y for y in obs if y < HOLDOUT)
        if HOLDOUT in obs and len(train) >= MIN_TRAIN_YEARS and u["region"] in weather:
            prepared[uid] = (obs, train)
    # lag chosen on training years only
    lag_scores = {}
    for lag in (0, 1):
        vals = []
        for uid, (obs, train) in prepared.items():
            f = fit_unit(obs, weather[units[uid]["region"]], lag, use_cdd, train)
            if f:
                b, X, y = f
                cv = cvrmse(y, X @ b)
                if cv is not None:
                    vals.append(cv)
        lag_scores[lag] = float(np.median(vals)) if vals else None
    lag = min((l for l in lag_scores if lag_scores[l] is not None), key=lambda l: lag_scores[l])
    rows = []
    for uid, (obs, train) in prepared.items():
        u, wx = units[uid], weather[units[uid]["region"]]
        f = fit_unit(obs, wx, lag, use_cdd, train)
        if not f:
            continue
        b, _, _ = f
        Xh, yh = design(obs[HOLDOUT], wx, lag, use_cdd)
        if len(yh) < 9 or yh.sum() <= 0:
            continue
        pred = Xh @ b
        full = fit_unit(obs, wx, lag, use_cdd, train + [HOLDOUT])
        bf = full[0]
        hn, cn = normal[u["region"]]
        base, heat = bf[0] * 365.25, bf[1] * hn
        cool = bf[2] * cn if use_cdd else 0.0
        tot = base + heat + cool
        merged = any(len(m) > 1 for y in obs for m, _ in obs[y])
        rows.append({
            "unit": uid, **{k: v for k, v in u.items() if k not in ("months", "years")},
            "train_years": len(train), "merged_billing": int(merged),
            "cvrmse_holdout": cvrmse(yh, pred), "bias_holdout": float((pred.sum() - yh.sum()) / yh.sum()),
            "pred_holdout_kwh": float(pred.sum()), "actual_holdout_kwh": float(yh.sum()),
            "a_kwh_per_day": float(bf[0]), "h_kwh_per_hdd": float(bf[1]), "c_kwh_per_cdd": float(bf[2]) if use_cdd else None,
            "normal_hdd": float(hn), "normal_cdd": float(cn), "normal_total_kwh": float(tot),
            "share_base": float(base / tot) if tot > 0 else None,
            "share_heat": float(heat / tot) if tot > 0 else None,
            "share_cool": float(cool / tot) if tot > 0 else None,
        })
    return rows, {"lag_train_cvrmse_median": lag_scores, "lag_chosen": lag, "units_with_holdout_and_train": len(prepared)}


def g3(rows: list[dict]) -> dict:
    if not rows:
        return {"units": 0}
    cv = np.array([r["cvrmse_holdout"] for r in rows if r["cvrmse_holdout"] is not None])
    bias = np.array([r["bias_holdout"] for r in rows])
    pooled = sum(r["pred_holdout_kwh"] for r in rows) / sum(r["actual_holdout_kwh"] for r in rows) - 1
    out = {
        "units": len(rows), "cvrmse_median": round(float(np.median(cv)), 4), "cvrmse_p25": round(float(np.percentile(cv, 25)), 4),
        "cvrmse_p75": round(float(np.percentile(cv, 75)), 4), "share_units_cvrmse_le_15": round(float((cv <= G3_CVRMSE).mean()), 3),
        "bias_median": round(float(np.median(bias)), 4), "bias_pooled": round(float(pooled), 4),
    }
    out["pass"] = bool(out["cvrmse_median"] <= G3_CVRMSE and abs(out["bias_median"]) <= G3_BIAS and abs(out["bias_pooled"]) <= G3_BIAS)
    return out


def share_table(rows: list[dict], key, field: str = "share_heat") -> dict:
    groups = defaultdict(list)
    for r in rows:
        if r[field] is not None:
            groups[key(r)].append(r[field])
    return {str(k): {"n": len(v), "median": round(float(np.median(v)), 4), "p25": round(float(np.percentile(v, 25)), 4),
                     "p75": round(float(np.percentile(v, 75)), 4)} for k, v in sorted(groups.items(), key=lambda kv: str(kv[0]))}


def spread(rows: list[dict], field: str) -> dict:
    by = defaultdict(list)
    for r in rows:
        if r[field] is not None:
            by[r["sigungu"]].append(r[field])
    med = {k: float(np.median(v)) for k, v in by.items() if len(v) >= MIN_UNITS_PER_SIGUNGU}
    if len(med) < 3:
        return {"sigungu": len(med)}
    vals = np.array(list(med.values()))
    return {"sigungu": len(med), "p10": round(float(np.percentile(vals, 10)), 4), "p90": round(float(np.percentile(vals, 90)), 4),
            "min": round(float(vals.min()), 4), "max": round(float(vals.max()), 4),
            "by_sigungu": {k: round(v, 4) for k, v in sorted(med.items())}}


def g2(rows: list[dict]) -> dict:
    """rows = decomposed individual-heating gas groups."""
    rows = [r for r in rows if r["share_heat"] is not None]
    shares = np.array([r["share_heat"] for r in rows])
    s_ref = float(np.median(shares))
    k = ENVELOPE_SAVING / s_ref

    def w_obs(sample: list[dict]) -> tuple[float | None, dict]:
        by = defaultdict(list)
        for r in sample:
            by[r["sigungu"]].append(r["share_heat"])
        ref = float(np.median([r["share_heat"] for r in sample]))
        adj = {sg: ENVELOPE_SAVING * float(np.median(v)) / ref for sg, v in by.items() if len(v) >= MIN_UNITS_PER_SIGUNGU}
        if len(adj) < 3:
            return None, adj
        vals = np.array(list(adj.values()))
        return float(np.percentile(vals, 90) - np.percentile(vals, 10)), adj

    w, adj = w_obs(rows)
    rng = np.random.default_rng(SEED)
    by_sg = defaultdict(list)
    for r in rows:
        by_sg[r["sigungu"]].append(r)
    boots = []
    for _ in range(N_BOOT):
        sample = []
        for sg, lst in by_sg.items():
            idx = rng.integers(0, len(lst), len(lst))
            sample.extend(lst[i] for i in idx)
        bw, _ = w_obs(sample)
        if bw is not None:
            boots.append(bw)

    def s_at(H: float) -> float:
        vals = []
        for r in rows:
            heat = r["h_kwh_per_hdd"] * H
            tot = r["a_kwh_per_day"] * 365.25 + heat
            if tot > 0:
                vals.append(heat / tot)
        return float(np.median(vals))

    clim = {str(int(H)): round(k * s_at(H), 3) for H in (H_LOW, H_HIGH, H_FALLBACK_MAX)}
    w_clim = clim[str(int(H_HIGH))] - clim[str(int(H_LOW))]
    counts = {sg: len(v) for sg, v in by_sg.items()}
    # rank correlation between regional heating share and normal HDD (sigungu with >= MIN units)
    hdd = {r["sigungu"]: r["normal_hdd"] for r in rows}
    from scipy.stats import spearmanr
    sg_keys = sorted(adj)
    rho = spearmanr([adj[s] for s in sg_keys], [hdd[s] for s in sg_keys]) if len(sg_keys) >= 3 else None
    if w is None:
        verdict = "판정 불가(20곳 이상 시군구가 3곳 미만)"
    elif w >= G2_THRESHOLD:
        verdict = "통과"
    elif w_clim >= G2_THRESHOLD:
        verdict = "엇갈림"
    else:
        verdict = "못 넘음"
    return {
        "units": len(rows), "s_ref_median_heat_share": round(s_ref, 4), "k_pct_of_heating_gas": round(k, 2),
        "threshold_pp": G2_THRESHOLD, "W_obs_pp": None if w is None else round(w, 3),
        "W_obs_boot_p05_p95": [round(float(np.percentile(boots, 5)), 3), round(float(np.percentile(boots, 95)), 3)] if boots else None,
        "adjusted_saving_pct_by_sigungu": {s: round(v, 2) for s, v in sorted(adj.items())},
        "units_by_sigungu": dict(sorted(counts.items())),
        "normal_hdd_by_sigungu": {s: round(hdd[s]) for s in sorted(hdd)},
        "adjusted_saving_pct_at_hdd": clim, "W_clim_pp": round(w_clim, 3),
        "spearman_share_vs_hdd": None if rho is None else {"rho": round(float(rho.statistic), 3), "p": round(float(rho.pvalue), 3), "n": len(sg_keys)},
        "verdict": verdict,
    }


def era(year: int | None) -> str:
    if year is None:
        return "모름"
    return "~2008" if year <= 2008 else ("2009~2016" if year <= 2016 else "2017~")


# ---------------------------------------------------------------- real data
def load_elec_units(weather: dict) -> dict[str, dict]:
    meta = {}
    for line in (EX / "complexes.csv").read_text(encoding="utf-8").splitlines():
        code, bjd, heat, appr, hh, gfa = line.split("|")
        meta[code] = {"sigungu": bjd[:5], "heating": heat or "-", "approval_year": int(appr[:4]) if appr[:4].isdigit() else None,
                      "households": int(hh) if hh else None, "gfa_m2": float(gfa) if gfa else None}
    months = defaultdict(dict)
    for line in (EX / "kapt_elec.csv").read_text(encoding="utf-8").splitlines():
        code, ym, q = line.split("|")
        months[code][ym] = float(q)
    units = {}
    for code, ms in months.items():
        m = meta.get(code)
        if not m:
            continue
        by_year = defaultdict(int)
        for ym in ms:
            by_year[int(ym[:4])] += 1
        years = sorted(y for y, n in by_year.items() if n == 12 and 2015 <= y <= 2025 and (m["approval_year"] is None or y > m["approval_year"]))
        units[code] = {"months": ms, "years": years, "region": weather_code(m["sigungu"]), **m, "era": era(m["approval_year"])}
    return units


def load_gas_units() -> dict[str, dict]:
    groups = {}
    with (LINK / "link_groups.csv").open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            ay = int(r["approval_year_max"]) if r["approval_year_max"] else None
            groups[r["group_id"]] = {
                "sigungu": r["sigungu_code"], "heating": r["heating_types"], "mixed": int(r["mixed"] or 0),
                "group_type": r["group_type"], "methods": r["methods"], "check_area": r["check_area"],
                "check_gas": r["check_gas"], "check_elec_v2": r["check_elec_v2"], "approval_year": ay,
                "households": int(float(r["households"])) if r["households"] else None,
                "gfa_m2": float(r["gfa_kapt_m2"]) if r["gfa_kapt_m2"] else None, "era": era(ay),
            }
    parcels = defaultdict(set)
    with (LINK / "complex_parcel_link.csv").open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["linked"] == "1" and int(r["gas_months"] or 0) > 0:
                parcels[r["group_id"]].add((r["sigungu_code"], r["bjdong_code"], r["lot_type"], r["bun"], r["ji"]))
    pm = defaultdict(dict)
    for line in (EX / "gas_parcel.csv").read_text(encoding="utf-8").splitlines():
        sgg, bjd, lt, bun, ji, ym, v = line.split("|")
        if v != "":
            pm[(sgg, bjd, lt, bun, ji)][ym] = float(v)
    units = {}
    for gid, ps in parcels.items():
        g = groups[gid]
        ms, years = {}, []
        for yr in range(2021, 2026):
            yms = [f"{yr}{m:02d}" for m in range(1, 13)]
            if all(all(ym in pm[p] for ym in yms) for p in ps):
                if g["approval_year"] is None or yr > g["approval_year"]:
                    years.append(yr)
                    for ym in yms:
                        ms[ym] = sum(pm[p][ym] for p in ps)
        units[gid] = {"months": ms, "years": years, "region": weather_code(g["sigungu"]), "n_gas_parcels": len(ps), **g}
    return units


def write_units(name: str, rows: list[dict]) -> None:
    if not rows:
        return
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def region_kind(r: dict) -> str:
    return "기상 전부 대체" if r["sigungu"] in FALLBACK_ALL else ("기상 일부 대체(세종)" if r["sigungu"] in FALLBACK_PART else "기상 관측")


def main() -> None:
    weather, normal = load_weather()
    out: dict = {"holdout_year": HOLDOUT, "rules": "regional-conditions-2026-11-20.md 3절"}

    eu = load_elec_units(weather)
    er, einfo = analyse(eu, weather, normal, use_cdd=True, merge_zero=False)
    write_units("decomp_elec_units.csv", er)
    out["electricity"] = {
        "unit": "K-apt 단지(세대 전기)", "units_total": len(eu), **einfo,
        "G3_all": g3(er),
        "G3_by_heating": {k: g3([r for r in er if r["heating"] == k]) for k in sorted({r["heating"] for r in er})},
        "G3_by_weather": {k: g3([r for r in er if region_kind(r) == k]) for k in sorted({region_kind(r) for r in er})},
        "share_heat_by_heating": share_table(er, lambda r: r["heating"]),
        "share_cool_by_heating": share_table(er, lambda r: r["heating"], "share_cool"),
        "share_heat_by_era": share_table(er, lambda r: r["era"]),
        "share_cool_by_era": share_table(er, lambda r: r["era"], "share_cool"),
        "share_heat_spread_sigungu": spread(er, "share_heat"),
        "share_cool_spread_sigungu": spread(er, "share_cool"),
    }

    gu = load_gas_units()
    gr, ginfo = analyse(gu, weather, normal, use_cdd=False, merge_zero=True)
    write_units("decomp_gas_units.csv", gr)
    gate = [r for r in gr if r["heating"] == "개별난방" and r["mixed"] == 0]
    clean = [r for r in gate if r["methods"] != "POINT" and r["check_area"] != "SUSPECT" and r["check_gas"] == "OK"]
    out["gas"] = {
        "unit": "연결 표 묶음(지번 합)", "units_total": len(gu),
        "units_gate_candidates": sum(1 for u in gu.values() if u["heating"] == "개별난방" and u["mixed"] == 0), **ginfo,
        "G3_gate_individual": g3(gate), "G3_gate_clean_sensitivity": g3(clean),
        "G3_by_heating": {k: g3([r for r in gr if r["heating"] == k]) for k in sorted({r["heating"] for r in gr})},
        "G3_by_weather": {k: g3([r for r in gate if region_kind(r) == k]) for k in sorted({region_kind(r) for r in gate})},
        "G3_by_merged_billing": {str(k): g3([r for r in gate if r["merged_billing"] == k]) for k in (0, 1)},
        "share_heat_by_heating": share_table(gr, lambda r: r["heating"]),
        "share_heat_by_era_gate": share_table(gate, lambda r: r["era"]),
        "share_heat_by_group_type_gate": share_table(gate, lambda r: r["group_type"]),
        "G2": g2(gate), "G2_clean_sensitivity": g2(clean),
    }
    (OUT / "decomp_summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


def selftest() -> None:
    rng = np.random.default_rng(1)
    hdd_m = [600, 480, 380, 180, 40, 0, 0, 0, 20, 150, 350, 560]
    cdd_m = [0, 0, 0, 0, 0, 20, 80, 90, 10, 0, 0, 0]
    wx = {"R": {f"{y}{m:02d}": (hdd_m[m - 1] * (1 + 0.1 * rng.standard_normal()), cdd_m[m - 1] * (1 + 0.1 * rng.standard_normal()))
                for y in range(2014, 2026) for m in range(1, 13)}}
    wx["R"] = {k: (max(h, 0.0), max(c, 0.0)) for k, (h, c) in wx["R"].items()}
    by_m = defaultdict(lambda: [[], []])
    for ym, (h, c) in wx["R"].items():
        if ym >= "201501":
            by_m[ym[4:]][0].append(h)
            by_m[ym[4:]][1].append(c)
    normal = {"R": (sum(np.mean(v[0]) for v in by_m.values()), sum(np.mean(v[1]) for v in by_m.values()))}
    units = {}
    truth = {}
    for i in range(60):
        a, h, c = rng.uniform(800, 1200), rng.uniform(20, 80), rng.uniform(0, 40)
        lag = 1
        months = {}
        for y in range(2021, 2026):
            for m in range(1, 13):
                ym = f"{y}{m:02d}"
                src = prev_ym(ym, lag)
                hd, cd = wx["R"][src]
                months[ym] = (a * days_in(src) + h * hd + c * cd) * (1 + 0.03 * rng.standard_normal())
        units[f"U{i}"] = {"months": months, "years": list(range(2021, 2026)), "region": "R", "sigungu": "R", "heating": "x", "era": "x"}
        truth[f"U{i}"] = (a, h, c)
    rows, info = analyse(units, wx, normal, use_cdd=True, merge_zero=False)
    assert info["lag_chosen"] == 1, info
    err_h = np.median([abs(r["h_kwh_per_hdd"] - truth[r["unit"]][1]) / truth[r["unit"]][1] for r in rows])
    err_a = np.median([abs(r["a_kwh_per_day"] - truth[r["unit"]][0]) / truth[r["unit"]][0] for r in rows])
    res = g3(rows)
    assert err_h < 0.10 and err_a < 0.03, (err_h, err_a)
    assert res["cvrmse_median"] < 0.06 and abs(res["bias_pooled"]) < 0.02, res
    # zero-month merge: a 0 followed by a doubled month must be merged; three zeros drop the year
    ms = {f"2024{m:02d}": 10.0 for m in range(1, 13)}
    ms["202407"], ms["202408"] = 0.0, 20.0
    o = observations(ms, [2024], True)
    assert len(o[2024]) == 11 and (["202407", "202408"], 20.0) in o[2024]
    ms.update({"202401": 0.0, "202402": 0.0, "202403": 0.0})
    assert observations(ms, [2024], True) == {}
    # non-negativity
    b = nnls_small(np.array([[30, 100.0], [31, 0.0], [30, 50.0], [31, 10.0]]), np.array([10.0, 40.0, 20.0, 35.0]))
    assert (b >= 0).all()
    print("selftest ok", {"lag": info["lag_chosen"], "median_rel_err_h": round(float(err_h), 4), "median_rel_err_a": round(float(err_a), 4), **res})


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
