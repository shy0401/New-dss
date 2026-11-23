"""U3 S2 live check (2026-11-23): the area report's change model section equals the bundle's change model block for the
same plan. Builds the report snapshot without saving it (no POST /api/area-reports) and calls /api/plans/evaluate. Reads only.
usage (api container, checkout backend at /app): python /scripts/report_change_live_check.py <region> <grid_id | admin:<code>>
"""
import json
import sys
import time

sys.path.insert(0, "/app")
from fastapi.testclient import TestClient  # noqa: E402

from app.area_report import AreaReportInput, _snapshot, area_html, area_markdown, key_results  # noqa: E402
from app.main import app  # noqa: E402

region, spec = sys.argv[1], sys.argv[2]
area = {"type": "admin", "code": spec.split(":", 1)[1]} if spec.startswith("admin:") else {"type": "grid", "grid_id": spec}
body = {"region": region, "area": area, "from_year": 2015, "to_year": 2025, "target_pct": 40,
        "uses_new": [{"use": "residential", "floor_area_m2": 50000, "dwellings": 500}]}


class NoGateway:
    headers: dict = {}


t = time.perf_counter()
r = TestClient(app).post("/api/plans/evaluate", json=dict(body, include=["plan_emission", "change_model"]))
print("bundle", r.status_code, f"{time.perf_counter() - t:.1f}s")
bundle = r.json()["blocks"] if r.status_code == 200 else {}
if r.status_code != 200:
    print(json.dumps(r.json(), ensure_ascii=False)[:400])
t = time.perf_counter()
snap = _snapshot(AreaReportInput(**body), http=NoGateway())
print("report snapshot", f"{time.perf_counter() - t:.1f}s")
b, c = bundle.get("change_model") or {}, snap.get("change_model") or {}
for k in ("status", "reading", "change_tco2e", "band_q10_tco2e", "band_q90_tco2e", "state_year", "after_year", "cells_used", "cells_total"):
    print(f"  {k:16s} bundle={b.get(k)!r:>12} report={c.get(k)!r:>12}")
print("  plan_added      bundle=", (bundle.get("plan_emission") or {}).get("net_added_kgco2eq"),
      " report=", next((t["net_added_kgco2eq"] for t in (snap["effort"] or {}).get("targets") or [] if t["key"] == "plan_added"), None))
for f in snap["facts"]:
    if f["id"].startswith("change_model"):
        print(" ", f["id"], "|", f["text"])
print("key:", [kv for kv in key_results(dict(snap, summary={"mode": "TEMPLATE", "paragraphs": [], "validation": ""})) if "변화" in kv[0] or "증가분" in kv[0]])
html = area_html(dict(snap, summary={"mode": "TEMPLATE", "paragraphs": [], "validation": "v"}))
md = area_markdown(dict(snap, summary={"mode": "TEMPLATE", "paragraphs": [], "validation": "v"}))
print("html 3-1:", "3-1. 계획 반영 뒤 변화 예측" in html, "| md section:", "## 변화 예측" in md)
