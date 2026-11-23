"""팀 변화 모델 서비스 (urban-carbon 7차) — Carbon Urban DSS가 개발 계획의 배출 변화를 묻는 작은 HTTP 서버.

* 팀 코드와 학습 표는 저장소에 넣지 않는다. ``TEAM_ROOT``(compose에서 ``data/raw/team_urban_carbon``을 읽기 전용으로
  붙임) 아래 가장 새 묶음의 ``code/``(urban-carbon 저장소 사본: ``src/``, ``config/``, ``data/processed/``)를 그대로 쓴다.
  학습 표에는 국토통계지도(국외 반출 금지) 값이 들어 있어 이 컨테이너 밖으로 표를 내보내지 않는다.
* 시작하면 뒤에서 ``00_합본_7차``로 변화 모델을 학습한다. 팀의 ``urban-carbon predict``와 같은 함수(``_Trained``,
  ``_predict_one``)를 그대로 불러 같은 답을 낸다(seed 5개 × 합계·에너지원 3, 사례 쌍 가중 ×10). 1~3분.
* 칸의 지금 상태는 그 지역 표(``data/processed/<코드>_<이름>/training.csv``)에서, 모델·환산 계수·구간은 ``00_합본_7차``에서.

GET /health, GET /status, POST /predict {"region": "52110", "plans": [{"x": 959500, "y": 1760500, "new": [...],
"removed": [...], "years_after": 3}]} — 칸은 이 도구의 500m 격자 왼쪽 아래 좌표(EPSG:5179).
POST /predict-area {"region": "52110", "cells": [{"x": .., "y": ..}, ...], "new": [...], "removed": [...], "years_after": 7}
— 한 개발의 용도별 합계를 쓸 수 있는 칸에 같게 나눠 칸마다 예측하고 개발로 더한다(모델 로드맵 7-B2, 기록 41절).
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import threading
import time
import traceback
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

TEAM_ROOT = Path(os.environ.get("TEAM_ROOT", "/team-root"))
TRAIN = os.environ.get("TEAM_TRAIN", "00_합본_7차")
PORT = int(os.environ.get("PORT", "8090"))
# 칸 수: 평가한 가장 큰 개발이 64칸(모델 로드맵 31절). 그 위는 검증 밖이라 받지 않는다
MAX_PLANS = 64
MAX_AREA_ITEMS = 10  # 구역 예측의 신축·철거 용도 줄 수(칸 계획과 같은 한도, 화면은 4줄)
# official (기본): 아래 두 입력을 공식 값으로 바꿔 학습·예측. team: 받은 팀 코드 그대로(전후 비교용)
INPUTS = os.environ.get("TEAM_INPUTS", "official")
STATION_FILE = Path(os.environ.get("TEAM_STATION_FILE", str(Path(__file__).with_name("station_annual.csv"))))
# 2024 electricity emission factor of each region's carbon-map 500m file (2026-11-18, methods performance-candidates
# §25-26): 2013-2022 use 0.4173, 2023 uses 0.4781 everywhere, 2024 is 0.4781 in 인천 · 경기 and 0.4173 elsewhere.
FACTOR_FILE = Path(os.environ.get("TEAM_FACTOR_FILE", str(Path(__file__).with_name("elec_factor_2024.csv"))))
_FACTOR_BASE, _FACTOR_HIGH = 0.4173, 0.4781
# model roadmap stages 4-5 · 7-A (2026-11-19, methods performance-candidates §35, §37, §39):
# cell (default): the region-drop exclusion judged per cell (region_drop.py), rows taken back join the training pairs only.
# team: the team marks as received
REGION_DROP = os.environ.get("TEAM_REGION_DROP", "cell")
# off (default): the pair input "after_year" is left out. Trees read any year past 2024 as 2024, so a plan's future year
# carried the 2024 effect (+10~15 % on development totals, §35); without it the development-level accuracy is the same
AFTER_YEAR_INPUT = os.environ.get("TEAM_AFTER_YEAR_INPUT", "off")
# prediction bands from the development-level cross-validation of this model (§39 rule 3); the team bands when missing
BANDS_FILE = Path(os.environ.get("TEAM_BANDS_FILE", str(Path(__file__).with_name("dev_bands.csv"))))
# years after the current state when a plan does not say (§39 rule 4): the evaluated development windows run 7 years
# (median, pre-construction → after completion) and 3 vs 7 years moved test predictions by 6.6 % (median); the team default was 3
DEFAULT_YEARS_AFTER = int(os.environ.get("TEAM_DEFAULT_YEARS_AFTER", "7"))
# developments (default): the development cases that get the case weight (x10) come from developments.csv, as in every
# evaluation of this model (record §34~§41: 762 pairs). team: the team predict path's baseline/development_cases.csv
# (158 pairs). Found 2026-11-19 (7-B2 check): the service then differed from the evaluated model by 5~13 % on developments
CASE_WEIGHTS = os.environ.get("TEAM_CASE_WEIGHTS", "developments")
# area cells without a usable row in the shared state year (record §43): start from the cell's nearest usable year (R-b) and
# empty-land cells from the empty state (R-c) instead of leaving them out
AREA_NEAREST_YEAR = os.environ.get("TEAM_AREA_NEAREST_YEAR", "off") == "on"  # off: §43 rule 2 not met (sum ratio 0.044 off 1 vs 0.036 when left out)
AREA_EMPTY_LAND = os.environ.get("TEAM_AREA_EMPTY_LAND", "on") == "on"
_INPUT_SOURCES: dict[str, Any] = {}
_CODE: dict[str, Path] = {}
_ELEC, _GAS, _HEAT = "elec_tco2e_total", "gas_tco2e_total", "heat_tco2e_total"
_TOTAL = "buildings_tco2e_total"
_WEATHER = ("temp_avg_c", "heating_degree_days_c", "cooling_degree_days_c")
# team estimates with an official value already in the table (audit 2026-11-17 §8): left out of the inputs
_ESTIMATED_INPUTS = ("floor_area_total_est_filled_m2", "complex_households_est")  # → reg_floor_area_m2, reg_dwellings
# counts read as 0 (and masked population as 3 persons) → the provider's observed sums, NULL where none observed
_OBSERVED_SUMS = {"building_count_filled": "building_count_sum", "apartment_building_count_filled": "apartment_building_count_sum",
                  "detached_building_count_filled": "detached_building_count_sum",
                  "population_total_persons_filled": "population_total_persons_sum"}
_MASKED_CELLS = "population_total_persons_masked_cells"  # withheld (N/A) 100 m cells: a provider fact, added as an input
_REGISTER_FLOOR = "reg_floor_area_m2"
# each region's own-city KMA ASOS station (Gyeonggi has 98, 99, 119, 202, 203 only). A row whose team station is not
# its own city's and that ``station_annual.csv`` does not cover gets NULL weather: no other city's station (DATA_STANDARD 2절)
_OWN_STATION = {"11": "108", "26": "159", "27": "143", "28": "112", "30": "133", "31": "152", "36110": "239",
                "41110": "119", "41111": "119", "41113": "119", "41115": "119", "41117": "119", "41480": "99",
                "43111": "131", "44133": "232", "48121": "155", "48129": "155", "48170": "192", "48250": "253",
                "51130": "114", "52110": "146"}
_STATION = "weather_station_id"

STATE: dict[str, Any] = {"status": "starting", "snapshot": None, "train": TRAIN, "started_at": None, "ready_at": None,
                         "train_seconds": None, "error": None, "versions": {}, "regions": [], "acceptance": [], "pair_inputs": None,
                         "inputs": {"mode": INPUTS, "tables": {}}}
_PREDICT_LOCK = threading.Lock()
_CTX: dict[str, Any] = {}
_TABLES: dict[str, Any] = {}


def find_code() -> tuple[str | None, Path | None]:
    """The newest bundle under TEAM_ROOT that has the team code and the training table."""
    if not TEAM_ROOT.is_dir():
        return None, None
    for snap in sorted((p for p in TEAM_ROOT.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))), reverse=True):
        code = snap / "code"
        if (code / "src" / "urban_carbon").is_dir() and (code / "data" / "processed" / TRAIN / "training.csv").is_file():
            return snap.name, code
    return None, None


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _fix_band_sign(P: Any) -> None:
    """Band of a predicted decrease (2026-11-16).

    The team code scores residuals as (actual − predicted) / |predicted| but builds the band as predicted × (1 + q),
    which flips the band when the prediction is negative (a decrease): q90 lands below q10. The right band is
    predicted + q × |predicted|. Patch ``band_of`` once here so ``_predict_one`` and ``combine`` (which look it up in the
    module at call time) use it; the bundle under data/raw is left as received.
    """
    if getattr(P, "_band_sign_fixed", False):
        return
    original = P.band_of

    def band_of(bands, site_kind, change, settings, *args, **kwargs):
        raw = original(bands, site_kind, change, settings, *args, **kwargs)
        if change >= 0:
            return raw
        # raw = change × (1 + q)  →  q = raw / change − 1  →  change + q × |change| = 2 × change − raw
        return {k: 2.0 * change - v for k, v in raw.items()}

    P.band_of = band_of
    P._band_sign_fixed = True


def official_inputs(table: Any, folder: Path, asos: Any, factor_high: set[str] | None = None) -> tuple[Any, dict[str, Any]]:
    """Official values in place of borrowed or estimated ones (2026-11-17 retraining, record methods/official-inputs).

    * 2024 electricity on one emission factor (2026-11-18): the carbon map's 2024 500m electricity uses 0.4781 in the
      regions of ``elec_factor_2024.csv`` marked 0.4781 (인천 · 경기) and 0.4173 elsewhere, while 2013-2022 use 0.4173.
      Those regions' 2024 electricity (annual and monthly columns) is put on 0.4173 (× 0.4173 / 0.4781) and the
      building total is recomputed, so a change target ending in 2024 carries no factor step. Done first, before the
      energy mix below. The received files are not changed.
    * ``heat_share_ctx``/``gas_share_ctx``: the team code gives a cell under 100 t the share of its 3 x 3 neighbours or of
      the region. Here every cell takes its own carbon-map share (heat or gas ÷ elec + gas + heat of that cell and year);
      a cell with no emission gets NULL, which the learner handles as missing.
    * weather: where the team table used another city's ASOS station (Seoul for Paju, Uijeongbu, Goyang, ...; Daejeon
      for Sejong), one station of the region's own city is used for all years (``station_annual.csv``: the KMA ASOS or
      AWS station with the most complete years; AWS from the 방재기상월보 via 기상청 API허브; team weather rules, a year
      needs 12 months without a missing day; made by scripts/team_model_weather/ (aws_annual_for_team.py,
      asos_annual_for_team.py, select_station_annual.py). Years that station does not complete, and regions without a usable station, get NULL:
      no substitute from another city.
    * building counts and population (2026-11-17 §8): the team reads a 100 m cell without a value as 0 and a withheld
      population cell as 3 persons. Here the columns keep their names (the scenario code updates them) but hold the
      provider's observed sums, NULL where nothing was observed; the count of withheld cells becomes an input
      (``official_features``). The estimated total floor area and area-split complex households leave the inputs.
    Same edit on the training table and on every region table, so training and prediction see the same inputs.
    """
    import numpy as np
    import pandas

    t = table.copy()
    note: dict[str, Any] = {}
    if factor_high and "year" in t and _ELEC in t:
        region = t["region"].astype(str).str[:5] if "region" in t else pandas.Series(folder.name[:5], index=t.index)
        rows = (t["year"] == 2024) & region.isin(factor_high)
        if rows.any():
            scale = _FACTOR_BASE / _FACTOR_HIGH
            cols = [c for c in t.columns if c == _ELEC or c.startswith("elec_tco2e_m")]
            t.loc[rows, cols] = t.loc[rows, cols] * scale
            if _TOTAL in t:
                t.loc[rows, _TOTAL] = t.loc[rows, [_ELEC, _GAS, _HEAT]].sum(axis=1, min_count=1)
        note["elec_factor_2024_rows"] = int(rows.sum())
    if all(c in t for c in (_ELEC, _GAS, _HEAT, "heat_share_ctx", "gas_share_ctx")):
        heat, gas = t[_HEAT].fillna(0.0), t[_GAS].fillna(0.0)
        total = (heat + gas + t[_ELEC].fillna(0.0)).where(lambda s: s > 0)
        old = t[["heat_share_ctx", "gas_share_ctx"]].copy()
        t["heat_share_ctx"], t["gas_share_ctx"] = heat / total, gas / total
        same = np.isclose(old.to_numpy(dtype=float), t[["heat_share_ctx", "gas_share_ctx"]].to_numpy(dtype=float), equal_nan=True)
        note["mix_rows_changed"] = int((~same.all(axis=1)).sum())
        note["mix_rows_null"] = int(total.isna().sum())
    if asos is not None and len(asos) and "year" in t and all(c in t for c in _WEATHER):
        # a joined table names each row's region; a region table is one region (its folder "<code>_<name>")
        region = t["region"].astype(str).str[:5] if "region" in t else pandas.Series(folder.name[:5], index=t.index)
        replaced = []
        own = pandas.Series(False, index=t.index)
        for r in asos.itertuples(index=False):
            rows = (region == str(r.region_code)) & (t["year"] == int(r.year))
            n = int(rows.sum())
            if n:
                t.loc[rows, list(_WEATHER)] = [float(r.temp_avg_c), float(r.heating_degree_days_c), float(r.cooling_degree_days_c)]
                own |= rows
                replaced.append({"region": str(r.region_code), "station": str(r.station), "year": int(r.year), "rows": n})
        note["stations"] = replaced
        if _STATION in t:
            station = t[_STATION].astype("Int64").astype(str)
            own |= pandas.Series([(_OWN_STATION.get(c) or _OWN_STATION.get(c[:2])) == s for c, s in zip(region, station)], index=t.index)
            t.loc[~own, list(_WEATHER)] = np.nan
            note["weather_null_rows"] = int((~own).sum())
            note["weather_null_regions"] = sorted(region[~own].unique().tolist())
    sums = {k: v for k, v in _OBSERVED_SUMS.items() if k in t and v in t}
    for filled, observed in sums.items():
        t[filled] = t[observed]
    if sums:
        note["observed_sums"] = sorted(sums)
    return t, note


def official_features(features: list[str], table: Any) -> list[str]:
    """The team's input list without the estimated columns, plus the withheld-cell count (when the table has it)."""
    out = [f for f in features if f not in _ESTIMATED_INPUTS]
    if _MASKED_CELLS in table and _MASKED_CELLS not in out:
        out.append(_MASKED_CELLS)
    return out


def use_register_floor_area(P: Any) -> None:
    """The predict module's floor area (out-of-range notes, floor area before/after, jump check) from the building
    register (``reg_floor_area_m2``) instead of the estimated total, which is no longer an input. The scenario code
    adds a plan's area to both columns, so before/after stay consistent. ``predict`` reads ``FLOOR_TOTAL`` at call time."""
    P.FLOOR_TOTAL = _REGISTER_FLOOR


def _patch_inputs(P: Any) -> None:
    """Wrap ``load_training`` (predict and baseline look it up at call time) so every table gets ``official_inputs``."""
    from urban_carbon.modeling import baseline as B

    if INPUTS != "official" or getattr(B, "_official_inputs", False):
        return
    import pandas

    asos = pandas.read_csv(STATION_FILE, dtype={"region_code": str, "station": str}) if STATION_FILE.is_file() else None
    factor_high: set[str] = set()
    if FACTOR_FILE.is_file():
        f = pandas.read_csv(FACTOR_FILE, dtype={"region_code": str, "factor_2024": str})
        factor_high = set(f.loc[f["factor_2024"] == str(_FACTOR_HIGH), "region_code"])
    STATE["inputs"]["elec_factor_2024_high_regions"] = sorted(factor_high)
    _INPUT_SOURCES.update(asos=asos, factor_high=factor_high)
    original = B.load_training

    def load_training(folder: Path) -> tuple[Any, list[str]]:
        table, features = original(folder)
        rd: dict[str, int] = {}
        if REGION_DROP == "cell" and "root" in _CODE:
            import region_drop
            from urban_carbon.modeling.energy_mix import add_energy_mix

            table, rd = region_drop.training_table(Path(folder), _CODE["root"] / "config" / "rules.yaml", factor_high,
                                                   _FACTOR_BASE, _FACTOR_HIGH, add_energy_mix)
        table, note = official_inputs(table, Path(folder), asos, factor_high)
        note.update(rd)
        features = official_features(features, table)
        note["inputs"] = len(features)
        STATE["inputs"]["tables"][Path(folder).name] = note
        return table, features

    B.load_training = load_training
    P.load_training = load_training
    use_register_floor_area(P)
    B._official_inputs = True


def _patch_pairs(P: Any) -> None:
    """Leave the pair input ``after_year`` out (``AFTER_YEAR_INPUT`` off). ``_Trained`` builds its pairs through
    ``predict.build_pairs``; ``pair_inputs`` reindexes a plan's inputs to the fitted columns, so it drops out there too."""
    if AFTER_YEAR_INPUT != "off" or getattr(P, "_after_year_off", False):
        return
    from dataclasses import replace

    original = P.build_pairs

    def build_pairs(*args: Any, **kwargs: Any) -> Any:
        pairs = original(*args, **kwargs)
        if "after_year" in pairs.matrix:
            pairs = replace(pairs, matrix=pairs.matrix.drop(columns=["after_year"]))
        return pairs

    P.build_pairs = build_pairs
    P._after_year_off = True


def _patch_warnings(P: Any) -> None:
    """Use-class warnings with this model's development-level numbers (record §39: 42 regions held out, cross-validated
    developments of 1,000 tCO2e and more, 12 seeds). The team text quoted cell cases of the team inputs (0.42~0.46)."""
    from urban_carbon.modeling import use_class as U

    def scope_warnings(use: str) -> list[str]:
        if use == U.INDUSTRIAL:
            return ["범위 밖: 공장·물류 위주 계획. 탄소공간지도가 그 에너지를 거의 담지 않아 맞히지 못함(개발 단위 47개 오차 0.59, "
                    "예측 합이 실제의 0.67배) — 값보다 방향·크기 등급으로만 읽을 것"]
        if use == U.COMMERCIAL:
            return ["상업·업무 위주 계획: 개발 단위 33개 오차 중앙값 0.56, ±50% 안 42%, 예측 합이 실제의 0.70배(작게 잡음) "
                    "— 주거(0.30 · 75%)보다 크게 빗나가므로 구간을 넓게 읽을 것"]
        if use == U.OTHER_NONRES:
            return ["기타 비주거(교육·의료 등) 위주 계획: 검증 개발이 12개뿐(오차 0.34)이라 정확도를 말하기 어려움 — 구간을 넓게 읽을 것"]
        return []

    P.scope_warnings = scope_warnings


def _patch_bands(P: Any) -> None:
    """Bands of a plan and of several plans together from this model's development-level residuals (``BANDS_FILE``)."""
    if not BANDS_FILE.is_file() or getattr(P, "_dev_bands", False):
        return
    import pandas

    bands = pandas.read_csv(BANDS_FILE, encoding="utf-8")
    P.load_bands = lambda folder: bands
    P.load_unit_bands = lambda folder: bands
    P._dev_bands = True


def _patch_case_weights(P: Any) -> None:
    """``_Trained`` weights the pairs of the cases it reads from ``CASES_FILE`` (also the fill stats' source, unchanged);
    the evaluated model weights the cases of ``developments.csv``. Swap only the cases ``chosen_pairs`` sees there."""
    if CASE_WEIGHTS != "developments":
        return
    from urban_carbon.modeling.developments import chosen_pairs, load_developments

    def chosen(cases: Any, table: Any, settings: Any) -> Any:
        dev = load_developments(_CODE["root"] / "data" / "processed" / TRAIN)
        return chosen_pairs(dev if dev is not None else cases, table, settings)

    P.chosen_pairs = chosen


def train() -> None:
    snap, code = find_code()
    if code is None:
        STATE.update(status="unavailable", error=f"팀 인계 묶음이 없습니다: {TEAM_ROOT}/<묶음 날짜>/code (src/urban_carbon, data/processed/{TRAIN})")
        return
    try:
        sys.path.insert(0, str(code / "src"))
        import numpy
        import pandas
        import sklearn
        from urban_carbon.core.paths import ProjectPaths
        from urban_carbon.modeling import predict as P
        _CODE["root"] = code
        _fix_band_sign(P)
        _patch_inputs(P)
        _patch_pairs(P)
        _patch_bands(P)
        _patch_warnings(P)
        _patch_case_weights(P)
        STATE["inputs"].update(region_drop=REGION_DROP, after_year_input=AFTER_YEAR_INPUT, case_weights=CASE_WEIGHTS,
                               area_nearest_year=AREA_NEAREST_YEAR, area_empty_land=AREA_EMPTY_LAND,
                               bands=BANDS_FILE.name if BANDS_FILE.is_file() else "team")
        from urban_carbon.modeling.settings import load_baseline, load_change

        STATE.update(snapshot=snap, versions={"python": sys.version.split()[0], "numpy": numpy.__version__, "pandas": pandas.__version__,
                                              "scikit-learn": sklearn.__version__})
        paths = ProjectPaths(code)
        config = paths.config_dir / "modeling.yaml"
        settings, change = load_baseline(config), load_change(config)
        if change is None:
            raise RuntimeError(f"{config}에 change_model 절이 없습니다")
        processed = paths.processed_dir
        STATE["regions"] = sorted(p.name for p in processed.iterdir() if p.is_dir() and p.name[:5].isdigit() and p.name[5:6] == "_")
        acceptance = processed / TRAIN / "baseline" / "change_acceptance.csv"
        if acceptance.is_file():
            STATE["acceptance"] = pandas.read_csv(acceptance, encoding="utf-8").to_dict("records")
        STATE.update(status="training", started_at=_now())
        t0 = time.time()
        trained = P._Trained(paths, TRAIN, settings, change, None)
        _CTX.update(P=P, paths=paths, settings=settings, change=change, trained=trained, processed=processed, pandas=pandas)
        STATE.update(status="ready", ready_at=_now(), train_seconds=round(time.time() - t0, 1), pair_inputs=int(len(trained.fitted.columns)))
    except Exception as exc:  # noqa: BLE001 - reported on /status
        traceback.print_exc()
        STATE.update(status="error", error=f"{type(exc).__name__}: {exc}")


def region_folder(code: str) -> Path | None:
    processed: Path = _CTX["processed"]
    found = sorted(p for p in processed.glob(f"{code}_*") if p.is_dir())
    return found[0] if found else None


def cell_context(code: str) -> tuple[Any, str, Any]:
    """(context, dataset name, region filter) for a region code.

    학습 42곳은 팀 예시(``predict --name 00_합본_7차``)처럼 합본 표에서 그 지역 행으로 칸 상태를 고르고, 나머지(시험 10곳·동탄)는
    그 지역 표(``--name <지역> --train 00_합본_7차``)를 쓴다. 모델·환산 계수·구간은 어느 쪽이든 합본으로 학습한 것."""
    trained = _CTX["trained"]
    table = trained.table
    if "region" in table:
        names = sorted({str(v) for v in table["region"].unique() if str(v).startswith(f"{code}_")})
        if names:
            return trained, names[0], names[0]
    folder = region_folder(code)
    if folder is None:
        raise LookupError(f"팀 데이터셋에 지역 {code}이(가) 없습니다(53개 지역만)")
    if folder.name not in _TABLES:
        from urban_carbon.modeling.baseline import load_training
        own = load_training(folder)[0]
        missing = [f for f in trained.features if f not in own]
        if missing:
            raise LookupError(f"{folder.name} 표에 학습 입력 {missing}이(가) 없습니다")
        _TABLES[folder.name] = own
    ctx = copy.copy(trained)
    ctx.folder = folder
    ctx.cell_table = _TABLES[folder.name]
    return ctx, folder.name, None


def grid_id_of(table: Any, x: int, y: int, region: str | None) -> str | None:
    rows = table[(table["x_min_m"].round() == x) & (table["y_min_m"].round() == y)]
    if region is not None and "region" in rows:
        rows = rows[rows["region"].astype(str) == region]
    return str(rows["grid_id_500m"].iloc[0]) if len(rows) else None


def _item(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or "use" not in raw or "floor_area_m2" not in raw:
        raise ValueError("항목마다 use와 floor_area_m2가 필요합니다")
    out = {"use": str(raw["use"]), "floor_area_m2": float(raw["floor_area_m2"])}
    for key in ("dwellings", "buildings", "floors", "height_m"):
        if raw.get(key) is not None:
            out[key] = float(raw[key])
    return out


def predict(body: dict[str, Any], context: tuple[Any, str, Any] | None = None) -> dict[str, Any]:
    import yaml

    P, settings, change = _CTX["P"], _CTX["settings"], _CTX["change"]
    code = str(body.get("region") or "")
    plans = body.get("plans") or []
    if not code.isdigit() or len(code) != 5 or not isinstance(plans, list) or not 1 <= len(plans) <= MAX_PLANS:
        raise ValueError(f"region(5자리 코드)과 plans(1~{MAX_PLANS}개)가 필요합니다")
    ctx, dataset, region = context or cell_context(code)
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, plan in enumerate(plans):
            grid = grid_id_of(ctx.cell_table, int(plan["x"]), int(plan["y"]), region)
            if grid is None:
                raise LookupError(f"칸 ({plan['x']}, {plan['y']})은 {dataset} 표에서 학습에 쓸 수 있는 해가 없습니다(결측·결함 표시 칸)")
            doc: dict[str, Any] = {"cell": grid, "new": [_item(r) for r in plan.get("new") or []],
                                   "removed": [_item(r) for r in plan.get("removed") or []]}
            if region is not None:
                doc["region"] = region
            doc["years_after"] = int(plan["years_after"]) if plan.get("years_after") is not None else DEFAULT_YEARS_AFTER
            if plan.get("year") is not None:  # the area path starts every cell from the same state year
                doc["year"] = int(plan["year"])
            if plan.get("zone"):
                doc["zone"] = str(plan["zone"])
            path = Path(tmp) / f"plan_{i + 1}.yaml"
            path.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
            result = P._predict_one(ctx, path, settings, change)
            results.append(result)
    out: dict[str, Any] = {"dataset": dataset, "cell_table": TRAIN if region else dataset, "train": TRAIN, "snapshot": STATE["snapshot"],
                           "results": [dict(asdict(r), describe=P.describe(r)) for r in results], "combined": None}
    if len(results) > 1:
        combined = P.combine(results, P.load_unit_bands(_CTX["trained"].train_folder), change)
        out["combined"] = dict(asdict(combined), describe=P.describe_combined(combined))
    return out


def split_equal(items: list[dict[str, Any]], k: int) -> list[dict[str, Any]]:
    """A development's items (use totals) for one of its k cells: floor area and dwellings / k (record §41: the equal split
    predicted the developments as well as the register's own split, error 0.221 vs 0.226, sum ratio 0.979 vs 0.950)."""
    out = []
    for raw in items:
        it = _item(raw)
        cell = {"use": it["use"], "floor_area_m2": it["floor_area_m2"] / k}
        if it.get("dwellings"):
            cell["dwellings"] = it["dwellings"] / k
        out.append(cell)
    return out


def usable_years(ctx: Any, x: int, y: int, region: str | None) -> tuple[str | None, set[int], str | None]:
    """(grid id, years the model can start from, reason when none) — ``pick_row``'s rule (usable rows of the cell)."""
    table = ctx.cell_table
    grid = grid_id_of(table, x, y, region)
    if grid is None:
        return None, set(), "쓸 수 있는 해가 없는 칸(결측·결함 표시이거나 이 지역 표 밖)"
    rows = table[table["grid_id_500m"].astype(str) == grid]
    if region is not None and "region" in rows:
        rows = rows[rows["region"].astype(str) == region]
    if "train_usable" in rows:
        rows = rows[rows["train_usable"].astype(bool)]
    years = {int(v) for v in rows["year"]}
    return grid, years, None if years else "쓸 수 있는 해가 없는 칸(결측·결함 표시)"


def common_year(years_of: list[set[int]]) -> int | None:
    """The state year all cells of a development start from (record §43 R-a): the latest year at least half of the cells can
    use; without one, the year most cells can use (the later one on a tie). A prediction is the change from that year, so an
    early year mixes in change that has already happened; one shared year keeps the cells on the same period (§42)."""
    count: dict[int, int] = {}
    for ys in years_of:
        for yr in ys:
            count[yr] = count.get(yr, 0) + 1
    if not count:
        return None
    half = [yr for yr, n in count.items() if 2 * n >= len(years_of)]
    return max(half) if half else max(count, key=lambda yr: (count[yr], yr))


def nearest_year(years: set[int], year: int) -> int | None:
    """§43 R-b: a cell without a usable row in the shared year starts from its own usable year nearest to it (earlier on a tie)."""
    return min(years, key=lambda yr: (abs(yr - year), yr)) if years else None


_EMPTY: dict[str, Any] = {}


def empty_land_rows(ctx: Any, folder_name: str, region: str | None) -> Any:
    """§43 R-c: state rows for the cells without a usable row that are empty land by the providers' own values — no
    building emission in any year, the register floor area given as 0 in every year it is given, no 국토통계 building count
    above 0. Their emission (NULL or 0 from the carbon map) is read as 0, the only value an empty cell can have; the rows get
    the same edits as every table (team energy mix, ``official_inputs``) and ``train_usable`` for ``pick_row``. Cached per table."""
    import pandas

    key = folder_name
    if key not in _EMPTY:
        folder = _CTX["processed"] / folder_name
        raw = pandas.read_csv(folder / "training.csv", encoding="utf-8", low_memory=False)
        cells = ["region", "grid_id_500m"] if "region" in raw else ["grid_id_500m"]
        table = ctx.cell_table
        live = table[table["train_usable"].astype(bool)] if "train_usable" in table else table  # cells pick_row can start from
        kept = set(map(tuple, live[cells].astype(str).drop_duplicates().to_numpy()))
        raw_keys = list(map(tuple, raw[cells].astype(str).to_numpy()))
        cand = raw[[k not in kept for k in raw_keys]]
        cand = cand.assign(**{c: cand[c].astype(str) for c in cells})
        g = cand.groupby(cells)
        emis = g[_TOTAL].max().fillna(0.0) <= 0
        reg_n, reg_max = g["reg_floor_area_m2"].count(), g["reg_floor_area_m2"].max()
        bld = g["building_count_sum"].max().fillna(0.0) <= 0 if "building_count_sum" in cand else True
        empty = emis & (reg_n > 0) & (reg_max <= 0) & bld
        chosen = {v if isinstance(v, tuple) else (v,) for v in empty[empty].index}
        rows = cand[[k in chosen for k in map(tuple, cand[cells].astype(str).to_numpy())]].copy()
        for c in [col for col in rows.columns if col in (_ELEC, _GAS, _HEAT, _TOTAL) or col.startswith(("elec_tco2e_m", "gas_tco2e_m", "heat_tco2e_m"))]:
            rows[c] = rows[c].fillna(0.0)
        rows["train_usable"] = True
        if len(rows):
            from urban_carbon.modeling.energy_mix import add_energy_mix
            rows, _ = official_inputs(add_energy_mix(rows.reset_index(drop=True)), folder, _INPUT_SOURCES.get("asos"), _INPUT_SOURCES.get("factor_high"))
        _EMPTY[key] = rows.reindex(columns=table.columns)
    rows = _EMPTY[key]
    if region is not None and "region" in rows:
        rows = rows[rows["region"].astype(str) == region]
    return rows


def predict_area(body: dict[str, Any]) -> dict[str, Any]:
    """One development over several cells: the use totals split equally over the cells, each cell predicted with the service
    model and added up (``combine``: development band). Every cell starts from the shared state year (§43 R-a); a cell without
    a usable row that year starts from its nearest usable year (R-b), an empty-land cell from the empty state (R-c); the rest
    are left out and listed, and the totals stay."""
    import copy as _copy

    import pandas

    code = str(body.get("region") or "")
    cells = body.get("cells") or []
    new, removed = body.get("new") or [], body.get("removed") or []
    if not code.isdigit() or len(code) != 5 or not isinstance(cells, list) or not 1 <= len(cells) <= MAX_PLANS:
        raise ValueError(f"region(5자리 코드)과 cells(1~{MAX_PLANS}칸)가 필요합니다")
    if not isinstance(new, list) or not isinstance(removed, list) or len(new) > MAX_AREA_ITEMS or len(removed) > MAX_AREA_ITEMS:
        raise ValueError(f"신축·철거는 각각 {MAX_AREA_ITEMS}줄까지입니다")
    if not new and not removed:
        raise ValueError("신축이나 철거를 하나 이상 적어 주세요")
    ctx, dataset, region = cell_context(code)
    found = [(int(c["x"]), int(c["y"]), *usable_years(ctx, int(c["x"]), int(c["y"]), region)) for c in cells]
    # a named state year (checks against past developments) or R-a
    year = int(body["year"]) if body.get("year") is not None else common_year([ys for *_, ys, _ in found if ys])
    # the same table the cell states come from: the training join for its 42 regions (filtered by region), else the region table
    empty = empty_land_rows(ctx, TRAIN if region is not None else dataset, region) if AREA_EMPTY_LAND else None
    empty_xy = set(zip(empty["x_min_m"].round().astype(int), empty["y_min_m"].round().astype(int))) if empty is not None and len(empty) else set()
    used, skipped, extra = [], [], []
    for x, y, grid, ys, why in found:
        if year is not None and year in ys:
            used.append({"x": x, "y": y, "grid_id": grid, "year": year, "start": "shared"})
        elif ys and AREA_NEAREST_YEAR and year is not None:
            used.append({"x": x, "y": y, "grid_id": grid, "year": nearest_year(ys, year), "start": "nearest"})
        elif (x, y) in empty_xy:
            rows = empty[(empty["x_min_m"].round() == x) & (empty["y_min_m"].round() == y)]
            pick = rows.iloc[(rows["year"] - (year or int(rows["year"].max()))).abs().argsort()[:1]]
            extra.append(pick)
            used.append({"x": x, "y": y, "grid_id": str(pick["grid_id_500m"].iloc[0]), "year": int(pick["year"].iloc[0]), "start": "empty"})
        else:
            skipped.append({"x": x, "y": y, "reason": why if not ys else f"기준 해({year}년)에 쓸 수 있는 자료가 없는 칸(이 칸은 {', '.join(map(str, sorted(ys)))}년만)"})
    if not used:
        raise LookupError(f"구역의 칸 {len(cells)}개 모두 모델이 쓸 수 있는 해가 없습니다(결측·결함 표시 칸이거나 이 지역 표 밖)")
    context = None
    if extra:
        ctx = _copy.copy(ctx)
        ctx.cell_table = pandas.concat([ctx.cell_table, *extra], ignore_index=True)
        context = (ctx, dataset, region)
    k = len(used)
    per_new, per_removed = split_equal(new, k), split_equal(removed, k)
    years = body.get("years_after")
    plans = [{"x": u["x"], "y": u["y"], "year": u["year"], "new": per_new, "removed": per_removed, "years_after": years} for u in used]
    started = time.time()
    out = predict({"region": code, "plans": plans}, context)
    if out["combined"] is None:  # one usable cell: the development is that cell
        r = out["results"][0]
        out["combined"] = {"cells": [r["cell"]], "site_kind": r["site_kind"], "change_tco2e": r["change_tco2e"], "band": r["band"],
                           "sources_tco2e": r.get("sources_tco2e"), "attribution": r.get("attribution"),
                           "out_of_range": r.get("out_of_range") or [], "describe": r.get("describe")}
    if year is None:  # only empty-land cells: their own state year
        year = max(u["year"] for u in used)
    out["area"] = {"split": "equal", "year": year, "cells_total": len(cells), "cells_used": used, "cells_skipped": skipped,
                   "per_cell": {"new": per_new, "removed": per_removed}, "seconds": round(time.time() - started, 1)}
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "team-model/1"

    def _send(self, code: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=float).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:  # one short line per request, no bodies
        sys.stderr.write("%s %s\n" % (self.command, self.path.split("?")[0]))

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/health"):
            self._send(200, {"ok": True})
        elif self.path.startswith("/status"):
            self._send(200, STATE)
        else:
            self._send(404, {"detail": "없는 주소"})

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.startswith("/predict"):
            self._send(404, {"detail": "없는 주소"})
            return
        if STATE["status"] != "ready":
            self._send(503, {"detail": {"training": "변화 모델을 학습하는 중입니다(1~3분)", "starting": "시작하는 중입니다"}.get(STATE["status"], STATE.get("error") or STATE["status"]),
                             "status": STATE["status"]})
            return
        try:
            length = min(int(self.headers.get("Content-Length") or 0), 64 * 1024)
            body = json.loads(self.rfile.read(length) or b"{}")
            with _PREDICT_LOCK:
                self._send(200, predict_area(body) if self.path.startswith("/predict-area") else predict(body))
        except (ValueError, KeyError, TypeError) as exc:
            self._send(422, {"detail": str(exc)})
        except LookupError as exc:
            self._send(404, {"detail": str(exc)})
        except Exception as exc:  # noqa: BLE001 - the team code raises its own ConfigError/RawDataError
            traceback.print_exc()
            name = type(exc).__name__
            if name in ("ConfigError", "RawDataError"):  # the team code's own checks: the plan or the table is the cause
                self._send(422, {"detail": f"변화 모델이 이 계획을 계산하지 못했습니다(입력 · 표 점검: {exc})"})
            else:
                self._send(500, {"detail": f"변화 모델 계산 중 예상하지 못한 오류가 났습니다({name}). 서비스 기록(docker logs)에 자세한 내용이 있습니다"})


def main() -> None:
    threading.Thread(target=train, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
