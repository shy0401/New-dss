import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MeasuresPanel } from './AreaWorkflow';
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
