# 2026-11-23 감축 근거 스크립트를 저장소로 옮김 (`scripts/reduction_evidence/`)
- 관련: 새 `scripts/reduction_evidence/`(짝 비교 `link/` · `pair/`, 감축 근거표 `evidence_table/`, 인증 단지 비교 `kea/`, 지자체 계획 `local_plans/`, 지역 가이드 `regional_guide/`, 규칙 `rules/`, 경로 `_paths.py`, `README.md`), `backend/reference/README.md`(만든 곳 칸), `docs/presentation/PRESENTATION_FACTS.md` 3절
- 사용자: "근거 스크립트 scripts로 옮기는 작업 진행해" — 팀원이 GitHub만으로 감축 근거 숫자를 다시 계산 · 확인할 수 있게

## 왜
- 저장소 근거표(`backend/reference/`)와 감축 지표(단열 · 창호 −13.7%)를 만든 스크립트가 이 PC 실험 폴더에만 있어, 팀원이 숫자를 다시 만들거나 규칙을 볼 수 없었음([현황 기록](2026-11-23-status-new-plan-acceptance.md) 7절, [단열 · 창호 기록](2026-11-20-envelope-step-rerun.md) "짝 비교 스크립트는 아직 저장소 밖")

## 무엇을 옮겼나
- 스크립트 · SQL · 결과를 보기 전에 적은 규칙 문서 5개 · 손으로 정리한 입력(원문 대조표, 문헌 보강 행, 냉방 보강 행, 지자체 계획 옮겨 적은 표 1.9 MB, 그린투게더 화면 옮겨 적은 글)
- 바꾼 것은 경로뿐: DB 내보내기 · 결과는 Git 밖 `data/derived/reduction_evidence/<단계>/`에 씀(`_paths.py`). 생성된 SQL(지번 1,833개 값 목록)은 틀 `e5_parcel_year.sql.tmpl`(`{KEYS}`)로 바꿈(값을 채우면 원래 파일과 같음을 확인). 콘솔 출력은 UTF-8로 고정. 결과 표 안에 글자로 들어가는 문서 경로(근거표 출처 칸)는 그대로 둠
- 옮기지 않은 것: 탐색 · 출력용 일회 스크립트(look · show · diag · count 등), 세션 메모

## 확인 (PC의 11-20 입력으로 다시 돌려 sha256 비교)
| 묶음 | 결과 파일 | PC 원본과 |
|---|---|---|
| 짝 비교 | 연결 표 8개, `pairs.csv`, `pair_result.json`(117쌍, 중앙 −13.7%) | 같음 |
| 감축 근거표 | 543행 → 보강 610행 → 냉방 645행(4개 파일) | 같음 |
| 지자체 계획 | 합친 표, 단위 맞춘 표 | 같음(= 저장소 표) |
| 지역 가이드 | `apartment_energy_stats_2025.csv` · `regional_climate_guide.csv` | 같음(= 저장소 표) |
- 감축 근거표는 스크립트 결과(645행)에 11-21 · 11-22 기록의 칸 고침(도구 지표 행 22칸 · 비고 15칸)을 더한 것이 저장소 표(README 2절에 적음)
- DB 내보내기 명령(README 1절)은 `e3_point.sql`로 돌려 열이 11-20 내보내기와 같음을 확인. 지금 DB로 다시 내보내면 그 뒤 추가된 지역 때문에 짝이 달라질 수 있음(다시 돌리면 기록)
- 인증 단지 비교(`kea/`)는 이번에 다시 돌리지 않음(근거표의 해당 숫자는 `build_added.py` 안의 값)

## 남은 것
- 영국 NEED 표를 CSV로 내보낸 방법(확인 필요)
- 지자체 계획은 옮겨 적은 표가 입력(처음부터 다시 옮겨 적는 순서는 없음)
