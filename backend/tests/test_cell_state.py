"""칸 · 해 상태 표(U2-c): 팀 규칙(배치 몫 · 사용승인 기준 달 · 0/빈 값 NULL · 열 이름)을 DB 없이 확인한다."""
import math

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Polygon, box

from app import cell_state as cs
from app.sgis_grid500 import code500_for


def test_team_pnu_follows_the_team_lot_rule():
    assert cs.team_pnu("41290", "10300", "0", "0641", "0000") == "4129010300106410000"
    assert cs.team_pnu("41290", "10300", "1", "0641", "0002") == "4129010300206410002"  # 산 = 2
    assert cs.team_pnu("41290", "10300", "2", "0641", "0000") is None  # block lot: no parcel number
    assert cs.team_pnu("41290", "10300", "0", "641", "0") is None  # short numbers are not padded


def test_register_date_blank_or_invalid_is_none():
    assert cs.register_date("20160815") == "2016-08-15"
    assert cs.register_date(" ") is None
    assert cs.register_date("19800100") is None  # day 00
    assert cs.register_date(None) is None


def test_cutoff_month_and_undated_buildings():
    assert cs.approval_cutoff(2016) == "2016-08"
    assert cs.approval_cutoff(2024) == "2024-12"
    dates = ["2016-08-31", "2016-09-01", None, float("nan"), "2015-01-01"]
    assert cs.built_by(dates, "2016-08").tolist() == [True, False, True, True, True]


def test_clean_floor_area_replaces_far_too_large_records():
    assert cs.clean_floor_area(1000.0, 200.0, 5, 0) == 1000.0
    assert cs.clean_floor_area(26_406_330.0, 1000.0, 20, 2) == 22_000.0  # > 2 x footprint x floors
    assert cs.clean_floor_area(None, 100.0, 2, None) == 0.0  # missing adds nothing to a sum
    assert cs.clean_floor_area(500.0, None, None, None) == 500.0  # no footprint: kept


def test_positive_makes_zero_and_blank_null():
    assert cs.positive(0) is None and cs.positive(" ") is None and cs.positive(-3) is None
    assert cs.positive("12.5") == 12.5


def test_small_parcel_goes_whole_to_its_centroid_cell():
    shares = cs.cell_shares(box(1090, 1090, 1120, 1120), 100, 5.0, 2500.0)  # 900 m² < 2,500
    assert shares == {(1100, 1100): 1.0}


def test_large_parcel_is_split_by_lattice_points():
    shares = cs.cell_shares(box(1050, 1000, 1150, 1100), 100, 5.0, 2500.0)  # 10,000 m², half in each cell
    assert set(shares) == {(1000, 1000), (1100, 1000)}
    assert shares[(1000, 1000)] == pytest.approx(0.5) and sum(shares.values()) == pytest.approx(1.0)


def test_parcel_placement_sums_to_one_per_500m_cell_and_names_the_main_cell():
    geom = box(1400, 1000, 1700, 1100)  # 30,000 m²: 100 m in 500m cell x=1000, 200 m in x=1500
    shares, main = cs.parcel_placement(geom)
    assert shares[(1000, 1000)] == pytest.approx(1 / 3, abs=1e-3)
    assert shares[(1500, 1000)] == pytest.approx(2 / 3, abs=1e-3)
    assert sum(shares.values()) == pytest.approx(1.0)
    assert main in shares


def test_complex_cells_counts_every_reached_500m_cell():
    assert cs.complex_cells(box(900, 900, 1100, 1000)) == [(500, 500), (1000, 500)]


def test_code500_matches_the_sgis_code():
    for x, y in [(955500, 1936500), (964000, 1757500), (1114500, 1666000)]:
        assert cs.code500(x, y) == code500_for(x, y)
    assert cs.code500(955500, 1936500) == "다사55b36b"


def test_zone_counts_smallest_rule_output_and_ties():
    names = ["제2종일반주거지역"] * 10 + ["자연녹지지역"] * 10 + ["도시지역기타"] * 3 + [None] * 2
    out = cs.zone_counts(names)
    assert out["zone_residential_cells"] == 10 and out["zone_green_cells"] == 10
    assert out["zone_other_cells"] == 3 and out["zone_none_cells"] == 2
    assert out["zone_main_class"] == "green"  # tie: first in the team order (green before residential)
    assert cs.zone_counts([None] * 25)["zone_main_class"] == "none"


def _month(m, **kw):
    days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m]
    row = dict(provider="KMA ASOS 146 전주", source_type="OFFICIAL", mean_temperature=10.0 + m, hdd=100.0, cdd=5.0,
               days_observed=days, expected_days=days)
    row.update(kw)
    return row


def test_annual_weather_needs_twelve_official_full_months():
    months = [_month(m) for m in range(12)]
    values, station, quality = cs.annual_weather(months)
    days = np.array([m["expected_days"] for m in months])
    assert station == "146" and quality == "OBSERVED_ASOS_12M"
    assert values["temp_avg_c"] == round(float(np.dot(np.arange(12) + 10.0, days) / days.sum()), 2)
    assert values["heating_degree_days_c"] == 1200.0 and values["cooling_degree_days_c"] == 60.0
    fallback = months[:11] + [_month(11, source_type="FALLBACK", provider="Open-Meteo / ERA5-Land")]
    assert cs.annual_weather(fallback)[0] == {c: None for c in cs.WEATHER_COLUMNS}
    short = months[:11] + [_month(11, days_observed=30)]
    assert cs.annual_weather(short)[2] == "NULL_INCOMPLETE_MONTH"
    assert cs.annual_weather(months[:11])[2] == "NULL_MONTHS_MISSING"


def _title(pk, ji, **kw):
    row = {"id": pk, "sigunguCd": "41290", "bjdongCd": "10300", "platGbCd": "0", "bun": "0001", "ji": ji, "totArea": "1000",
           "archArea": "200", "grndFlrCnt": "5", "ugrndFlrCnt": "0", "heit": "15", "useAprDay": "20150101", "hhldCnt": "10",
           "fmlyCnt": "0", "mainAtchGbCdNm": "주건축물", "mainPurpsCdNm": "공동주택"}
    row.update(kw)
    return row


def test_building_table_keeps_null_for_form_values_and_splits_housing_by_title():
    t = cs.building_table([_title("a", "0000"), _title("b", "0000", archArea="0", heit=" ", mainPurpsCdNm="제2종근린생활시설",
                                                          mainAtchGbCdNm="부속건축물", useAprDay=" ")])
    a, b = t.iloc[0], t.iloc[1]
    assert a.reg_residential_floor_area_m2 == 1000 and a.reg_nonresidential_floor_area_m2 == 0
    assert b.reg_residential_floor_area_m2 == 0 and b.reg_nonresidential_floor_area_m2 == 1000
    assert math.isnan(b.area) and math.isnan(b.height) and b.floors == 5
    assert b.reg_building_count == 0 and a.reg_building_count == 1
    assert pd.isna(b.approval_date) and pd.isna(b.approval_year)


def test_register_sums_use_the_share_and_the_year_cutoff():
    t = cs.building_table([_title("a", "0000", useAprDay="20160901"), _title("b", "0000", useAprDay="20150101")])
    shares = pd.DataFrame({"pnu": [t.pnu[0]] * 2, "x": [0, 500], "y": [0, 0], "share": [0.25, 0.75]})
    s = cs.register_sums(t, shares, [2016, 2017]).set_index(["x", "y", "year"])
    assert s.loc[(0, 0, 2016), "reg_floor_area_m2"] == pytest.approx(250.0)  # only b by 2016-08
    assert s.loc[(500, 0, 2017), "reg_floor_area_m2"] == pytest.approx(1500.0)
    assert s.loc[(500, 0, 2017), "reg_building_count"] == pytest.approx(1.5)


def test_regform_means_skip_null_values_and_count_undated_buildings():
    t = cs.building_table([_title("a", "0000", archArea="100", useAprDay="20000101"),
                           _title("b", "0000", archArea="0", useAprDay=" "),
                           _title("c", "0000", archArea="300", useAprDay="20300101")])
    main = pd.DataFrame({"pnu": [t.pnu[0]], "x": [0], "y": [0]})
    r = cs.regform_means(t, main, [2024]).iloc[0]
    assert r.regform_buildings == 2  # c is not approved yet
    assert r.regform_area_mean_m2 == 100.0  # b's 0 is NULL, not 0
    assert r.regform_age_mean_years == 24.0  # b has no date: no age


def test_complex_lots_need_200_households_and_a_date():
    t = cs.building_table([_title(f"a{i}", "0000", hhldCnt="100", useAprDay=d) for i, d in enumerate(["20100301", "20090101"])]
                          + [_title("b", "0001", hhldCnt="150"), _title("c", "0002", hhldCnt="250", useAprDay=" ")])
    lots = cs.complex_lots(t, {"4129010300100010002": "2012-05-01"}).set_index("pnu")
    assert list(lots.index) == ["4129010300100010000", "4129010300100010002"]
    assert lots.loc["4129010300100010000", "approval_year"] == 2009
    assert lots.loc["4129010300100010002", "approval_source"] == "kapt"
    counts = cs.complex_counts(lots.reset_index(), {"4129010300100010000": [(0, 0), (500, 0)]}, [2008, 2009])
    assert counts[counts.year == 2009]["complex_count"].tolist() == [1, 1] and counts[counts.year == 2008].empty


def test_assemble_columns_and_null_rules():
    cells = pd.DataFrame({"grid_id": ["cell_955500_1936500"], "x": [955500], "y": [1936500], "state_partial": [False]})
    zones = pd.DataFrame([{"grid_id": "cell_955500_1936500", **cs.zone_counts(["준주거지역"] * 25)}])
    sgis = pd.DataFrame({"grid_id_500m": ["다사55b36b"], "year": [2024], "sgis_households": [10.0],
                         "sgis_housing_units": [8.0], "sgis_population": [25.0]})
    weather = {2023: ({c: None for c in cs.WEATHER_COLUMNS}, None, "NULL_FALLBACK_MONTH"),
               2024: ({"temp_avg_c": 14.0, "heating_degree_days_c": 2000.0, "cooling_degree_days_c": 100.0}, "146", "OBSERVED_ASOS_12M")}
    out = cs.assemble("41290", cells, [2023, 2024], zones, sgis, weather, None, None, None)
    assert list(out.columns) == cs.COLUMNS
    assert len(cs.STATE_COLUMNS) == 26
    r23, r24 = out.iloc[0], out.iloc[1]
    assert r24.grid_id_500m == "다사55b36b" and r24.x_min_m == 955500 and r24.zone_main_class == "residential"
    assert r24.sgis_households == 10 and pd.isna(r23.sgis_households)  # no SGIS row: NULL, never 0
    assert r23.sgis_quality == "NO_YEAR" and r24.sgis_quality == "OBSERVED"
    assert pd.isna(r23.temp_avg_c) and r24.weather_station_id == "146"
    assert out["reg_floor_area_m2"].isna().all() and (out["reg_quality"] == "NULL_NO_REGISTER").all()  # register not loaded
    assert out["regform_area_mean_m2"].isna().all()


def test_assemble_register_zero_when_queried_without_buildings():
    cells = pd.DataFrame({"grid_id": ["cell_0_0", "cell_500_0"], "x": [0, 500], "y": [0, 0], "state_partial": [False, True]})
    reg = pd.DataFrame({"x": [0], "y": [0], **{c: [1.0] for c in cs.REG_COLUMNS}, "year": [2024]})
    cx = pd.DataFrame(columns=["x", "y", "complex_count", "year"])
    rf = pd.DataFrame(columns=["x", "y", *cs.REGFORM_COLUMNS, "regform_buildings", "year"])
    out = cs.assemble("x", cells, [2024], pd.DataFrame(columns=["grid_id", *cs.ZONE_COLUMNS]),
                      pd.DataFrame(columns=["grid_id_500m", "year", *cs.SGIS_COLUMNS]), {}, reg, cx, rf).set_index("grid_id")
    assert out.loc["cell_500_0", "reg_floor_area_m2"] == 0.0 and out.loc["cell_500_0", "complex_count"] == 0
    assert pd.isna(out.loc["cell_500_0", "regform_area_mean_m2"]) and bool(out.loc["cell_500_0", "state_partial"])
    assert out.loc["cell_0_0", "zone_quality"] == "NULL_NO_ZONING"


def test_parse_years():
    assert cs.parse_years("2016-2018,2024") == [2016, 2017, 2018, 2024]
    with pytest.raises(ValueError):
        cs.parse_years(" ")


def test_lattice_points_are_centred_on_the_step():
    xs, ys = cs.lattice_points(Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]), 5.0)
    assert sorted(zip(xs.tolist(), ys.tolist())) == [(2.5, 2.5), (2.5, 7.5), (7.5, 2.5), (7.5, 7.5)]


@pytest.mark.db
def test_build_cell_state_gwacheon_reads_the_db():
    from app.db import Session
    with Session() as db:
        table, summary = cs.build_cell_state(db, "41290", [2024])
    assert list(table.columns) == cs.COLUMNS and len(table) == summary["cells"]
    assert table["grid_id_500m"].notna().all() and summary["titles"] > 0
