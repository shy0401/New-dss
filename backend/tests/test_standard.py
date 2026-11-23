"""The shared data standard (docs/DATA_STANDARD.md): degree-day rule, factor schedule, and the CSV check."""
from pathlib import Path

from app import emissions
from app.degree_days import CDD_BASE_C, HDD_BASE_C, degree_days
from app.kma_asos import aggregate_asos_months
from app.standard import check_csv, summary


def test_degree_days_use_18_and_24_and_need_every_day():
    assert (HDD_BASE_C, CDD_BASE_C) == (18.0, 24.0)
    assert degree_days([10.0, 26.0, 18.0], 3) == (8.0, 2.0)
    assert degree_days([10.0, None, 26.0], 3) == (None, None)       # a missing day: no value, not a partial sum
    assert degree_days([], 30) == (None, None)


def test_asos_month_counts_each_date_once_and_skips_incomplete_months():
    rows = [{"observed_date": f"2025-06-{d:02d}", "station_id": "146", "avg_temperature_c": 25.0} for d in range(1, 31)]
    rows.append(dict(rows[0]))  # the same date twice (re-collected page)
    june = aggregate_asos_months(rows)[0]
    assert june["valid_day_count"] == 30 and june["cdd"] == 30.0 and june["hdd"] == 0.0
    july = aggregate_asos_months([{"observed_date": "2025-07-01", "station_id": "146", "avg_temperature_c": 28.0}])[0]
    assert july["hdd"] is None and july["cdd"] is None


def test_electricity_factor_schedule_is_the_registered_one():
    f = emissions.electricity_factor_for_year
    assert [f(y) for y in (2018, 2019, 2021, 2022, 2024, 2025)] == [None, 0.4594, 0.4594, 0.4781, 0.4781, 0.4330]
    registered = {i["effective_from"]: i["factor"] for i in emissions.HISTORIC_ELECTRICITY} | {"2025-03-31": 0.4541}
    assert dict(emissions.ELECTRICITY_SCHEDULE) == registered
    rules = summary()
    assert rules["degree_days"]["cdd_base_c"] == 24.0 and rules["electricity_factors"][-1] == {"published": "2025-12-18", "factor": 0.4330}


def _write(tmp_path: Path, name: str, text: str, encoding: str = "utf-8") -> Path:
    path = tmp_path / name
    path.write_bytes(text.encode(encoding))
    return path


def test_csv_check_finds_null_markers_missing_units_duplicates_and_bad_ids(tmp_path):
    good = _write(tmp_path, "grid.csv", "grid_id,year,electricity_kwh,floor_area_m2\ncell_964000_1757500,2024,100.5,\ncell_964500_1757500,2024,,2000\n")
    assert {i["id"]: i["status"] for i in check_csv(good)} == {
        "csv_encoding": "OK", "csv_header": "OK", "csv_nulls": "OK", "csv_units": "OK", "csv_negative": "OK", "csv_keys": "OK", "csv_grid_id": "OK"}
    bad = _write(tmp_path, "bad.csv", "grid_id,year,usage,electricity_kwh\ncell_1_2,2024,5,-3\ncell_1_2,2024,N/A,-\n다마71b61b,2024,7,1\n")
    items = {i["id"]: i for i in check_csv(bad)}
    assert items["csv_nulls"]["status"] == "WARN" and items["csv_nulls"]["count"] == 2
    assert items["csv_units"]["status"] == "WARN" and "usage" in items["csv_units"]["detail"]
    assert items["csv_negative"]["status"] == "FAIL"
    assert items["csv_keys"]["status"] == "FAIL" and items["csv_keys"]["count"] == 1
    assert items["csv_grid_id"]["status"] == "FAIL" and items["csv_grid_id"]["count"] == 1


def test_csv_check_rejects_cp949_and_reads_bom_copies(tmp_path):
    cp949 = _write(tmp_path, "cp.csv", "지역,값_kwh\n전주,1\n", "cp949")
    assert check_csv(cp949)[0]["status"] == "FAIL"
    bom = _write(tmp_path, "bom.csv", "﻿complex_code,year_month,electricity_kwh\nA1,202501,10\nA1,202502,\n")
    items = {i["id"]: i for i in check_csv(bom)}
    assert items["csv_encoding"]["status"] == "OK" and "BOM" in items["csv_encoding"]["detail"] and items["csv_keys"]["status"] == "OK"


def _region_db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.kma_asos import WeatherDailyObservation, WeatherMonthlyObservation
    from app.models import WeatherMonthly
    from app.regions import RegionWeatherMonthly
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for model in (WeatherDailyObservation, WeatherMonthlyObservation, WeatherMonthly, RegionWeatherMonthly):
        model.__table__.create(engine)
    return sessionmaker(engine)()


def _region_row(code, ym, provider, source_type, hdd, cdd):
    from app.regions import RegionWeatherMonthly
    return RegionWeatherMonthly(region_code=code, use_ym=ym, provider=provider, source_type=source_type, latitude=35.9, longitude=128.6,
                                hdd=hdd, cdd=cdd, days_observed=31, expected_days=31)


def _era5_file(raw: Path, code: str, temp_c: float) -> None:
    import json
    days = [f"2025-01-{d:02d}" for d in range(1, 32)] + [f"2025-02-{d:02d}" for d in range(1, 29)]
    daily = {"time": days, "temperature_2m_mean": [temp_c] * len(days), "temperature_2m_min": [temp_c - 3] * len(days),
             "temperature_2m_max": [temp_c + 3] * len(days), "precipitation_sum": [0.0] * len(days)}
    (raw / "weather-regions").mkdir(parents=True, exist_ok=True)
    (raw / "weather-regions" / f"{code}.json").write_text(json.dumps({"daily": daily}), encoding="utf-8")


def _asos_page(raw: Path, station: str, temp_c: float) -> None:
    import json
    items = [{"stnId": station, "stnNm": "대구", "tm": f"2025-01-{d:02d}", "avgTa": str(temp_c)} for d in range(1, 32)]
    body = {"response": {"header": {"resultCode": "00"}, "body": {"totalCount": 31, "items": {"item": items}}}}
    folder = raw / "kma" / "asos-regions" / station
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "2025-p1.json").write_text(json.dumps(body), encoding="utf-8")


def test_region_degree_days_recompute_keeps_asos_months_on_asos(tmp_path):
    """OFFICIAL months come from the station's daily pages, FALLBACK months from ERA5-Land — never ERA5 under an ASOS label."""
    from app.regions import RegionWeatherMonthly
    from app.standard import recompute_degree_days
    raw = tmp_path / "raw"
    _era5_file(raw, "27110", 0.0)       # ERA5-Land: 18 HDD a day
    _asos_page(raw, "143", 2.0)         # ASOS 143: 16 HDD a day (January only)
    db = _region_db()
    db.add_all([_region_row("27110", "202501", "KMA ASOS 143 대구", "OFFICIAL", 1.0, 1.0),
                _region_row("27110", "202502", "Open-Meteo / ERA5-Land", "FALLBACK", 1.0, 1.0)])
    db.commit()
    stats = recompute_degree_days(db, tmp_path, log=lambda _m: None, fetch=False)
    jan, feb = db.get(RegionWeatherMonthly, ("27110", "202501")), db.get(RegionWeatherMonthly, ("27110", "202502"))
    assert (jan.hdd, jan.cdd, jan.provider) == (16.0 * 31, 0.0, "KMA ASOS 143 대구")   # ASOS value, not ERA5 18 × 31
    assert (feb.hdd, feb.cdd) == (18.0 * 28, 0.0)                                      # ERA5-Land as before
    assert stats["region_asos_months"] == 1 and stats["region_months"] == 1 and stats["region_asos_kept"] == 0


def test_region_asos_month_without_daily_pages_is_left_as_stored_and_counted(tmp_path):
    from app.regions import RegionWeatherMonthly
    from app.standard import recompute_degree_days
    raw = tmp_path / "raw"
    _era5_file(raw, "44800", 0.0)       # ERA5-Land exists, but the ASOS 177 pages do not
    db = _region_db()
    db.add(_region_row("44800", "202501", "KMA ASOS 177 홍성", "OFFICIAL", 450.5, 0.0))
    db.commit()
    messages: list[str] = []
    stats = recompute_degree_days(db, tmp_path, log=messages.append, fetch=False)
    jan = db.get(RegionWeatherMonthly, ("44800", "202501"))
    assert (jan.hdd, jan.cdd) == (450.5, 0.0)                     # untouched: neither ERA5 nor NULL
    assert stats["region_asos_kept"] == 1 and stats["region_asos_months"] == 0 and stats["region_months"] == 0
    assert any("44800:177 1" in m for m in messages)
