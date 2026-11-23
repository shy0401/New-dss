# 문서 길잡이

`docs/`에 문서가 많아 무엇을 먼저 볼지 정리한 색인입니다(2026-11-24). 문서는 지우거나 옮기지 않았습니다. 날짜가 붙은 문서는 그때의 기록(경과)이라, 숫자가 지금과 다를 수 있습니다. **지금 숫자 · 규칙은 (가)의 문서가 기준**입니다.

## 무엇을 하려면 → 어느 문서

| 하려는 일 | 먼저 볼 문서 |
|---|---|
| 자료를 모으거나 계산 · 보고서 규칙을 확인 | [공통 데이터 기준](DATA_STANDARD.md) (0절은 매번) |
| 최근에 무엇이 바뀌었는지 | [작업 기록 목록](records/README.md) |
| 발표 자료에 쓸 숫자 · 표현 · 한계 | [발표 반영 목록](presentation/PRESENTATION_FACTS.md) |
| 감축 수단의 값과 근거 | [감축 지표와 근거](REDUCTION_INDICATORS.md) · 근거 스크립트 [scripts/reduction_evidence](../scripts/reduction_evidence/README.md) |
| 결과를 읽을 때 조심할 점 | [알려진 한계](LIMITATIONS.md) · [정확도 · 신뢰도](ACCURACY.md) |
| 화면 사용법 | [사용자 매뉴얼](USER_MANUAL.md) · [사용 안내](USAGE.md) · [5분 시연](DEMO_SCRIPT.md) |
| 팀원 PC에서 똑같이 띄우기 · 자료 받기 | [팀원 PC 재현](TEAM_SETUP.md) · [Git 작업 방식](GIT_WORKFLOW.md) |
| 지역별로 어떤 자료가 있는지 | [자료 범위와 완성도](DATA_COVERAGE.md) |

## (가) 지금 기준 (규칙 · 방법)
- [공통 데이터 기준](DATA_STANDARD.md) — 수집 · 계산 · 보고서 기준의 유일한 원본(계수 · 기준온도 · 임계값 5절)
- [감축 지표와 근거](REDUCTION_INDICATORS.md) — 감축 수단 14개의 지표 · 범위 · 근거(사다리 규칙은 기준 문서 5.15)
- [운영탄소 계산](CARBON_METHOD.md) — 전력 · 가스 계수의 근거와 경과(지금 값은 기준 문서 5.4 · 5.5)
- [지역 개발 시뮬레이션 (/area)](AREA_SIMULATION.md) · [시나리오와 최적화](SIMULATION_METHOD.md) · [모델 방법과 검증](MODEL_VALIDATION.md)
- [알려진 한계](LIMITATIONS.md) · [정확도 · 신뢰도 평가](ACCURACY.md)
- [팀 데이터셋 연동](TEAM_DATASET.md) — 팀 변화 모델(urban-carbon) 입력과 쓰임
- [구성과 데이터 흐름](ARCHITECTURE.md) · [데이터 사전](DATA_DICTIONARY.md) · [입력 → 산출 명세](DATA_TO_OUTPUT_SPEC.md) · [구현 요구사항](SRS.md)

## (나) 사용 · 설치 · 운영
- [사용자 매뉴얼](USER_MANUAL.md)(PDF: [manual/](manual/)) · [사용 안내](USAGE.md)(발표 자료: [usage/](usage/)) · [5분 시연](DEMO_SCRIPT.md)
- [팀원 PC 재현 · 백업 · 복원](TEAM_SETUP.md) · [Git 작업 방식](GIT_WORKFLOW.md) · [무료 온라인 배포](DEPLOYMENT.md) · [실제 실행 검증](TESTING.md)
- 자료: [수집과 업로드](DATA_COLLECTION.md) · [데이터 재설정 · 수집 안내](DATA_SETUP_GUIDE.md) · [실제 데이터 출처](DATA_SOURCES.md) · [자료 범위와 완성도](DATA_COVERAGE.md) · [사람이 신청해야 하는 자료](EXTERNAL_DATA_REQUESTS.md) · [SGIS 1km 격자](SGIS_GRID.md) · [선도소프트 탄소공간지도 100m](SUNDOSOFT_KCSM100.md)
- 화면 디자인: [디자인 시스템 D안](DESIGN.md) · [적용 기록](DESIGN_APPLY_LOG.md)

## (다) 팀 · 발표
- [발표 반영 목록](presentation/PRESENTATION_FACTS.md) · 발표 자료 PDF · PPTX: [presentation/](presentation/)
- [팀원 데이터와 이 도구 비교](TEAM_DATA_COMPARISON.md) · [팀 사례 자료: 전주 두 동](TEAM_CASE_JEONJU_DONGS.md) · [팀원 작업 지시서 (2026-10)](TEAM_TASKS_2026-10.md) · 비교표 틀: [team/](team/)
- 업계 · 정부 대조: [활용 방식과 대응](INDUSTRY_USE_CASES.md) · [시뮬레이션 방식 대조](INDUSTRY_COMPARISON.md)

## (라) 경과 · 점검 기록 (그때의 기록, 숫자가 지금과 다를 수 있음)
- 작업별 기록: [records/](records/README.md) (PR 하나에 기록 하나)
- 점검 · 검토: [11-11 면담 피드백 점검 (2026-11-13)](FEEDBACK_AUDIT_2026-11-13.md) · [사용성 검토 (2026-10-13)](UX_REVIEW_2026-10-13.md) · [수집 실패 원인 (2026-09-18)](COLLECTION_FAILURE_AUDIT_2026-09-18.md) · [Phase 1 자료 점검](PHASE2_AUDIT.md)
- 결과 · 현황: [수집 · 정제 · 결과 현황 (2026-09-26)](RESULTS_2026-09-26.md) · [검증 보고서](FINAL_REPORT.md) · [구현 · API 연동 현황](PROJECT_IMPLEMENTATION_STATUS.md) · [구현 보완 결과](IMPLEMENTATION_UPDATE.md) · [진행 장부](PROGRESS.md)
- 계획 · 조사: [구현 계획](IMPLEMENTATION_PLAN.md) · [최종 Goal 로드맵 (2026-09-18)](FINAL_GOAL_ROADMAP_2026-09-18.md) · [전국 단위 적용 (2026-09-27)](NATIONWIDE.md) · [전국 분석 범위 (2026-09-29)](NATIONWIDE_DATA.md) · [100m 격자 우선순위 (2026-10-01)](GRID100_PRIORITY.md)(자료: [grid100/](grid100/)) · [자료원 조사 (2025)](SOURCE_RESEARCH.md) · [실제 접근 결과](DATA_SOURCE_DISCOVERY.md) · [주거 테스트베드 선정](TESTBED_SELECTION.md)
- AI 도구 인계 (2026-09-23): [인수인계서](CLAUDE_HANDOFF_2026-09-23.md) · [시작 프롬프트](CLAUDE_START_PROMPT_2026-09-23.md) · [디자인 프롬프트](CLAUDE_DESIGN_PROMPT_2026-09-23.md) · 작업 계획: [superpowers/plans/](superpowers/plans/)
