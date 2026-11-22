"""Where the screen's slow first requests spend their time (user readiness U1, 2026-11-23).

Calls the endpoints in-process with FastAPI's TestClient (fresh process = cold caches) under cProfile and prints the
functions with the most cumulative time inside `app/`. Reads only.
usage (api container, repo backend mounted at /app): python -m scripts_profile <region> [request ...]
  run as: python /scripts/profile_requests.py 41130 dashboard map overlays model
"""
from __future__ import annotations

import cProfile
import io
import pstats
import sys
import time

REGION = sys.argv[1] if len(sys.argv) > 1 else "41130"
WANTED = sys.argv[2:] or ["dashboard", "map", "overlays", "model"]
YEAR = 2025


def main() -> None:
    sys.path.insert(0, "/app")
    from fastapi.testclient import TestClient

    from app.main import app
    c = TestClient(app)
    grid = c.get(f"/api/regions/{REGION}").json().get("default_grid_id")
    paths = {"dashboard": f"/api/dashboard?year={YEAR}&region={REGION}" + (f"&grid_id={grid}" if grid else ""),
             "map": f"/api/map?year={YEAR}&region={REGION}", "overlays": f"/api/map/overlays?region={REGION}",
             "model": f"/api/model?year={YEAR}&region={REGION}", "area_options": f"/api/areas/options?region={REGION}"}
    for name in WANTED:
        prof = cProfile.Profile()
        t = time.perf_counter()
        prof.enable()
        r = c.get(paths[name])
        prof.disable()
        sec = time.perf_counter() - t
        out = io.StringIO()
        stats = pstats.Stats(prof, stream=out).sort_stats("cumulative")
        stats.print_stats(r"/app/app/", 18)
        print(f"===== {name} {r.status_code} {sec:.1f}s =====")
        lines = [ln for ln in out.getvalue().splitlines() if "/app/app/" in ln]
        print("\n".join(lines[:18]))
        # the same request again: what the in-memory caches save
        t = time.perf_counter()
        c.get(paths[name])
        print(f"----- {name} second call {time.perf_counter() - t:.1f}s")


if __name__ == "__main__":
    main()
