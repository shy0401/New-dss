"""U2-c 상태 표 대조: `build-cell-state`가 만든 표와 팀 학습 표(training.csv)를 칸 · 해마다 견준다.

같은 칸(`grid_id_500m`) · 같은 해 행끼리 열마다
* 칸 수 열(용도지역 · SGIS · 단지 수)은 값이 같은 비율,
* 나머지는 상대 차 1% · 5% · 10% 안 비율(둘 다 0이면 같음, 한쪽만 NULL이면 다름),
* 대장 열은 기준 7.1의 큰 칸(연면적 1,000 m² · 건물 5동 · 20세대 이상)에서 5% · 20% 안 비율과 지역 합 비(우리/팀)
를 센다. 기본은 팀 표의 온전한 칸(`is_partial_cell = False`)만 보고, 경계 칸은 따로 적는다.
기상은 서비스 규칙(같은 시 ASOS, `station_annual.csv` 덮어쓰기, 아니면 NULL)으로 고친 팀 값과 지역 · 해 단위로 견준다.
대장 형태(`regform_*`)는 팀 표에 없어 실험 표(`regform_500m.csv`, 팀 묶음 표제부로 만든 것)와 견준다.

usage: python scripts/validate_cell_state.py --team-processed <T>/data/processed --ours <data>/derived/cell_state
       --regions 41290,27290,52110 [--station-annual deploy/team-model/station_annual.csv] [--regform <regform_500m.csv>]
       [--out <stats.csv>]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

EXACT = [f"zone_{n}_cells" for n in ("agricultural", "commercial", "conservation", "green", "industrial", "management",
                                    "residential", "other", "none")] + ["zone_main_class",
                                                                       "sgis_households", "sgis_housing_units", "sgis_population",
                                                                       "complex_count"]
REG = ["reg_floor_area_m2", "reg_residential_floor_area_m2", "reg_nonresidential_floor_area_m2", "reg_dwellings", "reg_building_count"]
REGFORM = ["regform_area_mean_m2", "regform_floors_mean", "regform_height_mean_m", "regform_age_mean_years"]
WEATHER = ["temp_avg_c", "heating_degree_days_c", "cooling_degree_days_c"]
BIG = {"reg_floor_area_m2": 1000, "reg_residential_floor_area_m2": 1000, "reg_nonresidential_floor_area_m2": 1000,
       "reg_dwellings": 20, "reg_building_count": 5}
# deploy/team-model/server.py _OWN_STATION (the service weather rule)
OWN_STATION = {"11": "108", "26": "159", "27": "143", "28": "112", "30": "133", "31": "152", "36110": "239",
               "41110": "119", "41111": "119", "41113": "119", "41115": "119", "41117": "119", "41480": "99",
               "43111": "131", "44133": "232", "48121": "155", "48129": "155", "48170": "192", "48250": "253",
               "51130": "114", "52110": "146"}


def team_folder(processed: Path, code: str) -> Path:
    hits = sorted(p for p in processed.glob(f"{code}_*") if (p / "training.csv").exists())
    if not hits:
        raise SystemExit(f"팀 표 없음: {code}")
    return min(hits, key=lambda p: len(p.name))  # 52110_전주시 before 52111_..., which has no training.csv anyway


def rel_ok(a: pd.Series, b: pd.Series, tol: float) -> pd.Series:
    a, b = a.astype(float), b.astype(float)
    both_null = a.isna() & b.isna()
    diff = (a - b).abs()
    return both_null | (diff <= tol * b.abs()) | ((a == 0) & (b == 0))


def eq_ok(a: pd.Series, b: pd.Series) -> pd.Series:
    both_null = a.isna() & b.isna()
    if not (pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b)):
        return both_null | (a.astype(str) == b.astype(str))
    return both_null | (a.astype(float) - b.astype(float)).abs().lt(1e-9)


def col_stats(m: pd.DataFrame, c: str, exact: bool) -> dict:
    a, b = m[f"{c}_ours"], m[f"{c}_team"]
    keep = ~(a.isna() & b.isna())
    out = {"column": c, "rows": int(len(m)), "both_null": int((~keep).sum()),
           "null_one_side": int((a.isna() ^ b.isna()).sum()),
           "ours_null_team_0": int((a.isna() & (b == 0)).sum()) if pd.api.types.is_numeric_dtype(b) else 0}
    if not keep.any():
        return out
    a, b = a[keep], b[keep]
    if exact:
        out["exact"] = float(eq_ok(a, b).mean())
        if c.startswith("sgis_"):
            out["exact_no_row_as_0"] = float(eq_ok(a.fillna(0), b).mean())
    else:
        for t in (0.01, 0.05, 0.10):
            out[f"within_{int(t * 100)}pct"] = float(rel_ok(a, b, t).mean())
        rd = ((a - b).abs() / b.abs()).replace([np.inf], np.nan)
        out["median_rel_diff"] = float(rd.median()) if rd.notna().any() else None
    if c in BIG:
        big = b >= BIG[c]
        if big.any():
            out["big_cells"] = int(big.sum())
            out["big_within_5pct"] = float(rel_ok(a[big], b[big], 0.05).mean())
            out["big_within_20pct"] = float(rel_ok(a[big], b[big], 0.20).mean())
    if c in REG or c in ("complex_count", "sgis_households", "sgis_population", "sgis_housing_units"):
        tb = b.astype(float).sum()
        out["sum_ratio"] = float(a.astype(float).sum() / tb) if tb else None
    return out


def service_weather(team: pd.DataFrame, code: str, stations: pd.DataFrame | None) -> pd.DataFrame:
    """Region-year weather after the service edit: station_annual.csv value, else the team value when its station is
    the region's own city ASOS, else NULL."""
    w = team.groupby("year").agg(**{c: (c, "first") for c in WEATHER}, station=("weather_station_id", "first")).reset_index()
    own = OWN_STATION.get(code) or OWN_STATION.get(code[:2])
    keep = w["station"].astype("Int64").astype(str) == str(own)
    w.loc[~keep, WEATHER] = np.nan
    if stations is not None:
        for r in stations[stations["region_code"].astype(str) == code].itertuples(index=False):
            hit = w["year"] == int(r.year)
            w.loc[hit, WEATHER] = [r.temp_avg_c, r.heating_degree_days_c, r.cooling_degree_days_c]
    return w[["year", *WEATHER]]


def compare_region(code: str, team_dir: Path, ours_csv: Path, stations: pd.DataFrame | None,
                   regform: pd.DataFrame | None) -> tuple[list[dict], dict]:
    team = pd.read_csv(team_dir / "training.csv", low_memory=False)
    ours = pd.read_csv(ours_csv, low_memory=False)
    years = sorted(set(team["year"]) & set(ours["year"]))
    team, ours = team[team["year"].isin(years)], ours[ours["year"].isin(years)]
    cells_t, cells_o = set(team["grid_id_500m"]), set(ours["grid_id_500m"])
    partial = team["is_partial_cell"].astype(str).str.lower()
    team = team.assign(_full=partial.eq("false"), _part=partial.eq("true"))
    keys = ["grid_id_500m", "year"]
    m = ours.merge(team, on=keys, how="inner", suffixes=("_ours", "_team"))
    presence = {"region": code, "team_folder": team_dir.name, "years": years, "cells_team": len(cells_t),
                "cells_ours": len(cells_o), "cells_both": len(cells_t & cells_o),
                "cells_team_only": len(cells_t - cells_o), "cells_ours_only": len(cells_o - cells_t),
                "cells_both_share_of_union": len(cells_t & cells_o) / len(cells_t | cells_o),
                "rows_both": len(m), "rows_both_full": int(m["_full"].sum()), "rows_both_partial": int(m["_part"].sum())}
    stats = []
    for subset, mask in (("full", m["_full"]), ("partial", m["_part"])):
        sub = m[mask]
        for c in EXACT:
            stats.append({"region": code, "subset": subset, **col_stats(sub, c, True)})
        for c in REG:
            stats.append({"region": code, "subset": subset, **col_stats(sub, c, False)})
        if regform is not None:
            rf = regform[regform["region"].str[:5] == code].rename(columns={c: f"{c}_team" for c in REGFORM + ["regform_buildings"]})
            if len(rf):
                mm = sub.drop(columns=[f"{c}_team" for c in REGFORM if f"{c}_team" in sub]).merge(
                    rf[keys + [f"{c}_team" for c in REGFORM + ["regform_buildings"]]], on=keys, how="left")
                mm = mm.rename(columns={c: f"{c}_ours" for c in REGFORM if c in mm})
                for c in REGFORM:
                    s = col_stats(mm, c, False)
                    five = mm["regform_buildings_team"].fillna(0) >= 5
                    if five.any():
                        s["big_cells"] = int(five.sum())
                        s["big_within_5pct"] = float(rel_ok(mm.loc[five, f"{c}_ours"], mm.loc[five, f"{c}_team"], 0.05).mean())
                    stats.append({"region": code, "subset": subset, **s})
    w_t = service_weather(team, code, stations)
    w_o = ours.groupby("year")[WEATHER].first().reset_index()
    wm = w_o.merge(w_t, on="year", suffixes=("_ours", "_team"))
    for c in WEATHER:
        tol = 0.011 if c == "temp_avg_c" else 0.11
        a, b = wm[f"{c}_ours"], wm[f"{c}_team"]
        ok = (a.isna() & b.isna()) | ((a - b).abs() <= tol)
        stats.append({"region": code, "subset": "region_year", "column": c, "rows": int(len(wm)),
                      "both_null": int((a.isna() & b.isna()).sum()), "null_one_side": int((a.isna() ^ b.isna()).sum()),
                      "exact": float(ok.mean()),
                      "detail": "; ".join(f"{int(y)}: ours {x} team {t}" for y, x, t in zip(wm["year"], a, b))})
    return stats, presence


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--team-processed", required=True)
    p.add_argument("--ours", required=True, help="folder with <code>/cell_state.csv")
    p.add_argument("--regions", required=True)
    p.add_argument("--station-annual", default=None)
    p.add_argument("--regform", default=None)
    p.add_argument("--out", default=None)
    a = p.parse_args()
    stations = pd.read_csv(a.station_annual) if a.station_annual else None
    regform = pd.read_csv(a.regform, dtype={"region": str, "grid_id_500m": str}) if a.regform else None
    rows, pres = [], []
    for code in [c.strip() for c in a.regions.split(",") if c.strip()]:
        s, pr = compare_region(code, team_folder(Path(a.team_processed), code), Path(a.ours) / code / "cell_state.csv",
                               stations, regform)
        rows += s
        pres.append(pr)
    stats = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    pd.set_option("display.max_rows", 500)
    print(pd.DataFrame(pres).to_string(index=False))
    show = [c for c in ["region", "subset", "column", "rows", "both_null", "null_one_side", "ours_null_team_0", "exact",
                        "exact_no_row_as_0", "within_1pct", "within_5pct", "within_10pct", "median_rel_diff", "big_cells",
                        "big_within_5pct", "big_within_20pct", "sum_ratio"] if c in stats]
    print(stats[stats["subset"] != "region_year"][show].round(3).to_string(index=False))
    print(stats[stats["subset"] == "region_year"][["region", "column", "exact", "detail"]].to_string(index=False))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        stats.to_csv(a.out, index=False, encoding="utf-8")
        pd.DataFrame(pres).to_csv(Path(a.out).with_name(Path(a.out).stem + "_presence.csv"), index=False, encoding="utf-8")


if __name__ == "__main__":
    main()
