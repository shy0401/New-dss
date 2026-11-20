"""VWorld 타일 미리 받기 (2026-11-21): 여러 흐름이 저장 단계와 같은 요청으로 캐시를 채움."""
import json
import threading
import time

from app import vworld


def body(total_pages, page):
    return json.dumps({"response": {"status": "OK", "page": {"total": total_pages, "current": page},
                                    "result": {"featureCollection": {"features": []}}}}).encode()


class FakeSession:
    """Answers per tile: the tile at x=968000 has 3 pages, the others 1. Records (operation, params) per call."""

    def __init__(self, calls, lock):
        self.calls, self.lock = calls, lock

    def get(self, provider, operation, url, params):
        with self.lock:
            self.calls.append((threading.current_thread().name, operation, dict(params)))
        time.sleep(0.05)   # like a network answer: the other flow gets to take a tile meanwhile
        pages = 3 if "-968000-" in operation else 1
        return {"body": body(pages, params["page"]), "status": 200}


def test_prefetch_asks_every_page_of_every_tile_like_the_stored_pass(monkeypatch):
    monkeypatch.setattr(vworld, "load_layer_config", lambda: {"cadastral": {"dataset_id": "LP_PA_CBND_BUBUN", "source_crs": "EPSG:5179"}})
    calls, lock = [], threading.Lock()
    cells = ["cell_968000_1762000", "cell_968500_1762500", "cell_969000_1762000", "cell_970000_1762000"]
    done, failed = vworld.prefetch_vworld_cells("cadastral", cells, flows=2, api_key="k", domain="http://localhost",
                                                session_factory=lambda: FakeSession(calls, lock))
    assert (done, failed) == (5, 0)                                       # 3 pages + 1 + 1
    asked = sorted((op, p["page"]) for _, op, p in calls)
    assert asked == [("cadastral-tile1000-968000-1762000-1", 1), ("cadastral-tile1000-968000-1762000-2", 2),
                     ("cadastral-tile1000-968000-1762000-3", 3), ("cadastral-tile1000-969000-1762000-1", 1),
                     ("cadastral-tile1000-970000-1762000-1", 1)]
    # the same cache identity as the stored pass: same operation name and params for the tile
    tiles = vworld.tiles_for(cells)
    op, params = vworld.tile_request("cadastral", {"dataset_id": "LP_PA_CBND_BUBUN", "source_crs": "EPSG:5179"}, "k", "http://localhost",
                                     968000, 1762000, tiles[(968000, 1762000)], 1)
    assert (op, params) in [(o, p) for _, o, p in calls]
    assert len({name for name, _, _ in calls}) == 2                      # two flows worked


def test_prefetch_does_nothing_without_a_key_or_with_one_flow(monkeypatch):
    monkeypatch.delenv("VWORLD_API_KEY", raising=False)
    assert vworld.prefetch_vworld_cells("cadastral", ["cell_968000_1762000"], flows=2) == (0, 0)
    assert vworld.prefetch_vworld_cells("cadastral", ["cell_968000_1762000"], flows=1, api_key="k") == (0, 0)


def test_a_failed_page_is_left_to_the_stored_pass(monkeypatch):
    monkeypatch.setattr(vworld, "load_layer_config", lambda: {"zoning": {"dataset_id": "LT_C_UQ111", "source_crs": "EPSG:5179"}})

    class Broken:
        def get(self, *a):
            return {"body": json.dumps({"response": {"status": "ERROR", "error": {"code": "SYSTEM_ERROR"}}}).encode(), "status": 200}

    assert vworld.prefetch_vworld_cells("zoning", ["cell_968000_1762000"], flows=2, api_key="k", session_factory=Broken) == (0, 1)
