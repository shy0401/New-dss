import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TeamAreaPanel } from './TeamAreaPanel';

afterEach(() => { vi.restoreAllMocks(); });

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const STATUS = { status: 'ready', train: '00_합본_7차', accuracy: { model: 'm', train: 't', by_use: 'u', band_coverage: 'b', source: 's', test: [],
  development: { basis: 'b', by_use: 'u', electricity: '전기 개발 단위 오차 0.32', small: '방향 0.67', band_coverage: 'c', requirement: 'r',
    rows: [{ band: '교차검증 2~9칸 개발', cases: 100, median_error: 0.27, within_50pct: 0.78, sum_ratio: 1.0 }] } } };
const cell = (grid: string, change: number) => ({ grid, cell: grid, region: null, before_year: 2021, after_year: 2028, emission_before_tco2e: 1000,
  floor_area_before_m2: 1, floor_area_after_m2: 2, site_kind: 'new_site', use_class: 'residential', change_tco2e: change, band: {}, sources_tco2e: {},
  filled: [], factors: [], warnings: ['주거 위주 계획'], out_of_range: [], attribution: {} });
const RESULT = { dataset: '52110_전주시', train: 't', snapshot: null, data_class: 'SCENARIO', note: 'n',
  results: [cell('cell_1000_2000', 1500), cell('cell_1500_2000', 1700)],
  combined: { cells: ['a', 'b'], site_kind: 'new_site', change_tco2e: 3200, band: { q10: 1200, q90: 5400 }, sources_tco2e: { elec_tco2e_total: 2000, gas_tco2e_total: 1200 } },
  area: { split: 'equal', year: 2021, cells_total: 3, seconds: 4,
    cells_used: [{ x: 1000, y: 2000, grid: 'cell_1000_2000', year: 2021, start: 'shared' }, { x: 1500, y: 2000, grid: 'cell_1500_2000', year: 2021, start: 'empty' }],
    cells_skipped: [{ x: 2000, y: 2000, grid: 'cell_2000_2000', reason: '쓸 수 있는 해가 없는 칸(결측·결함 표시)' }],
    per_cell: { new: [{ use: 'residential', floor_area_m2: 25000 }, { use: 'commercial', floor_area_m2: 5000 }], removed: [] } } };
const GRIDS = ['cell_1000_2000', 'cell_1500_2000', 'cell_2000_2000'];

describe('TeamAreaPanel', () => {
  it('starts from the plan above, sends the area totals and shows the development total with the cells left out', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes('/team-model/status')) return json(STATUS);
      if (url.includes('/team-model/predict-area')) return json(RESULT);
      return json({}, 404);
    });
    render(<TeamAreaPanel grids={GRIDS} region="52110" plannedFloor={50000} plannedRemoved={0} />);
    expect(await screen.findByText(/학습 완료/)).toBeTruthy();
    expect(screen.getByTestId('team-area-cells').textContent).toContain('3개');
    expect(screen.getByTestId('team-area-fit-note').textContent).toContain('개발 부지에 맞게');
    expect((screen.getByPlaceholderText('예: 120000') as HTMLInputElement).value).toBe('50000');
    expect(screen.getByTestId('team-area-sync').textContent).toContain('그대로');
    fireEvent.click(screen.getByRole('button', { name: /용도 추가/ }));
    fireEvent.change(screen.getAllByPlaceholderText('예: 120000')[1], { target: { value: '10000' } });
    expect(screen.getByTestId('team-area-sync').textContent).toContain('다릅니다');
    fireEvent.click(screen.getByRole('button', { name: '이 구역 배출 변화 예측' }));
    const result = await screen.findByTestId('team-area-result');
    expect(result.textContent).toContain('+3,200');
    expect(result.textContent).toContain('2021→2028년, 칸 2개 합계');
    expect(screen.getByTestId('team-area-meaning').textContent).toContain('계획 밖 변화');
    expect(result.textContent).toContain('+1,200 ~ +5,400');
    const note = screen.getByTestId('team-area-skipped').textContent ?? '';
    expect(note).toContain('칸 3개 중 기준 해(2021년) 상태로 1개');
    expect(note).toContain('빈 땅으로 보고 1개(추정)');
    expect(note).toContain('뺀 칸 1개');
    expect(screen.getByTestId('team-area-cells-table').textContent).toContain('빈 땅으로 봄, 추정');
    expect(screen.getByTestId('team-area-size-accuracy').textContent).toContain('2~9칸');
    expect(result.textContent).toContain('주거 위주 계획');
    const call = fetchMock.mock.calls.find(([u]) => String(u).includes('/team-model/predict-area'));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ region: '52110', grids: GRIDS, years_after: 7,
      new: [{ use: 'residential', floor_area_m2: 50000 }, { use: 'commercial', floor_area_m2: 10000 }], removed: [] });
  });

  it('shows the intensity-based increase instead when the region has no team table (U2-0)', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes('/team-model/status')) return json(STATUS);
      if (url.includes('/team-model/predict-area')) return json({ detail: '이 지역은 팀 데이터셋(칸 상태 표)이 없어 변화 모델 예측을 아직 내지 못합니다(준비 중). 원단위 기반 계산 값을 참고하세요' }, 404);
      return json({}, 404);
    });
    render(<TeamAreaPanel grids={GRIDS} region="41130" plannedFloor={50000} plannedRemoved={0} fallback={{ netAddedKgco2eq: 584691.4, baselineYear: 2025 }} />);
    await screen.findByText(/학습 완료/);
    fireEvent.click(screen.getByRole('button', { name: '이 구역 배출 변화 예측' }));
    const box = await screen.findByTestId('team-area-fallback');
    expect(screen.getByRole('alert').textContent).toContain('준비 중');
    expect(box.textContent).toContain('+584.7');
    expect(box.textContent).toContain('전력 운영탄소만');
    expect(box.textContent).toContain('2025년 관측 원단위');
    expect(box.textContent).toContain('견주거나 더하지 않습니다');
  });

  it('follows the plan above until the user edits, and blocks areas over 64 cells', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json(STATUS));
    const many = Array.from({ length: 65 }, (_, i) => `cell_${1000 + 500 * i}_2000`);
    const { rerender } = render(<TeamAreaPanel grids={many} region="52110" plannedFloor={50000} plannedRemoved={0} />);
    expect(await screen.findByTestId('team-area-too-many')).toBeTruthy();
    expect((screen.getByRole('button', { name: '이 구역 배출 변화 예측' }) as HTMLButtonElement).disabled).toBe(true);
    rerender(<TeamAreaPanel grids={many} region="52110" plannedFloor={80000} plannedRemoved={0} />);
    expect((screen.getByPlaceholderText('예: 120000') as HTMLInputElement).value).toBe('80000');
    fireEvent.change(screen.getByPlaceholderText('예: 120000'), { target: { value: '70000' } });
    rerender(<TeamAreaPanel grids={many} region="52110" plannedFloor={90000} plannedRemoved={0} />);
    expect((screen.getByPlaceholderText('예: 120000') as HTMLInputElement).value).toBe('70000');
    fireEvent.click(screen.getByRole('button', { name: '위 계획 값으로' }));
    expect((screen.getByPlaceholderText('예: 120000') as HTMLInputElement).value).toBe('90000');
  });

  it('is hidden on the public address', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => json({ status: 'restricted', reason: '공개 시연 주소' }));
    const { container } = render(<TeamAreaPanel grids={GRIDS} region="52110" plannedFloor={1} plannedRemoved={0} />);
    await vi.waitFor(() => expect(container.querySelector('[data-testid="team-area-fold"]')).toBeNull());
  });
});
