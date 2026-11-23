"""Pick one own-city station per region for the team change model's weather (deploy/team-model/station_annual.csv).

Rule (2026-11-17, records: official inputs): among the region's own-city stations (region_stations.csv), the one with the
most complete years in the team years (2014 · 2016 · 2018 · 2019 · 2021 · 2022 · 2024) is used for every year; a tie
goes to ASOS. Only complete years (12 months, no missing day) are written; years that station does not complete stay
out (NULL in the service), and a region with no complete team year gets no row (no substitute from another city).
Inputs: AWS candidates (aws_annual_for_team.py daily → <data>/aws_annual_candidates.csv) and ASOS years
(asos_annual_for_team.py → <data>/asos_team.csv).
usage: python select_station_annual.py <aws candidates csv> <asos csv> <out csv>
"""
import csv
import sys
from pathlib import Path

HERE = Path(__file__).parent
TEAM_YEARS = {2014, 2016, 2018, 2019, 2021, 2022, 2024}
COLUMNS = ["region_code", "station", "source", "year", "months", "temp_avg_c", "heating_degree_days_c", "cooling_degree_days_c"]


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


aws = {}
for r in read(sys.argv[1]):
    if r["complete_months"] == "12" and r["temp_avg_c"]:
        aws[(r["station"], int(r["year"]))] = (r["temp_avg_c"], r["heating_degree_days_c"], r["cooling_degree_days_c"])
asos = {}
for r in read(sys.argv[2]):
    if r["months"] == "12" and r["temp_avg_c"]:
        asos[(r["station"], int(r["year"]))] = (r["temp_avg_c"], r["heating_degree_days_c"], r["cooling_degree_days_c"])
out = []
for reg in read(HERE / "region_stations.csv"):
    cands = []
    for item in reg["stations"].split(";"):
        source, station = item.split(":")
        values = asos if source == "ASOS" else aws
        years = {y: v for (s, y), v in values.items() if s == station}
        cands.append((sum(y in TEAM_YEARS for y in years), source == "ASOS", source, station, years))
    cands.sort(key=lambda c: (-c[0], not c[1]))
    if not cands or cands[0][0] == 0:
        continue
    _, _, source, station, years = cands[0]
    for y in sorted(years):
        out.append([reg["region_code"], station, source, y, 12, *years[y]])
with open(sys.argv[3], "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(COLUMNS)
    w.writerows(out)
print(len(out), "rows,", len({r[0] for r in out}), "regions")
