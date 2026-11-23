# 2026-11-24 지역난방 열 · 지역 평균 기준의 단지 기억을 ORM 객체 대신 일반 값으로 (DetachedInstanceError)
- 관련: `backend/app/service.py`(`_slim_complexes`, `SlimComplex`), 시험 `backend/tests/test_pooled_cache.py`, 앞 기록 [지역 화면 첫 계산 속도](2026-11-23-area-first-request-speed.md)(#95)
- 계기: #102를 올리며 전체 시험 623개 중 `tests/test_reporting_api.py::test_selected_grid_is_preserved_in_dashboard_and_report` 1개가 main에서도 실패(그 파일만 돌리면 통과)

## 왜
- 11-23(#95)에서 `pooled_baseline`이 쓰는 전국 단지(약 2.2만 개, 6열)를 5분 동안 기억하게 했는데, 기억 값이 **ORM 객체(`ApartmentComplex`)**였음
- 세션을 `expire_on_commit=False`로 열어도 `db.rollback()`은 그 세션에 붙은 모든 ORM 객체를 만료시킴. 기억을 채운 세션이 그 뒤 rollback하고 닫히면, 기억 속 객체는 "만료 + 세션 없음"이 되어 다음 요청에서 `c.heating_type`을 읽는 순간 `DetachedInstanceError`
- 재현(가지 코드를 붙인 임시 컨테이너, 실제 DB):
  - `test_extended_api.py`의 첫 시험(빈 격자로 `dashboard` → 기억 채움 → 끝에서 `db.rollback()`) → `test_reporting_api.py`의 해당 시험: **실패**. 뒤 시험만 따로: 통과
  - 실제 서비스와 같은 세션으로 "요청 A가 기억 채움 → rollback → 닫힘, 요청 B가 수원 지역난방 열 계산"을 따라 함: 고치기 전 `DetachedInstanceError`, 고친 뒤 정상

## 실제 서비스에서도 날 수 있었나: 예(드물지만 나면 5분 동안 계속)
- 계획 묶음(`/api/plans/evaluate`)은 한 세션에서 지역난방 열 블록(기억 채움) 뒤에 조례 블록을 돌리고, 조례 읽기 · 지역 평균 에너지 행 읽기(`_pooled_rows`) 등에 오류 시 `db.rollback()`이 있음. 블록 호출은 예외로 감싸지 않음
- 그런 rollback이 한 번 일어나면 기억이 살아 있는 5분 동안 지역난방 열 블록(묶음 전체 500)과 자기 기준이 없는 격자의 대시보드(`baseline_estimate`)가 실패. 평소 경로에서는 rollback이 오류 때만 나므로 드묾. 실제 서비스에서 일어난 기록은 확인하지 못함(확인 필요)

## 무엇을 바꿨나 (비포 → 애프터)
| 항목 | 비포 | 애프터 |
|---|---|---|
| 단지 기억 값 | `ApartmentComplex` ORM 객체(`load_only` 6열) | `SlimComplex` 이름 붙은 튜플(같은 6열: `kapt_code` · `heating_type` · `households` · `gross_floor_area_m2` · `management_area_m2` · `name`) |
| 읽는 방법 | `select(ApartmentComplex).options(load_only(...))` | `select(6열)` |
- 에너지 행 기억(`_pooled_rows`)은 이미 일반 dict라 그대로. 계산식 · 기억 시간(300초) 그대로

## 숫자 (실제 DB, 임시 컨테이너, main `2d7eb90` → 이 가지)
| 측정 | main | 가지 |
|---|---|---|
| 수원 칸 계획 묶음(기준 · 계획 배출 · 감축 · 지역난방 열, 80,000 m²) 첫 호출 / 두 번째 | 19.5초 / 0.0초 | 19.2초 / 0.0초 |
| 수원 2025 지역 평균(개별 · 지역난방) 첫 호출 / 두 번째 | 4.70초 / 0.01초 | 4.53초 / 0.01초 |
- 값 같음: 지역난방 열 300,406.8 kgCO2eq(합격 시험 300.4 t와 같음), 증가분 1,697,741.3 kgCO2eq, 개별난방 가스 64.507132 · 지역난방 2.48369 kWh/m²(면적 5,121,557.01 · 15,404,454.01 m²)
- 11-23 기록(수원 칸 첫 호출 21.8초, 둘째 0.1초)보다 나빠지지 않음. 그때와 계획 내용이 달라 초는 직접 견주지 않고, 같은 조건의 main과 견줌
- 시험: 백엔드 전체 624 통과 · 6 건너뜀(새 시험 1개 포함). 고치기 전 새 시험은 실패

## 하지 않은 것 · 남은 일
- 기억 키에 DB 엔진을 넣지 않음: 서비스는 DB 하나라 필요 없고, 기억 값이 일반 값이면 세션과 무관. 다른 DB(SQLite)를 쓰는 시험이 같은 프로세스에서 `pooled_baseline`을 부르면 실제 DB 기억을 볼 수 있음(지금 그런 시험 없음)
- 다른 5분 기억은 같은 문제가 없음: `area._INPUTS`는 단지를 열만 읽은 dict로(11-21), `energy_parcels._register_area`는 지번 → 연면적 숫자로 기억함(코드 확인)
