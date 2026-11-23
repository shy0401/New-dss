# 2026-11-24 도일 다시 계산: 지역 기상의 ASOS 달은 ASOS 일자료로 (ERA5로 덮지 않음)
- 관련: `backend/app/standard.py`(`recompute_degree_days` → `_recompute_region_degree_days`, `_asos_station_months`), 시험 `tests/test_standard.py`, [기준 문서](../DATA_STANDARD.md) 5.10 · 판 1.58, [대구 · 홍성 ASOS 기록](2026-11-24-region-asos-daegu-hongseong.md)
- 계기: 대구 · 홍성 ASOS 연결(PR #102) 중 발견. 그 기록의 "남은 일"을 처리함

## 왜
- 지역 기상 표(`region_weather_monthly`)는 ERA5-Land 월값(`FALLBACK`)을 깔고, 같은 시 · 군 ASOS 관측소의 완전월은 ASOS 값(`OFFICIAL`, 출처 `KMA ASOS <지점> <이름>`)으로 바꾼다(2절, 11-16 · 11-21).
- `recompute_degree_days`는 코드 기준 판(`standard.VERSION`)이 바뀔 때 서비스 시작(`main.py`의 `apply_standard`)과 `python -m app.cli apply-standard`에서 돈다. 지역 기상 표의 **모든 행** 도일을 ERA5-Land 원본(`data/raw/weather-regions/<코드>.json`)으로 다시 계산했다 → ASOS 달의 도일이 ERA5 값으로 바뀌고 출처 표시는 ASOS로 남음(평균기온 등은 ASOS 그대로). 값의 종류를 섞지 않는다는 원칙(1절 3)에 어긋남.

## 무엇을 바꿨나 (비포 → 애프터)
| 항목 | 비포 | 애프터 | 근거 |
|---|---|---|---|
| ASOS 달(`OFFICIAL`) 다시 계산 | ERA5-Land 일자료로 HDD · CDD 계산 | 그 지점의 ASOS 일자료 원본(`data/raw/kma/asos-regions/<지점>/<연도>-p<쪽>.json`, `_asos_overlay`가 저장)을 `parse_asos_response` · `aggregate_asos_months`로 다시 계산 | 같은 원본 · 같은 함수 |
| ASOS 원본이 없거나 그달이 다 차지 않음 | (ERA5로 덮음) | 저장된 값 그대로, `region_asos_kept`로 세고 로그에 지역 · 지점별로 알림 | 짐작으로 채우지 않음 |
| 대체 달(`FALLBACK`) | ERA5-Land로 계산, 원본에 없는 달은 CDD NULL | 같음 | — |
| 결과 수 | `region_months` · `region_cleared` | 더해서 `region_asos_months` · `region_asos_kept` | `ops/standard.json`에 남음 |
- 지점 번호는 출처 문자열(`KMA ASOS 143 대구`)에서 읽음. 지점 원본은 지점마다 한 번만 읽음(여러 구가 한 지점을 씀).
- 도일 규칙(HDD 18 ℃ · CDD 24 ℃, 빠진 날이 있으면 NULL)과 코드 기준 판 `VERSION = "1.3"`은 그대로. 이번 변경으로 다시 계산이 돌지 않음.

## 숫자 (이 PC DB, 읽기 전용으로 셈 · 2026-11-24)
- 방법: api 이미지의 일회용 컨테이너, `data/`는 읽기 전용, DB 거래는 `READ ONLY`. 저장값과 두 방법(옛: ERA5 / 새: ASOS 원본)을 달마다 비교(차이 0.05 넘으면 다름). 스크립트는 PC 임시 폴더(저장소 밖).
- 지역 기상 표 26,928행 = `FALLBACK` 10,594 + `OFFICIAL` 16,334(126곳, ASOS 지점 67곳). ASOS 원본이 없는 `OFFICIAL` 달 0개.
- 옛 방법을 지금 돌리면: `OFFICIAL` 14,776개월(114곳)의 도일이 ERA5 값으로 바뀜, 한 달 HDD 차이 최대 161.6.
- 새 방법을 지금 돌리면: 1,475개월(12곳)만 바뀜 — 아래 "이미 덮인 달"을 ASOS 값으로 되돌리는 것. `FALLBACK` 달은 두 방법이 같음.

### 이미 덮인 달 (판 1.3 적용, 2026-11-20 22:34 UTC)
- `data/ops/standard.json`: 판 1.3 적용 때 `region_months 3168`. 이때 11-16에 ASOS로 바꾼 손정리 12곳(서울 108 · 부산 159 · 세종 239 · 수원 119 · 군산 140 · 정읍 245 · 남원 247 · 장수 248 · 임실 244 · 순창 254 · 고창 172 · 부안 243)의 ASOS 달이 ERA5 도일로 덮였음.
- 확인: 그 12곳의 `OFFICIAL` 1,482개월 중 1,475개월은 저장 도일이 ERA5 원본 값과 같고 ASOS 원본 값과 다름(나머지 7개월은 두 값이 같음). 평균기온은 ASOS 원본과 같음. 11-21 뒤 연결한 114곳은 14,776개월 모두 ASOS 값, 76개월은 두 값이 같음.
- 연 도일(12달 모두 ASOS인 해의 평균, 지금 저장값 → ASOS 원본):

| 지역 | 해 수 | HDD | CDD |
|---|---|---|---|
| 서울 강동구(11740, 108) | 11 | 2,767 → 2,515 (−251) | 139 → 227 (+88) |
| 부산 강서구(26440, 159) | 11 | 1,869 → 1,721 (−149) | 145 → 189 (+44) |
| 세종(36110, 239) | 4 | 2,479 → 2,421 (−58) | 185 → 193 (+7) |
| 수원(41110, 119) | 11 | 2,747 → 2,578 (−169) | 126 → 192 (+66) |
| 군산(52130, 140) | 6 | 2,329 → 2,360 (+31) | 170 → 205 (+35) |
| 정읍(52180, 245) | 10 | 2,348 → 2,358 (+10) | 171 → 206 (+35) |
| 남원(52190, 247) | 5 | 2,473 → 2,487 (+14) | 169 → 226 (+57) |
| 장수(52740, 248) | 8 | 2,755 → 2,882 (+127) | 66 → 68 (+2) |
| 임실(52750, 244) | 8 | 2,845 → 2,661 (−184) | 62 → 130 (+69) |
| 순창(52770, 254) | 5 | 2,562 → 2,445 (−117) | 108 → 202 (+94) |
| 고창(52790, 172) | 3 | 2,250 → 2,411 (+161) | 159 → 190 (+31) |
| 부안(52800, 243) | 10 | 2,208 → 2,311 (+103) | 152 → 190 (+38) |

- 이 표를 쓰는 곳: `regions.weather_rows`(지역 화면 기상), `cell_state`(칸 상태의 `heating_degree_days_c` · `cooling_degree_days_c`, 12달 모두 ASOS일 때), `merge_bundle`(팀 묶음). 이미 만든 칸 상태 · 묶음에 덮인 값이 들어갔는지는 확인 필요.

## 시험
- `test_region_degree_days_recompute_keeps_asos_months_on_asos`: ASOS 달은 ASOS 원본 값(16 × 31), 대체 달은 ERA5 값(18 × 28), 출처 표시 그대로.
- `test_region_asos_month_without_daily_pages_is_left_as_stored_and_counted`: ASOS 원본이 없으면 저장값(450.5) 그대로, `region_asos_kept` 1, 로그에 `44800:177 1`.
- 옛 `standard.py`로 두 시험 모두 실패함(ASOS 달에 ERA5 558이 들어감)을 확인. DB 없이 도는 백엔드 시험 599개 통과(6개는 문서 · DB 없는 환경이라 건너뜀).

## 결정
- 사용자(메인 세션 지시): OFFICIAL 달은 ASOS 일자료로 다시 계산, 원본이 없으면 건드리지 않고 셈, 이 PC DB에는 적용하지 않음.

## 하지 않은 것 · 보류한 것과 이유
- 이 PC DB의 덮인 1,475개월을 되돌리지 않음(지시: 적용하지 않음). 되돌리는 길: 이 코드가 들어간 뒤 `apply-standard`(또는 다음 판 올림)가 그 달들을 ASOS 원본 값으로 바꿈 — 위 "새 방법" 1,475개월이 바로 그것. 언제 돌릴지는 메인 세션이 정함.
- `check-standard`의 도일 점검은 전주 표(`weather_monthly_observations`)만 봄. 지역 ASOS 달이 원본과 맞는지 세는 점검은 넣지 않음(따로 할 일).
- 화면 · 발표 숫자 바뀜 없음(DB 값 그대로).
