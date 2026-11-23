import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MeasuresPanel, TargetBases } from './AreaWorkflow';
import { NO_MEASURES, type EffortResult } from '../../lib/area';

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
    expect(links).toHaveTextContent('지표만: 가스 −13.7%');
    expect(links).toHaveTextContent('86.7%가 지역난방');
  });
});
