/**
 * 사례 링크: 화면 입력을 주소(쿼리)로 주고받는다. 같은 링크를 다른 PC에서 열면 같은 지역·구역·입력으로 시작하므로,
 * 같은 자료 묶음이면 같은 결과가 나온다 (docs/USER_MANUAL.md 5·9절, backend/cases/simulation_cases.json).
 *
 * 시뮬레이션: /simulation?region=52110&grid=cell_966500_1764500&site=127.13219,35.880124,0&site_area=40000&building_count=10&…
 * 지역 시뮬레이션: /area?region=52110&area=admin:35012650&from=2015&to=2025&plan=90000&target=20&basis=apartments
 *   용도 줄(U3 S5): `uses=residential:60000:500,commercial:30000`(용도:연면적[:세대]) · `ruses=commercial:2000` · `years=5` ·
 *   `floors=20` · `buildings=5` · `footprint=800`. `plan` · `removed`는 줄의 합이고, 용도 줄이 없는 옛 링크는 그 합을 '용도 미정' 한 줄로 받는다.
 */
import type { ScenarioInput } from '../types';
import { usesBody, plannedArea, plannedRemoved, type AreaMode, type AreaSpec, type EffortBasis, type MeasuresState, type PlanState, type PlanUse } from './area';
import { TEAM_USES, type TeamUse } from './teamModel';

/** The original study region. The analysis scope keeps it as null; a link always names a region so it opens the same place. */
export const DEFAULT_REGION = '52110';

export const SCENARIO_KEYS: Array<keyof ScenarioInput> = ['site_area', 'building_count', 'footprint_per_building', 'floors', 'households', 'population',
  'efficiency_factor', 'pv_ratio', 'green_ratio', 'average_household_area'];

export interface ScopeLink { region?: string | null; grid?: string | null; year?: number }
export interface ScenarioLink extends ScopeLink {
  input: Partial<ScenarioInput>;
  site?: { lon: number; lat: number; rotation: number };
  constraints?: { min_households?: number; min_population?: number };
}
export interface AreaLink extends ScopeLink {
  mode?: AreaMode; spec?: AreaSpec; from?: number; to?: number; event?: number | null; window?: number;
  plan?: Partial<PlanState>; target?: number; pv?: string; basis?: EffortBasis;
  /** 감축 수단 조합 `mx=신축%,기존%,태양광kW`. */
  measures?: MeasuresState;
}

/** Commas and colons are valid in a query value; keeping them makes the link readable (127.13,35.88 / admin:35012650). */
const readable = (params: URLSearchParams) => params.toString().replace(/%2C/gi, ',').replace(/%3A/gi, ':');

const num = (value: string | null): number | undefined => {
  if (value === null || value.trim() === '') return undefined;
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
};

function scope(params: URLSearchParams): ScopeLink {
  const out: ScopeLink = {};
  const region = params.get('region');
  if (region !== null) out.region = /^\d{5}$/.test(region) && region !== DEFAULT_REGION ? region : null;
  const grid = params.get('grid');
  if (grid !== null && /^cell_\d+_\d+$/.test(grid)) out.grid = grid;
  const year = num(params.get('year'));
  if (year && year >= 2000 && year <= 2100) out.year = year;
  return out;
}

/** null when the address carries no scenario input (the page keeps its own defaults). */
export function parseScenarioLink(search: string): ScenarioLink | null {
  const params = new URLSearchParams(search);
  const input: Partial<ScenarioInput> = {};
  for (const key of SCENARIO_KEYS) {
    const value = num(params.get(key));
    if (value !== undefined && value >= 0) input[key] = value;
  }
  const link: ScenarioLink = { ...scope(params), input };
  const site = (params.get('site') ?? '').split(',').map(Number);
  if (site.length >= 2 && site.slice(0, 2).every(Number.isFinite) && site[0] >= 124 && site[0] <= 132 && site[1] >= 33 && site[1] <= 39) {
    link.site = { lon: site[0], lat: site[1], rotation: Number.isFinite(site[2]) ? Math.min(89.9, Math.max(0, site[2])) : 0 };
  }
  const minHouseholds = num(params.get('min_households'));
  const minPopulation = num(params.get('min_population'));
  if (minHouseholds !== undefined || minPopulation !== undefined) link.constraints = { min_households: minHouseholds, min_population: minPopulation };
  const empty = !Object.keys(input).length && !link.site && !link.constraints && link.region === undefined && !link.grid;
  return empty ? null : link;
}

export function scenarioLink(input: ScenarioInput, site: { lon: number; lat: number; rotation: number } | null, at: ScopeLink,
  constraints?: { min_households: number; min_population: number }): string {
  const params = new URLSearchParams();
  params.set('region', at.region ?? DEFAULT_REGION);
  if (at.grid) params.set('grid', at.grid);
  if (at.year) params.set('year', String(at.year));
  if (site) params.set('site', `${site.lon.toFixed(6)},${site.lat.toFixed(6)},${Math.round(site.rotation * 10) / 10}`);
  for (const key of SCENARIO_KEYS) params.set(key, String(input[key]));
  if (constraints) { params.set('min_households', String(constraints.min_households)); params.set('min_population', String(constraints.min_population)); }
  return `/simulation?${readable(params)}`;
}

const MODES: AreaMode[] = ['admin', 'circle', 'zone', 'grid'];
const USE_KEYS = new Set<string>(TEAM_USES.map(([k]) => k));

/** `residential:60000:500,commercial:30000` → 용도 줄(1~4줄). 하나라도 읽을 수 없으면 undefined(옛 `plan` 합으로). */
function parseUses(value: string | null): PlanUse[] | undefined {
  if (!value) return undefined;
  const rows = value.split(',').map((part): PlanUse | null => {
    const [use, area, dwellings] = part.split(':');
    const floor = Number(area); const d = dwellings === undefined ? undefined : Number(dwellings);
    if (!USE_KEYS.has(use) || !Number.isFinite(floor) || floor <= 0 || floor > 3_000_000) return null;
    return { use: use as TeamUse, floor_area_m2: floor, ...(use === 'residential' && d !== undefined && Number.isFinite(d) && d > 0 && d <= 50_000 ? { dwellings: d } : {}) };
  });
  return rows.length >= 1 && rows.length <= 4 && rows.every((r) => r !== null) ? (rows as PlanUse[]) : undefined;
}
const usesText = (rows: ReturnType<typeof usesBody>) => rows.map((r) => `${r.use}:${r.floor_area_m2}${r.dwellings ? `:${r.dwellings}` : ''}`).join(',');

/** `area=admin:35012650 | grid:cell_… | circle:lon,lat,radius | zone:COMMERCIAL` and the analysis inputs. */
export function parseAreaLink(search: string): AreaLink | null {
  const params = new URLSearchParams(search);
  const link: AreaLink = scope(params);
  const area = params.get('area');
  if (area) {
    const [kind, value = ''] = area.split(/:(.*)/s);
    const mode = kind as AreaMode;
    if (MODES.includes(mode)) {
      if (mode === 'admin' && /^\d{5,10}$/.test(value)) link.spec = { type: 'admin', code: value };
      if (mode === 'zone' && /^[A-Z]+$/.test(value)) link.spec = { type: 'zone', category: value };
      if (mode === 'grid' && /^cell_\d+_\d+$/.test(value)) link.spec = { type: 'grid', grid_id: value };
      if (mode === 'circle') {
        const [lon, lat, radius] = value.split(',').map(Number);
        if ([lon, lat].every(Number.isFinite) && lon >= 124 && lon <= 132 && lat >= 33 && lat <= 39) {
          link.spec = { type: 'circle', lon, lat, radius_m: Number.isFinite(radius) && radius >= 100 && radius <= 5000 ? radius : 1000 };
        }
      }
      if (link.spec) link.mode = mode;
    }
  }
  const from = num(params.get('from')); const to = num(params.get('to'));
  if (from && from >= 2000 && from <= 2100) link.from = from;
  if (to && to >= 2000 && to <= 2100) link.to = to;
  const event = params.get('event');
  if (event !== null) link.event = num(event) ?? null;
  const window = num(params.get('window'));
  if (window && window >= 1 && window <= 5) link.window = window;
  const added = num(params.get('plan')); const removed = num(params.get('removed'));
  // 용도 줄이 없는 옛 링크: 합을 '용도 미정' 한 줄로(주거로 짐작하지 않음, 설계 2.1)
  const usesNew = parseUses(params.get('uses')) ?? (added !== undefined && added >= 0 ? [{ use: null, floor_area_m2: added }] : undefined);
  const usesRemoved = parseUses(params.get('ruses')) ?? (removed !== undefined && removed > 0 ? [{ use: null, floor_area_m2: removed }] : undefined);
  const plan: Partial<PlanState> = {};
  if (usesNew) plan.uses_new = usesNew;
  if (usesRemoved) plan.uses_removed = usesRemoved;
  const years = num(params.get('years'));
  if (years !== undefined && Number.isInteger(years) && years >= 1 && years <= 10) plan.years_after = years;
  for (const [key, field] of [['floors', 'floors'], ['buildings', 'building_count'], ['footprint', 'footprint_per_building'], ['green', 'green_area_m2']] as const) {
    const v = num(params.get(key));
    if (v !== undefined && v > 0) plan[field] = field === 'green_area_m2' ? Math.min(v, 10_000_000) : v;
  }
  if (Object.keys(plan).length) link.plan = plan;
  const target = num(params.get('target'));
  if (target !== undefined && target >= 0 && target <= 100) link.target = target;
  const pv = num(params.get('pv'));
  if (pv !== undefined && pv > 0) link.pv = String(pv);
  const basis = params.get('basis');
  if (basis === 'apartments' || basis === 'buildings' || basis === 'kcsm') link.basis = basis;
  const mx = (params.get('mx') ?? '').split(',').map(Number);
  if (mx.length === 3 && mx.every((v) => Number.isFinite(v) && v >= 0) && mx[0] <= 100 && mx[1] <= 100) {
    link.measures = { new_efficiency_pct: mx[0], existing_efficiency_pct: mx[1], pv_kw: mx[2] };
  }
  return Object.keys(link).length ? link : null;
}

export function areaLink(spec: AreaSpec | null, a: { region: string | null; from: number; to: number; event: number | null; window: number; plan: PlanState; target: number; pv: string; basis: EffortBasis; measures?: MeasuresState | null }): string | null {
  if (!spec || spec.type === 'polygon') return null;   // a drawn polygon does not fit in an address
  const params = new URLSearchParams();
  params.set('region', a.region ?? DEFAULT_REGION);
  const value = spec.type === 'admin' ? spec.code : spec.type === 'zone' ? spec.category : spec.type === 'grid' ? spec.grid_id
    : `${spec.lon},${spec.lat},${spec.radius_m}`;
  params.set('area', `${spec.type}:${value}`);
  params.set('from', String(a.from)); params.set('to', String(a.to));
  if (a.event) params.set('event', String(a.event));
  params.set('window', String(a.window));
  params.set('plan', String(plannedArea(a.plan)));
  if (plannedRemoved(a.plan) > 0) params.set('removed', String(plannedRemoved(a.plan)));
  params.set('target', String(a.target));
  if (a.pv && Number(a.pv) > 0) params.set('pv', a.pv);
  params.set('basis', a.basis);
  const m = a.measures;
  if (m && (m.new_efficiency_pct > 0 || m.existing_efficiency_pct > 0 || m.pv_kw > 0)) params.set('mx', `${m.new_efficiency_pct},${m.existing_efficiency_pct},${m.pv_kw}`);
  // 용도 줄 · 몇 년 뒤 · 건물 모양(U3 S5): 있을 때만 뒤에 붙인다(옛 링크와 앞부분이 같음)
  const usesNew = usesBody(a.plan.uses_new); const usesRemoved = usesBody(a.plan.uses_removed);
  if (usesNew.length) params.set('uses', usesText(usesNew));
  if (usesRemoved.length) params.set('ruses', usesText(usesRemoved));
  if (a.plan.years_after !== 7) params.set('years', String(a.plan.years_after));
  if (a.plan.floors > 0) params.set('floors', String(a.plan.floors));
  if (a.plan.building_count > 0) params.set('buildings', String(a.plan.building_count));
  if (a.plan.footprint_per_building > 0) params.set('footprint', String(a.plan.footprint_per_building));
  if ((a.plan.green_area_m2 ?? 0) > 0) params.set('green', String(a.plan.green_area_m2));   // 2026-11-25 계획 v3 H: 녹지 면적도 링크로
  return `/area?${readable(params)}`;
}
