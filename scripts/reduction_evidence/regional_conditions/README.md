# 지역 조건표 (`backend/reference/regional_conditions_sigungu.csv`) — `regional_conditions/`

지역마다 설계 지역 구분 · 평년 도일 · 전기 · 가스의 냉난방 몫(분해) · 2025 통계를 모은 표와, 그 판정(관문 G2 · G3)을 만드는 스크립트다. 2026-11-24에 PC 실험 폴더(`project/tools/experiments/regional_adjust/`)에서 옮겼고, 같은 입력으로 다시 돌려 **결과 9개가 PC 원본과 바이트까지 같음**을 확인했다([기록](../../../docs/records/2026-11-24-pc-tools-to-repo.md)).

- 규칙 · 결과(결과를 보기 전에 적은 판정 규칙): [`../rules/regional-conditions-2026-11-20.md`](../rules/regional-conditions-2026-11-20.md), 관문 판정 기록 [지역 보정 관문](../../../docs/records/2026-11-20-regional-adjustment-gates.md)
- 자료 · 결과는 Git 밖 `data/derived/reduction_evidence/regional_conditions/`(DB에서 읽은 단지 · 지번 값 `extract/`, 분해 결과). 설계 지역 구분 · 그린투게더 표는 `data/derived/reduction_evidence/regional_guide/`(만드는 스크립트는 `../regional_guide/`)
- DB는 읽기 전용으로만 접속(`PGOPTIONS=-cdefault_transaction_read_only=on`). `extract/`와 분해 결과는 PC 밖으로 내보내지 않는다
- 파이썬: numpy가 있는 환경. Windows에서는 `-X utf8`

## 다시 만드는 차례
| 차례 | 명령 | 만드는 것 |
|---|---|---|
| 1 | `python ../regional_guide/design_zone.py` | `design_zone_sigungu.csv`(시군구 269행 → 중부1 · 중부2 · 남부 · 제주) = 저장소 표 |
| 2 | `python ../regional_guide/greentogether_parse.py` | `greentogether_apt_2025.csv`(화면에서 옮긴 글 `../regional_guide/inputs/`) |
| 3 | `q_weather_normal.sql`을 psql로 | `weather_normal_2015_2025.txt`(지역 코드별 평년 도일) |
| 4 | `python extract.py` | `extract/`(기상 · K-apt 전기 · 단지 · 연결 지번의 가스 월 자료). 연결 표는 `../link/`의 결과(`data/derived/reduction_evidence/link/`)를 읽기만 |
| 5 | `python decompose.py --selftest` → `python decompose.py` | 분해 v1: `decomp_summary.json`, `decomp_elec_units.csv`, `decomp_gas_units.csv` |
| 6 | `python diag_gas.py` | `diag_gas.json`(가스가 G3을 못 넘은 까닭) |
| 7 | `python decompose_v2.py` | 가스 분해 v2: `decomp_summary_v2.json`, `decomp_gas_units_v2.csv` |
| 8 | `python build_conditions.py` | `regional_conditions_sigungu.csv`(23개 시군구) = 저장소 표 |
| 9 | `python g2_rejudge.py` | `g2_rejudge.json`(새 지표 −13.7%로 G2 재판정) |
| — | `python kogas_compare.py` | `kogas_compare.json`(가스공사 도일 파일과의 비 · 상관, 원본 `data/raw/kogas_degree_days/2026-11-20/`) |

- 손으로 옮긴 표(저장소): `inputs/standard_baseline_residential.csv` · `standard_baseline_factors.csv`(그린투게더 표준베이스라인 화면 · 자료 설명, 규칙 문서의 점검에 씀). 공동주택 열관류율은 저장소 표 `backend/reference/design_zone_uvalue_apartment.csv`가 원본
- `q_toe_check2.sql`: 2025 통계 TOE 환산 점검용 질의(규칙 문서 참고)
- 확인(2026-11-24, 11-20 입력 그대로): 차례 5~9와 kogas의 결과 9개(`decomp_*` 5개, `diag_gas.json`, `g2_rejudge.json`, `kogas_compare.json`, `regional_conditions_sigungu.csv`)가 PC 원본과 같음. 차례 1 · 3 · 4는 DB를 읽으므로 지금 다시 돌리면 그 뒤 바뀐 DB를 따름
