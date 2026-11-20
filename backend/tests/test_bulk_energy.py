"""건축HUB 대용량 건물에너지 파일 (2026-11-21): reading, storing next to API rows, and the region step using it."""
import zipfile

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import bulk_energy
from app.models import EnergyMonthly


def line(ym, seq, sg, bd, bun, ji, qty, lot="0", road="", road_main="", road_sub="", under="0", dong="호평동"):
    sido, sigungu = ("경기도", "남양주시") if sg.startswith("41") else ("전북특별자치도", "전주시 덕진구")
    road_code = "413603197012" if road else ""
    return "|".join([ym, str(seq), sg, bd, sido, sigungu, dong, lot, bun, ji, road_code, road, under if road else "",
                     "지상" if road else "", road_main, road_sub, str(qty)])


def write_zip(folder, kind, ym, lines):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"MART_KEY_{kind}_ENERGY_DATA_{ym}.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"eais_{kind.lower()}_{ym}.txt", ("\n".join(lines) + "\n").encode("utf-8"))
    return path


def make_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    EnergyMonthly.__table__.create(engine)
    return sessionmaker(engine)()


def test_month_files_take_the_newest_folder_and_need_both_types(tmp_path):
    write_zip(tmp_path / "2026-11-01", "ELCTY", "202501", [line("202501", 1, "41360", "10100", "0001", "0000", 1)])
    newer = write_zip(tmp_path / "2026-11-21", "ELCTY", "202501", [line("202501", 1, "41360", "10100", "0001", "0000", 2)])
    write_zip(tmp_path / "2026-11-21", "GAS", "202501", [line("202501", 1, "41360", "10100", "0001", "0000", 3)])
    write_zip(tmp_path / "2026-11-21", "GAS", "202502", [line("202502", 1, "41360", "10100", "0001", "0000", 3)])
    files = bulk_energy.month_files(tmp_path)
    assert files["202501"]["ELECTRICITY"] == newer
    assert bulk_energy.complete_months(2025, tmp_path) == ["202501"]   # 202502 has gas only


def test_read_month_one_value_per_lot_addresses_like_the_api_and_conflicts(tmp_path):
    path = write_zip(tmp_path, "ELCTY", "202501", [
        # one 지번 with two road addresses: same value, the API keeps the road address of the lowest 순번
        line("202501", 2, "41360", "10100", "0005", "0030", 350, lot="1", road="천마산로14번길", road_main="30", road_sub="10"),
        line("202501", 1, "41360", "10100", "0005", "0030", 350, lot="1", road="천마산로", road_main="68", road_sub="13"),
        line("202501", 1, "41360", "10100", "0000", "0000", -50),                      # no number, negative use
        line("202501", 1, "41360", "10100", "0014", "0000", 9, road="성남대로", road_main="491", under="1"),
        line("202501", 2, "41360", "10100", "0020", "0001", 6),                         # same 지번, other value,
        line("202501", 1, "41360", "10100", "0020", "0001", 5),                         # lower 순번 listed later
        line("202501", 1, "41360", "10200", "0001", "0000", 7),                         # not wanted
    ])
    rows = bulk_energy.read_month(path, "ELECTRICITY", {("41360", "10100")})
    key = ("41360", "10100", "1", "0005", "0030", "202501", "ELECTRICITY")
    assert rows[key]["value"] == 350 and rows[key]["rows"] == 2 and not rows[key]["conflict"]
    assert rows[key]["record"]["platPlc"] == "경기도 남양주시 호평동 산5-30"
    assert rows[key]["record"]["newPlatPlc"] == "경기도 남양주시 천마산로 68-13 (호평동) "
    empty = rows[("41360", "10100", "0", "0000", "0000", "202501", "ELECTRICITY")]
    assert empty["value"] is None and empty["record"]["useQty"] == -50                   # NULL, raw kept
    assert empty["record"]["platPlc"] == "경기도 남양주시 호평동 "                       # the API keeps the space
    assert rows[("41360", "10100", "0", "0014", "0000", "202501", "ELECTRICITY")]["record"]["newPlatPlc"] == "경기도 남양주시 성남대로 지하491 (호평동) "
    two = rows[("41360", "10100", "0", "0020", "0001", "202501", "ELECTRICITY")]
    # the API answers the lowest 순번's value (2025-01 ~ 12: 120 of 120); the other value stays in the record
    assert two["conflict"] and two["value"] == 5 and two["record"]["useQty"] == 5 and two["record"]["bulk_other_useQty"] == [6]
    assert not any(k[1] == "10200" for k in rows)


def test_import_keeps_api_rows_replaces_kapt_rows_and_maps_old_jeonbuk_codes(tmp_path, monkeypatch):
    from app import energy_parcels
    monkeypatch.setattr(energy_parcels, "place_missing_parcels", lambda db, codes: {"placed": 0})
    db = make_db()
    hub, kapt = bulk_energy.HUB, "K-apt"
    db.add_all([
        EnergyMonthly(source=hub, sigungu_code="52113", bjdong_code="11600", lot_type="0", bun="0011", ji="0000", use_ym="202301",
                      energy_type="ELECTRICITY", usage_kwh=100.0, raw_record={"useQty": 100}),
        EnergyMonthly(source=hub, sigungu_code="52113", bjdong_code="11600", lot_type="0", bun="0012", ji="0000", use_ym="202301",
                      energy_type="ELECTRICITY", usage_kwh=1.0, raw_record={"useQty": 1}),
        EnergyMonthly(source=kapt, sigungu_code="52113", bjdong_code="11600", lot_type="0", bun="0013", ji="0000", use_ym="202301",
                      energy_type="ELECTRICITY", usage_kwh=999.0, raw_record={}),
    ])
    db.commit()
    # 전북 up to 2023-10: the provider's files carry the old 45xxx code, like the API answers
    write_zip(tmp_path / "2026-11-21", "ELCTY", "202301", [
        line("202301", 1, "45113", "11600", "0011", "0000", 100),
        line("202301", 1, "45113", "11600", "0012", "0000", 2),
        line("202301", 1, "45113", "11600", "0013", "0000", 30),
        line("202301", 1, "45113", "11600", "0014", "0000", 40),
        line("202301", 1, "45113", "11600", "0015", "0000", 5),
        line("202301", 2, "45113", "11600", "0015", "0000", 6),
    ])
    write_zip(tmp_path / "2026-11-21", "GAS", "202301", [line("202301", 1, "45113", "11600", "0014", "0000", 0)])
    stats = bulk_energy.import_months(db, [{"sigunguCd": "52113", "bjdongCd": "11600"}], ["202301"], root=tmp_path)
    assert (stats["same"], stats["different"], stats["replaced"], stats["inserted"], stats["conflicts"]) == (1, 1, 1, 3, 1)
    rows = {(r.bun, r.energy_type): r for r in db.scalars(select(EnergyMonthly))}
    assert rows[("0012", "ELECTRICITY")].usage_kwh == 1.0                                # API value kept
    replaced = rows[("0013", "ELECTRICITY")]
    assert replaced.source == hub and replaced.usage_kwh == 30
    assert replaced.raw_record["replaced_source"] == kapt and replaced.raw_record["replaced_usage_kwh"] == 999.0
    new = rows[("0014", "ELECTRICITY")]
    assert new.sigungu_code == "52113" and new.raw_record["bulk_file"] == "MART_KEY_ELCTY_ENERGY_DATA_202301.zip"
    assert rows[("0014", "GAS")].usage_kwh == 0                                         # the provider's 0 stays 0
    two = rows[("0015", "ELECTRICITY")]                                                  # two values: the lowest 순번's
    assert two.usage_kwh == 5 and two.raw_record["bulk_other_useQty"] == [6]


def test_region_step_reads_file_months_and_asks_the_api_only_for_the_rest(tmp_path, monkeypatch):
    from app import energy_parcels, region_prepare
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(region_prepare, "analysis_year", lambda: 2025)
    monkeypatch.setattr(region_prepare, "legal_leaves", lambda db, codes: [{"sigunguCd": "41360", "bjdongCd": "10100"}])
    monkeypatch.setattr(energy_parcels, "build_parcel_grid", lambda db, codes=None: 0)
    imported, asked = [], []
    monkeypatch.setattr(bulk_energy, "import_months", lambda db, leaves, months, progress=None: imported.append(list(months)) or
                        {"inserted": 10, "replaced": 0, "same": 0, "different": 0, "conflicts": 0})
    monkeypatch.setattr(energy_parcels, "prefetch_energy", lambda leaves, year, months=None: asked.append(("prefetch", list(months))))
    monkeypatch.setattr(energy_parcels, "collect_energy_all", lambda db, year, progress, regions, months=None:
                        asked.append(("collect", list(months))) or {"requests": 3, "inserted": 4, "updated": 0})

    class Region:
        legal_codes = ["4136010100"]

    folder = tmp_path / "raw" / "bldhub_bulk_energy" / "2026-11-21"
    for kind in ("ELCTY", "GAS"):
        write_zip(folder, kind, "202501", [line("202501", 1, "41360", "10100", "0001", "0000", 1)])
    result = region_prepare.step_building_energy(None, Region(), lambda m: None)
    rest = [f"2025{m:02d}" for m in range(2, 13)]
    assert imported == [["202501"]] and asked == [("prefetch", rest), ("collect", rest)]
    assert result["rows"] == 14 and result["file_months"] == 1 and result["year"] == 2025

    for month in range(2, 13):
        for kind in ("ELCTY", "GAS"):
            write_zip(folder, kind, f"2025{month:02d}", [line(f"2025{month:02d}", 1, "41360", "10100", "0001", "0000", 1)])
    imported.clear(); asked.clear()
    result = region_prepare.step_building_energy(None, Region(), lambda m: None)
    assert len(imported[0]) == 12 and asked == []                                       # a whole year from files: no API
    assert "API" not in result["message"]
