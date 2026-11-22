"""Same request, old service vs this checkout: are the responses identical? (user readiness U1, 2026-11-23)

Old = the running api (http://api:8000 inside the compose network); new = this checkout in-process (TestClient).
Floats are compared after rounding to 6 significant digits (summing the same numbers in another order may move the
last bit). Prints per request: identical / the first differing paths, and the two times.
usage (api container, checkout backend at /app): python /scripts/compare_responses.py <region,...> [request ...]
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

sys.path.insert(0, "/app")
REGIONS = sys.argv[1].split(",")
WANTED = sys.argv[2:] or ["dashboard", "map", "overlays", "model"]
OLD = "http://api:8000"
YEAR = 2025


def norm(v):
    if isinstance(v, float):
        return float(f"{v:.6g}")
    if isinstance(v, dict):
        return {k: norm(x) for k, x in v.items()}
    if isinstance(v, list):
        return [norm(x) for x in v]
    return v


def diff(a, b, path="$", out=None):
    out = [] if out is None else out
    if len(out) >= 5:
        return out
    if type(a) is not type(b):
        out.append(f"{path}: {type(a).__name__} vs {type(b).__name__}")
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{path}.{k}: only in {'new' if k in b else 'old'}")
            else:
                diff(a[k], b[k], f"{path}.{k}", out)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} vs {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append(f"{path}: {str(a)[:60]} vs {str(b)[:60]}")
    return out


def main() -> None:
    from fastapi.testclient import TestClient

    from app.main import app
    c = TestClient(app)
    for region in REGIONS:
        grid = c.get(f"/api/regions/{region}").json().get("default_grid_id")
        paths = {"dashboard": f"/api/dashboard?year={YEAR}&region={region}" + (f"&grid_id={grid}" if grid else ""),
                 "map": f"/api/map?year={YEAR}&region={region}", "overlays": f"/api/map/overlays?region={region}",
                 "model": f"/api/model?year={YEAR}&region={region}"}
        for name in WANTED:
            t = time.perf_counter()
            with urllib.request.urlopen(OLD + paths[name], timeout=600) as r:
                old = json.load(r)
            t_old = time.perf_counter() - t
            t = time.perf_counter()
            new = c.get(paths[name]).json()
            t_new = time.perf_counter() - t
            d = diff(norm(old), norm(new))
            print(f"{region} {name:9s} old {t_old:5.1f}s new {t_new:5.1f}s  {'IDENTICAL' if not d else 'DIFF ' + ' | '.join(d)}", flush=True)


if __name__ == "__main__":
    main()
