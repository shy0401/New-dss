import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { setAnalysisScope } from '../hooks/useAnalysisScope';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { AreaPage } from './AreaPage';

vi.mock('../components/Chart', () => ({ Chart: ({ ariaLabel }: { ariaLabel: string }) => <div role="img" aria-label={ariaLabel} /> }));
vi.mock('../components/area/AreaMap', () => ({ AreaMap: () => <div data-testid="area-map" /> }));

const carrier = { kwh: null, observed_parcels: 0, complete_parcels: 0, partial_parcels: 0, months_max: 0, by_cohort: {}, intensity_kwh_per_m2: null, intensity_area_m2: null, kwh_per_household: null, households: null };
const year = (y: number, est: number) => ({ year: y, electricity: carrier, gas: carrier, electricity_carbon_kgco2eq: null, estimated: { kwh: est, carbon_kgco2eq: est * 0.4541, basis: '연면적 × 원단위', data_class: 'ESTIMATED' } });
const analysis = {
  history: {
    years: [2018, 2019, 2020],
    area: { type: 'admin', label: '덕진구 송천1동 (행정동)', method: '행정동 경계 안', geometry: null, grid_ids: ['g1'], complex_codes: ['A'], admin_codes: ['35012650'], admin_exact: true, admin_names: ['송천1동'] },
    energy: { '2018': year(2018, 100), '2019': year(2019, 150), '2020': year(2020, 160) },
    weather: {}, population: {},
    events: { '2018': { year: 2018, complexes: 0, households: 0, gfa_m2: 0, names: [] }, '2019': { year: 2019, complexes: 1, households: 500, gfa_m2: 50000, names: ['에코시티'] }, '2020': { year: 2020, complexes: 0, households: 0, gfa_m2: 0, names: [] } },
    stock: { '2018': { year: 2018, complexes: 1, households: 300, gfa_m2: 30000, gfa_excluded: 0, unknown_approval: 0 }, '2019': { year: 2019, complexes: 2, households: 800, gfa_m2: 80000, gfa_excluded: 0, unknown_approval: 0 }, '2020': { year: 2020, complexes: 2, households: 800, gfa_m2: 80000, gfa_excluded: 0, unknown_approval: 0 } },
    factor: { electricity: 0.4541 }, factor_basis: '최신 계수 동일 적용', complexes: [], city_intensity: { year: 2025, kwh_per_m2: 30.97, area_m2: 1000, parcels: 3 },
    coverage: { energy_years: [], weather_years: [], population_years: [], grid_count: 1, complex_count: 2 },
  },
  before_after: { available: true, event_year: 2019, window: 1, before_years: [2018], after_years: [2020], event: { year: 2019, complexes: 1, households: 500, gfa_m2: 50000, names: ['에코시티'] }, metrics: { electricity: { before_total_kwh: null, after_total_kwh: null, total_change_kwh: null, total_change_pct: null, existing_before_kwh: null, existing_after_kwh: null, existing_change_pct: null, new_development_kwh: null, new_share_pct: null }, gas: {}, electricity_carbon: {}, estimated: { before_kwh: 100, after_kwh: 160, change_kwh: 60, change_pct: 60, added_gfa_m2: 50000, data_class: 'ESTIMATED', event_added_kwh: 1548500, event_change_pct: 166.7, prior_gfa_m2: 30000 } }, weather: { before_hdd: null, after_hdd: null, before_cdd: null, after_cdd: null }, population: { before: null, after: null, basis: '행정동 값' }, gaps: ['전후 기간에 12개월이 모두 관측된 전력 자료가 부족합니다 (과거 수집 필요)'] },
  effort: { available: true, baseline_year: 2020, target_pct: 40, baseline_mode: 'ESTIMATED', data_class: 'SCENARIO', intensity_kwh_per_m2: 30.97, intensity_area_m2: 80000, added_floor_area_m2: 50000, removed_floor_area_m2: 0, baseline_kwh: 2477600, baseline_kgco2eq: 1125078.2, new_load_kwh: 1548500, bau_kwh: 4026100, bau_kgco2eq: 1828252, target_kgco2eq: 675046.9, required_reduction_kgco2eq: 1153205.1, already_met: false, feasible_with_new_only: false, options: { new_only_efficiency_pct: 164, all_buildings_efficiency_pct: 63.1, offset_kwh_per_year: 2539540, pv_capacity_kw: null, new_building_intensity_target: null }, curve: [{ target_pct: 0, all_buildings_efficiency_pct: 38.5, new_only_efficiency_pct: 100 }], scope: '전력 운영탄소 기준', assumptions: ['기상은 기준 연도와 같다고 가정합니다'] },
  grid_features: { type: 'FeatureCollection', features: [] },
  facts: [{ id: 'scope', text: '분석 대상은 덕진구 송천1동 (행정동)이고 기간은 2018~2020년입니다.', numbers: [2018, 2020] }],
  admin_year: 2024,
};

// /api/plans/evaluate 응답(U3 S5): analysis는 /api/areas/analyze와 같은 모양, 블록 · 세 범위 줄을 함께
const SCOPES = [
  { key: 'plan_emission', label: '원단위 기반 계획 배출(이 화면 계산)', data_class: 'SCENARIO', scope: '전력 운영탄소만(가스 · 열 제외)', what: '관측 원단위 × 계획 연면적 × 전력 계수' },
  { key: 'district_heat', label: '지역난방 열(추정)', data_class: 'ESTIMATED', scope: '지역난방 열만', what: '계획 연면적 × 지역난방 비중 × 열 원단위 × 공급자 계수' },
  { key: 'change_model', label: '팀 변화 모델 예측', data_class: 'SCENARIO', scope: '탄소공간지도 건물 배출(전기 · 가스 · 지역난방)', what: '과거 개발 사례로 학습한 모델의 변화 예측(구간 함께)' },
  { key: 'simulation', label: '한 칸 계획안(시뮬레이션 화면)', data_class: 'SCENARIO', scope: '전력 + 가스', what: '그 화면의 계획안 계산(여기서는 계산하지 않음)' },
];
function bundleOf(a: object, blocks: Record<string, unknown> = {}) {
  const x = a as typeof analysis;
  return { plan: { added_floor_area_m2: x.effort?.added_floor_area_m2 ?? null, removed_floor_area_m2: null, grid_ids: x.history.area.grid_ids, grid_count: x.history.area.grid_ids.length },
    analysis: a, scopes: SCOPES, facts: x.facts, timing_s: { analyze: 0.6 },
    blocks: { baseline: { status: 'OK', reason: null }, reduction: { status: 'OK', reason: null }, change_model: { status: 'NOT_REQUESTED', reason: null },
      plan_emission: { status: 'OK', reason: null, net_added_kgco2eq: 703173, text: '이 계획으로 전력 운영탄소가 연간 703,173 kgCO2eq 늘어납니다(신축 1,548,500 kWh − 철거 0 kWh, 2020년 원단위 · 계수 0.4541). 이만큼을 줄이거나 메우면 개발 전 수준입니다.' },
      district_heat: { status: 'NEEDS_CELL', reason: '지역난방 열은 대상지 칸 하나의 단지로 계산합니다', heat_kwh: null },
      ordinance: { status: 'NEEDS_SITE', reason: '대지(중심 · 면적)를 정하면 용도지역 · 상한과 계획 판정을 냅니다' }, ...blocks } };
}
const withTargets = { ...analysis, effort: { ...analysis.effort, targets: [{ key: 'plan_added', label: '개발 증가분 상쇄', data_class: 'SCENARIO', net_added_kwh: 1548500, net_added_kgco2eq: 703173, required_reduction_kgco2eq: 703173, existing_share_kgco2eq: null, already_met: false }] } };
const OPTIONS = { admin: [{ code: '35012650', name: '덕진구 송천1동' }], admin_geojson: { type: 'FeatureCollection', features: [] }, admin_year: 2024, zones: [], energy_years: [2025], default_grid: 'cell_1' };
const TEAM_READY = { status: 'ready', train: '00_합본_7차' };
const teamResult = (change: number) => ({ dataset: '52110_전주시', train: 't', snapshot: null, data_class: 'SCENARIO', note: 'n',
  results: [{ grid: 'g1', cell: 'g1', region: null, before_year: 2021, after_year: 2028, emission_before_tco2e: 1000, floor_area_before_m2: 1, floor_area_after_m2: 2, site_kind: 'new_site', use_class: 'residential',
    change_tco2e: change, band: {}, sources_tco2e: {}, filled: [], factors: [], warnings: [], out_of_range: [], attribution: {} }],
  combined: { cells: ['g1'], site_kind: 'new_site', change_tco2e: change, band: { q10: 1200, q90: 5400 } },
  area: { split: 'equal', year: 2021, cells_total: 1, seconds: 4, cells_used: [{ x: 1, y: 2, grid: 'g1', year: 2021, start: 'shared' }], cells_skipped: [], per_cell: { new: [], removed: [] } } });

describe('AreaPage — 계획 한 번 넣기 → 결과 한 화면 (U3 S5)', () => {
  afterEach(() => { vi.restoreAllMocks(); window.history.pushState({}, '', '/'); });

  it('용도 줄의 합을 계획 연면적으로 /plans/evaluate에 보내고, 목표만 바꾸면 빠른 답만 · 용도 줄을 바꾸면 예측도 다시 묻고, 보고서 요청에 용도 줄을 싣는다', async () => {
    window.history.pushState({}, '', '/area');
    const bodies: Array<Record<string, unknown>> = [];
    const predicts: Array<Record<string, unknown>> = [];
    const reports: Array<Record<string, unknown>> = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith('/api/areas/options')) return new Response(JSON.stringify(OPTIONS));
      if (url.endsWith('/api/areas/collection')) return new Response(JSON.stringify({ items: {}, runs: [], summary: {} }));
      if (url.endsWith('/api/areas/analyze')) throw new Error('the page asks the bundle address now');
      if (url.endsWith('/api/plans/evaluate')) { bodies.push(JSON.parse(String(init?.body))); return new Response(JSON.stringify(bundleOf(withTargets))); }
      if (url.endsWith('/api/team-model/status')) return new Response(JSON.stringify(TEAM_READY));
      if (url.endsWith('/api/team-model/predict-area')) { predicts.push(JSON.parse(String(init?.body))); return new Response(JSON.stringify(teamResult(3200))); }
      if (url.endsWith('/api/area-reports') && init?.method === 'POST') {
        reports.push(JSON.parse(String(init.body)));
        return new Response(JSON.stringify({ id: 'r1', title: '보고서', created_at: '2026-11-23T00:00:00Z', area: {}, facts: [], evidence_hash: 'a'.repeat(64), summary: { mode: 'TEMPLATE', model: null, paragraphs: ['본문'], validation: 'ok', violations: [] } }));
      }
      if (url.endsWith('/api/area-reports')) return new Response(JSON.stringify([]));
      return new Response('{}', { status: 404 });
    });
    render(<MemoryRouter><AreaPage /></MemoryRouter>);
    await waitFor(() => expect(bodies.length).toBe(1));
    const first = bodies[0] as { plan: { added_floor_area_m2: number }; uses_new: Array<{ floor_area_m2: number }>; uses_removed: unknown[]; years_after: number; include: string[] };
    expect(first).toMatchObject({ uses_new: [{ use: 'residential', floor_area_m2: 50000 }], uses_removed: [], years_after: 7, plan: { added_floor_area_m2: 50000 } });
    expect(first.uses_new.reduce((a, r) => a + r.floor_area_m2, 0)).toBe(first.plan.added_floor_area_m2);   // one floor area per plan (422 otherwise)
    expect(first.include).not.toContain('change_model');   // 13~29 s: asked separately after the quick answer
    // 빠른 답 뒤에 변화 모델이 같은 계획으로 한 번
    await waitFor(() => expect(predicts.length).toBe(1));
    expect(predicts[0]).toEqual({ region: null, grids: ['g1'], new: [{ use: 'residential', floor_area_m2: 50000 }], removed: [], years_after: 7 });
    // 결과: 한 줄 결론은 엔진 문장, 세 범위 표는 kg → t만, 더하지 않는다는 문장
    expect(screen.getByTestId('area-plan-headline').textContent).toContain('703,173 kgCO2eq 늘어납니다');
    expect(screen.getByTestId('area-scope-plan_emission').textContent).toContain('+703.2');
    expect(screen.getByTestId('area-scope-plan_emission').textContent).toContain('원단위 기반 계획 배출');
    await waitFor(() => expect(screen.getByTestId('area-scope-change_model').textContent).toContain('+3,200 tCO₂e/년'));
    expect(screen.getByTestId('area-scope-simulation').querySelector('a')?.getAttribute('href')).toBe('/simulation');
    expect(screen.getByTestId('area-scopes-note').textContent).toContain('더하거나 평균하지 않습니다');
    expect(screen.queryByTestId('area-district-heat')).toBeNull();   // NEEDS_CELL: no line
    expect(screen.getByTestId('area-plan-received').textContent).toContain('50,000');

    // 목표 %만 바꿈 → 빠른 답은 다시, 예측은 그대로
    fireEvent.change(screen.getByLabelText('목표 감축률'), { target: { value: '30' } });
    await waitFor(() => expect(bodies.some((b) => b.target_pct === 30)).toBe(true), { timeout: 3000 });
    await new Promise((r) => setTimeout(r, 50));
    expect(predicts.length).toBe(1);

    // 용도 줄을 바꿈 → 빠른 답과 예측 둘 다
    fireEvent.change(screen.getByLabelText('신축 연면적 1'), { target: { value: '60000' } });
    await waitFor(() => expect(bodies.some((b) => (b.plan as { added_floor_area_m2: number }).added_floor_area_m2 === 60000)).toBe(true), { timeout: 3000 });
    const changed = bodies[bodies.length - 1] as { uses_new: Array<{ floor_area_m2: number }> };
    expect(changed.uses_new).toEqual([{ use: 'residential', floor_area_m2: 60000 }]);
    await waitFor(() => expect(predicts.length).toBe(2));
    expect((predicts[1].new as Array<{ floor_area_m2: number }>)[0].floor_area_m2).toBe(60000);

    // 보고서 요청에 용도 줄 · 몇 년 뒤(변화 예측 절)
    fireEvent.click(screen.getByRole('button', { name: /현재 조건으로 보고서 작성/ }));
    await waitFor(() => expect(reports.length).toBe(1));
    expect(reports[0]).toMatchObject({ uses_new: [{ use: 'residential', floor_area_m2: 60000 }], uses_removed: [], years_after: 7, plan: { added_floor_area_m2: 60000 }, target_pct: 30 });
  });

  it('변화 모델 표가 없는 지역(404)이면 까닭과 원단위 기반 대신 값을 보이고, 지역난방 열은 OK일 때만 한 줄 보인다', async () => {
    window.history.pushState({}, '', '/area');
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith('/api/areas/options')) return new Response(JSON.stringify(OPTIONS));
      if (url.endsWith('/api/areas/collection')) return new Response(JSON.stringify({ items: {}, runs: [], summary: {} }));
      if (url.endsWith('/api/plans/evaluate')) return new Response(JSON.stringify(bundleOf(withTargets, { district_heat: { status: 'OK', reason: null, data_class: 'ESTIMATED', text: '지역난방 열(추정): 연 1,234,000 kWh = 계획 연면적 50,000 m² × 지역난방 비중 80% × …' } })));
      if (url.endsWith('/api/team-model/status')) return new Response(JSON.stringify(TEAM_READY));
      if (url.endsWith('/api/team-model/predict-area')) return new Response(JSON.stringify({ detail: '이 지역은 팀 데이터셋(칸 상태 표)이 없어 변화 모델 예측을 아직 내지 못합니다(준비 중). 원단위 기반 계산 값을 참고하세요' }), { status: 404 });
      if (url.endsWith('/api/area-reports')) return new Response(JSON.stringify([]));
      return new Response('{}', { status: 404 });
    });
    render(<MemoryRouter><AreaPage /></MemoryRouter>);
    const box = await screen.findByTestId('team-area-fallback');
    await waitFor(() => expect(screen.getByTestId('team-area-panel').textContent).toContain('준비 중'));
    expect(box.textContent).toContain('+703.2');
    expect(box.textContent).toContain('2020년 관측 원단위');
    expect(screen.getByTestId('area-scope-change_model').textContent).toContain('예측 없음');
    expect(screen.getByTestId('area-district-heat').textContent).toContain('지역난방 열(추정): 연 1,234,000 kWh');
  });

  it('옛 링크(용도 없이 연면적만)는 용도를 짐작하지 않고 용도 줄 없이 보내며 변화 모델은 돌리지 않는다', async () => {
    window.history.pushState({}, '', '/area?area=admin:35012650&plan=75000');
    const bodies: Array<Record<string, unknown>> = [];
    let predicted = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith('/api/areas/options')) return new Response(JSON.stringify(OPTIONS));
      if (url.endsWith('/api/areas/collection')) return new Response(JSON.stringify({ items: {}, runs: [], summary: {} }));
      if (url.endsWith('/api/plans/evaluate')) { bodies.push(JSON.parse(String(init?.body))); return new Response(JSON.stringify(bundleOf(withTargets))); }
      if (url.endsWith('/api/team-model/status')) return new Response(JSON.stringify(TEAM_READY));
      if (url.endsWith('/api/team-model/predict-area')) { predicted++; return new Response(JSON.stringify(teamResult(3200))); }
      if (url.endsWith('/api/area-reports')) return new Response(JSON.stringify([]));
      return new Response('{}', { status: 404 });
    });
    render(<MemoryRouter><AreaPage /></MemoryRouter>);
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toMatchObject({ plan: { added_floor_area_m2: 75000 }, uses_new: [], uses_removed: [] });
    expect(await screen.findByTestId('area-plan-undecided')).toBeInTheDocument();
    expect((await screen.findByTestId('team-area-blocked')).textContent).toContain('용도를 짐작해 채우지 않음');
    await new Promise((r) => setTimeout(r, 50));
    expect(predicted).toBe(0);
  });
});

describe('AreaPage', () => {
  afterEach(() => vi.restoreAllMocks());

  it('지역을 바꾸면 앞 지역의 행정동 코드로 분석을 보내지 않고, 새 지역 선택지가 오면 그 행정동으로 첫 분석을 한다(2026-11-23 422)', async () => {
    window.localStorage.clear();
    window.history.pushState({}, '', '/area');
    act(() => setAnalysisScope({ region: '41130' }));
    const bodies: Array<{ region: string | null; area: { code?: string } }> = [];
    const dong: Record<string, { code: string; name: string }> = { '41130': { code: '31021510', name: '분당구 구미1동' }, '41290': { code: '31110510', name: '중앙동' } };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      const region = new URL(url, 'http://x').searchParams.get('region') ?? '';
      if (url.includes('/api/areas/options')) {
        await new Promise((resolve) => setTimeout(resolve, 30));   // the new region's options arrive a little later
        return new Response(JSON.stringify({ admin: [dong[region]], admin_geojson: { type: 'FeatureCollection', features: [] }, admin_year: 2024, zones: [], energy_years: [2025], default_grid: 'cell_1' }));
      }
      if (url.endsWith('/api/areas/collection')) return new Response(JSON.stringify({ items: {}, runs: [], summary: {} }));
      if (url.endsWith('/api/plans/evaluate')) { bodies.push(JSON.parse(String(init?.body))); return new Response(JSON.stringify(bundleOf(analysis))); }
      if (url.includes('/api/area-reports')) return new Response(JSON.stringify([]));
      return new Response('{}', { status: 404 });
    });
    try {
      render(<MemoryRouter><AreaPage /></MemoryRouter>);
      await waitFor(() => expect(bodies.some((b) => b.region === '41130')).toBe(true));
      act(() => setAnalysisScope({ region: '41290' }));
      await waitFor(() => expect(bodies.some((b) => b.region === '41290')).toBe(true), { timeout: 3000 });
      expect(bodies.filter((b) => b.region === '41290').map((b) => b.area.code)).toEqual(['31110510']);   // never the 분당 code
    } finally {
      act(() => setAnalysisScope({ region: null }));
    }
  });

  it('첫 행정동을 분석하고 관측이 없는 값은 0이 아니라 자료 없음으로, 감축 노력은 엔진 값 그대로 보여 준다', async () => {
    const bodies: unknown[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith('/api/areas/options')) return new Response(JSON.stringify({ admin: [{ code: '35011600', name: '완산구 동서학동' }, { code: '35012650', name: '덕진구 송천1동' }], admin_geojson: { type: 'FeatureCollection', features: [] }, admin_year: 2024, zones: [{ category: 'COMMERCIAL', label: '상업지역', grids: 18 }], energy_years: [2025], default_grid: 'cell_1' }));
      if (url.endsWith('/api/areas/collection')) return new Response(JSON.stringify({ items: {}, runs: [], summary: {} }));
      if (url.endsWith('/api/plans/evaluate')) { bodies.push(JSON.parse(String(init?.body))); return new Response(JSON.stringify(bundleOf(analysis))); }
      if (url.endsWith('/api/area-reports')) return new Response(JSON.stringify([]));
      return new Response('{}', { status: 404 });
    });
    render(<MemoryRouter><AreaPage /></MemoryRouter>);
    expect(await screen.findByRole('heading', { name: '덕진구 송천1동 (행정동)' })).toBeInTheDocument();
    await waitFor(() => expect(bodies.length).toBeGreaterThan(0));
    expect(bodies[0]).toMatchObject({ area: { type: 'admin', code: '35012650' }, from_year: 2015, to_year: 2025, target_pct: 40, plan: { added_floor_area_m2: 50000 } });
    expect(screen.getByText('과거 전력을 아직 수집하지 않았습니다.')).toBeInTheDocument();
    expect(screen.getByText(/scripts\\dss.cmd CollectAll/)).toBeInTheDocument();
    expect(screen.getByText("건축물대장을 아직 수집하지 않았습니다")).toBeInTheDocument();
    expect(screen.getByText(/지역 전체 건물의 전력 사용을 63.1% 줄이거나/)).toBeInTheDocument();
    expect(screen.getByText('164 % 필요 → 불가')).toBeInTheDocument();
    expect(screen.getByText('전후 기간에 12개월이 모두 관측된 전력 자료가 부족합니다 (과거 수집 필요)')).toBeInTheDocument();
    expect(screen.getAllByText('자료 없음').length).toBeGreaterThan(0);
    expect(screen.getByText('SGIS 격자 통계를 아직 가져오지 않았습니다')).toBeInTheDocument();
  });

  it('감축 노력의 기준을 건물 전체(건축HUB)로 바꾸면 그 기준으로 다시 계산을 요청한다', async () => {
    const bodies: Array<Record<string, unknown>> = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith('/api/areas/options')) return new Response(JSON.stringify({ admin: [{ code: '35011790', name: '완산구 효자5동' }], admin_geojson: { type: 'FeatureCollection', features: [] }, admin_year: 2024, zones: [], energy_years: [2025], default_grid: 'cell_1' }));
      if (url.endsWith('/api/areas/collection')) return new Response(JSON.stringify({ items: {}, runs: [], summary: {} }));
      if (url.endsWith('/api/plans/evaluate')) {
        const body = JSON.parse(String(init?.body)); bodies.push(body);
        const basis = body.effort_basis === 'buildings' ? 'buildings' : 'apartments';
        return new Response(JSON.stringify(bundleOf({ ...analysis, effort: { ...analysis.effort, basis, baseline_mode: 'OBSERVED' } })));
      }
      if (url.endsWith('/api/area-reports')) return new Response(JSON.stringify([]));
      return new Response('{}', { status: 404 });
    });
    render(<MemoryRouter><AreaPage /></MemoryRouter>);
    await waitFor(() => expect(bodies.length).toBeGreaterThan(0));
    expect(bodies[0]).toMatchObject({ effort_basis: 'apartments' });
    (await screen.findByRole('tab', { name: '건물 전체 (건축HUB)' })).click();
    await waitFor(() => expect(bodies.some((b) => b.effort_basis === 'buildings')).toBe(true), { timeout: 3000 });
    expect(await screen.findByText(/기준 부하 관측 · 2020년 · 건물 전체 \(건축HUB\)/)).toBeInTheDocument();
  });

  it('SGIS 1km 격자 합계는 관측, 면적 비례 인구는 추정으로 따로 보여 준다', async () => {
    const sgis = {
      year: 2024, cells: 3, cells_with_stats: 2, coverage_pct: 33.3, source: 'SGIS',
      estimated: { population: 12182, households: 6315, data_class: 'ESTIMATED', basis: '1km 격자 값 × (구역에 든 500m 격자 수 ÷ 4)' },
      overlap: { population: 34609, male: null, female: null, households: 17644, housing: 11482, businesses: null, workers: 18697, elderly_pct: 20.7, children_pct: null, single_household_pct: 57.5, old_housing_pct: 58.5, apartment_pct: 47.7,
        housing_age: {}, housing_types: {}, housing_area: {}, household_types: {}, sectors: [], small_flags: [] },
    };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith('/api/areas/options')) return new Response(JSON.stringify({ admin: [{ code: '35012650', name: '덕진구 송천1동' }], admin_geojson: { type: 'FeatureCollection', features: [] }, admin_year: 2024, zones: [], energy_years: [2025], default_grid: 'cell_1' }));
      if (url.endsWith('/api/areas/collection')) return new Response(JSON.stringify({ items: {}, runs: [], summary: {} }));
      if (url.endsWith('/api/plans/evaluate')) return new Response(JSON.stringify(bundleOf({ ...analysis, history: { ...analysis.history, sgis_grid: sgis } })));
      if (url.endsWith('/api/area-reports')) return new Response(JSON.stringify([]));
      return new Response('{}', { status: 404 });
    });
    render(<MemoryRouter><AreaPage /></MemoryRouter>);
    expect(await screen.findByText('지역 특성 (SGIS 1km 격자 2024년)')).toBeInTheDocument();
    expect(screen.getByText('34,609 명')).toBeInTheDocument();
    expect(screen.getByText('구역 인구 (면적 비례 추정)')).toBeInTheDocument();
    expect(screen.getByText('12,182 명')).toBeInTheDocument();
    expect(screen.getByText('33.3%')).toBeInTheDocument();
  });

  it('자동 전환된 기준·구체적 감축 방안·감축 수단 조합·행정동 비교를 엔진 값 그대로 보여 주고 다른 안 비교는 없다', async () => {
    window.localStorage.clear();
    const bodies: Array<Record<string, unknown>> = [];
    const effort = { ...analysis.effort, basis: 'buildings', baseline_mode: 'OBSERVED', baseline_year: 2025, intensity_kwh_per_m2: 44.25, fallback_from: 'apartments', fallback_reason: '지역 관측이 없고 연면적이 확인된 단지도 없어 기준 부하를 정할 수 없습니다',
      factor_kgco2eq_per_kwh: 0.433, pv_yield: { kwh_per_kw: 1199.9, basis: 'ESTIMATED', label: '추정' },
      // 2026-11-20부터 자동 방안은 태양광만(신축·기존 전력 절감 단계 없음)
      recommended: { kind: 'RECOMMENDED', new_efficiency_pct: 0, existing_efficiency_pct: 0, pv_kw: 2220, new_kwh: 0, existing_kwh: 0, pv_kwh: 2663778, pv_counted: true, total_kwh: 2663778,
        total_kgco2eq: 1153415.9, required_kgco2eq: 1153205.1, gap_kgco2eq: -210.8, met: true, share_pct: 100.0, basis: '식', roof_m2: 22200, offset_kwh: null,
        plan_roof_m2: 10000, plan_roof_basis: 'floor_area', roof_over_plan: true,
        steps: [{ key: 'pv', title: '태양광', detail: '2,220 kW (옥상 약 22,200 m²)', kwh: 2663778, kgco2eq: 1153415.9 }] } };
    const mix = { new_efficiency_pct: 30, existing_efficiency_pct: 0, pv_kw: 0, new_kwh: 464550, existing_kwh: 0, pv_kwh: 0, pv_counted: true, total_kwh: 464550, total_kgco2eq: 201150.2, required_kgco2eq: 1153205.1, gap_kgco2eq: 952054.9, met: false, share_pct: 17.4, basis: '식' };
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith('/api/areas/options')) return new Response(JSON.stringify({ admin: [{ code: '35510410', name: '완주군 경천면' }], admin_geojson: { type: 'FeatureCollection', features: [] }, admin_year: 2024, zones: [], energy_years: [2025], default_grid: 'cell_1', region: { code: '52710', name: '완주군', short_name: '완주', center: null, bbox: null } }));
      if (url.endsWith('/api/areas/collection')) return new Response(JSON.stringify({ items: {}, runs: [], summary: {} }));
      if (url.includes('/api/areas/benchmark')) return new Response(JSON.stringify({ basis: 'buildings', basis_label: '건물 전체(건축HUB)', years: [2015, 2025], reference_year: 2025, count: 5, admin_total: 13, median: 40, quintiles: [30, 38, 42, 50], min: 20, max: 70, note: '위치입니다.',
        items: [20, 35, 40, 48, 70].map((v, i) => ({ code: String(i), name: `면${i}`, year: 2025, kwh_per_m2: v, area_m2: 1 })) }));
      if (url.endsWith('/api/plans/evaluate')) {
        const body = JSON.parse(String(init?.body)); bodies.push(body);
        return new Response(JSON.stringify(bundleOf({ ...analysis, effort: { ...effort, ...(body.measures ? { mix } : {}) } })));
      }
      if (url.endsWith('/api/area-reports')) return new Response(JSON.stringify([]));
      return new Response('{}', { status: 404 });
    });
    render(<MemoryRouter><AreaPage /></MemoryRouter>);
    expect(await screen.findByText(/기준 자동 전환:/)).toBeInTheDocument();
    const summary = screen.getByTestId('area-summary');
    expect(within(summary).getByText('1,153.2 t')).toBeInTheDocument();   // 필요 감축량 kg → t
    expect(await within(summary).findByText('4/5번째')).toBeInTheDocument();   // 44.25: three of 20·35·40·48·70 are lower
    expect(bodies[0].measures).toBeNull();
    fireEvent.change(screen.getByLabelText('신축 건물 전력 절감'), { target: { value: '30' } });
    await waitFor(() => expect(bodies.some((b) => (b.measures as { new_efficiency_pct?: number } | null)?.new_efficiency_pct === 30)).toBe(true), { timeout: 3000 });
    expect(await screen.findByTestId('area-mix')).toHaveTextContent(/필요 감축량 1,153\.2 t의 17\.4 %/);
    // 다른 안을 저장·비교하는 단계는 없다(2026-11-05): 같은 계획을 줄이는 구체적 방안만
    expect(within(summary).queryByRole('button', { name: /시나리오 저장/ })).toBeNull();
    expect(screen.queryByTestId('area-compare')).toBeNull();
    const rec = screen.getByTestId('area-recommended');
    expect(rec).toHaveTextContent('구체적 감축 방안');
    expect(rec).toHaveTextContent('2,220 kW (옥상 약 22,200 m²)');
    // 2026-11-20 점검 A: 필요한 옥상이 계획 연면적보다 크면 경고
    expect(screen.getByTestId('area-roof-warning')).toHaveTextContent(/필요한 옥상 약 22,200\s?m²가 계획 연면적\(1층으로 지어도 지붕은 이보다 작음\) 10,000\s?m²보다 큽니다/);
    // 2026-11-20 점검 B: 태양광 칸만 채우고 넣어 둔 신축 30%는 그대로
    fireEvent.click(within(rec).getByRole('button', { name: /태양광 값을 아래 칸에 넣기/ }));
    await waitFor(() => expect(bodies.some((b) => { const m = b.measures as { new_efficiency_pct?: number; existing_efficiency_pct?: number; pv_kw?: number } | null; return m?.new_efficiency_pct === 30 && m.existing_efficiency_pct === 0 && m.pv_kw === 2220; })).toBe(true), { timeout: 3000 });
  });

  it('사례 링크로 열면 링크의 구역·계획·목표·기준 건물로 첫 계산을 하고 보고서 요청에도 기준 건물을 넣는다', async () => {
    window.history.pushState({}, '', '/area?area=zone:COMMERCIAL&from=2016&to=2025&plan=75000&target=20&basis=buildings&pv=1200');
    const bodies: Array<Record<string, unknown>> = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith('/api/areas/options')) return new Response(JSON.stringify({ admin: [{ code: '35012650', name: '덕진구 송천1동' }], admin_geojson: { type: 'FeatureCollection', features: [] }, admin_year: 2024, zones: [{ category: 'COMMERCIAL', label: '상업지역', grids: 18 }], energy_years: [2025], default_grid: 'cell_1' }));
      if (url.endsWith('/api/areas/collection')) return new Response(JSON.stringify({ items: {}, runs: [], summary: {} }));
      if (url.endsWith('/api/plans/evaluate')) { bodies.push(JSON.parse(String(init?.body))); return new Response(JSON.stringify(bundleOf(analysis))); }
      if (url.endsWith('/api/area-reports')) return new Response(JSON.stringify([]));
      return new Response('{}', { status: 404 });
    });
    try {
      render(<MemoryRouter><AreaPage /></MemoryRouter>);
      await waitFor(() => expect(bodies.length).toBeGreaterThan(0));
      expect(bodies[0]).toMatchObject({ area: { type: 'zone', category: 'COMMERCIAL' }, from_year: 2016, to_year: 2025, plan: { added_floor_area_m2: 75000 }, target_pct: 20, pv_yield_kwh_per_kw: 1200, effort_basis: 'buildings' });
      (await screen.findByRole('button', { name: /링크 복사/ })).click();
      expect(await screen.findByDisplayValue(/\/area\?region=52110&area=zone:COMMERCIAL&from=2016&to=2025&window=3&plan=75000&target=20&pv=1200&basis=buildings$/)).toBeInTheDocument();
    } finally {
      window.history.pushState({}, '', '/');
    }
  });
});

describe('KcsmPanel (탄소공간지도 100m, 선도소프트)', () => {
  it('shows the outline total, the 500m-grid total and the tool share side by side, never added', async () => {
    const { KcsmPanel } = await import('./AreaPage');
    const { render: r, screen: sc } = await import('@testing-library/react');
    const analysis = { history: { kcsm: { available: true, source: 's', boundary_basis: '행정동 경계 안에 중심점이 있는 100m 칸', note: '선도소프트가 준 값입니다.', years: {
      2023: { year: 2023, boundary_t: 550, grid_t: 580, cells: 3, value_cells: 3, zero_cells: 0, grid_cells: 4, monthly: [], drop_cells: 0, drop_from_t: null, drop_now_t: null },
      2024: { year: 2024, boundary_t: 120, grid_t: 160, cells: 3, value_cells: 2, zero_cells: 1, grid_cells: 4, monthly: [], drop_cells: 1, drop_from_t: 400, drop_now_t: 10, change_pct: -78.2, change_from: 2023,
        tool: { kwh: 200000, factor: 0.4781, t: 95.6, parcels: 3, complete: true, share_pct: 59.8 } } } } } } as never;
    r(<KcsmPanel analysis={analysis} />);
    const table = sc.getByTestId('area-kcsm');
    expect(table.textContent).toContain('120160 (4칸)');   // outline total and 500m-grid total in their own columns
    expect(table.textContent).toContain('59.8%');
    expect(table.textContent).toContain('-78.2%');
    expect(table.textContent).toContain('1칸');
  });
});

describe('EstimatesPanel·IndustryPanel (추정은 관측과 따로, 업계 기준은 참고 위치)', () => {
  it('shows backcast years, observed and estimated side by side, the collecting tag and when the estimate was computed', async () => {
    const { EstimatesPanel } = await import('./AreaPage');
    const { render: r, screen: sc } = await import('@testing-library/react');
    const analysis = { history: { estimates: { available: true, rule_version: 'est-1.0', created_at: '2026-10-27T09:30:00+00:00',
      buildings: {
        2019: { year: 2019, backcast: true, electricity_kwh: 800000, gas_kwh: 500000, electricity_observed_kwh: null, same_index: 0.98, exist_share: 0.9 },
        2025: { year: 2025, backcast: false, complete: false, electricity_kwh: 1000000, gas_kwh: null, electricity_observed_kwh: 900000, electricity_filled_kwh: 60000, electricity_filled_months: 2 } },
      apartments: { 2025: { year: 2025, observed_kwh: 500, observed_complexes: 1, estimated_kwh: 300, estimated_complexes: 1, total_kwh: 800, peer_median_complexes: 0 } },
      population: {} } } } as never;
    r(<EstimatesPanel analysis={analysis} />);
    const panel = sc.getByTestId('area-estimates');
    expect(panel.textContent).toContain('되돌림 추정');
    expect(panel.textContent).toContain('수집 중');
    expect(panel.textContent).toContain('빈 달 2개월 채움');
    expect(panel.querySelector('tr.is-estimated-row')).not.toBeNull();
    expect(sc.getByTestId('area-estimates-asof').textContent).toContain('2026-10-27');
    expect(sc.getByTestId('area-estimates-asof').textContent).toContain('est-1.0');
  });

  it('renders nothing when no estimate was computed for the region', async () => {
    const { EstimatesPanel, IndustryPanel } = await import('./AreaPage');
    const { render: r } = await import('@testing-library/react');
    const { container } = r(<><EstimatesPanel analysis={{ history: { estimates: { available: false } } } as never} /><IndustryPanel analysis={{ history: {} } as never} /></>);
    expect(container.innerHTML).toBe('');
  });

  it('lists the industry reference rows and notes without judging a grade', async () => {
    const { IndustryPanel } = await import('./AreaPage');
    const { render: r, screen: sc } = await import('@testing-library/react');
    const analysis = { history: { industry: { available: true, zone: '중부', table: [
      { label: '1차에너지 원단위 (전력×2.75 + 가스×1.1)', value: '186.0 kWh/m²·년', reference: '주거 2등급 구간 수준(참고)', source: '한국에너지공단' }],
      notes: ['인증은 설계 평가이고 이 값은 실사용 계량값이라 판정이 아닙니다.'] } } } as never;
    r(<IndustryPanel analysis={analysis} />);
    const panel = sc.getByTestId('area-industry');
    expect(panel.textContent).toContain('186.0 kWh/m²·년');
    expect(panel.textContent).toContain('참고');
    expect(panel.textContent).toContain('판정이 아닙니다');
  });
});

describe('RegionGuidePanel (지역 구분 · 평년 기후 · 방향 가이드 · 지자체 과제)', () => {
  const guide = { code: '27110', name: '대구광역시 중구', design_zone: '남부', standard_zone: '남부',
    climate: { station: '대구', mapping: '광역시 지점', summer_mean_c: 25.5, winter_mean_c: 2.5, hdd_ratio: 0.89, cdd_ratio: 1.06, sunshine_hours_year: 2300,
      guide_emission_change_pct: -2.9, guide_electricity_change_pct: 0.0, guide_gas_change_pct: -7.2, within_our_data: true },
    plans: [{ code: '27', region: '대구광역시', plan: '제1차 대구광역시 기본계획', tasks: 11, groups: [{ group: 'rooftop_pv', label: '태양광', tasks: 3 }], task_names: ['공공건물 태양광'] }],
    sources: { zone: '고시', climate: '기상청 평년값', plans: '기본계획' }, value_kinds: '배출 방향 = 추정 가이드(예측 아님)', check: "점검에서 '맞지 않음'이었습니다." };

  it('shows the guide as a direction with its failed check, not as a forecast', async () => {
    const { RegionGuidePanel } = await import('./AreaPage');
    const { render: r, screen: sc } = await import('@testing-library/react');
    r(<RegionGuidePanel analysis={{ history: { region_guide: guide } } as never} />);
    const panel = sc.getByTestId('area-region-guide');
    expect(sc.getByTestId('region-guide-emission').textContent).toContain('−2.9%');
    expect(sc.getByTestId('region-guide-emission').textContent).toContain('전주보다 낮은 쪽');
    expect(panel.textContent).toContain('0.89배 · 1.06배');
    expect(panel.textContent).toContain('예측 아님');
    expect(panel.textContent).toContain('맞지 않음');
    expect(panel.textContent).toContain('대구광역시 기본계획 건물 과제');
    expect(sc.queryByTestId('region-guide-heating')).toBeNull();   // 난방 방식 자료가 없으면 줄을 만들지 않음
  });

  it('shows the heating-type mix by household share with unknown complexes left out', async () => {
    const { RegionGuidePanel } = await import('./AreaPage');
    const { render: r, screen: sc } = await import('@testing-library/react');
    const heating = { complexes: 224, unknown_complexes: 3, households: 150000, source: 'K-apt 단지 기본정보', value_kind: '관측', reading: '단열·창호 가스 지표는 개별난방 단지 짝 비교에서 나온 값',
      kinds: [{ kind: '지역난방', complexes: 185, households: 130000, household_share_pct: 86.7 }, { kind: '개별난방', complexes: 33, households: 20000, household_share_pct: 13.3 },
        { kind: '중앙난방', complexes: 1, households: 300, household_share_pct: 0.2 }, { kind: '기타', complexes: 1, households: null, household_share_pct: null }] };
    r(<RegionGuidePanel analysis={{ history: { region_guide: { ...guide, heating } } } as never} />);
    const row = sc.getByTestId('region-guide-heating');
    expect(row.textContent).toContain('지역 87% · 개별 13% · 중앙 1% 미만 · 기타 1곳(세대수 없음)');   // 0 %로 채우지 않음
    expect(row.textContent).toContain('미상 3곳 제외');
    expect(row.textContent).toContain('개별난방 단지 짝 비교');
  });

  it('shows the regional PV yield next to normal sunshine, the cooling measures with their use and the rate note', async () => {
    const { RegionGuidePanel } = await import('./AreaPage');
    const { render: r, screen: sc } = await import('@testing-library/react');
    const extra = { reference: { station: '전주', sunshine_hours_year: 2063 }, rate_note: '감축률은 지역에 따라 크게 다르지 않다고 봅니다: 2.21 · 2.72%p',
      solar: { year: 2025, yield_kwh_per_kw: 1199.9, irradiation_kwh_m2: 1499.9, performance_ratio: 0.8, source: 'ERA5-Land', source_type: 'FALLBACK' },
      cooling: { items: [{ label: '외부 차양·일사 조절', use: '지표만', indicator: '냉방 부하 −34.5%' }, { label: '쿨루프(고반사 지붕)', use: '범위 참고(근거표, 값으로 쓰지 않음)', indicator: null }],
        reading: '냉방도일이 전주의 1.06배로 냉방이 전주보다 더 필요한 지역입니다. 냉방 수단의 효과는 냉방 에너지에 대한 %' } };
    r(<RegionGuidePanel analysis={{ history: { region_guide: { ...guide, ...extra } } } as never} />);
    expect(sc.getByTestId('region-guide-solar').textContent).toContain('1,200 kWh');
    expect(sc.getByTestId('region-guide-solar').textContent).toContain('(대체 자료: 재분석)');   // 관측 · 대체를 섞지 않음
    expect(sc.getByTestId('region-guide-solar').textContent).toContain('평년 일조 2,300시간(전주 2,063시간)');
    expect(sc.getByTestId('region-guide-cooling').textContent).toContain('쿨루프(고반사 지붕)(범위 참고');
    expect(sc.getByTestId('region-guide-cooling').textContent).toContain('더 필요한 지역');
    expect(sc.getByTestId('region-guide-rate-note').textContent).toContain('2.21 · 2.72%p');
  });

  it('takes the guide directly (전국 지역 화면) and shows the statistics district-heat share, blank instead of 0', async () => {
    const { RegionGuidePanel } = await import('../components/RegionGuide');
    const { render: r, screen: sc } = await import('@testing-library/react');
    const stats = { year: 2025, parts: ['경기도 수원시 장안구', '경기도 수원시 권선구'], total_toe: 172186, district_heat_toe: 60009, district_heat_share_pct: 34.9, source: '건물에너지사용량통계 2025 아파트' };
    const { unmount } = r(<RegionGuidePanel guide={{ ...guide, heat_stats: stats } as never} />);
    expect(sc.getByTestId('region-guide-heat-stats').textContent).toContain('34.9%');
    expect(sc.getByTestId('region-guide-heat-stats').textContent).toContain('2개 구를 더함');
    unmount();
    r(<RegionGuidePanel guide={{ ...guide, heat_stats: { ...stats, parts: null, district_heat_toe: null, district_heat_share_pct: null } } as never} />);
    expect(sc.getByTestId('region-guide-heat-stats').textContent).toContain('통계에 없음');
    expect(sc.getByTestId('region-guide-heat-stats').textContent).toContain('0이 아니라 빈칸');
  });

  it('stacks rows in the compact form for the narrow 전국 지역 detail', async () => {
    const { RegionGuidePanel } = await import('../components/RegionGuide');
    const { render: r, screen: sc } = await import('@testing-library/react');
    const { container } = r(<RegionGuidePanel guide={guide as never} compact />);
    expect(container.querySelector('table')).toBeNull();
    expect(container.querySelector('dl.region-guide-list')).not.toBeNull();
    expect(sc.getByTestId('region-guide-emission').textContent).toContain('−2.9%');
  });

  it('says no data for a region without a complete solar year instead of zero', async () => {
    const { RegionGuidePanel } = await import('./AreaPage');
    const { render: r, screen: sc } = await import('@testing-library/react');
    r(<RegionGuidePanel analysis={{ history: { region_guide: { ...guide, solar: null } } } as never} />);
    expect(sc.getByTestId('region-guide-solar').textContent).toContain('자료 없음');
  });

  it('keeps an unmapped climate empty instead of zero', async () => {
    const { RegionGuidePanel } = await import('./AreaPage');
    const { render: r, screen: sc } = await import('@testing-library/react');
    r(<RegionGuidePanel analysis={{ history: { region_guide: { ...guide, climate: null } } } as never} />);
    expect(sc.getByTestId('area-region-guide').textContent).toContain('기상 지점에 연결하지 못했습니다');
    expect(sc.queryByTestId('region-guide-emission')).toBeNull();
  });
});
