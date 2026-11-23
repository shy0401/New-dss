import { Download, FileText, Info, Link2, Pause, Play, Plus, Printer, RotateCcw, Undo2, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { AreaMap } from '../components/area/AreaMap';
import { AreaSummaryBar, BenchmarkPanel, FallbackNotice, MeasuresPanel } from '../components/area/AreaWorkflow';
import { BeforeAfterChart, DevelopmentChart, EffortBars, EffortCurve, ElectricityChart, RegisterChart, WeatherYearsChart } from '../components/area/AreaCharts';
import { TeamAreaPanel, teamScopeText, useTeamAreaPrediction, type TeamAreaRequest, type TeamAreaState } from '../components/area/TeamAreaPanel';
import { RegionGuidePanel } from '../components/RegionGuide';

export { RegionGuidePanel };
import { Fold, FoldAllButton, FoldStack, Note } from '../components/Fold';
import { MetricCard } from '../components/MetricCard';
import { PageHeader } from '../components/PageHeader';
import { ProvenanceBadge } from '../components/ProvenanceBadge';
import { SgisGridSummaryView } from '../components/SgisGridPanel';
import { EmptyState, ErrorState, LoadingState } from '../components/Status';
import { setAnalysisScope, useAnalysisScope } from '../hooks/useAnalysisScope';
import { areaLink, parseAreaLink, type AreaLink } from '../lib/caseLink';
import { useApi } from '../hooks/useApi';
import { useSystemInfo } from '../hooks/useSystemInfo';
import { slowLoadText, useElapsed } from '../hooks/useElapsed';
import { api } from '../lib/api';
import { at, BASELINE_MODE_LABEL, buildSpec, EFFORT_BASIS_LABEL, effortHeadline, eventYears, measuresBody, MODE_LABEL, NO_MEASURES, planBody, pvNote, QUICK_BLOCKS, REPORT_MODE_LABEL, usesBody, type AreaAnalysis, type AreaMode, type AreaOptions, type AreaReport, type AreaSpec, type BeforeAfter, type Benchmark, type EffortBasis, type EffortResult, type MeasuresState, type PlanEvaluation, type PlanState, type PlanUse } from '../lib/area';
import { formatDate, formatMetric } from '../lib/format';
import { AREA_MAX_USES, signed, TEAM_USES, type TeamAreaItem, type TeamUse } from '../lib/teamModel';

/** 연도 선택지: 2010년부터 자료가 있는 마지막 해(건축HUB 전력 연도·시스템 기준 연도 중 늦은 쪽)까지. 아직 오지 않은 해는 보이지 않는다. */
function yearChoices(energyYears: number[] | undefined, baselineYear: number | undefined, chosen: number[] = []): number[] {
  const last = Math.max(energyYears?.length ? energyYears[energyYears.length - 1] : 0, baselineYear ?? 0, 2025, ...chosen.filter((y) => y <= 2100));
  const first = Math.min(2010, ...chosen.filter((y) => y >= 1990));
  return Array.from({ length: last - first + 1 }, (_, i) => first + i);
}
/** 예시값(실제 계획이 아님): 화면을 처음 열었을 때 계산이 돌아가도록 채워 둔다. 주거 50,000 m² 한 줄, 건물 모양은 비움. */
const DEFAULT_PLAN: PlanState = { uses_new: [{ use: 'residential', floor_area_m2: 50000 }], uses_removed: [], floors: 0, building_count: 0, footprint_per_building: 0, years_after: 7 };
/** 빠른 답과 함께 받은 것: 블록 · 세 범위 줄, 그리고 그 요청의 용도 줄(변화 모델은 이 값으로 묻는다). */
interface BundleView { blocks: PlanEvaluation['blocks']; scopes: PlanEvaluation['scopes']; plan: PlanEvaluation['plan']; sent: { region: string | null; new: TeamAreaItem[]; removed: TeamAreaItem[]; years_after: number } }
const DEFAULT_TARGET = 40;
const MODES: AreaMode[] = ['admin', 'circle', 'polygon', 'zone', 'grid'];
const DATASET_LABEL: Record<string, string> = { sgis: 'SGIS 인구·가구', kma_asos: '기상청 ASOS', kapt_energy: 'K-apt 단지 에너지', energy: '건축HUB 지번 에너지', vworld_zoning: 'VWorld 용도지역', vworld_buildings: 'VWorld 건물', vworld_cadastral: 'VWorld 연속지적', building_register: '건축물대장', sgis_grid_500m: 'SGIS 500m 격자 경계' };

interface CollectionStatus { items: Record<string, { status: string; at?: string; reason?: string }>; runs: Array<{ started_at: string; finished_at?: string; from: number; to: number }>; summary: Record<string, Record<string, number>> }

export function AreaPage() {
  const { region, regionQuery } = useAnalysisScope();
  // 사례 링크(/area?region=…&area=admin:35012650&plan=90000&target=20&basis=…): 같은 구역·입력으로 시작한다.
  const linked = useRef<AreaLink | null | undefined>(undefined);
  if (linked.current === undefined) linked.current = parseAreaLink(typeof window === 'undefined' ? '' : window.location.search);
  const link = linked.current;
  const options = useApi<AreaOptions>(`/areas/options${regionQuery.replace('&', '?')}`);
  const collection = useApi<CollectionStatus>('/areas/collection');
  const [mode, setMode] = useState<AreaMode>(link?.mode ?? 'admin');
  const [adminCode, setAdminCode] = useState(link?.spec?.type === 'admin' ? link.spec.code ?? '' : '');
  const [category, setCategory] = useState(link?.spec?.type === 'zone' ? link.spec.category ?? '' : '');
  const [center, setCenter] = useState<[number, number] | null>(link?.spec?.type === 'circle' ? [link.spec.lon!, link.spec.lat!] : null);
  const [radius, setRadius] = useState(link?.spec?.type === 'circle' ? link.spec.radius_m ?? 1000 : 1000);
  const [vertices, setVertices] = useState<Array<[number, number]>>([]);
  const [fromYear, setFromYear] = useState(link?.from ?? 2015);
  const [toYear, setToYear] = useState(link?.to ?? 2025);
  const system = useSystemInfo();
  // 링크로 받은 연도가 범위 밖이어도(예전 링크) 선택 상자에서 사라지지 않게 함께 넣는다
  const yearChoiceList = useMemo(() => yearChoices(options.data?.energy_years, system?.baseline_year, [fromYear, toYear]), [options.data?.energy_years, system?.baseline_year, fromYear, toYear]);
  const energyYears = options.data?.energy_years ?? [];
  const yearOption = (y: number) => <option key={y} value={y}>{energyYears.length && !energyYears.includes(y) ? `${y} (건축HUB 전력 없음)` : y}</option>;
  const [eventYear, setEventYear] = useState<number | null>(link?.event ?? null);
  const [windowSize, setWindowSize] = useState(link?.window ?? 3);
  const [plan, setPlan] = useState<PlanState>({ ...DEFAULT_PLAN, ...(link?.plan ?? {}) });
  const [target, setTarget] = useState(link?.target ?? DEFAULT_TARGET);
  const [pvYield, setPvYield] = useState(link?.pv ?? '');
  const [effortBasis, setEffortBasis] = useState<EffortBasis>(link?.basis ?? 'apartments');
  const [measures, setMeasures] = useState<MeasuresState>(link?.measures ?? NO_MEASURES);
  const [bench, setBench] = useState<Benchmark | null>(null);
  const [linkUrl, setLinkUrl] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AreaAnalysis | null>(null);
  const [bundle, setBundle] = useState<BundleView | null>(null);
  const [running, setRunning] = useState(false);
  const elapsed = useElapsed(running);
  const [error, setError] = useState<string | null>(null);
  const [slider, setSlider] = useState(2025);
  const [playing, setPlaying] = useState(false);
  const lastSpec = useRef<AreaSpec | null>(null);
  const revision = useRef(0);
  const started = useRef(false);
  // 지금 지역의 선택지(행정동 · 용도지역)가 도착했는지. 지역을 바꾼 순간에는 앞 지역 선택지 · 행정동 코드가 남아 있어,
  // 그대로 첫 분석을 보내면 "행정동을 찾을 수 없습니다"(422)가 나고 새 지역 첫 분석도 돌지 않았음(2026-11-23 재현).
  const optionsReady = useRef(false);

  // 처음 열 때: 에코시티 개발이 있는 송천1동(없으면 목록 첫 동)과 가장 넓은 용도지역을 고른다.
  useEffect(() => {
    const o = options.data; if (!o) return;
    optionsReady.current = true;
    setAdminCode((old) => old || (o.admin.find((a) => a.name.includes('송천1동')) ?? o.admin[0])?.code || '');
    setCategory((old) => old || o.zones.find((z) => z.category === 'COMMERCIAL')?.category || o.zones[0]?.category || '');
  }, [options.data]);

  const run = useCallback(async (spec: AreaSpec | string) => {
    if (typeof spec === 'string') { setError(spec); return; }
    if (fromYear > toYear) { setError('시작 연도가 끝 연도보다 늦습니다.'); return; }
    lastSpec.current = spec;
    const id = ++revision.current;
    setRunning(true); setError(null);
    const pv = Number(pvYield);
    // 계획 하나 → 답 하나(U3 S5): 묶음 주소의 빠른 블록. 연면적은 용도 줄의 합 하나(planBody · usesBody가 같은 줄을 더함)
    const body = { area: spec, region, from_year: fromYear, to_year: toYear, event_year: eventYear, window: windowSize, plan: planBody(plan), target_pct: target, pv_yield_kwh_per_kw: pvYield && pv > 0 ? pv : null, effort_basis: effortBasis, measures: measuresBody(measures),
      uses_new: usesBody(plan.uses_new), uses_removed: usesBody(plan.uses_removed), years_after: plan.years_after, include: [...QUICK_BLOCKS] };
    try {
      const response = await api<PlanEvaluation>('/plans/evaluate', { method: 'POST', body: JSON.stringify(body) });
      if (id !== revision.current) return;
      const result = response.analysis;
      setAnalysis(result);
      setBundle({ blocks: response.blocks, scopes: response.scopes, plan: response.plan, sent: { region, new: body.uses_new, removed: body.uses_removed, years_after: body.years_after } });
      setSlider((s) => Math.min(Math.max(s, result.history.years[0]), result.history.years[result.history.years.length - 1]));
    } catch (reason) {
      if (id === revision.current) setError(reason instanceof Error ? reason.message : '분석에 실패했습니다.');
    } finally {
      if (id === revision.current) setRunning(false);
    }
  }, [fromYear, toYear, eventYear, windowSize, plan, target, pvYield, effortBasis, measures, region]);
  const runRef = useRef(run); runRef.current = run;
  // A link to another region switches the analysis scope first (once).
  useEffect(() => { if (link && link.region !== undefined && link.region !== region) setAnalysisScope({ region: link.region }, { fromLink: true }); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  // Another region: its 행정동, zones and grids are different, so start over there.
  const shownRegion = useRef(link && link.region !== undefined ? link.region : region);
  useEffect(() => {
    if (shownRegion.current === region) return;
    shownRegion.current = region;
    revision.current++; lastSpec.current = null; started.current = false; optionsReady.current = false;
    setAnalysis(null); setBundle(null); setAdminCode(''); setCategory(''); setCenter(null); setVertices([]); setError(null);
  }, [region]);

  // 변화 모델(U3 S5, 설계 Q1 가): 빠른 답이 온 뒤 그 요청의 구역 칸 · 용도 줄 · 몇 년 뒤로 한 번 묻는다.
  // 목표 % · 기준 건물 · 발전량만 바뀌면 이 요청이 같아 다시 묻지 않는다.
  const grids = analysis?.history.area.grid_ids;
  const teamRequest = useMemo<TeamAreaRequest | null>(() => (bundle && grids
    ? { region: bundle.sent.region, grids, new: bundle.sent.new, removed: bundle.sent.removed, years_after: bundle.sent.years_after } : null), [bundle, grids]);
  const team = useTeamAreaPrediction(teamRequest);

  const specFor = useCallback((m: AreaMode, over: Partial<{ code: string; category: string; center: [number, number]; vertices: Array<[number, number]> }> = {}) =>
    buildSpec(m, { code: over.code ?? adminCode, category: over.category ?? category, grid: options.data?.default_grid, center: over.center ?? center, radius, vertices: over.vertices ?? vertices }), [adminCode, category, options.data, center, radius, vertices]);

  // First analysis once the defaults are known (declared before the region reset above uses it).

  useEffect(() => {
    if (started.current || !options.data || !optionsReady.current) return;   // the previous region's options are still on screen
    if (link && link.region !== undefined && link.region !== region) return;   // wait for the linked region
    const first = link?.spec ?? (adminCode ? { type: 'admin' as const, code: adminCode } : null);
    if (!first) return;
    started.current = true; void runRef.current(first);
  }, [adminCode, options.data, region]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setLinkUrl(null); }, [analysis]);
  const copyLink = () => {
    const path = areaLink(lastSpec.current, { region, from: fromYear, to: toYear, event: eventYear, window: windowSize, plan, target, pv: pvYield, basis: effortBasis, measures });
    if (!path) { setLinkUrl('직접 그린 구역은 링크로 옮길 수 없습니다. 행정동·반경·용도지역·기준 격자로 고르세요.'); return; }
    const url = window.location.origin + path;
    setLinkUrl(url);
    void navigator.clipboard?.writeText(url).catch(() => undefined);
  };

  // Parameter changes re-run the last area (debounced) — the engine recomputes every number.
  useEffect(() => {
    if (!lastSpec.current) return;
    const timer = window.setTimeout(() => { if (lastSpec.current) void runRef.current(lastSpec.current); }, 450);
    return () => window.clearTimeout(timer);
  }, [fromYear, toYear, eventYear, windowSize, plan, target, pvYield, effortBasis, measures]);
  useEffect(() => {
    if (mode !== 'circle' || !center || lastSpec.current?.type !== 'circle') return;
    const timer = window.setTimeout(() => void runRef.current(specFor('circle')), 450);
    return () => window.clearTimeout(timer);
  }, [radius]); // eslint-disable-line react-hooks/exhaustive-deps

  // Year slider playback
  const years = analysis?.history.years ?? [];
  useEffect(() => {
    if (!playing || !years.length) return;
    const timer = window.setInterval(() => setSlider((s) => { if (s >= years[years.length - 1]) { setPlaying(false); return s; } return s + 1; }), 900);
    return () => window.clearInterval(timer);
  }, [playing, years]);

  const pickAdmin = (code: string) => { setAdminCode(code); if (mode === 'admin') void run({ type: 'admin', code }); };
  const pickPoint = (point: [number, number]) => {
    if (mode === 'circle') { setCenter(point); void run(specFor('circle', { center: point })); }
    if (mode === 'polygon') setVertices((v) => [...v, point]);
  };
  const changeMode = (next: AreaMode) => {
    setMode(next); setError(null);
    if (next === 'admin' && adminCode) void run({ type: 'admin', code: adminCode });
    if (next === 'zone' && category) void run({ type: 'zone', category });
    if (next === 'grid') void run(specFor('grid'));
  };

  // 같은 시·군·구 행정동 원단위 분포: 감축 기준(자동 전환 포함)과 기간이 바뀔 때만 다시 받는다. 실패해도 화면은 그대로.
  // 탄소공간지도 기준(kcsm)은 관측 원단위가 아니라 비교표가 없다: 행정동 비교는 관측 기준에서만.
  const benchBasis = analysis?.effort?.available && analysis.effort.basis !== 'kcsm' ? analysis.effort.basis ?? null : null;
  useEffect(() => {
    if (!benchBasis) { setBench(null); return; }
    let live = true;
    const params = new URLSearchParams({ from_year: String(fromYear), to_year: String(toYear), basis: benchBasis });
    if (region) params.set('region', region);
    api<Benchmark>(`/areas/benchmark?${params.toString()}`).then((b) => { if (live) setBench(b); }).catch(() => { if (live) setBench(null); });
    return () => { live = false; };
  }, [benchBasis, fromYear, toYear, region]);

  const activeEvent = analysis?.before_after.available ? analysis.before_after.event_year ?? null : null;

  if (options.loading) return <div className="page"><LoadingState label="지역 목록을 불러오는 중입니다" /></div>;
  if (options.error || !options.data) return <div className="page"><ErrorState message={options.error} onRetry={options.reload} /></div>;
  const o = options.data;

  return <div className="page area-page" data-testid="area-page">
    <PageHeader title="지역 개발 시뮬레이션" description="구역을 고르면 기준 배출, 계획 반영, 필요 감축량, 감축 방안을 한 줄로 먼저 보여 줍니다. 근거 자료와 계산 가정은 접힌 구역을 눌러 펼칩니다." action={<div className="badge-row"><span className="badge warn"><Info size={13} />운영 단계 1차 추정</span><FoldAllButton /><Link className="button ghost small" to="/guide#area">사용 방법</Link></div>} />

    <section className="panel area-controls" aria-label="분석 구역 선택" id="area-step-area">
      <div className="area-modes" role="tablist" aria-label="구역 선택 방식">
        {MODES.map((m) => <button key={m} role="tab" aria-selected={mode === m} onClick={() => changeMode(m)} disabled={m === 'grid' && !o.default_grid}>{MODE_LABEL[m]}</button>)}
      </div>
      <div className="area-control-row">
        {mode === 'admin' && <label className="area-select"><span>행정동 ({o.admin.length}개)</span><select value={adminCode} onChange={(e) => pickAdmin(e.target.value)}>{o.admin.map((a) => <option key={a.code} value={a.code}>{a.name}</option>)}</select></label>}
        {mode === 'zone' && <label className="area-select"><span>용도지역 (주 용도 격자 묶음)</span><select value={category} onChange={(e) => { setCategory(e.target.value); void run({ type: 'zone', category: e.target.value }); }}>{o.zones.map((z) => <option key={z.category} value={z.category}>{z.label} · 격자 {z.grids}개</option>)}</select></label>}
        {mode === 'circle' && <><label className="area-select narrow"><span>반경</span><div className="with-unit"><input type="number" min={100} max={5000} step={100} value={radius} onChange={(e) => setRadius(Number(e.target.value))} /><em>m</em></div></label><p className="area-hint">{center ? `중심 ${center[1].toFixed(4)}, ${center[0].toFixed(4)} — 지도를 다시 누르면 옮깁니다.` : '지도에서 개발 예정지 중심을 누르세요.'}</p></>}
        {mode === 'polygon' && <><p className="area-hint">지도를 눌러 꼭짓점을 찍습니다 ({vertices.length}개).</p><button className="button small" onClick={() => setVertices((v) => v.slice(0, -1))} disabled={!vertices.length}><Undo2 size={14} />마지막 점 취소</button><button className="button small" onClick={() => setVertices([])} disabled={!vertices.length}><RotateCcw size={14} />지우기</button><button className="button small primary" onClick={() => void run(specFor('polygon'))} disabled={vertices.length < 3}>구역 확정·분석</button></>}
        {mode === 'grid' && <p className="area-hint">예비 선정 격자 <code>{o.default_grid}</code> (500m).</p>}
        <label className="area-select narrow"><span>시작 연도</span><select value={fromYear} onChange={(e) => setFromYear(Number(e.target.value))}>{yearChoiceList.map(yearOption)}</select></label>
        <label className="area-select narrow"><span>끝 연도</span><select value={toYear} onChange={(e) => setToYear(Number(e.target.value))}>{yearChoiceList.map(yearOption)}</select></label>
        {running && <span className="area-running" role="status"><span className="spinner" aria-hidden="true" />계산 중{elapsed >= 8 ? ` ${elapsed}초` : ''}</span>}
        <button type="button" className="button ghost small area-link-button" onClick={copyLink} disabled={!analysis} title="이 구역·기간·계획·목표를 주소로 복사합니다"><Link2 size={14} />링크 복사</button>
      </div>
      {linkUrl && <label className="case-link"><span>이 조건의 링크 (다른 PC에서 열면 같은 구역·입력으로 시작)</span><input readOnly value={linkUrl} onFocus={(event) => event.currentTarget.select()} /></label>}
      {error && <p className="form-error" role="alert">{error}</p>}
      <Fold className="slim" title="이 구역에 자료가 있는 연도와 수집 진행" hint="펼치기"><CoverageStrip analysis={analysis} collection={collection.data} regionName={region ? (options.data?.region?.short_name ?? null) : null} /></Fold>
    </section>

    <AreaSummaryBar analysis={analysis} running={running} bench={bench} />

    <div className="area-workspace">
      <div className="area-map-stage">
        <AreaMap adminGeojson={o.admin_geojson} mode={mode} adminCode={adminCode} center={center} radius={radius} vertices={vertices} analysis={analysis} sliderYear={slider} eventYear={activeEvent} onPickAdmin={pickAdmin} onPickPoint={pickPoint} />
      </div>
      {analysis ? <YearPanel analysis={analysis} year={slider} setYear={setSlider} playing={playing} setPlaying={setPlaying} eventYear={activeEvent} /> : <div className="panel"><EmptyState title={running ? '계산 중입니다' : '구역을 고르세요'} description={running ? slowLoadText(elapsed) : '행정동을 고르거나 지도에서 위치를 누르면 계산합니다.'} /></div>}
    </div>

    {analysis && <>
      <div className="section-label" id="area-step-plan"><h2>계획 넣기</h2><span>용도별 신축 · 철거 연면적을 한 곳에 넣으면 감축 계산과 변화 모델이 같은 계획을 씁니다. 값을 바꾸면 다시 계산합니다</span></div>
      <PlanPanel plan={plan} setPlan={setPlan} target={target} setTarget={setTarget} pvYield={pvYield} setPvYield={setPvYield} basis={effortBasis} setBasis={setEffortBasis}
        kcsmAvailable={!!analysis.history.kcsm?.available} effort={analysis.effort} received={bundle?.plan ?? null} error={error} />

      <div className="section-label" id="area-step-result"><h2>결과</h2><span>원단위 기반 계산을 먼저, 변화 모델은 다른 범위로 나란히 둡니다. 두 값은 더하거나 평균하지 않습니다</span></div>
      <PlanResultPanel bundle={bundle} effort={analysis.effort} team={team} teamRequest={teamRequest} />
      <TeamAreaPanel team={team} request={teamRequest} fallback={intensityFallback(analysis.effort)} />
      <EffortResultPanel effort={analysis.effort} />
      <BenchmarkPanel bench={bench} effort={analysis.effort} regionName={options.data?.region?.short_name ?? '시·군·구'} />

      <div className="section-label" id="area-step-measures"><h2>감축 방안</h2><span>구체적 방안을 순서대로 더해 필요 감축량을 채웁니다. 다른 안과 비교하지 않습니다</span></div>
      <MeasuresPanel effort={analysis.effort} measures={measures} setMeasures={setMeasures} />

      <div className="section-label" id="area-step-site"><h2>배치·상한 확인 (선택)</h2><span>3D 배치와 조례 상한은 지금은 한 칸 화면에서 봅니다</span></div>
      <section className="panel area-site-step" aria-label="배치·상한 확인" data-testid="area-site-step">
        <p className="muted">구역의 칸 하나에 대지를 놓고 건폐율 · 용적률 상한을 확인하는 단계는 이 화면에 다음에 붙습니다. 지금은 <Link to="/simulation">탄소 시뮬레이션(한 칸 계획안)</Link>에서 대지 · 동수 · 층수를 넣어 3D 배치 · 조례 상한과 전력 + 가스 계획안을 봅니다. 그 값은 위 세 범위 표의 '한 칸 계획안'이며 이 화면의 값과 더하지 않습니다.</p>
      </section>

      <div className="section-label" id="area-step-report"><h2>보고서</h2><span>계산 엔진의 근거 문장으로 작성하고, 로컬 AI 문장은 숫자 검증을 통과할 때만 씁니다. 용도 줄이 있으면 변화 예측 절이 들어갑니다</span></div>
      <ReportPanel request={() => ({ area: lastSpec.current, region, from_year: fromYear, to_year: toYear, event_year: eventYear, window: windowSize, plan: planBody(plan), target_pct: target, pv_yield_kwh_per_kw: pvYield && Number(pvYield) > 0 ? Number(pvYield) : null, effort_basis: effortBasis, measures: measuresBody(measures),
        uses_new: usesBody(plan.uses_new), uses_removed: usesBody(plan.uses_removed), years_after: plan.years_after })} label={analysis.history.area.label} />

      <Fold title="근거 자료" hint="과거와 현재 · 개발 전후 · 기상 · 인구 · 대장 · 건물 전체 에너지" flat={false} id="area-evidence" testId="area-evidence">
      <div className="section-label"><h2>과거와 현재</h2><span>{analysis.history.years[0]}~{analysis.history.years[analysis.history.years.length - 1]} · {analysis.history.area.label}</span></div>
      <div className="content-grid two-up area-charts">
        <section className="panel"><div className="panel-title"><h3>연도별 전력 사용량</h3><div className="badge-row"><ProvenanceBadge kind="observed" detail="12개월 완전 지번" /><ProvenanceBadge kind="estimated" /></div></div><ElectricityChart history={analysis.history} eventYear={activeEvent} /><Note><p className="muted">막대는 12개월이 모두 관측된 단지만 더한 값을 단지 준공 시기별로 나눈 것입니다. 점선은 그 해까지 준공된 단지 연면적 × {analysis.history.region_label ?? '전주'} 관측 원단위로 낸 추정입니다. 전력은 모든 연도를 K-apt 관리비 전력 한 출처로 셉니다(건축HUB 계측값은 같은 단지에서 K-apt보다 커서, 섞으면 사용량이 늘어난 것처럼 보입니다). 건축HUB 값은 아래 '건물 전체 에너지'에 따로 둡니다.</p></Note></section>
        <section className="panel"><div className="panel-title"><h3>개발 이력 (사용승인 세대)</h3><ProvenanceBadge kind="computed" detail="K-apt 사용승인일" /></div><DevelopmentChart history={analysis.history} eventYear={activeEvent} /><Note><p className="muted">호박색 막대가 전후 비교에 쓰는 개발 연도입니다. 막대를 누르거나 마우스를 올리면 단지명이 보입니다.</p></Note></section>
      </div>
      <FoldStack title="근거 자료 더 보기" hint="기상, 인구, 건물 전체 에너지, 추정, 외부 기준과의 대조입니다. 눌러서 펼칩니다.">
        <Fold title="기상 추이"><section className="panel"><div className="panel-title"><h3>기상 (난방도일·냉방도일)</h3><ProvenanceBadge kind={region ? 'estimated' : 'observed'} detail={region ? 'ERA5-Land 재분석' : 'ASOS 전주'} /></div><WeatherYearsChart history={analysis.history} /><p className="muted">12개월이 모두 있는 해만 그립니다. 전후 사용량 차이의 일부는 기상 차이일 수 있습니다.</p></section></Fold>
        {analysis.history.region_guide && <Fold title="지역 기후·지자체 계획 가이드"><RegionGuidePanel analysis={analysis} /></Fold>}
        <Fold title="인구·가구 추이"><PopulationPanel analysis={analysis} /></Fold>
        <Fold title="건축물대장 개발 이력"><RegisterPanel analysis={analysis} eventYear={activeEvent} /></Fold>
        <Fold title="건물 전체 에너지 표"><BuildingEnergyPanel analysis={analysis} /></Fold>
        {analysis.history.estimates?.available && <Fold title="빈 자료 보정과 추정"><EstimatesPanel analysis={analysis} /></Fold>}
        {analysis.history.industry?.available && analysis.history.industry.table.length > 0 && <Fold title="업계·정부 기준 대조"><IndustryPanel analysis={analysis} /></Fold>}
        {analysis.history.kcsm && <Fold title="탄소공간지도 100m 건물 전기 배출"><KcsmPanel analysis={analysis} /></Fold>}
        <Fold title="지역 특성 (인구·사업체)"><SgisAreaPanel analysis={analysis} /></Fold>
      </FoldStack>

      <div className="section-label"><h2>개발 전후 영향</h2><span>개발 연도는 전환기라 제외하고 앞뒤 {windowSize}년 평균을 비교합니다</span></div>
      <BeforeAfterPanel comparison={analysis.before_after} candidates={eventYears(analysis.history)} eventYear={eventYear} setEventYear={setEventYear} windowSize={windowSize} setWindowSize={setWindowSize} />
      </Fold>
    </>}
  </div>;
}

function CoverageStrip({ analysis, collection, regionName }: { analysis: AreaAnalysis | null; collection: CollectionStatus | null; regionName?: string | null }) {
  const cov = analysis?.history.coverage;
  const summary = collection?.summary ?? {};
  const datasets = Object.keys(summary);
  const list = (ys: number[] | undefined) => (ys && ys.length ? ys.join(', ') : '없음');
  const hub = Object.values(analysis?.history.building_energy?.years ?? {}).filter((v) => v.electricity_kwh !== null).sort((a, b) => a.year - b.year);
  const hubText = hub.length ? hub.map((v) => `${v.year}${v.complete === false ? '(수집 중)' : v.provider_gap ? '(일부 결측)' : ''}`).join(', ') : '없음';
  return <div className="area-coverage">
    {cov && <dl>
      <div><dt>공동주택 전력 관측 연도 (K-apt)</dt><dd>{list(cov.energy_years)}</dd></div>
      <div><dt>건물 전체 계측 연도 (건축HUB)</dt><dd>{hubText}</dd></div>
      <div><dt>기상 12개월 연도</dt><dd>{list(cov.weather_years)}</dd></div>
      <div><dt>인구 연도</dt><dd>{list(cov.population_years)}</dd></div>
      <div><dt>구역</dt><dd>격자 {cov.grid_count}개 · 단지 {cov.complex_count}곳</dd></div>
    </dl>}
    <p className="area-collect">{regionName
      ? <>이 지역({regionName})에서 이 구역에 실제로 있는 연도는 왼쪽과 같습니다. 없는 연도는 0이 아니라 아직 수집하지 않았거나 제공되지 않은 자료입니다. 지역별 수집 단계는 <Link to="/regions">전국 지역</Link>에서 봅니다.</>
      : datasets.length
      ? <><span className="area-collect-title">과거 수집 진행 (연도·항목 수)</span><span className="area-collect-list">{datasets.map((d) => <span key={d} className="area-collect-item"><b>{DATASET_LABEL[d] ?? d}</b>{Object.entries(summary[d]).map(([st, n]) => <em key={st} className={`st-${st.toLowerCase()}`}>{statusLabel(st)} {n}</em>)}</span>)}</span></>
      : <>과거 연도 자료는 아직 수집하지 않았습니다. <Link to="/data#collect-missing">수집 데이터 → 빠진 자료 전부 수집</Link> 버튼을 누르거나 PC에서 <code>scripts\dss.cmd CollectAll</code>을 실행하면 채워집니다 (일일 한도에 걸리면 다음 날 자동으로 이어서).</>}</p>
  </div>;
}

function statusLabel(status: string) { return ({ DONE: '완료', NOT_PUBLISHED: '미공개', PARTIAL: '일부', FAILED: '실패', BLOCKED: '보류', TODO: '대기', RETRY: '재시도', WAITING: '대기' } as Record<string, string>)[status] ?? status; }

function YearPanel({ analysis, year, setYear, playing, setPlaying, eventYear }: { analysis: AreaAnalysis; year: number; setYear: (y: number) => void; playing: boolean; setPlaying: (p: boolean) => void; eventYear: number | null }) {
  const h = analysis.history;
  const first = h.years[0]; const last = h.years[h.years.length - 1];
  const stock = at(h.stock, year); const ev = at(h.events, year); const e = at(h.energy, year); const pop = at(h.population, year);
  const elec = e?.electricity;
  const collected = h.coverage.energy_years.length > 0;
  return <section className="panel area-year" aria-label="연도별 상태">
    <div className="panel-title"><h3>{h.area.label}</h3><small>{h.area.method}</small></div>
    {h.area.warnings?.map((w) => <p key={w} className="status-tag warn area-warning" role="note">{w}</p>)}
    <div className="area-slider">
      <button className="button small" onClick={() => { if (!playing && year >= last) setYear(first); setPlaying(!playing); }} aria-label={playing ? '재생 멈춤' : '연도 재생'}>{playing ? <Pause size={14} /> : <Play size={14} />}{playing ? '멈춤' : '재생'}</button>
      <input type="range" min={first} max={last} step={1} value={year} onChange={(ev2) => { setPlaying(false); setYear(Number(ev2.target.value)); }} aria-label="시점 연도" />
      <strong>{year}년{year === eventYear ? ' · 개발 연도' : ''}</strong>
    </div>
    <div className="metric-grid dense">
      <MetricCard dense title="준공 누적 세대" value={stock?.households} unit="세대" provenance="computed" />
      <MetricCard dense title="전력 관측" value={elec?.kwh} unit="kWh" provenance="observed" basis={elec?.kwh != null ? `12개월 관측 ${elec.complete_parcels}곳` : undefined} missingReason={collected ? '12개월이 모두 관측된 지번이 없습니다.' : '과거 전력을 아직 수집하지 않았습니다.'} />
      <MetricCard dense title="전력 탄소 (관측)" value={e?.electricity_carbon_kgco2eq} unit="kgCO₂eq" provenance="computed" basis="관측 전력 기준" missingReason="관측 전력이 없어 계산하지 않았습니다." />
      <MetricCard dense title="인구" value={pop?.population} unit="명" provenance="observed" basis={pop?.basis} missingReason={`${year}년 SGIS 인구가 이 도구에 없습니다(제공기관 공표 전이거나 아직 받지 않음).`} />
    </div>
    <Fold className="slim" title="이 해의 지표 4개 더 보기" hint="펼치기">
      <div className="metric-grid dense">
        <MetricCard dense title="준공 누적 단지" value={stock?.complexes} unit="곳" provenance="computed" basis="K-apt 사용승인일 기준" />
        <MetricCard dense title="연면적 확인 단지 합계" value={stock?.gfa_m2} unit="m²" provenance="computed" basis={stock?.gfa_excluded ? `연면적 이상 ${stock.gfa_excluded}곳 제외` : undefined} />
        <MetricCard dense title="이 해 사용승인" value={ev?.households ?? 0} unit="세대" provenance="computed" basis={ev?.complexes ? `${ev.complexes}개 단지` : '없음'} />
        <MetricCard dense title="전력 추정" value={e?.estimated?.kwh} unit="kWh" provenance="estimated" basis={`연면적 × ${h.region_label ?? '전주'} 원단위`} missingReason="연면적이 확인된 단지가 없습니다." />
      </div>
    </Fold>
    <Note label="전력 탄소 계산 기준"><p className="muted">{h.factor_basis}</p></Note>
  </section>;
}

function RegisterPanel({ analysis, eventYear }: { analysis: AreaAnalysis; eventYear: number | null }) {
  const reg = analysis.history.register;
  return <section className="panel area-register"><div className="panel-title"><h3>모든 건물의 개발 이력 (건축물대장)</h3><ProvenanceBadge kind="observed" detail="건축물대장 표제부" /></div>
    {reg?.linked_in_area ? <>
      <RegisterChart history={analysis.history} eventYear={eventYear} />
      <p className="muted">구역 격자 안 건물 {formatMetric(reg.linked_in_area)}동의 사용승인일 기준입니다(아파트 외 상가·업무·공공 건물 포함).{reg.unknown_year ? ` 사용승인일을 읽을 수 없는 ${formatMetric(reg.unknown_year)}동은 뺐습니다.` : ''} 연면적이 비어 있는 건물은 0이 아니라 합계에서 빠집니다.</p>
    </> : <EmptyState title={reg?.available ? '이 구역에 연결된 대장 건물이 없습니다' : '건축물대장을 아직 수집하지 않았습니다'} description={reg?.available ? '대장 건물의 위치(격자)는 연속지적 전체 수집 뒤 연결됩니다.' : "수집 데이터 화면의 '빠진 자료 전부 수집'으로 받을 수 있습니다 (건축물대장 활용신청 승인 필요)."} />}
  </section>;
}

/** 구역 격자 안 건축HUB 계측 건물 전체(전주 2020-). 공동주택 시계열과 따로 둔다. */
/** '2025년 3곳 5,836,169 kWh', or '2021년 없음': an empty set has no usage to report, not 0 kWh. */
function onlyIn(year: number, parcels: number, kwh: number) { return parcels ? `${year}년 ${formatMetric(parcels)}곳 ${formatMetric(kwh, 'kWh')}` : `${year}년 없음`; }

function BuildingEnergyPanel({ analysis }: { analysis: AreaAnalysis }) {
  const be = analysis.history.building_energy;
  const years = be ? Object.values(be.years).sort((a, b) => a.year - b.year) : [];
  return <section className="panel area-building-energy" aria-label="건물 전체 에너지">
    <div className="panel-title"><h3>건물 전체 에너지 (건축HUB 전 지번)</h3><ProvenanceBadge kind="observed" detail="12개월 계측 지번" /></div>
    {years.length ? <><div className="table-wrap"><table>
      <thead><tr><th>연도</th><th className="num">계측 지번</th><th className="num">전력 kWh</th><th className="num">가스 kWh</th><th className="num">전력 원단위 kWh/m²</th><th className="num">전력 탄소 tCO₂eq</th></tr></thead>
      <tbody>{years.map((v) => <tr key={v.year}><td>{v.year}{v.complete === false && <small className="status-tag warn">수집 중</small>}{v.provider_gap && <small className="status-tag warn" title={v.provider_gap}>일부 결측·비교 제외</small>}</td><td className="num">{formatMetric(v.parcels)}<small> (12개월 {formatMetric(v.electricity_complete)})</small></td><td className="num">{formatMetric(v.electricity_kwh)}</td><td className="num">{formatMetric(v.gas_kwh)}</td><td className="num">{formatMetric(v.kwh_per_m2, '', 1)}</td><td className="num">{v.electricity_carbon_kgco2eq === null ? '자료 없음' : formatMetric(v.electricity_carbon_kgco2eq / 1000, '', 1)}</td></tr>)}</tbody>
    </table></div>
    {be?.trend && be.trend.same_change_pct !== null && <p className="area-building-trend"><b>같은 지번 비교 ({be.trend.from}→{be.trend.to}):</b> 두 해 모두 12개월 계측된 지번 {formatMetric(be.trend.same_parcels)}곳의 전력 {formatMetric(be.trend.same_from_kwh, 'kWh')} → {formatMetric(be.trend.same_to_kwh, 'kWh')} ({be.trend.same_change_pct > 0 ? '+' : ''}{be.trend.same_change_pct.toFixed(1)}%). 한 해에만 계측된 지번: {onlyIn(be.trend.to, be.trend.new_parcels, be.trend.new_kwh)}, {onlyIn(be.trend.from, be.trend.gone_parcels, be.trend.gone_kwh)} (신축·계량 변경·다른 지번으로의 기록 이동이 섞일 수 있음). 공동주택 지번은 건축HUB가 싣는 범위가 해마다 넓어져, 같은 지번 비교에도 그 몫이 섞입니다(같은 단지의 K-apt 관리비 전력과 대조해 확인).</p>}
    <p className="muted">상가·업무·학교·대형 공동주택 등 건축HUB가 계측하는 모든 지번의 합계입니다(연속지적 대표점으로 격자 배치). 단독주택, 200세대 미만 공동주택, 산업·수송용은 제공 범위 밖이라 빠집니다. 건축HUB는 2020년 1월분부터 있습니다(전주 2020~, 수원·완주 2024~). {years.filter((v) => v.provider_gap).map((v) => `${v.year}년: ${v.provider_gap}. `).join('')}원단위는 같은 필지의 건축물대장 연면적 기준입니다.</p></>
      : <EmptyState title="이 구역의 건물 전체 에너지가 아직 없습니다" description="건축HUB 전 지번 수집(2020년~)이 끝나면 채워집니다. 구역 격자 안에 계측 지번이 없을 수도 있습니다(단독주택 위주)." />}
  </section>;
}

/** 빈 자료 보정·추정 (DATA_STANDARD 4.1): 관측 표 옆에 따로 둔다. 2015~2019 건물 전체는 되돌림 추정, 2020~는 계측 달 + 빈 달 채움. */
export function EstimatesPanel({ analysis }: { analysis: AreaAnalysis }) {
  const est = analysis.history.estimates;
  if (!est?.available) return null;
  const buildings = Object.values(est.buildings ?? {}).sort((a, b) => a.year - b.year);
  const apartments = Object.values(est.apartments ?? {}).sort((a, b) => a.year - b.year);
  const population = Object.values(est.population ?? {}).sort((a, b) => a.year - b.year);
  return <section className="panel area-estimates" aria-label="빈 자료 보정·추정" data-testid="area-estimates">
    <div className="panel-title"><h3>빈 자료 보정·추정</h3><ProvenanceBadge kind="estimated" detail="관측과 따로, 더하지 않음" /></div>
    {buildings.length > 0 && <div className="table-wrap"><table>
      <caption>건물 전체 전력 (건축HUB 계측 지번)</caption>
      <thead><tr><th>연도</th><th className="num">관측 kWh (12개월 지번)</th><th className="num">보정·추정 합계 kWh</th><th className="num">그중 추정분 kWh</th><th className="num">가스 보정·추정 kWh</th><th>방법</th></tr></thead>
      <tbody>{buildings.map((v) => <tr key={v.year} className={v.backcast ? 'is-estimated-row' : undefined}><td>{v.year}{v.complete === false && <small className="status-tag warn">수집 중</small>}{v.provider_gap && <small className="status-tag warn">일부 결측</small>}</td>
        <td className="num">{formatMetric(v.electricity_observed_kwh)}</td><td className="num">{formatMetric(v.electricity_kwh)}</td>
        <td className="num">{v.backcast ? formatMetric(v.electricity_kwh) : formatMetric(v.electricity_filled_kwh ?? null)}</td><td className="num">{formatMetric(v.gas_kwh)}</td>
        <td>{v.backcast ? '되돌림 추정 (2021년 지번 사용량 × 같은 단지 지수)' : v.electricity_filled_months ? `빈 달 ${formatMetric(v.electricity_filled_months)}개월 채움` : '계측 달 합'}</td></tr>)}</tbody>
    </table></div>}
    {apartments.length > 0 && <div className="table-wrap"><table>
      <caption>공동주택 전력 (K-apt)</caption>
      <thead><tr><th>연도</th><th className="num">관측 kWh (12개월 단지)</th><th className="num">추정 단지</th><th className="num">추정 kWh</th><th className="num">보정 합계 kWh</th></tr></thead>
      <tbody>{apartments.map((v) => <tr key={v.year}><td>{v.year}</td><td className="num">{formatMetric(v.observed_kwh)}<small> ({formatMetric(v.observed_complexes)}곳)</small></td><td className="num">{formatMetric(v.estimated_complexes)}{v.peer_median_complexes > 0 && <small> (미보고 {v.peer_median_complexes})</small>}</td><td className="num">{formatMetric(v.estimated_kwh)}</td><td className="num">{formatMetric(v.total_kwh)}</td></tr>)}</tbody>
    </table></div>}
    {population.length > 0 && <p className="area-estimate-note">{population.map((v) => `${v.year}년 행정동 인구 추정 ${formatMetric(v.population, '명')}${v.households !== null ? `, 가구 ${formatMetric(v.households)}` : ''}${v.trend_years?.length ? ` (${v.trend_years[0]}~${v.trend_years[v.trend_years.length - 1]}년 추세)` : ''}`).join(' · ')}</p>}
    <p className="muted">추정값은 관측 합계에 더하지 않고 나란히 둡니다. 2015~2019년 건물 전체 전력은 건축HUB가 제공하지 않아, 2021년에 계측된 지번 중 그해 있던 건물(건축물대장 사용승인)의 2021년 사용량에 공동주택 같은 단지끼리의 사용량 지수를 곱해 되돌렸습니다(관측 해 시험: 1년 떨어진 해 칸별 오차 합 7%, 3년 21%, 더 먼 해는 더 클 수 있음). 2020년 이후는 첫·마지막 계측 사이 3개월 이하로 빈 달만 같은 지번의 앞뒤 해로 채웠습니다. 방법과 시험 결과는 사용 방법 → 데이터 기준 4.1절에 있습니다.</p>
    {est.created_at && <p className="muted" data-testid="area-estimates-asof">추정 계산 {est.created_at.slice(0, 10)}{est.rule_version ? ` · 규칙 ${est.rule_version}` : ''} · 그 뒤에 받은 자료는 추정을 다시 계산해야(<code>estimate-gaps</code>) 반영됩니다.</p>}
  </section>;
}

/** 업계·정부 기준(1차에너지 환산, 효율등급 구간, 표준지표, ZEB 자립률) 위에 이 구역 값을 놓는다. 판정이 아니라 참고 위치. */
export function IndustryPanel({ analysis }: { analysis: AreaAnalysis }) {
  const ind = analysis.history.industry;
  if (!ind?.available || !ind.table.length) return null;
  return <section className="panel area-industry" aria-label="업계·정부 기준과 대조" data-testid="area-industry">
    <div className="panel-title"><h3>업계·정부 기준과 대조</h3><ProvenanceBadge kind="computed" detail="참고 위치, 판정 아님" /></div>
    <div className="table-wrap"><table>
      <thead><tr><th>항목</th><th className="num">이 구역</th><th>기준</th><th>출처</th></tr></thead>
      <tbody>{ind.table.map((r) => <tr key={r.label}><td>{r.label}</td><td className="num">{r.value}</td><td>{r.reference}</td><td><small>{r.source}</small></td></tr>)}</tbody>
    </table></div>
    <ul className="area-industry-notes">{ind.notes.map((n) => <li key={n}>{n}</li>)}</ul>
  </section>;
}


/** 선도소프트 탄소공간지도 100m 건물 전기 배출: 경계 안 100m 칸 합, 같은 500m 격자 범위 합, 같은 범위의 이 도구 건축HUB 값(더하지 않고 비율만). */
export function KcsmPanel({ analysis }: { analysis: AreaAnalysis }) {
  const k = analysis.history.kcsm;
  if (!k) return null;
  const years = Object.values(k.years ?? {}).sort((a, b) => a.year - b.year);
  const t1 = (v: number | null | undefined) => (v == null ? '자료 없음' : formatMetric(v, '', 1));
  return <section className="panel area-kcsm" aria-label="탄소공간지도 100m 전력 배출" data-testid="area-kcsm">
    <div className="panel-title"><h3>건물 전기 배출 (탄소공간지도 100m · 선도소프트 제공)</h3><div className="badge-row"><ProvenanceBadge kind="computed" detail="제공기관 산정값" /><span className="status-tag neutral">이 PC에서만</span></div></div>
    {!k.available || !years.length ? <EmptyState title="이 구역에는 100m 전력 배출 자료가 없습니다" description={k.reason ?? '전주시 2023·2024년만 받았습니다.'} /> : <>
      <div className="table-wrap"><table>
        <thead><tr><th>연도</th><th className="num">{k.boundary_basis ?? '경계 안 100m 칸'}</th><th className="num">tCO₂eq (경계 기준)</th><th className="num">tCO₂eq (500m 격자 범위)</th><th className="num">건축HUB 계측 tCO₂eq (같은 격자)</th><th className="num">급감 칸</th></tr></thead>
        <tbody>{years.map((v) => <tr key={v.year}>
          <td>{v.year}{v.change_pct != null && <small className="muted"> ({v.change_pct > 0 ? '+' : ''}{v.change_pct.toFixed(1)}%)</small>}</td>
          <td className="num">{formatMetric(v.cells)}<small> (값 {formatMetric(v.value_cells)} · 0 {formatMetric(v.zero_cells)})</small></td>
          <td className="num"><b>{t1(v.boundary_t)}</b></td>
          <td className="num">{t1(v.grid_t)}<small> ({formatMetric(v.grid_cells)}칸)</small></td>
          <td className="num">{v.tool ? <>{t1(v.tool.t)}<small> ({v.tool.share_pct == null ? '—' : `${v.tool.share_pct.toFixed(1)}%`})</small></> : '자료 없음'}</td>
          <td className="num">{v.drop_cells ? <span className="status-tag warn" title={`앞 해 ${t1(v.drop_from_t)} → ${t1(v.drop_now_t)} tCO₂eq`}>{v.drop_cells}칸</span> : '없음'}</td>
        </tr>)}</tbody>
      </table></div>
      <p className="muted">{k.note} 건축HUB 값은 같은 500m 격자의 12개월 계측 지번 전력 × 그해 승인 계수이고, 괄호 안은 탄소공간지도 값에 대한 비율입니다(단독주택·200세대 미만 공동주택은 건축HUB 범위 밖). 급감 칸은 앞 해 100 tCO₂eq 이상이던 칸이 절반 아래로 줄어든 칸으로, 원자료 누락이 의심되어 표시만 합니다.</p>
    </>}
  </section>;
}

/** 구역이 걸친 SGIS 1km 격자 전체의 합(관측)과, 면적 비례로 나눈 참고값(추정)을 나란히 둔다. */
function SgisAreaPanel({ analysis }: { analysis: AreaAnalysis }) {
  const sg = analysis.history.sgis_grid;
  return <section className="panel area-sgis" aria-label="지역 특성 (SGIS 1km 격자)">
    <div className="panel-title"><h3>지역 특성 (SGIS 1km 격자{sg ? ` ${sg.year}년` : ''})</h3><div className="badge-row"><ProvenanceBadge kind="observed" detail="1km 격자 합계" />{sg?.overlap && <ProvenanceBadge kind="estimated" detail="구역 면적 비례" />}</div></div>
    {!sg ? <EmptyState title="SGIS 격자 통계를 아직 가져오지 않았습니다" description="공공데이터포털 'SGIS 격자 통계 및 경계' 파일을 잘라 두면 API 시작 때 자동으로 들어옵니다 (사용 방법 → SGIS 격자 통계)." />
      : !sg.overlap ? <EmptyState title="이 구역이 걸친 1km 격자에는 공표된 통계가 없습니다" description="인구·사업체가 없거나 비공개인 격자이며 0이 아닙니다." />
      : <SgisGridSummaryView summary={sg.overlap}
          scope={<>구역이 걸친 1km 격자 <b>{sg.cells}개</b>(통계 있는 격자 {sg.cells_with_stats}개) 전체의 합계입니다. {sg.coverage_pct !== null && sg.coverage_pct < 99.9 ? <>구역은 이 격자 면적의 <b>{sg.coverage_pct.toFixed(1)}%</b>라 합계는 구역보다 넓은 범위입니다.</> : '구역이 이 격자들과 같은 범위입니다.'}</>}
          extra={sg.coverage_pct !== null && sg.coverage_pct < 99.9 ? <div className="is-estimated"><dt>구역 인구 (면적 비례 추정)</dt><dd>{formatMetric(sg.estimated.population, '명')}<small>{sg.estimated.basis}</small></dd></div> : undefined} />}
  </section>;
}

function PopulationPanel({ analysis }: { analysis: AreaAnalysis }) {
  const h = analysis.history;
  const rows = h.years.map((y) => ({ year: y, p: at(h.population, y) })).filter((r) => r.p?.population != null);
  return <section className="panel"><div className="panel-title"><h3>인구·가구 (행정동)</h3><ProvenanceBadge kind="observed" detail="SGIS" /></div>
    {rows.length ? <div className="table-wrap"><table><thead><tr><th>연도</th><th className="num">인구</th><th className="num">가구</th><th>기준</th></tr></thead><tbody>{rows.map(({ year, p }) => <tr key={year}><td>{year}</td><td className="num">{formatMetric(p?.population)}</td><td className="num">{formatMetric(p?.households)}</td><td><small>{p?.basis}</small></td></tr>)}</tbody></table></div>
      : <EmptyState title="인구 자료가 없습니다" description="이 구역과 겹치는 행정동의 SGIS 인구를 아직 수집하지 않았습니다." />}
    <p className="muted">{h.area.admin_exact ? '선택한 행정동의 값입니다.' : '구역과 겹치는 행정동 전체 값입니다. 격자·반경으로 나누어 배분하지 않았습니다.'} 수집 연도: {h.coverage.population_years.join(', ') || '없음'}</p>
  </section>;
}

/** 한 줄 수치. signed면 증감이라 양수에 +를 붙인다. 값이 없으면 0이 아니라 "자료 없음". */
/** 숫자 한 칸. caution이면(관측 범위가 달라 비교할 수 없는 값) 흐리게 해치를 깔고 '비교 주의'를 붙인다(F12). */
function Figure({ label, value, unit, digits = 0, note, signed = false, caution = false }: { label: string; value: number | null | undefined; unit: string; digits?: number; note?: ReactNode; signed?: boolean; caution?: boolean }) {
  const missing = value === null || value === undefined;
  return <div className={missing ? 'is-missing' : caution ? 'is-caution' : undefined}><dt>{label}{caution && !missing && <em className="caution-tag">비교 주의</em>}</dt><dd>{missing ? '자료 없음' : `${signed && value > 0 ? '+' : ''}${formatMetric(value, unit, digits)}`}{note && <small>{note}</small>}</dd></div>;
}

function BeforeAfterPanel({ comparison, candidates, eventYear, setEventYear, windowSize, setWindowSize }: { comparison: BeforeAfter; candidates: number[]; eventYear: number | null; setEventYear: (y: number | null) => void; windowSize: number; setWindowSize: (w: number) => void }) {
  const m = comparison.metrics;
  return <section className="panel area-before-after">
    <div className="area-inline-controls">
      <label className="area-select"><span>개발 연도</span><select value={eventYear ?? ''} onChange={(e) => setEventYear(e.target.value ? Number(e.target.value) : null)}><option value="">자동 (세대 증가가 가장 큰 해{comparison.available && !eventYear ? ` · ${comparison.event_year}` : ''})</option>{candidates.map((y) => <option key={y} value={y}>{y}</option>)}</select></label>
      <label className="area-select narrow"><span>비교 기간</span><select value={windowSize} onChange={(e) => setWindowSize(Number(e.target.value))}>{[1, 2, 3, 4, 5].map((w) => <option key={w} value={w}>앞뒤 {w}년</option>)}</select></label>
    </div>
    {!comparison.available ? <EmptyState title="비교할 개발이 없습니다" description={comparison.reason} /> : <>
      <p className="area-event"><b>{comparison.event_year}년</b> 사용승인 {comparison.event?.complexes}개 단지 · {formatMetric(comparison.event?.households)}세대 · 연면적 {formatMetric(comparison.event?.gfa_m2, 'm²')}<small>{(comparison.event?.names ?? []).join(', ')}</small></p>
      <div className="area-split">
        <BeforeAfterChart comparison={comparison} />
        <div>
          <h4 className="area-subhead">관측 <ProvenanceBadge kind="observed" /></h4>
          {comparison.coverage && comparison.coverage.comparable === false && <p className="area-fallback" role="note" data-testid="area-coverage-caution"><b>관측 범위 주의:</b> 개발 전 관측 단지가 평균 {formatMetric(comparison.coverage.before_parcels_mean, '곳', 1)}으로 개발 후 기존 단지 평균 {formatMetric(comparison.coverage.after_existing_parcels_mean, '곳', 1)}보다 적습니다. 지역 합계 변화에는 수집 범위 차이가 섞여 있습니다. {m?.electricity.existing_change_pct != null ? <>같은 단지끼리 비교한 <b>기존 단지만의 변화</b>를 보세요.</> : <>전후 모든 해에 관측된 같은 기존 단지가 없어 같은 단지 비교도 아직 할 수 없습니다(과거 연도 수집 뒤 다시 확인).</>}</p>}
          <dl className="area-figures">
            <Figure label="전력 연평균 변화" value={m?.electricity.total_change_pct} unit="%" digits={1} signed caution={comparison.coverage?.comparable === false} note={comparison.coverage ? `관측 연도 ${comparison.coverage.observed_before_years.join('·') || '없음'} → ${comparison.coverage.observed_after_years.join('·') || '없음'}` : undefined} />
            <Figure label="기존 단지만의 변화" value={m?.electricity.existing_change_pct} unit="%" digits={1} note={m?.electricity.existing_complexes ? `전후 모든 해에 보고한 같은 단지 ${m.electricity.existing_complexes}곳끼리` : '같은 단지끼리 비교'} signed />
            <Figure label="개발 후 신규 단지 비중" value={m?.electricity.new_share_pct} unit="%" digits={1} />
          </dl>
          <Fold className="slim" title="추정값과 맥락 (기상·인구) 보기" hint="펼치기">
          <h4 className="area-subhead">추정 <ProvenanceBadge kind="estimated" /></h4>
          <dl className="area-figures">
            <Figure label="이 개발로 늘어난 연면적" value={m?.estimated?.added_gfa_m2} unit="m²" />
            <Figure label="이 개발만의 전력 증가" value={m?.estimated?.event_added_kwh} unit="kWh/년" note={m?.estimated?.event_change_pct != null ? `직전 재고 대비 +${m.estimated.event_change_pct}%` : undefined} />
            <Figure label="전후 추정 변화 (다른 해 개발 포함)" value={m?.estimated?.change_pct} unit="%" digits={1} signed />
          </dl>
          <h4 className="area-subhead">맥락</h4>
          <dl className="area-figures">
            <Figure label="난방도일 전 → 후" value={comparison.weather?.before_hdd} unit="°C·일" note={comparison.weather?.after_hdd != null ? `→ ${formatMetric(comparison.weather.after_hdd, '°C·일')}` : undefined} />
            <Figure label="냉방도일 전 → 후" value={comparison.weather?.before_cdd} unit="°C·일" note={comparison.weather?.after_cdd != null ? `→ ${formatMetric(comparison.weather.after_cdd, '°C·일')}` : undefined} />
            <Figure label="인구 전 → 후" value={comparison.population?.before} unit="명" note={comparison.population?.after != null ? `→ ${formatMetric(comparison.population.after, '명')}` : comparison.population?.basis} />
          </dl>
          </Fold>
        </div>
      </div>
      {comparison.gaps?.length ? <Note label={`자료 공백 ${comparison.gaps.length}건`}><ul className="area-gaps">{comparison.gaps.map((g) => <li key={g}>{g}</li>)}</ul></Note> : null}
    </>}
  </section>;
}

/** U2-0(2026-11-23): 변화 모델이 없는 지역에서 대신 보일 원단위 기반 증가분(U4 plan_added 한 필드). 없으면 null. */
function intensityFallback(effort: EffortResult | null): { netAddedKgco2eq: number | null; baselineYear: number | null } | null {
  const added = effort?.targets?.find((t) => t.key === 'plan_added');
  return added ? { netAddedKgco2eq: added.net_added_kgco2eq, baselineYear: effort?.baseline_year ?? null } : null;
}

/** 용도 줄 하나: 용도 · 연면적 · (주거 줄만) 세대수. 용도 미정(옛 링크) 줄은 고르기 전까지 그 선택지를 둔다. */
function UseRowInput({ row, index, kind, onChange, onRemove }: { row: PlanUse; index: number; kind: '신축' | '철거'; onChange: (patch: Partial<PlanUse>) => void; onRemove?: () => void }) {
  const n = index + 1;
  return <div className="team-area-row" data-testid={kind === '신축' ? 'plan-use-row' : 'plan-removed-row'}>
    <label className="area-select"><span>{kind} 용도 {n}</span><select aria-label={`${kind} 용도 ${n}`} value={row.use ?? ''} onChange={(e) => onChange({ use: (e.target.value || null) as TeamUse | null })}>
      {row.use === null && <option value="">용도 미정 (변화 모델은 돌리지 않음)</option>}
      {TEAM_USES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
    </select></label>
    <label className="area-select narrow"><span>{kind} 연면적</span><div className="with-unit"><input type="number" min={0} max={3000000} step={1000} inputMode="numeric" aria-label={`${kind} 연면적 ${n}`} value={row.floor_area_m2 || ''} placeholder="예: 120000"
      onChange={(e) => onChange({ floor_area_m2: Math.max(0, Number(e.target.value) || 0) })} /><em>m²</em></div></label>
    {kind === '신축' && row.use === 'residential' && <label className="area-select narrow"><span>세대수 (선택)</span><div className="with-unit"><input type="number" min={0} max={50000} step={10} inputMode="numeric" aria-label={`세대수 ${n}`} value={row.dwellings || ''} placeholder="자동"
      onChange={(e) => onChange({ dwellings: Math.max(0, Number(e.target.value) || 0) || undefined })} /><em>세대</em></div></label>}
    {onRemove && <button type="button" className="button ghost small" aria-label={`${kind} 용도 ${n} 빼기`} onClick={onRemove}><X size={14} /></button>}
  </div>;
}

/**
 * 2단계 '계획 넣기'(U3 S5): 계획을 넣는 곳은 여기 하나. 연면적은 용도 줄의 합이고, 감축 계산 · 변화 모델 · 보고서가 같은 줄을 받는다.
 * 목표 % · 기준 건물 · 발전량은 '계산 설정'(접힘)에. 숫자 결과는 3단계에 둔다.
 */
function PlanPanel({ plan, setPlan, target, setTarget, pvYield, setPvYield, basis, setBasis, kcsmAvailable = false, effort, received, error }: { plan: PlanState; setPlan: (p: PlanState) => void; target: number; setTarget: (t: number) => void; pvYield: string; setPvYield: (v: string) => void; basis: EffortBasis; setBasis: (b: EffortBasis) => void; kcsmAvailable?: boolean; effort: EffortResult | null; received: PlanEvaluation['plan'] | null; error: string | null }) {
  const setRow = (side: 'uses_new' | 'uses_removed', i: number, patch: Partial<PlanUse>) => setPlan({ ...plan, [side]: plan[side].map((r, j) => (j === i ? { ...r, ...patch } : r)) });
  const dropRow = (side: 'uses_new' | 'uses_removed', i: number) => setPlan({ ...plan, [side]: plan[side].filter((_, j) => j !== i) });
  const shape = (key: 'floors' | 'building_count' | 'footprint_per_building', label: string, unit: string, step: number) => <label className="field" key={key}><span>{label}</span><div><input type="number" min={0} step={step} aria-label={label} value={plan[key] || ''} placeholder="선택"
    onChange={(e) => setPlan({ ...plan, [key]: Math.max(0, Number(e.target.value) || 0) })} /><em>{unit}</em></div></label>;
  const undecided = [...plan.uses_new, ...plan.uses_removed].some((r) => r.use === null && r.floor_area_m2 > 0);
  const nonResidential = plan.uses_new.some((r) => r.use !== null && r.use !== 'residential' && r.floor_area_m2 > 0);
  return <section className="panel area-plan" aria-label="계획 넣기" data-testid="area-plan">
    <div className="panel-title"><h3>계획 (한 곳에서 넣기)</h3><span className="status-tag neutral">예시값</span></div>
    <div className="area-plan-grid">
      <div className="team-area-rows" aria-label="용도별 신축 연면적">
        <h4 className="area-subhead">신축 (용도별 연면적 · 1~{AREA_MAX_USES}줄)</h4>
        {plan.uses_new.map((r, i) => <UseRowInput key={i} row={r} index={i} kind="신축" onChange={(p) => setRow('uses_new', i, p)} onRemove={plan.uses_new.length > 1 ? () => dropRow('uses_new', i) : undefined} />)}
        {plan.uses_new.length < AREA_MAX_USES && <button type="button" className="button ghost small" onClick={() => setPlan({ ...plan, uses_new: [...plan.uses_new, { use: 'commercial', floor_area_m2: 0 }] })}><Plus size={14} />용도 추가 (복합 개발)</button>}
      </div>
      <div className="team-area-rows" aria-label="용도별 철거 연면적">
        <h4 className="area-subhead">철거 (용도별 연면적 · 선택)</h4>
        {plan.uses_removed.map((r, i) => <UseRowInput key={i} row={r} index={i} kind="철거" onChange={(p) => setRow('uses_removed', i, p)} onRemove={() => dropRow('uses_removed', i)} />)}
        {plan.uses_removed.length < AREA_MAX_USES && <button type="button" className="button ghost small" onClick={() => setPlan({ ...plan, uses_removed: [...plan.uses_removed, { use: 'residential', floor_area_m2: 0 }] })}><Plus size={14} />철거 줄 추가</button>}
      </div>
    </div>
    <div className="field-grid">
      {shape('floors', '층수 (선택)', '층', 1)}{shape('building_count', '동수 (선택)', '동', 1)}{shape('footprint_per_building', '동당 건축면적 (선택)', 'm²', 50)}
      <label className="field"><span>몇 년 뒤 (변화 모델)</span><div><select aria-label="몇 년 뒤" value={plan.years_after} onChange={(e) => setPlan({ ...plan, years_after: Number(e.target.value) })}>{[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((y) => <option key={y} value={y}>{y}년 뒤</option>)}</select></div><span className="field-hint">평가한 개발 기간 중앙값 7년</span></label>
    </div>
    <p className="muted">층수만 넣으면 지붕 태양광 한도를 연면적 ÷ 층수로, 동수 · 동당 건축면적을 넣으면 건축면적 합으로 확정합니다. 셋을 다 넣으면 그 곱이 신축 합과 같아야 합니다(다르면 계산하지 않고 알립니다). 건물 모양은 변화 모델에는 쓰이지 않습니다.</p>
    <p className="muted" data-testid="area-plan-received">{received ? <>계산에 쓴 계획: 신축 {formatMetric(received.added_floor_area_m2, 'm²')} · 철거 {received.removed_floor_area_m2 ? formatMetric(received.removed_floor_area_m2, 'm²') : '없음'} · 구역 500m 칸 {formatMetric(received.grid_count)}개 (감축 계산 · 변화 모델 · 보고서가 같은 값)</> : '계산하면 서버가 받은 계획을 여기에 적습니다.'}</p>
    {undecided && <p className="area-fallback" role="note" data-testid="area-plan-undecided">용도 미정 줄이 있어 변화 모델은 돌리지 않습니다(용도를 짐작해 채우지 않음). 줄마다 용도를 고르면 예측합니다.</p>}
    {nonResidential && basis === 'apartments' && <p className="area-fallback" role="note" data-testid="area-plan-basis-hint">비주거 줄이 있습니다. 원단위는 기준 건물 하나의 값을 모든 용도에 곱하므로 상가 · 업무가 섞이면 '건물 전체(건축HUB)' 기준이 맞습니다. 기준은 자동으로 바꾸지 않습니다(아래 계산 설정에서 고름).</p>}
    {error && <p className="form-error">계산하지 못했습니다: {error}</p>}
    <Fold className="slim" title="계산 설정" figures={<>목표 {target}% · {EFFORT_BASIS_LABEL[basis]}</>} hint="목표 % · 기준 건물 · 태양광 발전량" testId="area-calc-settings">
      <div className="area-effort-form">
        <label className="area-target"><span>목표 감축률 (기준 연도 대비)</span><div><input type="range" min={0} max={100} step={1} value={target} onChange={(e) => setTarget(Number(e.target.value))} aria-label="목표 감축률 슬라이더" /><div className="with-unit"><input type="number" min={0} max={100} value={target} onChange={(e) => setTarget(Math.min(100, Math.max(0, Number(e.target.value))))} aria-label="목표 감축률" /><em>%</em></div></div></label>
        <Note label="목표 감축률 안내"><small className="muted area-target-note" data-testid="target-note">목표는 사용자가 정하는 값이고 기본 {DEFAULT_TARGET}%는 예시입니다. 참고로 국가 감축목표의 건물 부문은 2018년 대비 2030년 −32.8%, 2035년 −53.6~−56.2%입니다(기준 연도가 달라 그대로 비교하지 않습니다).</small></Note>
        <div className="area-effort-basis"><span>기준 건물</span><div className="area-modes small" role="tablist" aria-label="감축 노력 기준 건물">
          {(kcsmAvailable || basis === 'kcsm' ? (['apartments', 'buildings', 'kcsm'] as const) : (['apartments', 'buildings'] as const)).map((b) => <button key={b} role="tab" aria-selected={basis === b} onClick={() => setBasis(b)}>{EFFORT_BASIS_LABEL[b]}</button>)}
        </div><small className="muted">{basis === 'kcsm' ? '선도소프트가 준 탄소공간지도 100m 건물 전기 배출(단독주택 포함 모든 건물, 2024년까지). 경계 안 100m 칸 합을 기준으로, 신축 부하는 같은 격자의 배출 ÷ 건축물대장 연면적으로 냅니다.' : basis === 'buildings' ? '상가·업무·학교 등 구역의 계측 건물 전체(건축HUB, 최근 12개월 완비 연도). 상업지역은 이 기준이 맞습니다.' : '공동주택 관리비 전력(같은 출처로 연도 비교). 주거지역 기본값.'}</small></div>
        <label className="field"><span>태양광 kW당 연 발전량 (선택)</span><div><input type="number" min={0} step={10} value={pvYield} placeholder={effort?.pv_yield?.basis === 'ESTIMATED' ? `비우면 지역 추정 ${effort.pv_yield.kwh_per_kw.toLocaleString('ko-KR')}` : '근거가 있을 때만 입력'} onChange={(e) => setPvYield(e.target.value)} /><em>kWh/kW</em></div></label>
      </div>
    </Fold>
  </section>;
}

const SCOPE_FALLBACK: Record<string, { label: string; scope: string; what: string }> = {
  plan_emission: { label: '원단위 기반 계획 배출', scope: '전력 운영탄소만', what: '관측 원단위 × 계획 연면적 × 전력 계수' },
  change_model: { label: '팀 변화 모델 예측', scope: '탄소공간지도 건물 배출(전기 · 가스 · 지역난방)', what: '과거 개발 사례로 학습한 모델의 변화 예측' },
  simulation: { label: '한 칸 계획안(시뮬레이션 화면)', scope: '전력 + 가스', what: '그 화면의 계획안 계산(여기서는 계산하지 않음)' },
};

/**
 * 3단계 '결과'(U3 S5, 설계 4절 · Q2 가): 한 줄 결론(원단위 기반, 엔진 문장 그대로) → 세 범위 표 → 지역난방 열(추정) 한 줄.
 * 세 값은 범위가 달라 더하거나 평균하지 않는다. 값은 서버 응답 그대로(kg → t만).
 */
function PlanResultPanel({ bundle, effort, team, teamRequest }: { bundle: BundleView | null; effort: EffortResult | null; team: TeamAreaState; teamRequest: TeamAreaRequest | null }) {
  const pe = bundle?.blocks.plan_emission;
  const heat = bundle?.blocks.district_heat;
  const added = effort?.targets?.find((x) => x.key === 'plan_added');
  const scope = (key: string) => bundle?.scopes.find((s) => s.key === key) ?? SCOPE_FALLBACK[key];
  const headline = pe ? pe.text ?? pe.reason : null;
  const rows: Array<{ key: string; value: ReactNode }> = [
    { key: 'plan_emission', value: added && added.net_added_kgco2eq !== null ? <><b>{signed(added.net_added_kgco2eq / 1000, 1)}</b> tCO₂eq/년<small>{effort?.baseline_year ? ` · ${effort.baseline_year}년 원단위 · 계수` : ''}</small></> : '자료 없음' },
    { key: 'change_model', value: teamScopeText(team, teamRequest) },
    { key: 'simulation', value: <><Link to="/simulation">한 칸 화면에서 계산</Link><small> · 이 화면에서는 계산하지 않음</small></> },
  ];
  return <section className="panel area-plan-result" aria-label="이 계획의 결과" data-testid="area-plan-result">
    <div className="panel-title"><h3>이 계획의 결과</h3><ProvenanceBadge kind="scenario" /></div>
    {headline && <p className="area-headline" data-testid="area-plan-headline">{headline}</p>}
    {pe?.status === 'OK' && pe.intensity_note && <p className="muted">{pe.intensity_note}</p>}
    <div className="table-wrap"><table data-testid="area-scopes">
      <caption>세 범위 (나란히 · 서로 더하거나 평균하지 않음)</caption>
      <thead><tr><th>범위</th><th>무엇을 재나</th><th className="num">값</th></tr></thead>
      <tbody>{rows.map((r) => { const s = scope(r.key); return <tr key={r.key} data-testid={`area-scope-${r.key}`}><td>{s.label}</td><td><small>{s.scope} · {s.what}</small></td><td className="num">{r.value}</td></tr>; })}</tbody>
    </table></div>
    <p className="muted" data-testid="area-scopes-note">세 값은 재는 에너지원 · 건물 · 해가 달라 서로 더하거나 평균하지 않습니다. 감축 단계는 첫 줄(원단위 기반)에서 이어집니다.</p>
    {heat?.status === 'OK' && heat.text && <p className="area-district-heat" data-testid="area-district-heat"><ProvenanceBadge kind="estimated" detail="지역난방 열" /> {heat.text}</p>}
  </section>;
}

/** 3단계 결과의 '필요한 노력'(목표 % 기준). 예전 계획 조건 칸의 오른쪽을 그대로 옮김. */
function EffortResultPanel({ effort }: { effort: EffortResult | null }) {
  const headline = effortHeadline(effort);
  const o = effort?.options;
  const t = (v: number | undefined | null) => (v == null ? null : v / 1000);
  return <section className="panel area-effort">
      <div className="area-effort-result">
        {!effort ? <EmptyState title="목표를 넣으면 계산합니다" /> : !effort.available ? <EmptyState title="계산할 근거가 없습니다" description={effort.reason} /> : <>
          <div className="panel-title"><h3>필요한 노력</h3><div className="badge-row"><ProvenanceBadge kind="scenario" /><span className={`status-tag ${effort.baseline_mode === 'ESTIMATED' ? 'warn' : 'good'}`}>기준 부하 {BASELINE_MODE_LABEL[effort.baseline_mode ?? 'OBSERVED']} · {effort.baseline_year}년{effort.basis ? ` · ${EFFORT_BASIS_LABEL[effort.basis]}` : ''}</span></div></div>
          <FallbackNotice effort={effort} />
          {effort.basis === 'kcsm' && effort.provider_t != null && <p className="area-fallback" role="note" data-testid="kcsm-basis-note"><b>탄소공간지도 기준:</b> {effort.baseline_year}년 제공 값 {formatMetric(effort.provider_t, 'tCO₂eq', 1)}(행정동 경계 안 100m {formatMetric(effort.baseline_cells ?? 0)}칸)을 계수 {effort.provider_factor}로 전력 {formatMetric(effort.baseline_kwh, 'kWh')}로 되돌린 뒤(제공기관 계수는 추정, 확인 필요) 다른 기준과 같은 계수 {effort.factor_kgco2eq_per_kwh}를 곱했습니다.</p>}
          {headline && <p className={`area-headline ${headline.tone}`} role="status">{headline.text}</p>}
          <EffortBars effort={effort} />
          <dl className="area-figures cols">
            <Figure label="필요 감축량" value={t(effort.required_reduction_kgco2eq)} unit="tCO₂eq/년" digits={1} />
            <Figure label="신축 부하 (추가 대책 없음)" value={effort.new_load_kwh} unit="kWh/년" />
            <div className={o?.new_only_efficiency_pct == null ? 'is-missing' : undefined}><dt>신축 건물만 개선할 때</dt><dd>{o?.new_only_efficiency_pct == null ? '신축 없음' : o.new_only_efficiency_pct > 100 ? `${formatMetric(o.new_only_efficiency_pct, '%', 1)} 필요 → 불가` : `${formatMetric(Math.max(0, o.new_only_efficiency_pct), '%', 1)} 절감`}<small>{o?.new_building_intensity_target != null ? `신축 원단위 ${o.new_building_intensity_target} kWh/m²·년 이하 (현재 ${formatMetric(effort.intensity_kwh_per_m2, '', 2)})` : '신축 원단위를 0 아래로 낮출 수 없음'}</small></dd></div>
            <Figure label="지역 전체 건물 효율 개선" value={o?.all_buildings_efficiency_pct != null ? Math.max(0, o.all_buildings_efficiency_pct) : null} unit="%" digits={1} note="기존 + 신축 전력 사용 절감률" />
            <Figure label="재생에너지로 상쇄할 전력" value={o?.offset_kwh_per_year} unit="kWh/년" />
            <Figure label="태양광 설비 용량" value={o?.pv_capacity_kw} unit="kW" digits={1} note={pvNote(effort.pv_yield, o?.pv_capacity_kw)} />
          </dl>
          <Fold className="slim" title="목표 감축률별 필요 노력 곡선과 계산 가정" hint="펼치기">
            <EffortCurve effort={effort} />
            <div className="assumption-note"><strong>계산 가정 · {effort.scope}</strong><ul>{(effort.assumptions ?? []).map((a) => <li key={a}>{a}</li>)}</ul></div>
          </Fold>
        </>}
      </div>
  </section>;
}

function ReportPanel({ request, label }: { request: () => Record<string, unknown>; label: string }) {
  const recent = useApi<Array<{ id: string; created_at: string; title: string; mode: string }>>('/area-reports');
  const [useLocal, setUseLocal] = useState(false);
  const [title, setTitle] = useState('');
  const [report, setReport] = useState<AreaReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const create = async () => {
    const body = request();
    if (!body.area) { setError('먼저 구역을 분석하세요.'); return; }
    setBusy(true); setError(null);
    try {
      const next = await api<AreaReport>('/area-reports', { method: 'POST', body: JSON.stringify({ ...body, use_local_model: useLocal, title: title.trim() || null }) });
      setReport(next); void recent.reload();
    } catch (reason) { setError(reason instanceof Error ? reason.message : '보고서를 만들지 못했습니다.'); }
    finally { setBusy(false); }
  };
  const open = async (id: string) => { setError(null); try { setReport(await api<AreaReport>(`/area-reports/${id}`)); } catch (reason) { setError(reason instanceof Error ? reason.message : '보고서를 열지 못했습니다.'); } };
  const s = report?.summary;
  return <section className="panel area-report">
    <div className="area-report-form">
      <label className="area-select"><span>제목 (비우면 자동)</span><input type="text" maxLength={80} value={title} placeholder={`${label} 개발 영향·감축 검토`} onChange={(e) => setTitle(e.target.value)} /></label>
      <label className="area-check"><input type="checkbox" checked={useLocal} onChange={(e) => setUseLocal(e.target.checked)} /><span>로컬 AI로 요약 문장 쓰기<small>숫자·연도·증감 방향이 계산 결과와 하나라도 다르면 쓰지 않고 검증된 서식으로 바꿉니다.</small></span></label>
      <button className="button primary" onClick={() => void create()} disabled={busy}><FileText size={15} />{busy ? '작성 중…' : '현재 조건으로 보고서 작성'}</button>
    </div>
    {error && <p className="form-error" role="alert">{error}</p>}
    {report && s && <article className="area-report-body" data-testid="area-report">
      <header><h3>{report.title}</h3><div className="badge-row"><span className={`status-tag ${s.mode === 'TEMPLATE_FALLBACK' ? 'warn' : 'good'}`}>{REPORT_MODE_LABEL[s.mode]}</span><span className="muted">{formatDate(report.created_at)}</span></div></header>
      {s.reason && <p className="caveat">{s.reason}</p>}
      {s.paragraphs.map((p, i) => <p key={i}>{p}</p>)}
      {s.violations.length > 0 && <details><summary>불채택 사유 {s.violations.length}건</summary><ul>{s.violations.map((v) => <li key={v}>{v}</li>)}</ul>{s.rejected && <blockquote>{s.rejected}</blockquote>}</details>}
      {s.mode === 'LOCAL_SLM_NARRATIVE' && <details><summary>근거 문장 {report.facts.length}개</summary><ul>{report.facts.map((f) => <li key={f.id}>{f.text}</li>)}</ul></details>}
      <footer><small>검증: {s.validation} · 근거 SHA256 <code>{report.evidence_hash.slice(0, 16)}…</code></small><span className="badge-row"><a className="button small primary" href={`/api/area-reports/${report.id}/html`} target="_blank" rel="noopener"><Printer size={14} />인쇄·PDF용 보기</a><a className="button small" href={`/api/area-reports/${report.id}/markdown`}><Download size={14} />마크다운 내려받기</a></span></footer>
    </article>}
    {recent.data && recent.data.length > 0 && <div className="area-report-recent"><h4>최근 지역 보고서</h4><ul>{recent.data.slice(0, 6).map((r) => <li key={r.id}><button className="button ghost small" onClick={() => void open(r.id)}>{r.title}</button><small>{formatDate(r.created_at)} · {REPORT_MODE_LABEL[r.mode as AreaReport['summary']['mode']] ?? r.mode}</small></li>)}</ul></div>}
  </section>;
}
