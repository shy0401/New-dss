"""Annual ASOS weather for the team change model (2026-11-17): regions whose own city has an ASOS station.

Runs inside the api container (uses its data.go.kr key and HTTP cache). Daily ASOS → month (a month with any missing
daily mean gets no value, team rules.yaml max_missing_days 0) → year only when all 12 months have values; annual mean
weighted by days (team dataset/weather.py annual_weather), HDD/CDD base 18 / 24 °C summed. Raw responses are kept
under /data/raw/kma/asos_team/<station>/.
usage (in the api container): python asos_annual_for_team.py <region=station,...> <first year> <last year> <out.csv>
e.g. 41480=99,36110=239 2014 2025 /data/ops/asos_team.csv
"""
import calendar
import csv
import os
import sys
from pathlib import Path

from app.cache import CachedClient
from app.kma_asos import KMA_ASOS_BASE_URL, parse_asos_response

HEAT, COOL = 18.0, 24.0
pairs = [p.split("=") for p in sys.argv[1].split(",")]
first, last, out = int(sys.argv[2]), int(sys.argv[3]), Path(sys.argv[4])
key = os.environ["DATA_GO_KR_SERVICE_KEY"].strip()
root = Path(os.getenv("DATA_DIR", "/data"))
session = CachedClient(root / "cache" / "kma-asos-team")
rows_out = []
for region, station in pairs:
    raw_dir = root / "raw" / "kma" / "asos_team" / station
    raw_dir.mkdir(parents=True, exist_ok=True)
    for year in range(first, last + 1):
        params = {"serviceKey": key, "pageNo": 1, "numOfRows": 999, "dataType": "JSON", "dataCd": "ASOS", "dateCd": "DAY",
                  "startDt": f"{year}0101", "endDt": f"{year}1231", "stnIds": station}
        result = session.get("KMA", f"ASOS-team-{station}-{year}", f"{KMA_ASOS_BASE_URL}/getWthrDataList", params)
        (raw_dir / f"{year}.json").write_bytes(result["body"])
        try:
            parsed = parse_asos_response(result["body"])
        except Exception as exc:  # noqa: BLE001 - a year before the station opened answers with an error code
            print(region, station, year, "no data:", type(exc).__name__)
            continue
        daily = {r["observed_date"]: r["avg_temperature_c"] for r in parsed["rows"] if r["avg_temperature_c"] is not None}
        months, heat, cool, weighted, days_total = 0, 0.0, 0.0, 0.0, 0
        for m in range(1, 13):
            n = calendar.monthrange(year, m)[1]
            vals = [daily.get(f"{year}-{m:02d}-{d:02d}") for d in range(1, n + 1)]
            if any(v is None for v in vals):
                continue
            months += 1
            heat += round(sum(max(HEAT - v, 0.0) for v in vals), 1)
            cool += round(sum(max(v - COOL, 0.0) for v in vals), 1)
            weighted += round(sum(vals) / n, 2) * n
            days_total += n
        print(region, station, year, "days", len(daily), "complete months", months)
        if months == 12:
            rows_out.append([region, station, year, months, round(weighted / days_total, 2), round(heat, 1), round(cool, 1)])
with out.open("w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["region_code", "station", "year", "months", "temp_avg_c", "heating_degree_days_c", "cooling_degree_days_c"])
    w.writerows(rows_out)
print("wrote", len(rows_out), "years to", out)
