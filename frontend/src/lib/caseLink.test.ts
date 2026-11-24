import { describe, expect, it } from 'vitest';
import { areaLink, parseAreaLink, parseScenarioLink, scenarioLink } from './caseLink';
import type { ScenarioInput } from '../types';

const plan: ScenarioInput = { site_area: 40000, building_count: 10, footprint_per_building: 600, floors: 15, households: 1000, population: 2500, efficiency_factor: 1, pv_ratio: 0, green_ratio: 0.3, average_household_area: 84 };

describe('사례 링크', () => {
  it('시뮬레이션 입력·지역·격자·대지 위치가 주소를 오가도 같다', () => {
    const path = scenarioLink(plan, { lon: 127.13219, lat: 35.880124, rotation: 0 }, { region: '41110', grid: 'cell_950000_1919000', year: 2025 }, { min_households: 900, min_population: 2200 });
    const back = parseScenarioLink(path.split('?')[1]);
    expect(back?.input).toEqual(plan);
    expect(back?.site).toEqual({ lon: 127.13219, lat: 35.880124, rotation: 0 });
    expect([back?.region, back?.grid, back?.year]).toEqual(['41110', 'cell_950000_1919000', 2025]);
    // 전주(최초 연구 지역)는 범위에서 null이지만 링크에는 늘 코드를 적어, 다른 지역을 보던 사람도 전주로 연다
    expect(scenarioLink(plan, null, { region: null })).toMatch(/^\/simulation\?region=52110&site_area=40000/);
    expect(parseScenarioLink('region=52110')?.region).toBeNull();
    expect(back?.constraints).toEqual({ min_households: 900, min_population: 2200 });
  });

  it('주소에 입력이 없으면 화면 기본값을 그대로 쓰고, 이상한 값은 버린다', () => {
    expect(parseScenarioLink('')).toBeNull();
    const odd = parseScenarioLink('floors=abc&site=1,2&grid=../x&region=9&site_area=-5');
    expect(odd?.input).toEqual({});
    expect(odd?.site).toBeUndefined();
    expect(odd?.grid).toBeUndefined();
    expect(odd?.region).toBeNull();   // not a 5-digit code → the original region
  });

  it('지역 시뮬레이션 구역·기간·계획·목표·기준 건물', () => {
    const base = { region: '52110', from: 2015, to: 2025, event: null, window: 3, target: 20, pv: '', basis: 'buildings' as const,
      plan: { uses_new: [{ use: null, floor_area_m2: 75000 }], uses_removed: [], floors: 0, building_count: 0, footprint_per_building: 0, years_after: 7 } };
    const path = areaLink({ type: 'admin', code: '35011790' }, base)!;
    expect(path).toBe('/area?region=52110&area=admin:35011790&from=2015&to=2025&window=3&plan=75000&target=20&basis=buildings');
    const back = parseAreaLink(path.split('?')[1]);
    // 용도 줄이 없는 링크: 합을 '용도 미정' 한 줄로(주거로 짐작하지 않음)
    expect(back).toMatchObject({ region: null, mode: 'admin', spec: { type: 'admin', code: '35011790' }, from: 2015, to: 2025, window: 3, target: 20, basis: 'buildings',
      plan: { uses_new: [{ use: null, floor_area_m2: 75000 }] } });
    const circle = parseAreaLink('area=circle:127.13219,35.880124,1000&pv=1200');
    expect(circle?.spec).toEqual({ type: 'circle', lon: 127.13219, lat: 35.880124, radius_m: 1000 });
    expect(circle?.pv).toBe('1200');
    expect(parseAreaLink('area=zone:COMMERCIAL')?.spec).toEqual({ type: 'zone', category: 'COMMERCIAL' });
    expect(areaLink({ type: 'polygon', geometry: { type: 'Polygon', coordinates: [] } }, base)).toBeNull();
    expect(parseAreaLink('area=admin:abc')?.spec).toBeUndefined();
  });

  it('감축 수단 조합(mx)은 값이 있을 때만 링크에 넣고 다시 읽는다', () => {
    const base = { region: '52710', from: 2015, to: 2025, event: null, window: 3, target: 40, pv: '', basis: 'apartments' as const,
      plan: { uses_new: [{ use: null, floor_area_m2: 50000 }], uses_removed: [], floors: 0, building_count: 0, footprint_per_building: 0, years_after: 7 } };
    expect(areaLink({ type: 'admin', code: '35510410' }, { ...base, measures: { new_efficiency_pct: 0, existing_efficiency_pct: 0, pv_kw: 0 } })).not.toContain('mx=');
    const path = areaLink({ type: 'admin', code: '35510410' }, { ...base, measures: { new_efficiency_pct: 30, existing_efficiency_pct: 5, pv_kw: 120.5 } })!;
    expect(path).toMatch(/&mx=30,5,120.5$/);
    expect(parseAreaLink(path.split('?')[1])?.measures).toEqual({ new_efficiency_pct: 30, existing_efficiency_pct: 5, pv_kw: 120.5 });
    expect(parseAreaLink('area=admin:35510410&mx=130,0,0')?.measures).toBeUndefined();   // over 100%: ignored
    expect(parseAreaLink('area=admin:35510410&mx=1,2')?.measures).toBeUndefined();
  });

  it('용도 줄 · 철거 줄 · 몇 년 뒤 · 건물 모양을 링크에 담고 다시 읽는다(U3 S5)', () => {
    const plan = { uses_new: [{ use: 'residential' as const, floor_area_m2: 60000, dwellings: 500 }, { use: 'commercial' as const, floor_area_m2: 30000 }],
      uses_removed: [{ use: 'commercial' as const, floor_area_m2: 2000 }], floors: 20, building_count: 0, footprint_per_building: 0, years_after: 5 };
    const path = areaLink({ type: 'admin', code: '35012650' }, { region: '52110', from: 2015, to: 2025, event: null, window: 3, target: 40, pv: '', basis: 'apartments', plan })!;
    expect(path).toContain('&plan=90000&removed=2000&');   // 합은 그대로(옛 링크와 같은 자리)
    expect(path).toMatch(/&uses=residential:60000:500,commercial:30000&ruses=commercial:2000&years=5&floors=20$/);
    expect(parseAreaLink(path.split('?')[1])?.plan).toEqual({ uses_new: plan.uses_new, uses_removed: plan.uses_removed, years_after: 5, floors: 20 });
    // 읽을 수 없는 줄이 있으면 용도 줄은 버리고 합만(용도 미정)
    expect(parseAreaLink('area=admin:1234567&plan=1000&uses=house:1000')?.plan?.uses_new).toEqual([{ use: null, floor_area_m2: 1000 }]);
    expect(parseAreaLink('area=admin:1234567&years=11')?.plan).toBeUndefined();
  });

  it('녹지 면적(green)은 0보다 클 때만 링크에 넣고, 다시 읽을 때 1천만 m²에서 자른다(계획 v3 H)', () => {
    const base = { region: '52110', from: 2015, to: 2025, event: null, window: 3, target: 40, pv: '', basis: 'apartments' as const };
    const plan = { uses_new: [{ use: 'residential' as const, floor_area_m2: 60000, dwellings: 500 }], uses_removed: [], floors: 20, building_count: 0, footprint_per_building: 0, years_after: 5 };
    expect(areaLink({ type: 'admin', code: '35012650' }, { ...base, plan: { ...plan, green_area_m2: 0 } })).not.toContain('green=');
    const path = areaLink({ type: 'admin', code: '35012650' }, { ...base, plan: { ...plan, green_area_m2: 10000 } })!;
    expect(path).toMatch(/&green=10000$/);
    expect(parseAreaLink(path.split('?')[1])?.plan?.green_area_m2).toBe(10000);
    expect(parseAreaLink('area=admin:35012650&green=20000000')?.plan?.green_area_m2).toBe(10_000_000);
    expect(parseAreaLink('area=admin:35012650&green=-5')?.plan).toBeUndefined();
    expect(parseAreaLink('area=admin:35012650&green=abc')?.plan).toBeUndefined();
  });
});
