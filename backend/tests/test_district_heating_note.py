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
