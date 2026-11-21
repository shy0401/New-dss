"""K-apt 에너지 추가 키 흐름 (2026-11-21): 추가 키는 단지 목록 뒤에서부터 캐시를 채우고, 주 흐름을 만나거나 막히면 멈춤."""
import threading
from types import SimpleNamespace

from app import kapt_energy
from app.cache import QUOTA_ERROR, ExternalError


def test_extra_keys_skip_the_main_key_and_duplicates(monkeypatch):
    monkeypatch.setenv(kapt_energy.EXTRA_KEYS_ENV, " k2, main ,k3,k2,, ")
    assert kapt_energy.extra_keys("main") == ["k2", "k3"]
    monkeypatch.delenv(kapt_energy.EXTRA_KEYS_ENV)
    assert kapt_energy.extra_keys("main") == []


def run(monkeypatch, fake, *, position=0, answered=frozenset(), keys=("k2",)):
    calls = []
    monkeypatch.setattr(kapt_energy, "_fetch_month", lambda session, url, key, code, month, attempts=3: calls.append((key, code, month)) or fake(code, month))
    targets = [SimpleNamespace(kapt_code=f"A{i}") for i in range(6)]
    threads = kapt_energy.start_extra_key_prefetch(list(keys), targets, ["202501", "202502"], "u", {"main": position}, set(answered),
                                                   session_factory=lambda: object(), stop=threading.Event())
    for t in threads:
        t.join(5)
    return calls


def test_the_flow_starts_at_the_end_skips_answered_months_and_stops_at_the_main_pass(monkeypatch):
    calls = run(monkeypatch, lambda code, month: None, position=2, answered={("A5", "202501")})
    # from the end (A5, A4) and not past the main pass (index 2 + 1)
    assert calls == [("k2", "A5", "202502"), ("k2", "A4", "202501"), ("k2", "A4", "202502")]


def test_two_extra_keys_take_alternate_complexes(monkeypatch):
    calls = run(monkeypatch, lambda code, month: None, keys=("k2", "k3"))
    assert {code for key, code, _ in calls if key == "k2"} == {"A5", "A3"}
    assert {code for key, code, _ in calls if key == "k3"} == {"A4", "A2"}


def test_a_block_or_the_daily_quota_stops_the_flow(monkeypatch):
    def blocked(code, month):
        raise ExternalError("K-apt 제공기관 일시 오류: provider_code=04")
    assert len(run(monkeypatch, blocked)) == kapt_energy.EXTRA_STOP_AFTER_ERRORS

    def quota(code, month):
        raise ExternalError(QUOTA_ERROR)
    assert len(run(monkeypatch, quota)) == 1
