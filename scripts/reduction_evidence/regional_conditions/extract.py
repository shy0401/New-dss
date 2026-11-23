"""Read-only extracts for the end-use decomposition (regional-conditions-2026-11-20.md 3절).

Writes extract/*.csv (pipe-separated, from psql -At):
  weather.csv        region_code|use_ym|hdd|cdd|source_type      (전주 = 52110 from weather_monthly)
  kapt_elec.csv      complex_code|year_month|electricity_quantity (SUCCESS, electricity not null)
  complexes.csv      kapt_code|bjd_code|heating_type|approval_date|households|gross_floor_area_m2
  gas_parcel.csv     sigungu|bjdong|lot_type|bun|ji|use_ym|usage_kwh   (GAS, 2021-01~2025-12, linked gas parcels)
The link table is read from ../reduction_evidence/link (never written).
Run: python extract.py
"""
from __future__ import annotations

import csv
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _paths import REPO, data  # noqa: E402  (2026-11-24: data and results live outside Git)
OUT = data("regional_conditions")          # DB exports (extract/), results
GUIDE = data("regional_guide")            # design_zone_sigungu.csv, greentogether_apt_2025.csv (regional_guide/)
OUT = OUT / "extract"
LINK = data("link")
PSQL = ["docker", "exec", "-i", "-e", "PGOPTIONS=-cdefault_transaction_read_only=on", "carbon-urban-dss-postgres-1",
        "psql", "-U", "carbon", "-d", "carbon", "-At", "-F", "|", "-v", "ON_ERROR_STOP=1"]


def run(sql: str, name: str) -> int:
    res = subprocess.run(PSQL, input=sql.encode("utf-8"), capture_output=True)
    if res.returncode != 0:
        raise SystemExit(res.stderr.decode("utf-8", "replace"))
    (OUT / name).write_bytes(res.stdout)
    return res.stdout.count(b"\n")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    n = {}
    n["weather"] = run(
        "select region_code, use_ym, hdd, cdd, source_type from region_weather_monthly "
        "union all select '52110', use_ym, hdd, cdd, source_type from weather_monthly order by 1,2;", "weather.csv")
    n["kapt_elec"] = run(
        "select complex_code, year_month, electricity_quantity from apartment_energy_monthly "
        "where quality_status='SUCCESS' and electricity_quantity is not null order by 1,2;", "kapt_elec.csv")
    n["complexes"] = run(
        "select distinct on (kapt_code) kapt_code, bjd_code, heating_type, approval_date, households, gross_floor_area_m2 "
        "from apartment_complexes order by kapt_code, snapshot_month desc;", "complexes.csv")
    keys = set()
    with (LINK / "complex_parcel_link.csv").open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["linked"] == "1" and int(r["gas_months"] or 0) > 0:
                keys.add((r["sigungu_code"], r["bjdong_code"], r["lot_type"], r["bun"], r["ji"]))
    values = ",".join("('%s','%s','%s','%s','%s')" % k for k in sorted(keys))
    n["gas_parcel"] = run(
        f"with k(sgg,bjd,lt,bun,ji) as (values {values}) "
        "select e.sigungu_code, e.bjdong_code, e.lot_type, e.bun, e.ji, e.use_ym, e.usage_kwh "
        "from energy_monthly e join k on k.sgg=e.sigungu_code and k.bjd=e.bjdong_code and k.lt=e.lot_type "
        "and k.bun=e.bun and k.ji=e.ji "
        "where e.energy_type='GAS' and e.use_ym between '202101' and '202512' order by 1,2,3,4,5,6;", "gas_parcel.csv")
    print({"gas_parcel_keys": len(keys), **n})


if __name__ == "__main__":
    main()
