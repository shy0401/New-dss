"""팀 변화 모델 서비스 (urban-carbon 7차) — Carbon Urban DSS가 개발 계획의 배출 변화를 묻는 작은 HTTP 서버.

* 팀 코드와 학습 표는 저장소에 넣지 않는다. ``TEAM_ROOT``(compose에서 ``data/raw/team_urban_carbon``을 읽기 전용으로
  붙임) 아래 가장 새 묶음의 ``code/``(urban-carbon 저장소 사본: ``src/``, ``config/``, ``data/processed/``)를 그대로 쓴다.
  학습 표에는 국토통계지도(국외 반출 금지) 값이 들어 있어 이 컨테이너 밖으로 표를 내보내지 않는다.
* 시작하면 뒤에서 ``00_합본_7차``로 변화 모델을 학습한다. 팀의 ``urban-carbon predict``와 같은 함수(``_Trained``,
  ``_predict_one``)를 그대로 불러 같은 답을 낸다(seed 5개 × 합계·에너지원 3, 사례 쌍 가중 ×10). 1~3분.
* 칸의 지금 상태는 그 지역 표(``data/processed/<코드>_<이름>/training.csv``)에서, 모델·환산 계수·구간은 ``00_합본_7차``에서.

GET /health, GET /status, POST /predict {"region": "52110", "plans": [{"x": 959500, "y": 1760500, "new": [...],
"removed": [...], "years_after": 3}]} — 칸은 이 도구의 500m 격자 왼쪽 아래 좌표(EPSG:5179).
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
MAX_PLANS = 9
# official (기본): 아래 두 입력을 공식 값으로 바꿔 학습·예측. team: 받은 팀 코드 그대로(전후 비교용)
INPUTS = os.environ.get("TEAM_INPUTS", "official")
ASOS_FILE = Path(os.environ.get("TEAM_ASOS_FILE", str(Path(__file__).with_name("asos_annual.csv"))))
_ELEC, _GAS, _HEAT = "elec_tco2e_total", "gas_tco2e_total", "heat_tco2e_total"
_WEATHER = ("temp_avg_c", "heating_degree_days_c", "cooling_degree_days_c")
# team estimates with an official value already in the table (audit 2026-11-17 §8): left out of the inputs
_ESTIMATED_INPUTS = ("floor_area_total_est_filled_m2", "complex_households_est")  # → reg_floor_area_m2, reg_dwellings
# counts read as 0 (and masked population as 3 persons) → the provider's observed sums, NULL where none observed
_OBSERVED_SUMS = {"building_count_filled": "building_count_sum", "apartment_building_count_filled": "apartment_building_count_sum",
                  "detached_building_count_filled": "detached_building_count_sum",
                  "population_total_persons_filled": "population_total_persons_sum"}
_MASKED_CELLS = "population_total_persons_masked_cells"  # withheld (N/A) 100 m cells: a provider fact, added as an input
_REGISTER_FLOOR = "reg_floor_area_m2"

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


def official_inputs(table: Any, folder: Path, asos: Any) -> tuple[Any, dict[str, Any]]:
    """Official values in place of borrowed or estimated ones (2026-11-17 retraining, record methods/official-inputs).

    * ``heat_share_ctx``/``gas_share_ctx``: the team code gives a cell under 100 t the share of its 3 x 3 neighbours or of
      the region. Here every cell takes its own carbon-map share (heat or gas ÷ elec + gas + heat of that cell and year);
      a cell with no emission gets NULL, which the learner handles as missing.
    * weather of a region whose own ASOS station has 12 months of a year (``asos_annual.csv``, from region_weather_monthly
      OFFICIAL; Sejong 36110 ← ASOS 239, the team table used Daejeon) replaces temp/HDD/CDD of that region and year.
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
        for r in asos.itertuples(index=False):
            rows = (region == str(r.region_code)) & (t["year"] == int(r.year))
            n = int(rows.sum())
            if n:
                t.loc[rows, list(_WEATHER)] = [float(r.temp_avg_c), float(r.heating_degree_days_c), float(r.cooling_degree_days_c)]
                replaced.append({"region": str(r.region_code), "station": str(r.station), "year": int(r.year), "rows": n})
        note["asos"] = replaced
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

    asos = pandas.read_csv(ASOS_FILE, dtype={"region_code": str, "station": str}) if ASOS_FILE.is_file() else None
    original = B.load_training

    def load_training(folder: Path) -> tuple[Any, list[str]]:
        table, features = original(folder)
        table, note = official_inputs(table, Path(folder), asos)
        features = official_features(features, table)
        note["inputs"] = len(features)
        STATE["inputs"]["tables"][Path(folder).name] = note
        return table, features

    B.load_training = load_training
    P.load_training = load_training
    use_register_floor_area(P)
    B._official_inputs = True


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
        _fix_band_sign(P)
        _patch_inputs(P)
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


def predict(body: dict[str, Any]) -> dict[str, Any]:
    import yaml

    P, settings, change = _CTX["P"], _CTX["settings"], _CTX["change"]
    code = str(body.get("region") or "")
    plans = body.get("plans") or []
    if not code.isdigit() or len(code) != 5 or not isinstance(plans, list) or not 1 <= len(plans) <= MAX_PLANS:
        raise ValueError(f"region(5자리 코드)과 plans(1~{MAX_PLANS}개)가 필요합니다")
    ctx, dataset, region = cell_context(code)
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
            if plan.get("years_after") is not None:
                doc["years_after"] = int(plan["years_after"])
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
                self._send(200, predict(body))
        except (ValueError, KeyError, TypeError) as exc:
            self._send(422, {"detail": str(exc)})
        except LookupError as exc:
            self._send(404, {"detail": str(exc)})
        except Exception as exc:  # noqa: BLE001 - the team code raises its own ConfigError/RawDataError
            traceback.print_exc()
            self._send(422 if type(exc).__name__ in ("ConfigError", "RawDataError") else 500, {"detail": f"{type(exc).__name__}: {exc}"})


def main() -> None:
    threading.Thread(target=train, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
