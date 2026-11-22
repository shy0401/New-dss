# 2026-11-23 감축 추천을 쓸 수 있는 답으로: 목표 기준 둘 · 지붕 한도까지만 태양광 · 남는 양 · 수단 연결
- 관련: `backend/app/area.py`(`target_bases`, `onsite_plan`, `roof_limit`, `recommended_mix`, `_effort_result`, `area_facts`, `analyze`), `backend/app/reduction_measures.py`(`applicable_measures`), `backend/app/area_report.py`(낡은 문구), `docs/DATA_STANDARD.md` 5.9 · 5.15 · 판 1.54, `docs/REDUCTION_INDICATORS.md`, `docs/AREA_SIMULATION.md`, 시험 `tests/test_u4_targets.py`
- 사용자: 계획 추천안대로(사용자 활용 단계 U4, D4 "나": "개발로 늘어난 만큼 상쇄"를 함께 보임). 설계: Fable high 검토 문서(이 PC의 `project/working/methods/u4-reduction-design-2026-11-23.md`)

## 왜
- 지역 화면 자동 방안이 "구역 전체(기존 건물 포함) 40%"만 보고, 남는 양을 모두 태양광으로 채웠음. 점검한 3구역(계획 50,000 m²) 모두 필요 옥상이 계획 연면적보다 큼(성남 5,030 kW · 50,300 m², 전주 29,270 kW, 강남 13,920 kW) → 경고만 하고 용량은 그대로 추천, "신축만 432.6% 필요 → 불가"
- 계획 담당자가 쓸 답이 없음. 지역 화면 한도는 건축면적 100%와 견줬고(3D 계획안은 60%), 근거표 645행은 추천과 이어지지 않았음

## 무엇을 바꿨나 (정할 것 Q1~Q8은 모두 설계 문서의 추천안 "가"로)
- **목표 기준 둘**(`effort.targets`): `plan_added` 개발 증가분 = (신축 − 철거 부하) × 계수(목표 %와 무관), `area_total` 구역 전체 = 증가분 + 기존 건물 몫(기준 배출 × 목표 %). 더하지 않고 나란히. 철거가 더 크면 필요 감축량은 비우고 '늘지 않음'
- **지붕 한도까지만**: 한도 = 계획 건축면적 합 × 0.60 ÷ 10 m²/kW(`reduction_plan.roof_pv`, 3D와 같은 규칙). 건축면적 합 = 동 수 × 동당 건축면적, 연면적 + 층수면 연면적 ÷ 층수(새로 받음), 연면적만이면 연면적이 위 한계(확정 아님). 넘는 몫은 남는 양(kgCO2eq · kWh · 구역 밖 태양광 kW 상당), 다 채우면 남는 양 NULL + 여유. 음수 · 0 없음
- 상태: `MET` · `PARTIAL` · `UPPER_BOUND_ONLY`(연면적만, 위 한계 안) · `NO_YIELD` · `NO_INCREASE`. B는 % 로 '가능'을 판정하지 않음
- 기존 `recommended` 필드: 이름 그대로, **`pv_kw`의 뜻이 '한도 안 용량'으로 바뀜**, `roof_over_plan` = 필요 용량이 한도를 넘음. 남는 양 필드 더함
- **수단 연결**(`effort.measure_links`): 추천 줄(계획 지붕 태양광 · 남는 양 신축 · 남는 양 기존 건물)마다 쓸 수 있는 운영 단계 수단과 근거 종류 · 근거표 요약. 값이 있는 것은 태양광 줄뿐. 기존 건물 수단은 구역 전체 기준에만, 지역난방 제어는 지역난방 세대가 있을 때만, 운영은 '계획 단계 밖'. 난방 구성은 지역 전체 단지 기준(구역 단지 아님)
- 새 근거 문장: `effort_added` · `effort_added_none` · `effort_split` · `effort_rec_added`, `effort_rec`에 한도 · 남는 양
- 계수 · 상수 새로 만든 것 없음(0.60 · 10 m²/kW · 10 kW 올림은 그대로)

## 숫자
- 전후 표(READY 56곳 같은 계획): 아래 '확인'에 채움

## 확인
- 시험: `test_u4_targets.py`(증가분이 목표 %와 무관, 구역 전체 = 증가분 + 기존 몫, 늘지 않음 = NULL, 한도 안 · 태양광 + 남는 양 = 필요량, 남는 양 음수 · 0 없음, 위 한계는 '가능' 아님, 발전량 없음, 기존 필드 유지, 수단 연결 조건, 근거표 행은 요약 그대로, 기준 문서 숫자 = 상수)

## 남은 것
- 화면(승인 뒤 Draft): 두 기준 나란히, 남는 양 줄, '넣기' 버튼이 한도 안 값, 수단 · 근거 표시, 연면적 입력에 층수 칸
- 지역 보고서 5절에 두 기준 표(지금은 근거 문장으로만 들어감)
- B의 가스 증가분 줄(Q5 나)은 U3 묶음 응답 때
