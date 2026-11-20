"""대상지 지역난방 비중과 가정 문장(2026-11-20): 지역난방 열 탄소는 계산 밖이라 숫자는 바꾸지 않고 문장으로만 알린다."""
from types import SimpleNamespace as C

from app.service import district_heating_note, heating_share


def test_share_is_floor_area_weighted_and_unknown_is_left_out():
    share = heating_share([C(heating_type="지역난방", gross_floor_area_m2=30000), C(heating_type="개별난방", gross_floor_area_m2=10000),
                           C(heating_type="-", gross_floor_area_m2=50000)])
    assert share == {"district_share_pct": 75.0, "complexes": 2, "unknown_complexes": 1}
    assert heating_share([C(heating_type="-", gross_floor_area_m2=1000)]) is None   # 아는 단지가 없으면 0 %가 아니라 None
    assert heating_share([]) is None


def test_note_only_when_district_heating_is_present():
    note = district_heating_note({"district_share_pct": 75.0, "complexes": 2, "unknown_complexes": 1})
    assert "난방 방식을 아는 K-apt 단지 2곳 중 연면적 75%가 지역난방" in note and "운영탄소가 작게 잡힙니다" in note and "13.7%" in note
    assert district_heating_note({"district_share_pct": 0.0, "complexes": 3, "unknown_complexes": 0}) is None
    assert district_heating_note(None) is None


def test_heat_factor_is_the_supplier_branch_value_of_that_year():
    from app.emissions import district_heat_factor
    f = district_heat_factor("36110", 2025)   # 세종지사 2025: 40,026 + 0.7199×28 + 0.072×265 kg/TJ
    assert f["branch"] == "세종" and f["co2eq_kg_per_tj"] == 40065.2 and f["kg_per_kwh"] == 0.1442
    assert district_heat_factor("41110", 2025)["kg_per_kwh"] == 0.1302      # 수도권 연계지사(수원 · 광교)
    assert district_heat_factor("11740", 2025) is None                     # 공급자 확인 전 지역
    assert district_heat_factor("36110", 2014) is None                     # 그해 값이 없으면 가까운 해로 채우지 않음


def test_heat_estimate_uses_individual_minus_district_gas(monkeypatch):
    import app.service as service
    month = lambda gas: {"area_m2": 1000.0, "monthly": [{"gas_kwh": gas / 12} for _ in range(12)]}
    pools = {"individual": month(70_000.0), "district": month(3_000.0)}
    monkeypatch.setattr(service, "pooled_baseline", lambda db, year, sc, heating: pools[heating])
    est = service.district_heat_estimate(None, 2025, None, "36110", {"district_share_pct": 50.0, "complexes": 4, "unknown_complexes": 0}, 10_000)
    assert est["heat_kwh_per_m2"] == 67.0 and est["heat_kwh"] == 335_000.0          # 10,000 m² × 50% × (70 − 3)
    assert est["carbon_kg"] == round(335_000 * 0.1442, 1) and est["data_class"] == "ESTIMATED"
    assert "관측 전력·가스 합계에 섞지 않고" in service.district_heat_text(est)
    # 가스 달이 빠지면 값을 내지 않음(0이 아님), 공급자 없는 지역도 None
    pools["district"] = {"area_m2": 1000.0, "monthly": [{"gas_kwh": None}] + [{"gas_kwh": 250.0}] * 11}
    assert service.district_heat_estimate(None, 2025, None, "36110", {"district_share_pct": 50.0}, 10_000) is None
    assert service.district_heat_estimate(None, 2025, None, "11740", {"district_share_pct": 50.0}, 10_000) is None


def test_standard_doc_heat_table_matches_the_code():
    """기준 문서 5.16의 계수표와 emissions 상수가 같다(AGENTS.md: 계수는 문서와 코드가 같아야 함)."""
    import re
    from pathlib import Path
    from app.emissions import KDHC_HEAT_KG_PER_TJ, district_heat_factor
    import pytest
    path = Path(__file__).resolve().parents[2] / "docs" / "DATA_STANDARD.md"
    if not path.exists():   # 백엔드 폴더만 넣은 컨테이너에서는 문서가 없음(CI는 저장소 전체)
        pytest.skip("docs/DATA_STANDARD.md 없음")
    doc = path.read_text(encoding="utf-8")
    section = doc.split("### 5.16", 1)[1].split("## 6.", 1)[0]
    rows = re.findall(r"^\| (20\d\d) \| ([\d,.· ]+) \| ([\d.]+) \| ([\d,.· ]+) \| ([\d.]+) \|$", section, re.M)
    assert len(rows) == 11
    num = lambda s: tuple(float(x.replace(",", "")) for x in s.split("·"))
    for year, sejong, sejong_kwh, metro, metro_kwh in rows:
        y = int(year)
        assert num(sejong) == KDHC_HEAT_KG_PER_TJ["세종"][y] and num(metro) == KDHC_HEAT_KG_PER_TJ["수도권연계"][y]
        assert float(sejong_kwh) == district_heat_factor("36110", y)["kg_per_kwh"] and float(metro_kwh) == district_heat_factor("41110", y)["kg_per_kwh"]
