"""KMA AWS (방재기상관측) annual weather for the team change model (2026-11-17).

Source: 기상청 API허브 방재기상월보 조회 (AwsMtlyInfoService): getAwsStnLstTbl (station list) and getDailyAwsData
(daily values of one station and month, as published in the monthly report). Key: KMA_APIHUB_KEY in <dss>/.env.
Raw responses are kept under <dss>/data/raw/kma/aws_apihub/ (never edited); repeated runs read them instead of calling.
Weather rules = team rules.yaml / dataset/weather.py: a month with any day without daily mean temperature has no value,
a year needs 12 such months; HDD/CDD base 18 / 24 °C summed per month (rounded 0.1), monthly mean rounded 0.01,
annual mean weighted by days. Monthly-report marks: a value ending in ")" is a published daily mean computed with
some hourly observations missing (kept, counted in flagged_days); "x" is no value (the day is missing).
usage:
  python aws_annual_for_team.py <dss root> stations <YYYYMM,...> <out.csv>
  python aws_annual_for_team.py <dss root> daily <stn,...> <first year> <last year> <out.csv>
"""
import calendar
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(sys.argv[1])
MODE = sys.argv[2]
ENV = dict(l.split("=", 1) for l in (ROOT / ".env").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#"))
KEY = ENV["KMA_APIHUB_KEY"].strip()
BASE = "https://apihub.kma.go.kr/api/typ02/openApi/AwsMtlyInfoService/"
RAW = ROOT / "data" / "raw" / "kma" / "aws_apihub"
HEAT, COOL = 18.0, 24.0
sys.stdout.reconfigure(encoding="utf-8")


def fetch(op: str, path: Path, **params) -> dict:
    if not path.is_file():
        query = urllib.parse.urlencode({"pageNo": 1, "numOfRows": 999, "dataType": "JSON", **params, "authKey": KEY})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(BASE + op + "?" + query, timeout=60) as r:
                    body = r.read()
                break
            except OSError:
                if attempt == 2:
                    raise
                time.sleep(3)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        time.sleep(0.1)
    body = path.read_bytes()
    for enc in ("utf-8", "cp949"):
        try:
            return json.loads(body.decode(enc))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise ValueError(f"cannot read {path}")


def items(doc: dict) -> list:
    body = doc.get("response", {}).get("body", {})
    item = (body.get("items") or {}).get("item") or []
    return item if isinstance(item, list) else [item]


def num(v):
    """(value, flagged): '12.8)' -> (12.8, True); 'x' / 'null' -> (None, False)."""
    text = str(v).strip()
    flagged = text.endswith(")")
    try:
        return float(text.rstrip(")").strip()), flagged
    except (TypeError, ValueError):
        return None, False


if MODE == "stations":
    rows = {}
    for ym in sys.argv[3].split(","):
        doc = fetch("getAwsStnLstTbl", RAW / "stations" / f"{ym}.json", year=ym[:4], month=ym[4:], station=0)
        for it in items(doc):
            for s in (it.get("stn_aws") or {}).get("info", []):
                r = rows.setdefault(s["stn_id"], {"stn_id": s["stn_id"], "name": s["stn_ko"].strip(), "addr": s["addr"].strip(),
                                                  "lat": s["lat"], "lon": s["lon"], "ht": str(s["ht"]).strip(), "lists": []})
                r["lists"].append(ym)
    with open(sys.argv[4], "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stn_id", "name", "addr", "lat", "lon", "ht_m", "in_lists"])
        for r in sorted(rows.values(), key=lambda r: r["stn_id"]):
            w.writerow([r["stn_id"], r["name"], r["addr"], r["lat"], r["lon"], r["ht"], " ".join(r["lists"])])
    print("stations", len(rows))
elif MODE == "daily":
    stations = sys.argv[3].split(",")
    first, last = int(sys.argv[4]), int(sys.argv[5])
    out = []
    for stn in stations:
        for year in range(first, last + 1):
            months, heat, cool, weighted, days_total, flagged_days = 0, 0.0, 0.0, 0.0, 0, 0
            for m in range(1, 13):
                doc = fetch("getDailyAwsData", RAW / "daily" / stn / f"{year}{m:02d}.json", year=year, month=f"{m:02d}", station=stn)
                n = calendar.monthrange(year, m)[1]
                vals, flags = {}, 0
                for it in items(doc):
                    for d in (it.get("awsmdays") or {}).get("info", []):
                        t, flagged = num(d.get("ta_day"))
                        if t is not None and str(d.get("tm", "")).strip().isdigit() and int(d["tm"]) <= n:
                            vals[int(d["tm"])] = t
                            flags += flagged
                if len(vals) != n or any(day not in vals for day in range(1, n + 1)):
                    continue
                v = [vals[d] for d in range(1, n + 1)]
                months += 1
                flagged_days += flags
                heat += round(sum(max(HEAT - x, 0.0) for x in v), 1)
                cool += round(sum(max(x - COOL, 0.0) for x in v), 1)
                weighted += round(sum(v) / n, 2) * n
                days_total += n
            row = [stn, year, months, flagged_days]
            row += [round(weighted / days_total, 2), round(heat, 1), round(cool, 1)] if months == 12 else ["", "", ""]
            out.append(row)
            print(stn, year, "complete months", months, flush=True)
    with open(sys.argv[6], "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["station", "year", "complete_months", "flagged_days", "temp_avg_c", "heating_degree_days_c", "cooling_degree_days_c"])
        w.writerows(out)
