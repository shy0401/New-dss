"""Region weather: run only the ASOS overlay of the weather step (region_prepare._asos_overlay) for chosen regions, or
snapshot their region_weather_monthly rows. Used on 2026-11-24 for 대구 · 홍성 (docs/records/2026-11-24-region-asos-daegu-hongseong.md)
and for the 12-region degree-day restore (docs/records/2026-11-24-restore-asos-degree-days.md). ERA5-Land rows and
irradiation are not fetched again; the running api and worker containers are not touched.
Runs inside the api image with this repo's backend mounted at /src:
  docker compose -p carbon-urban-dss -f compose.yaml -f compose.demo.yaml run --rm --no-deps -T \\
    -v "<repo>/backend:/src" -v "<repo>/scripts/region_weather:/tools:ro" -w /src api python /tools/asos_overlay.py <mode> ...
  snap <out.csv>   : region_weather_monthly rows of 대구 (27xxx) and 홍성 (44800) — edit the filter for other regions
  apply <codes...> : the ASOS overlay for those regions (writes the DB; take a snapshot first)"""
import csv
import sys

sys.path.insert(0, "/src")
sys.stdout.reconfigure(encoding="utf-8")
from sqlalchemy import or_, select  # noqa: E402

from app.db import Session  # noqa: E402
from app.regions import RegionWeatherMonthly, StudyRegion  # noqa: E402

db = Session()
mode = sys.argv[1]
if mode == "snap":
    q = select(RegionWeatherMonthly).where(or_(RegionWeatherMonthly.region_code.like("27%"), RegionWeatherMonthly.region_code == "44800")) \
        .order_by(RegionWeatherMonthly.region_code, RegionWeatherMonthly.use_ym)
    cols = ["region_code", "use_ym", "provider", "source_type", "mean_temperature", "min_temperature", "max_temperature", "precipitation",
            "hdd", "cdd", "days_observed", "expected_days"]
    n = 0
    with open(sys.argv[2], "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(cols)
        for r in db.scalars(q):
            w.writerow([getattr(r, c) for c in cols]); n += 1
    print("rows", n)
elif mode == "apply":
    from app.region_prepare import _asos_overlay, analysis_year
    last = analysis_year()
    for code in sys.argv[2:]:
        region = db.get(StudyRegion, code)
        if region is None:
            print(code, "no region"); continue
        out = _asos_overlay(db, region, last, lambda m: print("  log:", m))
        print(code, region.name, out)
