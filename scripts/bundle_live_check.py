"""One live call of POST /api/plans/evaluate with every block (U3 S1 check, 2026-11-23). Reads only.
usage (api container, checkout backend at /app): python /scripts/bundle_live_check.py <region> <grid_id>
"""
import json
import sys
import time

sys.path.insert(0, "/app")
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

region, grid = sys.argv[1], sys.argv[2]
body = {"region": region, "area": {"type": "grid", "grid_id": grid}, "target_pct": 40,
        "uses_new": [{"use": "residential", "floor_area_m2": 50000, "dwellings": 500}],
        "plan": {"floors": 20, "building_count": 5, "footprint_per_building": 500},
        "site": {"grid_id": grid, "site_area_m2": 20000},
        "include": ["baseline", "plan_emission", "change_model", "reduction", "district_heat", "ordinance"]}
t = time.perf_counter()
r = TestClient(app).post("/api/plans/evaluate", json=body)
print("status", r.status_code, f"{time.perf_counter() - t:.1f}s")
d = r.json()
if r.status_code != 200:
    print(json.dumps(d, ensure_ascii=False)[:500])
    sys.exit(1)
for name, b in d["blocks"].items():
    keep = {k: b.get(k) for k in ("status", "data_class", "reason", "net_added_kgco2eq", "baseline_kgco2eq", "change_tco2e", "reading",
                                   "band_q10_tco2e", "band_q90_tco2e", "heat_kwh", "heat_kgco2eq", "far_limit_pct", "plan_far_pct", "plan_bcr_pct") if b.get(k) is not None}
    print(f"{name:14s}", json.dumps(keep, ensure_ascii=False)[:300])
print("timing", d["timing_s"], "| footprint", d["plan"]["footprint_sum_m2"], d["plan"]["footprint_basis"])
red = d["blocks"]["reduction"]
for t in red.get("targets") or []:
    rec = t["recommended"]
    print(" target", t["key"], "need", t["required_reduction_kgco2eq"], "| pv", rec["pv_kw"], "status", rec["onsite_status"], "remaining", rec["remaining_kgco2eq"])
