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
    assert len(r) == 653   # 2026-11-20 냉방 쪽 보강 35행, 2026-11-24 팀 감축 방안 조사 8행(T-)
    grades = Counter(x["근거_등급"] for x in r)
    assert set(grades) == {"실측_국내", "실측_국외_조건맞음", "문헌_계산", "실측_국외_참고", "가정", "해당_없음"}
    assert grades["실측_국내"] == 140 and grades["문헌_계산"] == 153   # 2026-11-24 T- 행: 실측_국내 1 · 문헌_계산 7
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
    assert [x["sigungu_name"] for x in r if not x["mapping"]] == []
    # 세종: 지점 이름 '세종연서'(611)는 이름 규칙에 안 맞지만 좌표가 세종시 연서면 안(DB 경계, 2026-11-21) → 세종 지점
    sejong = next(x for x in r if x["sigungu_code"] == "36110")
    assert (sejong["station_id"], sejong["station_name"], sejong["mapping"]) == ("611", "세종연서", "광역시 이름 지점(좌표 확인)")
    assert sejong["hdd18_normal"] != "" and sejong["sunshine_hours_year"] == ""   # 이 지점 평년값에 일조가 없음: 0으로 채우지 않음
    jeonju = next(x for x in r if x["sigungu_name"] == "전북특별자치도 전주시 완산구")
    assert jeonju["station_name"] == "전주" and float(jeonju["guide_emission_change_pct"]) == 0.0 and float(jeonju["hdd_ratio_vs_jeonju"]) == 1.0
    assert all("ESTIMATED" in x["value_kinds"] and "예측 아님" in x["value_kinds"] for x in r)
    daegu = [x for x in r if x["sigungu_code"].startswith("27")]
    assert len(daegu) == 9 and {x["station_name"] for x in daegu} == {"대구"}


def test_zone_lookup_uses_the_notice_table_not_the_sido_prefix():
    from app.reference_tables import design_zone, standard_zone
    assert design_zone("52110") == "중부2" and standard_zone("52110") == "중부"
    assert standard_zone("48120") == "남부"          # 경남 창원: 시도 앞자리 방식에서는 중부였다
    assert standard_zone("47110") == "남부"          # 경북 포항(시군 예외)
    assert standard_zone("27720") == "중부"          # 대구 군위(중부2)
    assert design_zone("50110") == "제주" and standard_zone("50110") is None   # 표준지표에 제주 값 없음
    assert design_zone("99999") is None and standard_zone(None) is None


def test_evidence_summary_links_rows_to_tool_measures():
    from app.reference_tables import evidence_summary
    ev = evidence_summary()
    env = ev["by_measure"]["envelope"]
    assert env["rows"] == 50 and env["sources"] <= env["rows"]          # 단열 28 + 창호 18 + 짝 비교 4
    assert "keep_structure" not in ev["by_measure"]                      # 근거표 행 없음(0이 아님)
    assert ev["by_measure"]["operation"]["exclusion"] == [{"value": "예", "rows": 16}]
    groups = {g["group"]: g for g in ev["unlinked_groups"]}
    assert groups["heat_pump"]["exclusion"][0]["value"] == "예" and groups["heat_pump"]["reasons"]
    assert groups["layout_form"]["rows"] == 39 and groups["layout_form"]["exclusion"][0]["value"] == "아니오"   # 2026-11-24 T-008 더함
    # 2026-11-24 팀 감축 방안 조사: 입면 · 발코니 태양광은 아직 도구 수단이 아니라 따로 묶음(지붕 태양광 근거로 세지 않음)
    assert groups["facade_pv"]["label"] == "입면·발코니 태양광" and groups["facade_pv"]["rows"] == 5 and groups["facade_pv"]["sources"] == 2
    assert sum(g["rows"] for g in ev["unlinked_groups"]) == 230


def test_region_guide_joins_zone_climate_and_plans():
    from app.reference_tables import region_guide
    g = region_guide("52110")
    assert g["design_zone"] == "중부2" and g["standard_zone"] == "중부"
    assert g["climate"]["station"] == "전주" and g["climate"]["guide_emission_change_pct"] == 0.0
    assert [(p["code"], p["tasks"]) for p in g["plans"]] == [("52110", 32), ("52", 14)]   # 시 계획 먼저, 그다음 도 계획
    sejong = region_guide("36110")
    assert sejong["climate"]["station"] == "세종연서" and sejong["climate"]["sunshine_hours_year"] is None   # 일조는 빈칸(0이 아님)
    assert sejong["plans"][0]["tasks"] == 33
    assert region_guide("99999") is None
    assert "예측 아님" in g["value_kinds"]
    # 냉방 쪽 수단: 모든 지역에 같은 목록, 읽는 법만 냉방도일 비의 부호로(새 임계값 없음)
    assert [i["label"] for i in g["cooling"]["items"]] == ["외부 차양·일사 조절", "쿨루프(고반사 지붕)", "옥상·벽면 녹화", "냉방기 효율"]
    assert g["cooling"]["items"][0]["use"] == "지표만" and g["cooling"]["items"][3]["use"].startswith("설비 사양")
    assert "1.00배입니다" in g["cooling"]["reading"] and "더 필요한" not in g["cooling"]["reading"]
    assert "더 필요한 지역" in region_guide("27110")["cooling"]["reading"]   # 대구 중구 CDD 비 1.06
    assert "0.36배입니다" in sejong["cooling"]["reading"]   # 세종연서 CDD 비 0.360(2026-11-21 연결)
    from app.reference_tables import cooling_measures
    assert "견주지 못합니다" in cooling_measures(None)["reading"]   # 기후 값이 없는 지역
    assert "2.21 · 2.72%p" in g["rate_note"] and "중부2" in g["rate_note"]
    assert g["reference"]["station"] == "전주" and g["reference"]["sunshine_hours_year"] == 2063.0


def test_regional_conditions_mark_value_kinds_and_keep_gaps_empty():
    r = rows("regional_conditions_sigungu.csv")
    assert len(r) == 23
    assert all(x["value_kinds"] for x in r)
    zones = {x["sigungu_code"]: x["design_zone"] for x in rows("design_zone_sigungu.csv")}
    assert all(zones.get(x["sigungu_code"]) == x["design_zone"] for x in r)
    # 지역 보정 관문을 못 넘은 참고값은 계산에 쓰지 않음을 표에 적었다
    assert all("계산에 쓰지 않음" in x["value_kinds"] for x in r if x["envelope_saving_adjusted_ref_pct_v2"])


def test_heat_stats_share_from_toe_and_city_codes_sum_their_gu():
    from app.reference_tables import heat_stats, region_guide
    r = rows("apartment_energy_stats_2025.csv")
    assert len(r) == 249 and sum(1 for x in r if x["district_heat_share_pct"]) == 83   # 인천 중구 · 동구 · 서구는 코드가 없어 뺌
    assert heat_stats("36110")["district_heat_share_pct"] == 45.8 and heat_stats("36110")["parts"] is None
    suwon = heat_stats("41110")                                   # 수원시 = 장안 · 권선 · 팔달 · 영통 합
    gu = [x for x in r if x["sigungu_code"][:4] == "4111"]
    assert len(suwon["parts"]) == len(gu) == 4
    assert suwon["district_heat_share_pct"] == round(sum(float(x["district_heat_toe"]) for x in gu) / sum(float(x["total_toe"]) for x in gu) * 100, 1)
    busan = heat_stats("26440")                                   # 통계에 지역난방 "-" → 0 %가 아니라 빈칸
    assert busan["district_heat_toe"] is None and busan["district_heat_share_pct"] is None and busan["total_toe"] > 0
    assert heat_stats("99999") is None
    assert region_guide("27110")["heat_stats"]["year"] == 2025    # 상세 수집 전 지역(대구 중구)도 가이드에 통계가 붙음


def test_asos_station_is_the_regions_own_asos_station_only():
    """2026-11-21: 기후 가이드 표의 같은 시 · 군(광역시는 시 안) 지점 중 ASOS(번호 300 미만)만. 다른 도시 대표 지점 · 평년값 AWS는 쓰지 않음."""
    from app.reference_tables import asos_station
    assert asos_station("50110") == ("184", "제주") and asos_station("48330") == ("257", "양산시")
    assert asos_station("11740") == ("108", "서울") and asos_station("26440") == ("159", "부산")   # same as the hand list
    assert asos_station("41360") is None          # 541 남양주: 평년값 지점이지만 ASOS 일자료 없음
    # 대구: 가이드 지점 860(평년값, ASOS 일자료 없음) → 같은 시 ASOS 143 (2026-11-24). 구 · 군 모두
    assert all(asos_station(c) == ("143", "대구") for c in ("27110", "27170", "27200", "27290", "27710", "27720"))
    assert asos_station("44800") == ("177", "홍성")   # 손정리 덮어쓰기(가이드는 서산 129, 다른 시)
    assert asos_station("12190") is None          # 다른 도시 대표 지점(목포)으로 이어진 곳
    assert asos_station(None) is None and asos_station("99999") is None


def test_asos_overrides_are_the_one_station_rule_and_only_three_are_needed():
    """2026-11-24: 손정리(region_prepare)를 reference_tables.ASOS_OVERRIDES로 옮겨 지점 고르는 규칙을 한 곳에 둠.
    덮어쓰기 13곳 모두 asos_station이 그대로 돌려주고, 가이드 표만으로 다른 곳은 세종 · 순창 · 홍성 셋(까닭은 표 주석)."""
    from app.reference_tables import ASOS_OVERRIDES, asos_station, guide_asos_station
    from app.region_prepare import ASOS_STATIONS
    assert ASOS_STATIONS is ASOS_OVERRIDES and len(ASOS_OVERRIDES) == 13
    assert all(asos_station(code) == station for code, station in ASOS_OVERRIDES.items())
    differ = {code for code, station in ASOS_OVERRIDES.items() if guide_asos_station(code) != station}
    assert differ == {"36110", "52770", "44800"}
    assert guide_asos_station("36110") is None and guide_asos_station("44800") is None   # 평년값 AWS 611 · 다른 시 129
    assert guide_asos_station("52770") == ("254", "순창군")                                 # 같은 지점, 이름만 다름
