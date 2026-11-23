"""칸 · 해 상태 표: 팀 변화 모델 변형 H의 입력을 이 도구 DB로 만든다 (U2-c 1단계, 2026-11-23).

한 줄 = 500m 칸 하나 · 해 하나. 열 이름은 팀 학습 표(`training.csv`)와 같다. 변형 H(국토통계지도 100m 없음 ·
탄소공간지도 입력 없음 · 대장 용도별 연면적 없음)가 쓰는 상태 열 26개만 만든다.

| 묶음 | 열 | 출처(이 도구 DB) | 팀 규칙 |
|---|---|---|---|
| 용도지역 | `zone_*_cells` 9 · `zone_main_class` | `vworld_zoning_areas` (UQ111~114) | 100m 칸 중심 25점, 여러 구역이면 가장 작은 구역 |
| SGIS | `sgis_households` · `sgis_housing_units` · `sgis_population` | `sgis_grid500_values` | 500m 값 그대로 |
| 기상 | `temp_avg_c` · `heating_degree_days_c` · `cooling_degree_days_c` | `region_weather_monthly` / `weather_monthly` | 12달 모두 같은 시 ASOS일 때만 |
| 대장 합계 | `reg_floor_area_m2` · 주거 · 비주거 · `reg_dwellings` · `reg_building_count` | `building_register` + `cadastral_parcels` | 지번 100m 칸 면적 비율로 나눔, 사용승인 기준 달 |
| 단지 | `complex_count` | `building_register` (+ K-apt 승인일) | 대표 지번 도형이 닿는 500m 칸마다 1 |
| 대장 형태 | `regform_*` 4 | `building_register` + `cadastral_parcels` | 지번 몫이 가장 큰 100m 칸의 500m 칸, 0 · 빈 값은 NULL |

팀과 다르게 둔 것(기준 문서 1절 원칙 1 — 없는 값은 0이 아니다):
* SGIS 파일에 줄이 없는 칸 · 비공개 값은 팀이 0으로 읽지만 여기서는 NULL로 두고 `sgis_quality = NO_ROW`로 표시한다.
  모델에 넣을 때 팀처럼 0으로 바꿀지는 서비스 변경 단계에서 정한다(값을 고치지 않고 입력 단계에서만).
* 대장 합계는 그 지역 대장을 받았으면 건물이 없는 칸이 0(조회 결과 0동)이고, 대장을 받지 않은 지역이면 NULL.
* 주거 · 비주거 연면적은 층별개요가 DB에 없어 팀의 대체 규칙(표제부 주용도가 단독 · 공동주택이면 전부 주거)만 쓴다
  → `reg_quality = APPROX_TITLE_PURPOSE`(근사).
* 경계 칸은 칸 전체 값(용도지역 · SGIS)과 그 지역 대장만(대장)이 섞인다 → `state_partial = True`.

넓이 몫은 팀처럼 도형 안에 격자점(지번 5m, 단지 2m, 점 좌표 (k + 0.5) × 간격)을 찍어 센다.
모든 무거운 질의는 지역 조건(법정 시군구 코드 범위 · 그 지역 칸 목록)을 건다. 이 모듈은 DB에 쓰지 않는다.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import date
from typing import Any, Iterable

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- constants (team rules, read-only bundle)
# team config/rules.yaml register_buildings.max_shell_ratio
MAX_SHELL_RATIO = 2.0
# team config/sources.yaml vworld_parcel_all.settings: split_area_m2, sample_step_m
SPLIT_AREA_M2 = 2500.0
PARCEL_STEP_M = 5.0
# team config/rules.yaml complex_link.sample_step_m
COMPLEX_STEP_M = 2.0
# team config/sources.yaml vworld_parcel.settings.selection.min_households (complexes placed on the grid)
COMPLEX_MIN_HOUSEHOLDS = 200
# team rules.yaml register_buildings.residential_title_purposes (buildings without floor records)
RESIDENTIAL_TITLE_PURPOSES = ("단독주택", "공동주택")
# team quality.json approval_cutoff: the NGII building statistics month (2016-08); other years end in December
CUTOFF_MONTHS = {2016: "2016-08"}
MAIN_BUILDING = "주건축물"
APARTMENTS = "공동주택"
CELL_500_M = 500
CELL_100_M = 100
MIN_AGE_YEAR = 1900  # regform_build.py: approval years before 1900 are not real dates

# team config/variables.yaml zoning_classes (VWorld uname -> class); other names -> other, no outline -> none
ZONE_CLASSES = {
    "제1종전용주거지역": "residential", "제2종전용주거지역": "residential", "제1종일반주거지역": "residential",
    "제2종일반주거지역": "residential", "제3종일반주거지역": "residential", "준주거지역": "residential",
    "중심상업지역": "commercial", "일반상업지역": "commercial", "근린상업지역": "commercial", "유통상업지역": "commercial",
    "전용공업지역": "industrial", "일반공업지역": "industrial", "준공업지역": "industrial",
    "보전녹지지역": "green", "생산녹지지역": "green", "자연녹지지역": "green",
    "보전관리지역": "management", "생산관리지역": "management", "계획관리지역": "management",
    "농림지역": "agricultural", "자연환경보전지역": "conservation",
}
# team zoning.class_names: sorted classes, then other, then none (idxmax takes the first on ties)
ZONE_ORDER = [*sorted(set(ZONE_CLASSES.values())), "other", "none"]
ZONE_LAYERS = ("LT_C_UQ111", "LT_C_UQ112", "LT_C_UQ113", "LT_C_UQ114")

ID_COLUMNS = ["region", "grid_id_500m", "year", "x_min_m", "y_min_m"]
ZONE_COLUMNS = [f"zone_{name}_cells" for name in ZONE_ORDER] + ["zone_main_class"]
SGIS_COLUMNS = ["sgis_households", "sgis_housing_units", "sgis_population"]
WEATHER_COLUMNS = ["temp_avg_c", "heating_degree_days_c", "cooling_degree_days_c"]
REG_COLUMNS = ["reg_floor_area_m2", "reg_residential_floor_area_m2", "reg_nonresidential_floor_area_m2",
               "reg_dwellings", "reg_building_count"]
COMPLEX_COLUMNS = ["complex_count"]
REGFORM_COLUMNS = ["regform_area_mean_m2", "regform_floors_mean", "regform_height_mean_m", "regform_age_mean_years"]
# the 26 cell-state inputs of variant H (dev_eval.py mode rd_train_noyear_no100m_regsub_regform_nolog_nomix_noreguse)
STATE_COLUMNS = ZONE_COLUMNS + SGIS_COLUMNS + WEATHER_COLUMNS + REG_COLUMNS + COMPLEX_COLUMNS + REGFORM_COLUMNS
GROUPS = {"zone": ZONE_COLUMNS, "sgis": SGIS_COLUMNS, "weather": WEATHER_COLUMNS, "reg": REG_COLUMNS,
          "complex": COMPLEX_COLUMNS, "regform": REGFORM_COLUMNS}
SOURCES = {
    "zone": "VWorld 용도지역 LT_C_UQ111~114(vworld_zoning_areas, 한 시점) · 100m 중심점 규칙",
    "sgis": "SGIS 500m 격자 통계(sgis_grid500_values) 그 해 값",
    "weather": "KMA ASOS 같은 시 관측소 월값(region_weather_monthly / weather_monthly) 12달",
    "reg": "건축HUB 표제부(building_register) · 연속지적 도형(cadastral_parcels) 면적 비율",
    "complex": "건축HUB 표제부 공동주택 주건축물 세대 합 200 이상 지번 · 지번 도형",
    "regform": "건축HUB 표제부 건축면적 · 지상층수 · 높이 · 사용승인일",
}
SUPPORT_COLUMNS = ["grid_id", "state_partial", "weather_station_id", "regform_buildings", "sgis_quality", "weather_quality",
                   "reg_quality", "complex_quality", "zone_quality", "regform_quality"] + [f"{g}_source" for g in GROUPS]
COLUMNS = ID_COLUMNS + STATE_COLUMNS + SUPPORT_COLUMNS

_X0, _Y0 = 700_000, 1_300_000
_X_LETTERS = "가나다라마바사"
_Y_LETTERS = "가나다라마바사아"
_LAND_DIGIT = {"0": "1", "1": "2"}  # register platGbCd 0 land, 1 mountain (2 block: no parcel number)


# --------------------------------------------------------------------------- pure helpers
def team_pnu(sigungu: Any, bjdong: Any, plat_gb: Any, bun: Any, ji: Any) -> str | None:
    """19-digit PNU of a register lot by the team rule (`core/lots.pnu_of`): block lots and short numbers get none."""
    parts = [("" if v is None else str(v).strip()) for v in (sigungu, bjdong, plat_gb, bun, ji)]
    sigungu, bjdong, plat_gb, bun, ji = parts
    land = _LAND_DIGIT.get(plat_gb)
    sized = all(len(c) == n and c.isdigit() for c, n in ((sigungu, 5), (bjdong, 5), (bun, 4), (ji, 4)))
    return f"{sigungu}{bjdong}{land}{bun}{ji}" if land and sized else None


def register_date(value: Any) -> str | None:
    """YYYY-MM-DD of a register YYYYMMDD day, None for a blank or invalid day (team `register_fields.date`)."""
    text = "" if value is None else str(value).strip()
    if len(text) != 8 or not text.isdigit():
        return None
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:])).isoformat()
    except ValueError:
        return None


def number(value: Any) -> float | None:
    """A register number; blank or non-numeric = None (never 0)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        out = float(text)
    except ValueError:
        return None
    return out if math.isfinite(out) else None


def positive(value: Any) -> float | None:
    """regform rule: 0, negative or empty = not recorded (None)."""
    out = number(value)
    return out if out is not None and out > 0 else None


def approval_cutoff(year: int) -> str:
    """Last approval month (YYYY-MM) that counts for the year's register totals."""
    return CUTOFF_MONTHS.get(int(year), f"{int(year)}-12")


def built_by(approval_dates: Iterable[str | None], cutoff: str) -> np.ndarray:
    """Register buildings approved in or before the cutoff month; undated ones count (team `_built_by`)."""
    return np.array([not isinstance(d, str) or d[:7] <= cutoff for d in approval_dates], dtype=bool)


def clean_floor_area(total: float | None, arch: float | None, ground: float | None, under: float | None) -> float:
    """Team `clean_floor_area`: missing = 0 in the sum; above 2 x footprint x max(floors, 1) -> footprint x floors."""
    recorded = total or 0.0
    floors = max((ground or 0.0) + (under or 0.0), 1.0)
    shell = (arch or 0.0) * floors
    return shell if shell > 0 and recorded > MAX_SHELL_RATIO * shell else recorded


def lattice_points(geom: Any, step_m: float) -> tuple[np.ndarray, np.ndarray]:
    """Points (k + 0.5) x step inside the outline (team `geometry.lattice_inside`)."""
    import shapely
    minx, miny, maxx, maxy = geom.bounds
    cols = (np.arange(math.floor(minx / step_m), math.ceil(maxx / step_m)) + 0.5) * step_m
    rows = (np.arange(math.floor(miny / step_m), math.ceil(maxy / step_m)) + 0.5) * step_m
    if not len(cols) or not len(rows):
        return np.array([]), np.array([])
    xs, ys = np.meshgrid(cols, rows)
    xs, ys = xs.ravel(), ys.ravel()
    shapely.prepare(geom)
    inside = shapely.contains_xy(geom, xs, ys)
    return xs[inside], ys[inside]


def cell_shares(geom: Any, cell_m: int, step_m: float, split_area_m2: float = 0.0) -> dict[tuple[int, int], float]:
    """{lower-left corner of a cell: share of the outline's area}, the shares add up to 1.

    An outline of at least ``split_area_m2`` is measured with lattice points; a smaller one (or one too thin for any
    point) goes whole to the cell of its centroid (team `vworld_parcel_all.cell_shares`, `complexes.cell_shares`)."""
    if geom is None or geom.is_empty or geom.area <= 0:
        return {}
    if geom.area >= split_area_m2:
        xs, ys = lattice_points(geom, step_m)
        if len(xs):
            corners = np.stack([np.floor(xs / cell_m), np.floor(ys / cell_m)], axis=1).astype(np.int64) * cell_m
            cells, counts = np.unique(corners, axis=0, return_counts=True)
            return {(int(x), int(y)): int(c) / len(xs) for (x, y), c in zip(cells, counts)}
    c = geom.centroid
    return {(int(math.floor(c.x / cell_m) * cell_m), int(math.floor(c.y / cell_m) * cell_m)): 1.0}


def parcel_placement(geom: Any) -> tuple[dict[tuple[int, int], float], tuple[int, int] | None]:
    """(500m cell -> share of the parcel, 500m cell of the 100m cell with the largest share).

    100m shares as the team (5m lattice for parcels >= 2,500 m², centroid otherwise), rounded to 4 decimals and
    re-normalized like `register_buildings.place_buildings`, then summed per 500m parent."""
    shares = {k: round(v, 4) for k, v in cell_shares(geom, CELL_100_M, PARCEL_STEP_M, SPLIT_AREA_M2).items()}
    total = sum(shares.values())
    if total <= 0:
        return {}, None
    out: dict[tuple[int, int], float] = defaultdict(float)
    for (x, y), s in shares.items():
        out[(x // CELL_500_M * CELL_500_M, y // CELL_500_M * CELL_500_M)] += s / total
    main = max(sorted(shares), key=lambda k: shares[k])  # ties: lowest corner first (team order is by 100m id)
    return dict(out), (main[0] // CELL_500_M * CELL_500_M, main[1] // CELL_500_M * CELL_500_M)


def complex_cells(geom: Any) -> list[tuple[int, int]]:
    """500m cells the complex parcel reaches with its 2m lattice (team `complexes.cell_shares`)."""
    return sorted(cell_shares(geom, CELL_500_M, COMPLEX_STEP_M, 0.0))


def code500(x: int, y: int) -> str | None:
    """National 500m grid id (= SGIS 500m code) of a lower-left corner (team `grid_id`, `sgis_grid500.code500_for`)."""
    ix, iy = (x - _X0) // 100_000, (y - _Y0) // 100_000
    if not (0 <= ix < len(_X_LETTERS) and 0 <= iy < len(_Y_LETTERS)):
        return None
    rx, ry = x - _X0 - ix * 100_000, y - _Y0 - iy * 100_000
    return (f"{_X_LETTERS[ix]}{_Y_LETTERS[iy]}{rx // 1000:02d}{'a' if rx % 1000 < 500 else 'b'}"
            f"{ry // 1000:02d}{'a' if ry % 1000 < 500 else 'b'}")


def cell_corner(grid_id: str) -> tuple[int, int] | None:
    """`cell_<x>_<y>` -> (x, y)."""
    m = re.fullmatch(r"cell_(\d+)_(\d+)", str(grid_id))
    return (int(m.group(1)), int(m.group(2))) if m else None


def zone_counts(names: Iterable[str | None]) -> dict[str, Any]:
    """Zone class counts of the 100m centres of one 500m cell and its main class (team `zoning.zones_500m`).

    ``names`` holds the zone name at each centre (None = no outline). Unknown names count as other."""
    counts = {name: 0 for name in ZONE_ORDER}
    for n in names:
        counts["none" if n is None else ZONE_CLASSES.get(n, "other")] += 1
    zoned = [(name, counts[name]) for name in ZONE_ORDER if name != "none"]
    best = max(zoned, key=lambda kv: kv[1])  # max keeps the first of equal counts, like idxmax
    out: dict[str, Any] = {f"zone_{name}_cells": counts[name] for name in ZONE_ORDER}
    out["zone_main_class"] = best[0] if sum(c for _, c in zoned) > 0 else "none"
    return out


_STATION = re.compile(r"ASOS\s*(?:station)?\s*(\d+)")


def station_of(provider: str | None) -> str | None:
    m = _STATION.search(provider or "")
    return m.group(1) if m else None


def annual_weather(months: list[dict[str, Any]]) -> tuple[dict[str, float | None], str | None, str]:
    """(annual values, station id, quality) of one year (team `weather.annual_weather` + the service own-city rule).

    A value only when all 12 months are OFFICIAL, fully observed and from one station; mean temperature weighted by the
    days of each month (2 decimals), degree days summed (1 decimal). Otherwise every value is None."""
    empty = {c: None for c in WEATHER_COLUMNS}
    stations = {station_of(m.get("provider")) for m in months}
    station = next(iter(stations)) if len(stations) == 1 else None
    if len(months) != 12:
        return empty, station, "NULL_MONTHS_MISSING"
    if any(m.get("source_type") != "OFFICIAL" for m in months):
        return empty, station, "NULL_FALLBACK_MONTH"
    if station is None:
        return empty, None, "NULL_STATION_MIXED"
    if any(m.get("days_observed") != m.get("expected_days") or m.get(k) is None
           for m in months for k in ("mean_temperature", "hdd", "cdd")):
        return empty, station, "NULL_INCOMPLETE_MONTH"
    days = np.array([m["expected_days"] for m in months], dtype=float)
    temp = float(np.dot([m["mean_temperature"] for m in months], days) / days.sum())
    return {"temp_avg_c": round(temp, 2),
            "heating_degree_days_c": round(float(sum(m["hdd"] for m in months)), 1),
            "cooling_degree_days_c": round(float(sum(m["cdd"] for m in months)), 1)}, station, "OBSERVED_ASOS_12M"


# --------------------------------------------------------------------------- per-building tables (pure, tested)
def building_table(rows: Iterable[dict[str, Any]]) -> pd.DataFrame:
    """One row per register title with the values the state columns need (raw register fields in, NULL kept)."""
    out = []
    for r in rows:
        approved = register_date(r.get("useAprDay"))
        ground, under = number(r.get("grndFlrCnt")), number(r.get("ugrndFlrCnt"))
        arch, total = number(r.get("archArea")), number(r.get("totArea"))
        floor_area = clean_floor_area(total, arch, ground, under)
        purpose = (r.get("mainPurpsCdNm") or "").strip()
        housing = 1.0 if purpose in RESIDENTIAL_TITLE_PURPOSES else 0.0
        year = int(approved[:4]) if approved else None
        out.append({
            "pk": r.get("id"),
            "pnu": team_pnu(r.get("sigunguCd"), r.get("bjdongCd"), r.get("platGbCd"), r.get("bun"), r.get("ji")),
            "approval_date": approved,
            "approval_year": year if year is not None and year >= MIN_AGE_YEAR else None,
            "reg_floor_area_m2": floor_area,
            "reg_residential_floor_area_m2": floor_area * housing,
            "reg_nonresidential_floor_area_m2": floor_area * (1.0 - housing),
            "reg_dwellings": (number(r.get("hhldCnt")) or 0.0) + (number(r.get("fmlyCnt")) or 0.0),
            "reg_building_count": 1.0 if (r.get("mainAtchGbCdNm") or "").strip() == MAIN_BUILDING else 0.0,
            "main_apartment": (r.get("mainAtchGbCdNm") or "").strip() == MAIN_BUILDING and purpose == APARTMENTS,
            "households": number(r.get("hhldCnt")),
            "area": positive(arch), "floors": positive(ground), "height": positive(r.get("heit")),
        })
    cols = ["pk", "pnu", "approval_date", "approval_year", *REG_COLUMNS, "main_apartment", "households", "area", "floors", "height"]
    return pd.DataFrame(out, columns=cols)


def register_sums(buildings: pd.DataFrame, shares: pd.DataFrame, years: Iterable[int]) -> pd.DataFrame:
    """(cell x, y, year) -> register totals; ``shares`` = pnu, x, y, share (500m cell of the parcel)."""
    placed = buildings.dropna(subset=["pnu"]).merge(shares, on="pnu", how="inner")
    frames = []
    for year in years:
        on = placed[built_by(placed["approval_date"], approval_cutoff(year))]
        values = on[REG_COLUMNS].multiply(on["share"], axis=0)
        sums = values.groupby([on["x"], on["y"]]).sum().reset_index()
        sums["year"] = int(year)
        frames.append(sums)
    cols = ["x", "y", *REG_COLUMNS, "year"]
    return pd.concat(frames, ignore_index=True)[cols] if frames else pd.DataFrame(columns=cols)


def regform_means(buildings: pd.DataFrame, main_cell: pd.DataFrame, years: Iterable[int]) -> pd.DataFrame:
    """(cell, year) -> mean footprint, ground floors, height and age of the titles approved by the year's end
    (undated titles count but give no age); ``main_cell`` = pnu, x, y (regform_build.py rule)."""
    t = buildings.dropna(subset=["pnu"]).merge(main_cell, on="pnu", how="inner")
    frames = []
    for year in years:
        on = t[t["approval_year"].isna() | (t["approval_year"] <= year)]
        key = [on["x"], on["y"]]
        age = (year - on["approval_year"]).where(on["approval_year"].notna())
        g = pd.DataFrame({"regform_area_mean_m2": on["area"].groupby(key).mean(),
                          "regform_floors_mean": on["floors"].groupby(key).mean(),
                          "regform_height_mean_m": on["height"].groupby(key).mean(),
                          "regform_age_mean_years": age.groupby(key).mean(),
                          "regform_buildings": on["pk"].groupby(key).size()}).reset_index()
        g["year"] = int(year)
        frames.append(g)
    cols = ["x", "y", *REGFORM_COLUMNS, "regform_buildings", "year"]
    return pd.concat(frames, ignore_index=True)[cols] if frames else pd.DataFrame(columns=cols)


def complex_lots(buildings: pd.DataFrame, kapt_dates: dict[str, str] | None = None) -> pd.DataFrame:
    """Lots (pnu) whose main apartment buildings hold at least 200 households, with their approval year.

    Approval: earliest dated main apartment building with households on the lot (team `fill_approval_dates`), else the
    K-apt complex of the same lot (``kapt_dates`` pnu -> YYYY-MM-DD or YYYYMMDD), else unknown (never counted)."""
    apt = buildings[buildings["main_apartment"] & buildings["pnu"].notna()]
    if apt.empty:
        return pd.DataFrame(columns=["pnu", "households", "approval_year", "approval_source"])
    hh = apt.groupby("pnu")["households"].sum(min_count=1)
    lots = hh[hh >= COMPLEX_MIN_HOUSEHOLDS].index
    dated = apt[(apt["households"].fillna(0) > 0) & apt["approval_date"].notna()]
    earliest = dated.groupby("pnu")["approval_date"].min()
    rows = []
    for pnu in lots:
        d, source = earliest.get(pnu), "titles"
        if d is None and kapt_dates and kapt_dates.get(pnu):
            d, source = register_date(str(kapt_dates[pnu]).replace("-", "")), "kapt"
        rows.append({"pnu": pnu, "households": float(hh[pnu]), "approval_year": int(d[:4]) if d else None,
                     "approval_source": source if d else "none"})
    return pd.DataFrame(rows, columns=["pnu", "households", "approval_year", "approval_source"])


def complex_counts(lots: pd.DataFrame, cells: dict[str, list[tuple[int, int]]], years: Iterable[int]) -> pd.DataFrame:
    """(cell, year) -> number of built complexes reaching the cell (approval year <= year; unknown not counted)."""
    rows = []
    for year in years:
        built = lots[lots["approval_year"].notna() & (lots["approval_year"] <= year)]
        count: dict[tuple[int, int], int] = defaultdict(int)
        for pnu in built["pnu"]:
            for cell in cells.get(pnu, []):
                count[cell] += 1
        rows += [{"x": x, "y": y, "complex_count": n, "year": int(year)} for (x, y), n in count.items()]
    return pd.DataFrame(rows, columns=["x", "y", "complex_count", "year"])


def assemble(region: str, cells: pd.DataFrame, years: list[int], zones: pd.DataFrame, sgis: pd.DataFrame,
             weather: dict[int, tuple[dict[str, Any], str | None, str]], reg: pd.DataFrame | None,
             complexes: pd.DataFrame | None, regform: pd.DataFrame | None) -> pd.DataFrame:
    """Join the groups into the state table (one row per cell and year), columns in `COLUMNS` order.

    ``cells``: grid_id, x, y, state_partial. ``reg`` / ``complexes`` None = the region's register is not loaded
    (values NULL); otherwise a cell without buildings gets 0 (register queried, no building)."""
    def keyed(frame: pd.DataFrame, keys: tuple[str, ...] = ("x", "y", "year")) -> pd.DataFrame:
        # empty frames come with object columns; merge keys must share the int dtype
        return frame.astype({k: "int64" for k in keys if k in frame})

    sgis = keyed(sgis, ("year",))
    reg, complexes, regform = (None if f is None else keyed(f) for f in (reg, complexes, regform))
    base = cells.assign(key=1).merge(pd.DataFrame({"year": years, "key": 1}), on="key").drop(columns="key")
    base["region"] = region
    base["grid_id_500m"] = [code500(int(x), int(y)) for x, y in zip(base["x"], base["y"])]
    base["x_min_m"], base["y_min_m"] = base["x"].astype(int), base["y"].astype(int)
    out = base.merge(zones, on="grid_id", how="left")
    out["zone_quality"] = np.where(out["zone_main_class"].isna(), "NULL_NO_ZONING", "CALCULATED_CENTRES_25")
    out = out.merge(sgis, on=["grid_id_500m", "year"], how="left")
    year_has_sgis = set(sgis["year"].unique()) if len(sgis) else set()
    present = out["sgis_households"].notna() | out["sgis_population"].notna() | out["sgis_housing_units"].notna()
    out["sgis_quality"] = np.where(present, "OBSERVED", np.where(out["year"].isin(year_has_sgis), "NO_ROW", "NO_YEAR"))
    for c in WEATHER_COLUMNS:
        out[c] = out["year"].map(lambda y, c=c: weather.get(int(y), ({}, None, ""))[0].get(c))
    out["weather_station_id"] = out["year"].map(lambda y: weather.get(int(y), ({}, None, ""))[1])
    out["weather_quality"] = out["year"].map(lambda y: weather.get(int(y), ({}, None, "NULL_MONTHS_MISSING"))[2])
    if reg is None:
        for c in REG_COLUMNS:
            out[c] = np.nan
        out["reg_quality"] = "NULL_NO_REGISTER"
    else:
        out = out.merge(reg, on=["x", "y", "year"], how="left")
        out[REG_COLUMNS] = out[REG_COLUMNS].fillna(0.0)
        out["reg_quality"] = "APPROX_TITLE_PURPOSE"
    if complexes is None:
        out["complex_count"] = np.nan
        out["complex_quality"] = "NULL_NO_REGISTER"
    else:
        out = out.merge(complexes, on=["x", "y", "year"], how="left")
        out["complex_count"] = out["complex_count"].fillna(0).astype(int)
        out["complex_quality"] = "CALCULATED_FROM_TITLES"
    if regform is None:
        for c in [*REGFORM_COLUMNS, "regform_buildings"]:
            out[c] = np.nan
    else:
        out = out.merge(regform, on=["x", "y", "year"], how="left")
    out["regform_buildings"] = out["regform_buildings"].fillna(0).astype(int)
    out["regform_quality"] = np.where(out["regform_buildings"] > 0, "CALCULATED_MEAN", "NULL_NO_BUILDING")
    for g, text in SOURCES.items():
        out[f"{g}_source"] = text
    return out[COLUMNS].sort_values(["grid_id_500m", "year"], ignore_index=True)


# --------------------------------------------------------------------------- DB (read-only, region-scoped)
def _prefix_ranges(codes: Iterable[str]) -> list[tuple[str, str]]:
    """'41290' -> ('41290', '41291'): a btree range on the 19-digit PNU."""
    return [(c, str(int(c) + 1).zfill(len(c))) for c in codes]


def _region(db: Any, code: str) -> dict[str, Any]:
    from sqlalchemy import text
    row = db.execute(text("SELECT code, name, status, legal_codes FROM study_regions WHERE code = :c"), {"c": code}).mappings().first()
    if row is None:
        raise ValueError(f"지역 {code}이 study_regions에 없음")
    return dict(row)


def load_cells(db: Any, code: str) -> pd.DataFrame:
    from sqlalchemy import text
    rows = db.execute(text(
        "SELECT g.grid_id, (SELECT count(*) FROM grid_regions o WHERE o.grid_id = g.grid_id) > 1 AS shared "
        "FROM grid_regions g WHERE g.region_code = :c"), {"c": code}).all()
    out = []
    for grid_id, shared in rows:
        corner = cell_corner(grid_id)
        if corner:
            out.append({"grid_id": grid_id, "x": corner[0], "y": corner[1], "state_partial": bool(shared)})
    return pd.DataFrame(out, columns=["grid_id", "x", "y", "state_partial"])


def load_zones(db: Any, code: str) -> pd.DataFrame:
    """Zone name at the 25 centres of every region cell: the smallest containing UQ111~114 outline."""
    from sqlalchemy import text
    rows = db.execute(text("""
        WITH cells AS (
            SELECT g.grid_id, split_part(g.grid_id, '_', 2)::int AS x, split_part(g.grid_id, '_', 3)::int AS y
            FROM grid_regions g WHERE g.region_code = :c AND g.grid_id LIKE 'cell\\_%'),
        pts AS (
            SELECT grid_id, ST_SetSRID(ST_MakePoint(x + 50 + 100 * i, y + 50 + 100 * j), 5179) AS p
            FROM cells, generate_series(0, 4) i, generate_series(0, 4) j)
        SELECT pts.grid_id, (SELECT z.zone_name FROM vworld_zoning_areas z
                             WHERE ST_Contains(z.geom, pts.p) AND left(z.zone_code, 10) = ANY(:layers)
                             ORDER BY ST_Area(z.geom) ASC LIMIT 1) AS zone_name
        FROM pts"""), {"c": code, "layers": list(ZONE_LAYERS)}).all()
    by_cell: dict[str, list[str | None]] = defaultdict(list)
    for grid_id, name in rows:
        by_cell[grid_id].append(name)
    has_any = db.execute(text("SELECT EXISTS (SELECT 1 FROM vworld_zoning_areas WHERE left(zone_code, 10) = ANY(:layers))"),
                         {"layers": list(ZONE_LAYERS)}).scalar()
    out = [{"grid_id": g, **zone_counts(names)} for g, names in by_cell.items()] if has_any else []
    return pd.DataFrame(out, columns=["grid_id", *ZONE_COLUMNS])


def load_sgis(db: Any, codes: list[str], years: list[int]) -> pd.DataFrame:
    from sqlalchemy import text
    rows = db.execute(text(
        "SELECT grid_cd, year, households, housing, population FROM sgis_grid500_values "
        "WHERE grid_cd = ANY(:codes) AND year = ANY(:years)"), {"codes": codes, "years": years}).all()
    return pd.DataFrame([{"grid_id_500m": g, "year": int(y), "sgis_households": h, "sgis_housing_units": u,
                          "sgis_population": p} for g, y, h, u, p in rows],
                        columns=["grid_id_500m", "year", *SGIS_COLUMNS])


def load_weather(db: Any, code: str, years: list[int]) -> dict[int, tuple[dict[str, Any], str | None, str]]:
    from .regions import weather_rows
    rows = weather_rows(db, code, f"{min(years)}01", f"{max(years)}12")
    by_year: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_year[int(r.use_ym[:4])].append({k: getattr(r, k, None) for k in (
            "provider", "source_type", "mean_temperature", "hdd", "cdd", "days_observed", "expected_days")})
    return {y: annual_weather(by_year.get(y, [])) for y in years}


_REGISTER_FIELDS = ("sigunguCd", "bjdongCd", "platGbCd", "bun", "ji", "totArea", "archArea", "grndFlrCnt", "ugrndFlrCnt",
                    "heit", "useAprDay", "hhldCnt", "fmlyCnt", "mainAtchGbCdNm", "mainPurpsCdNm")


def load_register(db: Any, legal_codes: list[str]) -> pd.DataFrame:
    from sqlalchemy import text
    fields = ", ".join(f"raw_record->>'{f}' AS \"{f}\"" for f in _REGISTER_FIELDS)
    rows: list[dict[str, Any]] = []
    for lo, hi in _prefix_ranges(legal_codes):
        rows += [dict(r) for r in db.execute(text(
            f"SELECT id, {fields} FROM building_register WHERE parcel_code >= :lo AND parcel_code < :hi"),
            {"lo": lo, "hi": hi}).mappings()]
    return building_table(rows)


def load_parcels(db: Any, pnus: list[str]) -> dict[str, Any]:
    """pnu -> shapely outline (one per pnu, the latest collected)."""
    from shapely import wkb
    from sqlalchemy import text
    out: dict[str, Any] = {}
    for i in range(0, len(pnus), 20_000):
        part = pnus[i:i + 20_000]
        for pnu, blob in db.execute(text(
                "SELECT DISTINCT ON (pnu) pnu, ST_AsBinary(geom) FROM cadastral_parcels WHERE pnu = ANY(:p) "
                "ORDER BY pnu, collected_at DESC"), {"p": part}).all():
            geom = wkb.loads(bytes(blob))
            if geom is not None and not geom.is_empty and geom.area > 0:
                out[pnu] = geom
    return out


def load_kapt_dates(db: Any, legal_codes: list[str]) -> dict[str, str]:
    """pnu (land lots) -> K-apt approval date, only lots with one dated complex."""
    from sqlalchemy import text
    seen: dict[str, set[str]] = defaultdict(set)
    for lo, hi in _prefix_ranges(legal_codes):
        for bjd, bun, ji, approved in db.execute(text(
                "SELECT bjd_code, bun, ji, approval_date FROM apartment_complexes "
                "WHERE bjd_code >= :lo AND bjd_code < :hi AND approval_date IS NOT NULL"), {"lo": lo, "hi": hi}).all():
            b, j = re.sub(r"\D", "", str(bun or "")), re.sub(r"\D", "", str(ji or "0"))
            if bjd and b:
                seen[f"{bjd}1{b.zfill(4)[-4:]}{j.zfill(4)[-4:]}"].add(str(approved))
    return {pnu: next(iter(d)) for pnu, d in seen.items() if len(d) == 1}


def build_cell_state(db: Any, code: str, years: list[int]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """State rows of a study region for the given years, and a summary (counts of what could not be placed)."""
    from sqlalchemy import text
    db.execute(text("SET TRANSACTION READ ONLY"))
    region = _region(db, code)
    legal = [str(c) for c in (region.get("legal_codes") or [code])]
    cells = load_cells(db, code)
    if cells.empty:
        raise ValueError(f"지역 {code}의 칸(grid_regions)이 없음")
    inside = set(zip(cells["x"], cells["y"]))
    codes = [code500(int(x), int(y)) for x, y in inside]
    zones = load_zones(db, code)
    sgis = load_sgis(db, [c for c in codes if c], years)
    weather = load_weather(db, code, years)
    buildings = load_register(db, legal)
    summary: dict[str, Any] = {"region": code, "name": region.get("name"), "status": region.get("status"),
                               "cells": len(cells), "cells_partial": int(cells["state_partial"].sum()),
                               "years": years, "titles": len(buildings),
                               "cutoffs": {y: approval_cutoff(y) for y in years},
                               "weather": {y: w[2] for y, w in weather.items()},
                               "sgis_rows": len(sgis)}
    reg = complexes = regform = None
    if len(buildings):
        pnus = sorted(set(buildings["pnu"].dropna()))
        parcels = load_parcels(db, pnus)
        share_rows, main_rows, outside = [], [], 0
        for pnu, geom in parcels.items():
            shares, main = parcel_placement(geom)
            for (x, y), s in shares.items():
                if (x, y) in inside:
                    share_rows.append({"pnu": pnu, "x": x, "y": y, "share": s})
                else:
                    outside += 1
            if main and main in inside:
                main_rows.append({"pnu": pnu, "x": main[0], "y": main[1]})
        shares_df = pd.DataFrame(share_rows, columns=["pnu", "x", "y", "share"])
        main_df = pd.DataFrame(main_rows, columns=["pnu", "x", "y"])
        reg = register_sums(buildings, shares_df, years)
        regform = regform_means(buildings, main_df, years)
        lots = complex_lots(buildings, load_kapt_dates(db, legal))
        lot_cells = {p: [c for c in complex_cells(parcels[p]) if c in inside] for p in lots["pnu"] if p in parcels}
        complexes = complex_counts(lots, lot_cells, years)
        no_pnu = int(buildings["pnu"].isna().sum())
        no_parcel = int((buildings["pnu"].notna() & ~buildings["pnu"].isin(parcels)).sum())
        summary.update(parcels=len(parcels), titles_no_pnu=no_pnu, titles_no_parcel=no_parcel,
                       parcel_cell_parts_outside_region=outside, complex_lots=len(lots),
                       complex_lots_without_outline=int((~lots["pnu"].isin(parcels)).sum()),
                       complex_approval_source=lots["approval_source"].value_counts().to_dict())
    table = assemble(code, cells, years, zones, sgis, weather, reg, complexes, regform)
    db.rollback()
    return table, summary


def parse_years(text: str) -> list[int]:
    """'2016-2024' / '2016,2018,2024' -> sorted years."""
    years: set[int] = set()
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = (int(v) for v in part.split("-", 1))
            years.update(range(min(a, b), max(a, b) + 1))
        else:
            years.add(int(part))
    if not years:
        raise ValueError("해를 하나 이상 적어야 함")
    return sorted(years)
