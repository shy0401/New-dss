# 2026-11-24 PC에만 있던 도구를 저장소로: 지역 조건표 · 팀 모델 기상 · 지역 우선순위 · 지역 ASOS 덮어쓰기
- 관련: 새 `scripts/reduction_evidence/regional_conditions/`, `scripts/team_model_weather/`, `scripts/region_priority/`, `scripts/region_weather/`, 규칙 문서 2개(`scripts/reduction_evidence/rules/regional-conditions-2026-11-20.md` · `regional-climate-guide-2026-11-20.md`), 경로만 고친 곳(`docs/DATA_STANDARD.md` 2절 표 두 줄 · `docs/TEAM_DATASET.md` · `backend/reference/README.md` · `deploy/team-model/server.py` 주석 · `scripts/reduction_evidence/README.md`)
- 계기: 상태 점검(11-24)에서 "저장소 표 · DB 값을 만든 도구가 PC에만 있어 팀원이 다시 만들 수 없음"을 높은 항목으로 찾음 → 후속 계획 A2(사용자 "A2 진행")

## 왜
- `backend/reference/`의 표와 팀 모델 서비스 표를 만든 스크립트가 PC 실험 폴더에만 있었다. 저장소 문서 · 주석이 그 PC 경로를 가리켜, 팀원은 숫자를 다시 만들 수도 규칙을 확인할 수도 없었다
- 원칙은 #101(감축 근거 스크립트)과 같다: 스크립트 · 손으로 옮긴 입력 · 규칙 문서는 저장소, DB에서 읽은 값과 결과는 Git 밖 `data/derived/`. 계산은 고치지 않고 경로만 바꾼다

## 무엇을 옮겼나 · 어떻게 확인했나
| 도구 | 저장소 위치 | 만드는 것 | 확인 |
|---|---|---|---|
| 지역 조건표(분해 · 관문) 9개 스크립트 + SQL 2개 | `scripts/reduction_evidence/regional_conditions/` | `regional_conditions_sigungu.csv`, 분해 · 관문 결과 | 11-20 입력 그대로 다시 돌려 결과 9개가 PC 원본과 **바이트까지 같음**(저장소 표 포함). 설계 지역 구분 · 그린투게더 정리는 이미 `regional_guide/`에 있어 그것을 씀 |
| 팀 모델 기상 2개 + 새 고르기 스크립트 · 지역 → 후보 지점 표 | `scripts/team_model_weather/` | `deploy/team-model/station_annual.csv` | 지점 고르기는 11-17에 스크립트 없이 했다. 기록된 규칙(팀 해의 완전한 해가 가장 많은 한 곳, 같으면 ASOS)을 스크립트로 쓰고, 남아 있던 후보(`data/ops/aws_annual_candidates.csv` · `asos_team.csv`)로 돌려 **62행 모두 같음**(원본은 성남 · 화성이 나중에 끝에 붙어 줄 순서만 다름). 후보 표의 기록에 없던 4곳(506 파주 · 540 고양 · 611 · 629 세종)은 지점일람표 주소로 지역을 확인 |
| 지역 우선순위 | `scripts/region_priority/` | `region_priority.csv` | 11-21 입력(`regions.txt`)은 남아 있지 않음. 지금 표에서 거꾸로 만든 입력으로 돌려 **바이트까지 같음**(스크립트 · 참고표로 같은 표가 나온다는 확인, 그날 DB 상태를 다시 만든 것은 아님) |
| 지역 ASOS 덮어쓰기 | `scripts/region_weather/asos_overlay.py` | DB 지역 기상(쓰기) | 읽기만 하는 `snap`을 저장소 위치에서 돌려 11-24 덮어쓰기 뒤 저장값과 같음 |
| 규칙 문서 2개 | `scripts/reduction_evidence/rules/` | — | 본문은 그대로, 머리에 "옮긴 위치" 한 줄. 저장소에 없는 PC 계획 문서 링크 2개는 링크를 풀고 표시 |

- 옮기지 않은 것: 탐색 · 일회 확인 스크립트(`intensity_check_*`, `acceptance_*`, `u2c_model_compare.py` 등, 기록에 결과가 남아 있음), U2-c 새 지역용 `u2c_station_annual.py`(U2-c 서비스 변경 때 함께)
- 지난 기록(`docs/records/*.md`)의 PC 경로는 그때 사실이라 고치지 않음

## 숫자
- 저장소 표 · 서비스 표 · DB 바뀜 없음(같은 결과를 다시 만든 것뿐), 계산 · 화면 그대로
- 저장소 md 상대 링크 모두 열림, 이름 점검 0건

## 남은 것
- 팀 모델 기상의 `region_stations.csv`는 11-17 판단을 옮겨 적은 것이다. 지역을 늘릴 때는 같은 규칙(지점일람표 주소 · 좌표가 그 시 안)으로 줄을 더한다
- 지역 조건표의 차례 1 · 3 · 4(DB 읽기)는 지금 DB로 돌리면 결과가 달라질 수 있다(그 뒤 자료가 늘어남)
