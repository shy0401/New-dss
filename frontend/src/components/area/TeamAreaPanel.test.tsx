import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TeamAreaPanel, teamScopeText, useTeamAreaPrediction, type IntensityFallback, type TeamAreaRequest } from './TeamAreaPanel';

afterEach(() => { vi.restoreAllMocks(); });

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const STATUS = { status: 'ready', train: '00_합본_7차', accuracy: { model: 'm', train: 't', by_use: 'u', band_coverage: 'b', source: 's', test: [],
  development: { basis: 'b', by_use: 'u', electricity: '전기 개발 단위 오차 0.32', small: '방향 0.67', band_coverage: 'c', requirement: 'r',
    rows: [{ band: '교차검증 2~9칸 개발', cases: 100, median_error: 0.27, within_50pct: 0.78, sum_ratio: 1.0 }] } } };
const cell = (grid: string, change: number) => ({ grid, cell: grid, region: null, before_year: 2021, after_year: 2028, emission_before_tco2e: 1000,
  floor_area_before_m2: 1, floor_area_after_m2: 2, site_kind: 'new_site', use_class: 'residential', change_tco2e: change, band: {}, sources_tco2e: {},
  filled: [], factors: [], warnings: ['주거 위주 계획'], out_of_range: [], attribution: {} });
const result = (change: number) => ({ dataset: '52110_전주시', train: 't', snapshot: null, data_class: 'SCENARIO', note: 'n',
  results: [cell('cell_1000_2000', change / 2), cell('cell_1500_2000', change / 2)],
  combined: { cells: ['a', 'b'], site_kind: 'new_site', change_tco2e: change, band: { q10: 1200, q90: 5400 }, sources_tco2e: { elec_tco2e_total: 2000, gas_tco2e_total: 1200 } },
  area: { split: 'equal', year: 2021, cells_total: 3, seconds: 4,
    cells_used: [{ x: 1000, y: 2000, grid: 'cell_1000_2000', year: 2021, start: 'shared' }, { x: 1500, y: 2000, grid: 'cell_1500_2000', year: 2021, start: 'empty' }],
    cells_skipped: [{ x: 2000, y: 2000, grid: 'cell_2000_2000', reason: '쓸 수 있는 해가 없는 칸(결측·결함 표시)' }],
    per_cell: { new: [{ use: 'residential', floor_area_m2: 25000 }, { use: 'commercial', floor_area_m2: 5000 }], removed: [] } } });
const GRIDS = ['cell_1000_2000', 'cell_1500_2000', 'cell_2000_2000'];
const REQUEST: TeamAreaRequest = { region: '52110', grids: GRIDS, years_after: 7, new: [{ use: 'residential', floor_area_m2: 50000 }, { use: 'commercial', floor_area_m2: 10000 }], removed: [] };

function Harness({ request, fallback = null }: { request: TeamAreaRequest | null; fallback?: IntensityFallback | null }) {
  const team = useTeamAreaPrediction(request);
  return <><TeamAreaPanel team={team} request={request} fallback={fallback} /><p data-testid="scope-text">{teamScopeText(team, request)}</p></>;
}

function mockService(predict: () => Response, status: unknown = STATUS) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes('/team-model/status')) return json(status);
    if (url.includes('/team-model/predict-area')) return predict();
    return json({}, 404);
  });
}
const predictCalls = (fetchMock: ReturnType<typeof mockService>) => fetchMock.mock.calls.filter(([u]) => String(u).includes('/team-model/predict-area'));

describe('TeamAreaPanel (U3 S5: 계획을 받아 스스로 예측하는 결과 카드)', () => {
  it('runs the plan it is given once the model is ready and shows the development total with the cells left out', async () => {
    const fetchMock = mockService(() => json(result(3200)));
    render(<Harness request={REQUEST} />);
    const box = await screen.findByTestId('team-area-result');
    expect(box.textContent).toContain('+3,200');
    expect(box.textContent).toContain('2021→2028년, 칸 2개 합계');
    expect(box.textContent).toContain('+1,200 ~ +5,400');
    expect(screen.getByTestId('team-area-meaning').textContent).toContain('계획 밖 변화');
    const note = screen.getByTestId('team-area-skipped').textContent ?? '';
    expect(note).toContain('칸 3개 중 기준 해(2021년) 상태로 1개');
    expect(note).toContain('빈 땅으로 보고 1개(추정)');
    expect(note).toContain('뺀 칸 1개');
    expect(screen.getByTestId('team-area-cells-table').textContent).toContain('빈 땅으로 봄, 추정');
    expect(screen.getByTestId('team-area-size-accuracy').textContent).toContain('2~9칸');
    expect(box.textContent).toContain('주거 위주 계획');
    expect(screen.getByTestId('team-area-cells').textContent).toContain('3개');
    expect(screen.getByTestId('scope-text').textContent).toBe('+3,200 tCO₂e/년 (+1,200 ~ +5,400 tCO₂e (80% 구간))');
    expect(screen.queryByTestId('team-area-fallback')).toBeNull();   // a prediction came back: no stand-in value
    // the panel has no input form of its own any more: the plan comes from '계획 넣기'
    expect(screen.queryByRole('button', { name: '이 구역 배출 변화 예측' })).toBeNull();
    expect(predictCalls(fetchMock)).toHaveLength(1);
    expect(JSON.parse(String(predictCalls(fetchMock)[0][1]?.body))).toEqual(REQUEST);
  });

  it('asks again only when the plan itself changes, not for the same plan in a new object', async () => {
    const fetchMock = mockService(() => json(result(3200)));
    const { rerender } = render(<Harness request={REQUEST} />);
    await screen.findByTestId('team-area-result');
    rerender(<Harness request={{ ...REQUEST, new: [...REQUEST.new] }} />);
    await new Promise((r) => setTimeout(r, 20));
    expect(predictCalls(fetchMock)).toHaveLength(1);
    rerender(<Harness request={{ ...REQUEST, years_after: 5 }} />);
    await waitFor(() => expect(predictCalls(fetchMock)).toHaveLength(2));
    expect(JSON.parse(String(predictCalls(fetchMock)[1][1]?.body)).years_after).toBe(5);
  });

  it('shows the intensity-based increase instead when the region has no team table (U2-0)', async () => {
    mockService(() => json({ detail: '이 지역은 팀 데이터셋(칸 상태 표)이 없어 변화 모델 예측을 아직 내지 못합니다(준비 중). 원단위 기반 계산 값을 참고하세요' }, 404));
    render(<Harness request={{ ...REQUEST, region: '41130' }} fallback={{ netAddedKgco2eq: 584691.4, baselineYear: 2025 }} />);
    const box = await screen.findByTestId('team-area-fallback');
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('준비 중'));
    expect(box.textContent).toContain('+584.7');
    expect(box.textContent).toContain('전력 운영탄소만');
    expect(box.textContent).toContain('2025년 관측 원단위');
    expect(box.textContent).toContain('견주거나 더하지 않습니다');
    expect(screen.queryByRole('button', { name: /다시 예측/ })).toBeNull();   // 404: asking again gives the same answer
    expect(screen.getByTestId('scope-text').textContent).toContain('예측 없음: 이 지역은 팀 데이터셋');
  });

  it('does not ask for areas over 64 cells or a plan without use lines, and says why', async () => {
    const fetchMock = mockService(() => json(result(3200)));
    const many = Array.from({ length: 65 }, (_, i) => `cell_${1000 + 500 * i}_2000`);
    const { rerender } = render(<Harness request={{ ...REQUEST, grids: many }} />);
    expect(await screen.findByTestId('team-area-too-many')).toBeTruthy();
    rerender(<Harness request={{ ...REQUEST, new: [], removed: [] }} fallback={{ netAddedKgco2eq: 1000, baselineYear: 2025 }} />);
    expect((await screen.findByTestId('team-area-blocked')).textContent).toContain('용도를 짐작해 채우지 않음');
    expect(screen.getByTestId('team-area-fallback')).toBeTruthy();
    await new Promise((r) => setTimeout(r, 20));
    expect(predictCalls(fetchMock)).toHaveLength(0);
  });

  it('reads a change under 1,000 tCO₂e for direction only, without the value or band', async () => {
    mockService(() => json(result(600)));
    render(<Harness request={REQUEST} />);
    const box = await screen.findByTestId('team-area-result');
    expect(box.querySelector('.detail-figure')?.textContent).toContain('늘어나는 방향');
    expect(box.querySelector('.detail-figure')?.textContent).not.toContain('600');
    expect(box.textContent).not.toContain('80% 구간');
    expect(screen.getByTestId('scope-text').textContent).toBe('늘어나는 방향(1,000 tCO₂e 미만이라 값은 읽지 않음)');
  });

  it('says it is for this PC only on the public address and still shows the stand-in value', async () => {
    const fetchMock = mockService(() => json(result(3200)), { status: 'restricted', reason: '공개 시연 주소에서는 쓸 수 없습니다' });
    render(<Harness request={REQUEST} fallback={{ netAddedKgco2eq: 584691.4, baselineYear: 2025 }} />);
    await waitFor(() => expect(screen.getByTestId('team-area-status').textContent).toContain('공개 시연 주소'));
    expect(screen.getByTestId('team-area-fallback').textContent).toContain('+584.7');
    expect(screen.getByTestId('scope-text').textContent).toContain('이 PC 화면에서만');
    expect(predictCalls(fetchMock)).toHaveLength(0);
  });
});
