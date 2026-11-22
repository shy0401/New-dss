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
    assert district_heat_factor("11740", 2025)["factor_kind"] == "SUBSTITUTE"   # 강동 = 나래(공표 계수 없음 → 대체, 2026-11-21)
    assert district_heat_factor("47110", 2025) is None                     # 공급자를 모르는 지역
    assert district_heat_factor("36110", 2014) is None                     # 그해 값이 없으면 가까운 해로 채우지 않음
    # 2021 집단에너지사업 편람: 달서 = 대구지사(성서 · 대곡 · 용산 · 장기), 양산 = 양산지사(물금 · 사송)
    assert district_heat_factor("27290", 2025)["branch"] == "대구" and district_heat_factor("27290", 2025)["kg_per_kwh"] == 0.1324
    assert district_heat_factor("48330", 2025)["branch"] == "양산" and district_heat_factor("48330", 2025)["kg_per_kwh"] == 0.1325
    assert district_heat_factor("27290", 2022)["kg_per_kwh"] == 0.2081      # 대구지사는 해마다 크게 다름 → 그해 값
    # 사업자가 둘(성남: 한난 분당 · 판교 + 나래 위례), 공급자 모름(전주), 지정 지역 없음(제주) → 계산 안 함
    assert all(district_heat_factor(code, 2025) is None for code in ("41130", "52110", "50110"))
    assert district_heat_factor("27290", 2025)["factor_kind"] == "PUBLISHED"


def test_supplier_without_published_factor_uses_the_local_guideline_value_as_substitute():
    """2026-11-21 (기준 문서 5.16 · 판 1.41): 편람으로 공급자가 확인됐으나 공표 열 계수가 없는 사업자는 지자체 산정지침 공통값
    0.1226 tCO2eq/Gcal(서울시 인벤토리 · 탄소공간지도로 확인)을 대체로. 1 Gcal = 1,163 kWh → 0.1054 kg/kWh, 연도와 상관없이 같음."""
    from app.emissions import LOCAL_GUIDELINE_HEAT_KG_PER_KWH, district_heat_factor
    assert LOCAL_GUIDELINE_HEAT_KG_PER_KWH == 0.1054
    for code, supplier in (("11740", "나래에너지서비스"), ("26440", "부산도시가스"), ("52140", "전북집단에너지"), ("41360", "별내에너지")):
        f = district_heat_factor(code, 2025)
        assert f["factor_kind"] == "SUBSTITUTE" and f["supplier"] == supplier and f["kg_per_kwh"] == 0.1054
        assert "공급자 값 아님" in f["source"] and "2007 · 2008년" in f["source"]
        assert district_heat_factor(code, 2014)["kg_per_kwh"] == 0.1054   # 고정값: 해마다 같음


def test_substitute_heat_estimate_says_so_in_its_sentence(monkeypatch):
    import app.service as service
    month = lambda gas: {"area_m2": 1000.0, "monthly": [{"gas_kwh": gas / 12} for _ in range(12)]}
    pools = {"individual": month(72_700.0), "district": month(4_100.0)}
    monkeypatch.setattr(service, "pooled_baseline", lambda db, year, sc, heating: pools[heating])
    est = service.district_heat_estimate(None, 2025, None, "11740", {"district_share_pct": 50.0, "complexes": 4, "unknown_complexes": 0}, 10_000)
    assert est["factor_kind"] == "SUBSTITUTE" and est["carbon_kg"] == round(343_000 * 0.1054, 1)   # 10,000 m² × 50% × (72.7 − 4.1)
    text = service.district_heat_text(est)
    assert text.startswith("지역난방 열(추정, 대체 계수)") and "공급자 값 아님" in text


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
    assert service.district_heat_estimate(None, 2025, None, "47110", {"district_share_pct": 50.0}, 10_000) is None


def test_standard_doc_heat_table_matches_the_code():
    """기준 문서 5.16의 계수표와 emissions 상수가 같다(AGENTS.md: 계수는 문서와 코드가 같아야 함)."""
    import re
    from pathlib import Path
    from app.emissions import HEAT_SUPPLIER_BRANCH, KDHC_HEAT_KG_PER_TJ, district_heat_factor
    import pytest
    path = Path(__file__).resolve().parents[2] / "docs" / "DATA_STANDARD.md"
    if not path.exists():   # 백엔드 폴더만 넣은 컨테이너에서는 문서가 없음(CI는 저장소 전체)
        pytest.skip("docs/DATA_STANDARD.md 없음")
    doc = path.read_text(encoding="utf-8")
    section = doc.split("### 5.16", 1)[1].split("## 6.", 1)[0]
    region_of = {branch: code for code, branch in HEAT_SUPPLIER_BRANCH.items()}
    num = lambda s: tuple(float(x.replace(",", "")) for x in s.split("·"))
    seen = {}
    # 표마다 머리줄의 지사 이름 두 개("<지사>지사 CO2 · CH4 · N2O")를 읽고 그 아래 연도 줄을 코드와 견줌
    for head, body in re.findall(r"^\| 연도 \| (.+?) \|\n\|[-| ]+\|\n((?:\| 20\d\d \|.*\n?)+)", section, re.M):
        branches = [b.replace(" ", "") for b in re.findall(r"([^|]+?)지사 CO2", head)]
        assert len(branches) == 2, head
        for year, a, a_kwh, b, b_kwh in re.findall(r"^\| (20\d\d) \| ([\d,.· ]+) \| ([\d.]+) \| ([\d,.· ]+) \| ([\d.]+) \|$", body, re.M):
            y = int(year)
            for branch, values, kwh in ((branches[0], a, a_kwh), (branches[1], b, b_kwh)):
                assert num(values) == KDHC_HEAT_KG_PER_TJ[branch][y]
                assert float(kwh) == district_heat_factor(region_of[branch], y)["kg_per_kwh"]
                seen.setdefault(branch, set()).add(y)
    # 코드의 지사 · 연도가 문서에 빠짐없이 있음
    assert seen == {branch: set(years) for branch, years in KDHC_HEAT_KG_PER_TJ.items()}
    assert set(KDHC_HEAT_KG_PER_TJ) == set(HEAT_SUPPLIER_BRANCH.values())


def test_new_detailed_regions_get_their_supplier_or_stay_held():
    """2026-11-22 (기준 문서 5.16 · 판 1.49): 상세 수집을 넓힌 뒤 지역난방이 큰 23곳 — 편람으로 사업자가 하나로 확인된 곳만 연결."""
    from app.emissions import district_heat_factor
    published = {"41280": ("수도권연계", 0.1302), "11680": ("수도권연계", 0.1302), "41460": ("수도권연계", 0.1302),
                 "41480": ("수도권연계", 0.1302), "48250": ("김해", 0.1884), "12170": ("광주전남", 0.1510)}
    for code, (branch, kwh) in published.items():
        f = district_heat_factor(code, 2025)
        assert f["factor_kind"] == "PUBLISHED" and f["branch"] == branch and f["kg_per_kwh"] == kwh, code
    assert district_heat_factor("48250", 2024)["kg_per_kwh"] == 0.1288        # 김해지사도 그해 값(2025년 +46%)
    substitute = {"41290": "GS파워", "41410": "GS파워", "41170": "GS파워", "41430": "GS파워", "41190": "GS파워",
                  "11470": "서울에너지공사", "41450": "나래에너지서비스", "28185": "인천종합에너지", "41270": "안산도시개발",
                  "41370": "디에스파워", "44800": "내포그린에너지", "41210": "삼천리", "27710": "대성에너지"}
    for code, supplier in substitute.items():
        f = district_heat_factor(code, 2025)
        assert f["factor_kind"] == "SUBSTITUTE" and f["supplier"] == supplier and f["kg_per_kwh"] == 0.1054, code
    # 사업자 둘 이상(성남 · 송파 · 화성), 공급자 모름(대구 서구) → 계산하지 않음
    assert all(district_heat_factor(code, 2025) is None for code in ("41130", "11710", "41590", "27170"))
