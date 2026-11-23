"""Summary of measure_first_requests.py output: median / 90th percentile / max seconds per request (user readiness U1).
usage: python -I scripts/summarize_timings.py <timings.csv> [--exclude 52110,...]
"""
import csv
import statistics
import sys

rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
skip = set(sys.argv[sys.argv.index("--exclude") + 1].split(",")) if "--exclude" in sys.argv else set()
by: dict[str, list[float]] = {}
bad: list[str] = []
for r in rows:
    if r["region"] in skip or r["pass"] != "cold":
        continue
    by.setdefault(r["request"], []).append(float(r["seconds"]))
    if r["status"] != "200":
        bad.append(f"{r['region']} {r['request']} {r['status']}")
print(f"regions {len({r['region'] for r in rows} - skip)} (excluded {sorted(skip) or '-'})")
print(f"{'request':14s} {'n':>3s} {'median':>7s} {'p90':>7s} {'max':>7s}")
for name, v in by.items():
    v.sort()
    p90 = v[min(len(v) - 1, int(round(0.9 * (len(v) - 1))))]
    print(f"{name:14s} {len(v):3d} {statistics.median(v):7.1f} {p90:7.1f} {max(v):7.1f}")
first = {}
for r in rows:
    if r["region"] in skip or r["pass"] != "cold" or r["request"] not in ("system", "dashboard"):
        continue
    first[r["region"]] = first.get(r["region"], 0.0) + float(r["seconds"])
v = sorted(first.values())
print(f"first screen (system + dashboard): median {statistics.median(v):.1f} s, max {max(v):.1f} s")
print("non-200:", bad or "none")
