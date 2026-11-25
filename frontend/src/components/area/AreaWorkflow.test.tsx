import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { AREA_STEPS, AreaSummaryBar, Combinations, MeasuresPanel, TargetBases } from './AreaWorkflow';
import { NO_MEASURES, type EffortResult } from '../../lib/area';

describe('작업 단계 (U3 S5, 설계 6.1)', () => {
  it('구역 → 계획 넣기 → 결과 → 감축 → 배치·상한(선택) → 보고서 여섯 단계를 순서대로 보인다', () => {
    expect(AREA_STEPS.map((s) => s.id)).toEqual(['area-step-area', 'area-step-plan', 'area-step-result', 'area-step-measures', 'area-step-site', 'area-step-report']);
    render(<AreaSummaryBar analysis={null} running={false} bench={null} />);
    const links = screen.getByRole('navigation', { name: '작업 단계' }).querySelectorAll('a');
    expect([...links].map((a) => a.textContent)).toEqual(['1구역 고르기', '2계획 넣기', '3결과', '4감축 방안', '5배치·상한 (선택)', '6보고서']);
  });
});

describe('MeasuresPanel 구체적 감축 방안', () => {
  it('발전량 근거가 없어 태양광 단계가 없어도 칸을 지우지 않고 상쇄할 전력량을 적는다(2026-11-20 점검 A)', () => {
    const effort = {
      available: true, already_met: false, factor_kgco2eq_per_kwh: 0.5, new_load_kwh: 100000, baseline_kwh: 2000000, pv_yield: null,
      recommended: { kind: 'RECOMMENDED', new_efficiency_pct: 0, existing_efficiency_pct: 0, pv_kw: 0, new_kwh: 0, existing_kwh: 0, pv_kwh: 0, pv_counted: false,
        total_kwh: 0, total_kgco2eq: 0, required_kgco2eq: 225000, gap_kgco2eq: 225000, met: false, share_pct: 0, basis: '식', steps: [], roof_m2: null,
        offset_kwh: 450000, plan_roof_m2: 1000, plan_roof_basis: 'floor_area', roof_over_plan: false },
    } as unknown as EffortResult;
    render(<MeasuresPanel effort={effort} measures={NO_MEASURES} setMeasures={() => undefined} />);
    const rec = screen.getByTestId('area-recommended');
    expect(rec).toHaveTextContent(/발전량 근거가 없어 남는 450,000\s?kWh는 재생에너지 상쇄량으로 적습니다/);
    expect(screen.queryByRole('button', { name: /태양광 값을 아래 칸에 넣기/ })).toBeNull();   // 넣을 태양광 값이 없음
    expect(screen.queryByTestId('area-roof-warning')).toBeNull();
  });
});

describe('TargetBases (U4)', () => {
  const onsite = (over: Partial<import('../../lib/area').OnsitePlan>) => ({ onsite_status: 'PARTIAL' as const, pv_needed_kw: 1170, pv_kw: 150, pv_kgco2eq: 75510.9,
    roof_limit_m2: 1500, roof_limit_kw: 150, roof_limit_basis: 'footprint' as const, roof_limit_basis_label: '계획 건축면적 합(동 수 × 동당 건축면적)',
    plan_roof_m2: 2500, capped: true, covered_pct: 12.9, remaining_kgco2eq: 509180.5, remaining_kwh: 1175936.5, remaining_offsite_pv_kw: 1011.5,
    remaining_is_minimum: false, margin_kgco2eq: null, offset_kwh: null, ...over });
  const effort = {
    available: true, baseline_year: 2025, measure_links_note: '난방 구성은 지역 전체 공동주택 단지 기준입니다(구역 단지만 본 값이 아님)',
    targets: [
      { key: 'area_total' as const, label: '구역 전체 40% 목표', data_class: 'SCENARIO' as const, net_added_kwh: null, net_added_kgco2eq: null, required_reduction_kgco2eq: 2529315.0, existing_share_kgco2eq: 1944623.6, already_met: false, recommended: onsite({ pv_needed_kw: 5030, remaining_kgco2eq: 2453804.1 }) },
      { key: 'plan_added' as const, label: '개발 증가분 상쇄', data_class: 'SCENARIO' as const, net_added_kwh: 1350326.6, net_added_kgco2eq: 584691.4, required_reduction_kgco2eq: 584691.4, existing_share_kgco2eq: null, already_met: false, recommended: onsite({}) },
    ],
    measure_links: [
      { target: 'plan_added' as const, key: 'rooftop_pv', title: '지붕 태양광', attach_to: ['pv_onsite'], value_status: 'QUANTIFIED' as const, value_kgco2eq: 75510.9, no_value_reason: null, indicator_text: '옥상의 60%', evidence_label: '가정', n: null, group_kind: '계획 수단', condition_text: null },
      { target: 'plan_added' as const, key: 'envelope', title: '단열·창호 기준 강화', attach_to: ['remaining_new'], value_status: 'INDICATOR_ONLY' as const, value_kgco2eq: null, no_value_reason: '가스 지표라 이 계산에는 값이 없습니다', indicator_text: '가스 −13.7%', evidence_label: '실측', n: '국내 117쌍', group_kind: '계획 수단', condition_text: '이 지역 공동주택 세대의 86.7%가 지역난방입니다' },
    ],
  };

  it('shows the plan\'s own increase first, the roof limit and the remaining amount, never adding the two bases', () => {
    render(<TargetBases effort={effort as never} />);
    const box = screen.getByTestId('area-target-bases');
    const rows = box.querySelectorAll('[data-testid^="area-target-plan_added"], [data-testid^="area-target-area_total"]');
    expect(rows[0].getAttribute('data-testid')).toBe('area-target-plan_added');
    expect(screen.getByTestId('area-target-plan_added')).toHaveTextContent('584.7');
    expect(screen.getByTestId('area-target-plan_added-onsite')).toHaveTextContent(/계획 지붕 태양광 150(\.0)?\s?kW로 12\.9\s?% — 남는 양 509\.2/);
    expect(screen.getByTestId('area-target-area_total')).toHaveTextContent('기존 건물 몫 1,944.6');
    expect(box).toHaveTextContent('서로 더하지 않음');
    expect(box).toHaveTextContent('지역 전체 공동주택 단지 기준');
  });

  it('says "not confirmed" for an upper-bound roof and lists measures with a value only on the PV line', () => {
    const upper = { ...effort, targets: [{ ...effort.targets[1], recommended: onsite({ onsite_status: 'UPPER_BOUND_ONLY', capped: false, remaining_kgco2eq: null, pv_kw: 1170 }) }] };
    render(<TargetBases effort={upper as never} />);
    expect(screen.getByTestId('area-target-plan_added-onsite')).toHaveTextContent('층수를 넣어야 확정됩니다');
    const links = screen.getByText(/쓸 수 있는 수단 2개/).closest('details') as HTMLElement;
    expect(links).toHaveTextContent('지붕 태양광');
    expect(links).toHaveTextContent('지표: 가스 −13.7%');
    expect(links).toHaveTextContent('86.7%가 지역난방');
  });
});


describe('감축 제안 수준 · 태양광 세 수준 · 추정 · 상쇄 · 조합 (계획 v3 H, 2026-11-25)', () => {
  const base = { available: true, baseline_year: 2025, targets: [
    { key: 'plan_added' as const, label: '개발 증가분 상쇄', data_class: 'SCENARIO' as const, net_added_kwh: 1, net_added_kgco2eq: 1603344.8, required_reduction_kgco2eq: 1603344.8,
      existing_share_kgco2eq: null, already_met: false, recommended: { onsite_status: 'PARTIAL', pv_kw: 240, pv_kgco2eq: 124693.6, remaining_kgco2eq: 1478651.2, capped: true } }] };
  const level = (kw: [number, number], kg: [number, number], src: string) => ({ data_class: 'ESTIMATED', source_type: src, basis: 'b', kw_range: kw, kgco2eq_range: kg, capped: true, reason: null });
  const links = [
    { target: 'plan_added', key: 'rooftop_pv', title: '지붕 태양광', attach_to: ['pv_onsite'], value_status: 'QUANTIFIED', value_kgco2eq: 124693.6, no_value_reason: null,
      indicator_text: '옥상의 60%', evidence_label: '가정', n: null, group_kind: '계획 수단', condition_text: null, level: 'VALUE',
      pv_levels: { certified: level([120, 240], [62346.8, 124693.6], '공식 자료'), cases: level([78, 240], [40525.4, 124693.6], '기사'), region_rule: null, households: 600 } },
    { target: 'plan_added', key: 'envelope', title: '단열·창호 기준 강화', attach_to: ['remaining_new'], value_status: 'INDICATOR_ONLY', value_kgco2eq: null,
      no_value_reason: '값에는 곱하지 않고 추정 범위만 따로', indicator_text: '가스 −13.7%', evidence_label: '실측', n: '국내 117쌍', group_kind: '계획 수단', condition_text: null, level: 'RANGE',
      estimate: { data_class: 'ESTIMATED', kgco2eq_range: [54922.5, 96955.1], chain: ['신축 주거 연면적 60,000 m²', '× 9.8~17.3%'], basis: '117쌍 짝 비교', condition: '2025-06-30 이후 신축은 일부 추가 감축 아님', reason: null } },
    { target: 'plan_added', key: 'greenery', title: '녹지·조경 흡수(상쇄)', attach_to: ['remaining_new'], value_status: 'OFFSET', value_kgco2eq: null, no_value_reason: 'x',
      indicator_text: '녹지 1 m²에 연 1.0 kgCO2', evidence_label: '가정', n: null, group_kind: '계획 수단', condition_text: null, level: 'VALUE',
      offset_kgco2: 12000, offset_range_kgco2: [10560, 19080], offset_text: '녹지 12,000 m² × 연 1.0 kgCO2/m² — 상쇄' },
    { target: 'plan_added', key: 'operation', title: '에너지 절약 운영', attach_to: ['remaining_new'], value_status: 'INDICATOR_ONLY', value_kgco2eq: null, no_value_reason: '지표만 있는 수단입니다',
      indicator_text: '전력 −4.8%', evidence_label: '실측', n: null, group_kind: '계획 수단', condition_text: null, level: 'INDICATOR', why: ['지자체 계획 과제 3개'] },
  ];

  it('tags each line with its level, shows the three PV levels, the estimate with its basis and the offset apart', () => {
    render(<TargetBases effort={{ ...base, measure_links: links } as never} />);
    const box = screen.getByText(/쓸 수 있는 수단 4개/).closest('details') as HTMLElement;
    expect(box).toHaveTextContent('서로 더하지 않음');
    expect(screen.getByTestId('area-pv-levels')).toHaveTextContent('인증 수준');
    expect(screen.getByTestId('area-pv-levels')).toHaveTextContent('기사');
    expect(screen.getByTestId('area-pv-levels')).toHaveTextContent('세 수준은 더하지 않아요');
    expect(box).toHaveTextContent('추정 범위');
    expect(box).toHaveTextContent(/54\.9~97\.0 tCO2eq\/년 \(추정\)/);
    expect(box).toHaveTextContent('근거와 계산');
    expect(box).toHaveTextContent('2025-06-30 이후 신축은 일부 추가 감축 아님');
    const greenLi = [...box.querySelectorAll('li')].find((li) => li.textContent?.includes('녹지·조경 흡수'))!;
    expect(greenLi.querySelector('.status-tag')?.textContent).toBe('상쇄');
    expect(greenLi).toHaveTextContent(/12\.0 tCO2\/년 흡수/);
    const envLi = [...box.querySelectorAll('li')].find((li) => li.textContent?.includes('단열·창호'))!;
    expect(envLi.querySelector('.status-tag')?.textContent).toBe('추정 범위');
    const pvTable = screen.getByTestId('area-pv-levels');
    expect(pvTable.querySelectorAll('th[scope="col"]').length).toBe(4);
    expect([...pvTable.querySelectorAll('tbody tr')].filter((tr) => tr.textContent?.includes('(추정)')).length).toBe(2);   // 인증 · 사례 수준만
    expect(box).toHaveTextContent('이 지역: 지자체 계획 과제 3개');
  });

  it('shows combinations A · B · C with the value and the estimates in separate columns', () => {
    const combos = ['roof_max', 'certified', 'cases'].map((lv, i) => ({ key: 'ABC'[i], pv_level: lv, need_kgco2eq: 1603344.8,
      pv: i === 0 ? { data_class: 'SCENARIO', kgco2eq: 124693.6 } : { data_class: 'ESTIMATED', kgco2eq_range: [62346.8, 124693.6] },
      after_pv: i === 0 ? { data_class: 'SCENARIO', kgco2eq: 1478651.2, covered: false, at_least: false }
        : { data_class: 'ESTIMATED', kgco2eq_range: [1478651.2, 1540998.0], covered: 'no', margin_kgco2eq_range: null },
      after_estimates: { data_class: 'ESTIMATED', kgco2eq_range: [1478561.3, 1478598.0], covered: 'no', margin_kgco2eq_range: null },
      electricity_estimates: [], gas_estimates: [{ key: 'envelope', title: '단열·창호 기준 강화(가스)', kgco2eq_range: [54922.5, 96955.1] }],
      co2_estimates: [{ key: 'elevator_regeneration', title: '승강기 회생제동', kgco2_range: [4105.3, 16132.1] }],
      indicators: [{ key: 'operation', title: '에너지 절약 운영', why: ['지자체 계획 과제 3개'] }] }));
    render(<Combinations effort={{ ...base, combinations: combos } as never} />);
    const box = screen.getByTestId('area-combinations');
    expect(box).toHaveTextContent('A 지붕 최대');
    expect(box).toHaveTextContent('B 인증 수준');
    expect(box).toHaveTextContent('1,478.7');
    expect(box).toHaveTextContent('(추정)');
    expect(box).toHaveTextContent('빼지 않고 나란히');
    expect(box).toHaveTextContent('4.1~16.1 tCO2');
    expect(box).toHaveTextContent('에너지 절약 운영(지자체 계획 과제 3개)');
  });

  it('gives the reason when there are no combinations', () => {
    render(<Combinations effort={{ ...base, combinations: null, combinations_reason: '개발 증가분이 없어 조합을 만들지 않음' } as never} />);
    expect(screen.getByText('개발 증가분이 없어 조합을 만들지 않음')).toBeInTheDocument();
  });
});
