# 2026-11-24 같은 규칙을 한 곳으로: ASOS 지점 덮어쓰기 표 · ZEB 등급표, 지역 난방 구성은 가벼운 단지 기억에서
- 관련: `backend/app/reference_tables.py`(`ASOS_OVERRIDES`, `asos_station`, `guide_asos_station`), `region_prepare.py`, `reduction_plan.py`, `service.py`(`SlimComplex`, `baseline_estimate`), 시험 `tests/test_reference_tables.py` · `test_reduction_measures.py`
- 계기: 상태 점검(11-24) 후속 계획의 발표 전 안전 묶음 B3 · B2(사용자 "B1부터 진행"). 값 · 계산 · 화면은 그대로인 내부 정리만

## 왜
- 같은 규칙이 두 곳에 있어 한쪽만 고치면 어긋날 수 있었다: ASOS 지점(손정리 `region_prepare.ASOS_STATIONS` ↔ 가이드 표 `reference_tables.asos_station`), ZEB 등급 구간표(`reduction_plan` ↔ `benchmarks`). 감축 수단 목록의 글자 지표("옥상의 60% · 10 m²/kW", "연 1.0 kgCO2")는 상수와 따로 적혀 있었는데 숫자만 시험하고 글자는 보지 않았다
- 격자에 난방 정보가 없을 때 `baseline_estimate`가 지역 난방 구성을 보려고 전국 단지 표 전체(JSON 열 포함)를 요청마다 ORM으로 읽었다(#104가 없앤 읽기와 같은 꼴)

## 바뀐 것
| 곳 | 전 | 후 |
|---|---|---|
| ASOS 지점 고르기 | `region_prepare`의 손정리 13곳을 먼저 보고, 없으면 `reference_tables` 가이드 규칙 | 둘 다 `reference_tables`에: `asos_station` = 덮어쓰기 표(`ASOS_OVERRIDES`) → 가이드 규칙(`guide_asos_station`). `region_prepare.ASOS_STATIONS`는 같은 표를 가리키는 별칭(스크립트 호환) |
| ZEB 등급 구간표 | 두 모듈에 같은 표 | `benchmarks.ZEB_GRADES` 하나. 등급 함수는 둘 그대로(20% 미만을 사다리용은 None, 기준 대조용은 "등급 기준(20%) 미만" 문구로 — 일부러 다름) |
| 수단 글자 지표 | 시험 없음 | 지붕 · 녹지 지표 글자가 `ROOF_USABLE_RATIO` · `ROOF_M2_PER_KW` · `GREEN_UPTAKE_KG_PER_M2`와 같은지 시험(수단 목록이 `reduction_plan`을 가져오면 순환 가져오기라 상수 대신 시험으로 묶음) |
| 지역 난방 구성 | 단지 표 전체 ORM 읽기 | 5분 기억하는 가벼운 단지 목록(`SlimComplex`에 `bjd_code` · `grid_id` 더함)에서 읽음. 읽는 행은 같음 |

## 확인
- 덮어쓰기 13곳 모두 `asos_station`이 그대로 돌려줌. 가이드 표만으로 다른 곳은 **세종 · 순창 · 홍성 셋**: 세종은 가이드 지점이 평년값 AWS(611), 순창은 같은 지점인데 이름이 '순창군'이라 응답 지점명 확인이 어긋남, 홍성은 가이드가 다른 시(서산 129). 나머지 10곳은 가이드 결과와 같음(이유를 표 주석에 적음)
- 지점을 고르는 순서(덮어쓰기 → 가이드)가 전과 같아 모든 지역의 지점 결과가 같음
- 전체 시험 통과(새 시험 1개, 고친 시험 2개)

## 하지 않은 것
- 시험의 고정 숫자(근거표 653행, 지자체 계획 447행, 설계 지역 구분 269행 등)를 느슨하게 바꾸는 일(계획 B7): 이 숫자들은 참고표가 바뀌면 일부러 알아채게 하는 장치로 쓰고 있어 그대로 둠. 점검이 짚은 DB 시험의 CI 제외는 시험 DB 분리가 필요해 발표 뒤
- 난방 분류기 둘(2분류 · 4분류)을 하나로 · 면적 없는 단지의 가중치(값이 바뀔 수 있음): 발표 뒤
