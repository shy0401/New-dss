"""참조 표(backend/reference)의 모양과 규칙: 행 수 · 필수 열 · 값의 성격 · NULL을 0으로 채우지 않음."""
import csv
from collections import Counter
from pathlib import Path

REF = Path(__file__).resolve().parent.parent / "reference"


def rows(name: str) -> list[dict[str, str]]:
    with (REF / name).open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def test_evidence_table_rows_grades_and_exclusions():
    r = rows("reduction_evidence.csv")
    assert len(r) == 645   # 2026-11-20 냉방 쪽 보강 35행
    grades = Counter(x["근거_등급"] for x in r)
    assert set(grades) == {"실측_국내", "실측_국외_조건맞음", "문헌_계산", "실측_국외_참고", "가정", "해당_없음"}
    assert grades["실측_국내"] == 139 and grades["문헌_계산"] == 146
    a10 = [x for x in r if x["번호"].startswith("A10-")]
    assert len(a10) == 35 and all(x["쓰임"].startswith("범위 참고") for x in a10)
    assert {x["추천_제외"] for x in r} == {"예", "아니오", "따로 추천 안 함", "해당 없음"}
    # 추천에서 뺀 행에는 까닭이 있다
    assert all(x["제외_까닭"] for x in r if x["추천_제외"] in ("예", "따로 추천 안 함"))
    # 효과 값이 비어 있으면 빈칸 그대로(0으로 채우지 않음): 대표값이 빈 행이 있다
    assert sum(1 for x in r if x["대표값_pct"] == "") > 0


def test_local_plans_are_plan_values_with_unit_columns():
    r = rows("local_plans_building.csv")
    assert len(r) == 447 and len({x["지역_코드"] for x in r}) == 20
    assert {x["값의_종류"] for x in r} == {"지자체 계획값(자체 평가)"}
    for x in r:
        if not x["목표_감축량"].strip():   # 목표가 없으면 맞춘 열도 빈칸
            assert x["목표_감축량_tco2eq"] == "" and x["목표_기준"] == ""
        else:
            assert x["목표_기준"] in ("한 해", "누적", "확인 필요")
            assert x["목표_배율"] in ("1", "1000")


def test_design_zones_follow_the_notice():
    r = rows("design_zone_sigungu.csv")
    assert len(r) == 269
    assert Counter(x["design_zone"] for x in r) == {"중부2": 159, "남부": 85, "중부1": 23, "제주": 2}
    assert {x["design_zone"] for x in r if x["sigungu_code"].startswith("52")} == {"중부2"}   # 전북 16개 시군구
    assert len(rows("design_zone_uvalue_apartment.csv")) == 11


def test_regional_climate_guide_is_a_marked_estimate_against_jeonju():
    r = rows("regional_climate_guide.csv")
    assert len(r) == 269
    assert [x["sigungu_name"] for x in r if not x["mapping"]] == ["세종특별자치시"]   # 지점 이름이 '세종연서'라 연결 안 됨
    blank = next(x for x in r if not x["mapping"])
    assert blank["hdd18_normal"] == "" and blank["guide_emission_change_pct"] == ""   # 0으로 채우지 않음
    jeonju = next(x for x in r if x["sigungu_name"] == "전북특별자치도 전주시 완산구")
    assert jeonju["station_name"] == "전주" and float(jeonju["guide_emission_change_pct"]) == 0.0 and float(jeonju["hdd_ratio_vs_jeonju"]) == 1.0
    assert all("ESTIMATED" in x["value_kinds"] and "예측 아님" in x["value_kinds"] for x in r)
    daegu = [x for x in r if x["sigungu_code"].startswith("27")]
    assert len(daegu) == 9 and {x["station_name"] for x in daegu} == {"대구"}


def test_regional_conditions_mark_value_kinds_and_keep_gaps_empty():
    r = rows("regional_conditions_sigungu.csv")
    assert len(r) == 23
    assert all(x["value_kinds"] for x in r)
    zones = {x["sigungu_code"]: x["design_zone"] for x in rows("design_zone_sigungu.csv")}
    assert all(zones.get(x["sigungu_code"]) == x["design_zone"] for x in r)
    # 지역 보정 관문을 못 넘은 참고값은 계산에 쓰지 않음을 표에 적었다
    assert all("계산에 쓰지 않음" in x["value_kinds"] for x in r if x["envelope_saving_adjusted_ref_pct_v2"])
