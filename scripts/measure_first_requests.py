"""First-visit response times of the screen's opening requests, per READY region (user readiness U1, 2026-11-23).

Reads only (GET, plus POST /api/areas/analyze which does not save). Run right after the api container starts so the
in-memory caches are cold, like a user's first visit; pass --warm to measure a second pass in the same run.
usage: python -I scripts/measure_first_requests.py <out.csv> [--base http://localhost:8000] [--limit N] [--warm]
"""
from __future__ import annotations

import csv
import json
import sys
import time
import urllib.error
import urllib.request

ARGS = sys.argv[1:]
OUT = ARGS[0]
BASE = ARGS[ARGS.index("--base") + 1] if "--base" in ARGS else "http://localhost:8000"
LIMIT = int(ARGS[ARGS.index("--limit") + 1]) if "--limit" in ARGS else None
WARM = "--warm" in ARGS
YEAR = 2025


def call(path: str, body: dict | None = None, timeout: float = 300.0) -> tuple[int, float, int]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"} if data else {},
                                 method="POST" if data is not None else "GET")
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            n = len(r.read())
            return r.status, time.perf_counter() - t, n
    except urllib.error.HTTPError as e:
        return e.code, time.perf_counter() - t, len(e.read() or b"")
    except Exception:  # noqa: BLE001 - timeouts and refused connections are results too
        return 0, time.perf_counter() - t, 0


def ready_regions() -> list[dict]:
    with urllib.request.urlopen(BASE + "/api/system", timeout=60) as r:
        regions = json.load(r).get("regions") or []
    return [r for r in regions if r.get("status") == "READY"]


def requests_for(region: dict) -> list[tuple[str, str, dict | None]]:
    code, grid = region["code"], region.get("default_grid_id")
    out = [("system", f"/api/system?region={code}", None),
           ("dashboard", f"/api/dashboard?year={YEAR}&region={code}" + (f"&grid_id={grid}" if grid else ""), None),
           ("map", f"/api/map?year={YEAR}&region={code}", None),
           ("overlays", f"/api/map/overlays?region={code}", None),
           ("area_options", f"/api/areas/options?region={code}", None),
           ("model", f"/api/model?year={YEAR}&region={code}", None)]
    if grid:
        out.append(("area_analyze", "/api/areas/analyze", {"region": code, "area": {"type": "grid", "grid_id": grid}}))
    return out


def main() -> None:
    regions = ready_regions()[:LIMIT] if LIMIT else ready_regions()
    rows = []
    passes = ("cold", "warm") if WARM else ("cold",)
    for i, region in enumerate(regions, 1):
        for p in passes:
            for name, path, body in requests_for(region):
                status, sec, size = call(path, body)
                rows.append({"region": region["code"], "pass": p, "request": name, "status": status, "seconds": round(sec, 2), "bytes": size})
        last = [r for r in rows if r["region"] == region["code"] and r["pass"] == "cold"]
        print(f"{i}/{len(regions)} {region['code']} " + " ".join(f"{r['request']} {r['seconds']}" for r in last), flush=True)
        with open(OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    print("saved", OUT)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
