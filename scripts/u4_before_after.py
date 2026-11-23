"""U4 before/after (2026-11-23): the same plan in every READY region, old service (running api) vs this checkout.

Plan: 50,000 m² added (floor area only) and, as a second row, 20 floors × 5 buildings × 500 m² (same floor area,
footprint 2,500 m²); target 40 %. Reads only (POST /api/areas/analyze does not save).
usage (api container, checkout backend at /app): python /scripts/u4_before_after.py <out.csv>
"""
from __future__ import annotations

import csv
import json
import sys
import urllib.request

sys.path.insert(0, "/app")
OUT = sys.argv[1]
OLD = "http://api:8000"
PLANS = {"floor_area": {"added_floor_area_m2": 50000}, "footprint": {"floors": 20, "building_count": 5, "footprint_per_building": 500}}


def post_old(body):
    req = urllib.request.Request(OLD + "/api/areas/analyze", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.load(r)


def main() -> None:
    from fastapi.testclient import TestClient

    from app.main import app
    c = TestClient(app)
    regions = [r for r in c.get("/api/system").json()["regions"] if r.get("status") == "READY" and r.get("default_grid_id")]
    rows = []
    for i, r in enumerate(regions, 1):
        for pname, plan in PLANS.items():
            body = {"region": r["code"], "area": {"type": "grid", "grid_id": r["default_grid_id"]}, "plan": plan, "target_pct": 40}
            try:
                old = (post_old(body).get("effort") or {})
                new = (c.post("/api/areas/analyze", json=body).json().get("effort") or {})
            except Exception as exc:  # noqa: BLE001 - one region must not stop the table
                rows.append({"region": r["code"], "plan": pname, "error": f"{type(exc).__name__}: {exc}"[:120]})
                continue
            o, n = old.get("recommended") or {}, new.get("recommended") or {}
            t = {x["key"]: x for x in new.get("targets") or []}
            b, a = t.get("plan_added") or {}, t.get("area_total") or {}
            rows.append({"region": r["code"], "plan": pname, "available": new.get("available"),
                         "old_required_kgco2eq": old.get("required_reduction_kgco2eq"), "new_required_kgco2eq": new.get("required_reduction_kgco2eq"),
                         "old_pv_kw": o.get("pv_kw"), "old_roof_over_plan": o.get("roof_over_plan"),
                         "new_pv_kw": n.get("pv_kw"), "new_pv_needed_kw": n.get("pv_needed_kw"), "new_roof_limit_kw": n.get("roof_limit_kw"),
                         "new_status_area": (a.get("recommended") or {}).get("onsite_status"),
                         "new_remaining_area_kgco2eq": (a.get("recommended") or {}).get("remaining_kgco2eq"),
                         "added_need_kgco2eq": b.get("required_reduction_kgco2eq"), "added_status": (b.get("recommended") or {}).get("onsite_status"),
                         "added_pv_kw": (b.get("recommended") or {}).get("pv_kw"), "added_covered_pct": (b.get("recommended") or {}).get("covered_pct"),
                         "added_remaining_kgco2eq": (b.get("recommended") or {}).get("remaining_kgco2eq"),
                         "existing_share_kgco2eq": a.get("existing_share_kgco2eq"), "measure_links": len(new.get("measure_links") or [])})
        print(f"{i}/{len(regions)} {r['code']}", flush=True)
        keys = sorted({k for row in rows for k in row}, key=lambda k: (k not in ("region", "plan"), k))
        with open(OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
    print("saved", OUT)


if __name__ == "__main__":
    main()
