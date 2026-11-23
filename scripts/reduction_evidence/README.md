# 감축 근거 · 지역 조건 표를 만드는 스크립트

`backend/reference/`의 감축 근거 · 지역 조건 표와 감축 지표의 숫자(예: 단열 · 창호 −13.7%)를 다시 만드는 스크립트다. 2026-11-23에 PC 실험 폴더에서 옮겼고, 옮긴 뒤 같은 입력으로 다시 돌려 **결과 파일이 PC 원본과 바이트까지 같음**을 확인했다([기록](../../docs/records/2026-11-23-reduction-evidence-scripts.md)).

- 규칙(결과를 보기 전에 적은 판정 · 계산 규칙)은 `rules/`에 있다. 스크립트는 규칙을 바꾸지 않는다
- DB 내보내기 · 계산 결과는 자료라서 Git에 올리지 않는다: `data/derived/reduction_evidence/<단계>/`(또는 환경 변수 `REDUCTION_EVIDENCE_DATA`) — `_paths.py`
- 손으로 정리해 저장소에 두는 입력: 원문 대조표(`evidence_table/source_checks.csv` · `fulltext_checks*.csv`), 문헌 보강 행(`rows_*.csv` · `cooling_rows.csv`), 지자체 계획 옮겨 적은 표(`local_plans/inputs/`), 그린투게더 화면 옮겨 적은 글(`regional_guide/inputs/`)
- 파이썬: 저장소 `urban-carbon` 가상환경 또는 pandas 없는 표준 파이썬(이 스크립트들은 표준 라이브러리만 씀). 한글 출력 때문에 Windows에서는 `-X utf8`을 권함

## 1. 단열 · 창호 짝 비교 (−13.7%, 117쌍) — `link/` → `pair/`
1. DB 내보내기(읽기만). `W=data/derived/reduction_evidence/link/work`
   ```bash
   for q in e1_parcels e2_complexes e3_point e4_register e6_kapt_year; do
     docker exec -i carbon-urban-dss-postgres-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q' < scripts/reduction_evidence/link/$q.sql > $W/$q.csv
   done
   ```
2. `python scripts/reduction_evidence/link/build_link_a.py` → `work/link_a.csv` · `linked_keys.txt`(단지 ↔ 건축HUB 지번 후보, 규칙 `rules/complex-parcel-link-2026-11-20.md` 1~2절)
3. `e5_parcel_year.sql.tmpl`의 `{KEYS}`를 `linked_keys.txt`의 값으로 채워(한 줄 = `(sgg,bjd,lt,bun,ji)`) 같은 방법으로 `work/e5_parcel_year.csv`를 내보냄
4. `python scripts/reduction_evidence/link/build_link_b.py` → `link_groups.csv` · `link_group_year.csv` · `link_summary.json`
5. `pair/e7_areas.sql`을 내보내 `data/derived/reduction_evidence/pair/areas.csv`, 그다음 `python scripts/reduction_evidence/pair/pair_compare.py` → `pairs.csv` · `pair_result.json`(관문 G1, 규칙 `rules/pair-comparison-rerun-2026-11-20.md`). `posthoc_*.py`는 결과를 본 뒤의 보조 계산(관문에 쓰지 않음)
- 확인(2026-11-23): 11-20에 내보낸 같은 CSV로 다시 돌린 `pairs.csv` · `pair_result.json`이 원본과 같음. **DB가 그 뒤 바뀌어(지역 추가 등) 지금 다시 내보내면 짝이 달라질 수 있음** — 다시 내보내 돌리면 기록에 전후를 적음

## 2. 감축 근거표 (`backend/reference/reduction_evidence.csv`, 653행) — `evidence_table/`
1. 입력: 팀 데이터셋 감축전략 효과 조사표의 '근거 행' 시트를 CSV로 → `data/derived/reduction_evidence/evidence_table/work/근거_행.csv`(543행), 영국 NEED 2026 표 내보내기 → `.../evidence_table/need/`(받은 원본은 `data/raw`, CSV로 내보낸 방법 확인 필요)
2. `python .../evidence_table/build_evidence_table.py` → `evidence_table.csv`(543행, 규칙 `rules/reduction-evidence-table-2026-11-20.md` 1~6절)
3. `python .../evidence_table/build_added.py` → `evidence_added.csv` · `evidence_table_all.csv`(610행: NEED · 이 도구의 짝 비교(`pair/pair_result.json`) · 인증 단지 비교 · 문헌 보강)
4. `python .../evidence_table/merge_cooling.py <evidence_table_all.csv> evidence_table/cooling_rows.csv <evidence_table_all_v2.csv>` → 645행
5. 저장소 표 = 4의 결과 + 기록에 적은 칸 고침(도구 지표 행 22칸 [11-21 기록](../../docs/records/2026-11-21-evidence-table-tool-rows.md), 비고 15칸 [11-22 기록](../../docs/records/2026-11-22-evidence-audit.md))
6. 2026-11-24 팀 감축 방안 조사 8행(T-001~T-008): `python scripts/reduction_evidence/evidence_table/append_team_2026_11_24.py` — `rows_team_2026-11-24.csv`(원문 대조한 값만)를 표 끝에 덧붙임(한 번만, 기존 행은 바이트 그대로). [기록](../../docs/records/2026-11-24-team-reduction-evidence.md)
- 인증 단지 비교(`kea/`, 규칙 `rules/kea-grade-real-use-rule-2026-11-20.md`)의 숫자는 `build_added.py`에 값으로 들어 있음. `kea/`는 그 값을 만든 스크립트(이번에 다시 돌려 확인하지 않음)

## 3. 지자체 계획 건물 과제 (`backend/reference/local_plans_building.csv`) — `local_plans/`
1. `python .../local_plans/merge_plans.py` → `local_plans_building.csv` · `changes_all.csv` · 요약(입력 `local_plans/inputs/plans_*.csv` · `inputs/recheck/`)
2. `python .../local_plans/normalize_units.py <local_plans_building.csv> <out.csv>` → 단위 맞춤 열이 붙은 저장소 표
- `transcription/`: 원문 PDF(`data/raw/local_carbon_plans/<코드>/2026-11-20/plan.pdf`)에서 옮겨 적은 스크립트. 앞선 표를 다시 읽으며 여러 번 대조한 작업이라 처음부터 다시 돌리는 순서가 없음 → 기록용으로 보관(입력 표 `inputs/`가 그 결과). 규칙 `rules/local-carbon-plans-building-2026-11-20.md`

## 4. 지역 가이드 (`apartment_energy_stats_2025.csv` · `regional_climate_guide.csv`) — `regional_guide/`
1. `python .../regional_guide/greentogether_parse.py` → `greentogether_apt_2025.csv`(그린투게더 2025 아파트 화면을 옮겨 적은 글 `inputs/`, 설계 지역 구분 `design_zone.py`)
2. `python .../regional_guide/build_heat_stats.py <greentogether_apt_2025.csv> <apartment_energy_stats_2025.csv>`
3. `python .../regional_guide/fetch_kma_normals.py <out>`(기상청 평년값, 이미 `data/raw/kma_normals/2026-11-20`에 있음) → `python .../regional_guide/build_guide.py data/raw/kma_normals/2026-11-20 backend/reference <out>` → `regional_climate_guide.csv`

## 확인한 것 (2026-11-23, PC의 11-20 입력으로 다시 돌림, sha256 비교)
| 결과 | 같음 |
|---|---|
| `link/` 8개 파일, `pair/pairs.csv` · `pair_result.json` | 예 |
| `evidence_table.csv` · `evidence_added.csv` · `evidence_table_all.csv` · `evidence_table_all_v2.csv` | 예 |
| `local_plans_building.csv` · 단위 맞춘 표(= 저장소 표) | 예 |
| `apartment_energy_stats_2025.csv` · `regional_climate_guide.csv`(= 저장소 표) | 예 |
