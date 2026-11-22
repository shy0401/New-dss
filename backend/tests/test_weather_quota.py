"""기상(Open-Meteo) 하루 한도는 한국 자정이 아니라 세계 표준시 자정 뒤에 다시 묻는다 (2026-11-22)."""
from datetime import datetime, timezone

from app import region_prepare
from app.cache import ExternalError


def at(monkeypatch, iso):
    monkeypatch.setattr(region_prepare, "now", lambda: datetime.fromisoformat(iso))


def test_weather_waits_for_utc_midnight_and_data_go_kr_for_kst_midnight(monkeypatch):
    at(monkeypatch, "2026-11-21T20:10:00+00:00")          # 05:10 KST: still 429 on 2026-11-22
    assert region_prepare.resume_time("weather") == datetime(2026, 11, 22, 0, 5, tzinfo=timezone.utc)
    assert region_prepare.resume_time("building_energy") == datetime(2026, 11, 22, 15, 20, tzinfo=timezone.utc)
    at(monkeypatch, "2026-11-22T00:02:00+00:00")          # just after the reset → the next day, never in the past
    assert region_prepare.resume_time("weather") == datetime(2026, 11, 23, 0, 5, tzinfo=timezone.utc)


def test_the_open_meteo_limit_is_named_and_still_waits():
    status, message = region_prepare._classify(ExternalError(region_prepare.OPEN_METEO_QUOTA))
    assert status == "WAITING" and message.startswith("Open-Meteo") and "공공데이터" not in message
