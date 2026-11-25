/**
 * 지역 시뮬레이션의 업무 흐름 부품 (2026-10 사용성 개선).
 * - 결과 요약 막대: 단계 이동 + 핵심 지표(엔진 값 그대로)
 * - 감축 수단 조합: 신축·기존 건물 절감률과 태양광을 함께 넣어 필요 감축량을 채우는지 확인 (도시·군기본계획 방식)
 * - 같은 시·군·구 행정동 비교: 원단위 분포 속 위치 (ENERGY STAR·서울 건물에너지 등급처럼 동종 비교, 단 등급 아님)
 * - 구체적 감축 방안(자동): 남는 양 태양광(2026-11-20부터 신축 11.3% · 기존 4.8% 단계 없음), 2026-11-23(U4)부터 계획 지붕 한도까지만 + 남는 양.
 *   목표 기준 둘(개발 증가분 · 구역 전체)을 나란히. 다른 안과 비교하지 않는다(2026-11-05: 시나리오 비교 단계 삭제)
 * 숫자는 모두 서버 계산 엔진이 낸 값이며 여기서는 고르거나 단위(kg→t)만 바꾼다.
 */
import { ListChecks, Sun } from 'lucide-react';
import type { ReactNode } from 'react';
import { BASELINE_MODE_LABEL, benchmarkPosition, EFFORT_BASIS_LABEL, NO_MEASURES, toTonnes, type AreaAnalysis, type Benchmark, type EffortResult, type AfterRange, type Combination, type EffortTarget, type MeasureEstimate, type MeasureLink, type MeasuresState, type OnsitePlan, type PvLevels } from '../../lib/area';
import { formatMetric } from '../../lib/format';
import { Note } from '../Fold';

/** 작업 단계(U3 S5, 설계 6.1): 구역 → 계획 넣기 → 결과 → 감축 → 배치·상한(선택) → 보고서. */
export const AREA_STEPS = [
  { id: 'area-step-area', label: '구역 고르기' },
  { id: 'area-step-plan', label: '계획 넣기' },
  { id: 'area-step-result', label: '결과' },
  { id: 'area-step-measures', label: '감축 방안' },
  { id: 'area-step-site', label: '배치·상한 (선택)' },
  { id: 'area-step-report', label: '보고서' },
] as const;

const t1 = (kg: number | null | undefined) => formatMetric(toTonnes(kg), 't', 1);

function go(id: string) {
  const el = typeof document === 'undefined' ? null : document.getElementById(id);
  if (el && typeof el.scrollIntoView === 'function') el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function Kpi({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: string; tone?: 'good' | 'warn' | 'bad' }) {
  return <div className={tone ? `is-${tone}` : undefined}><dt>{label}</dt><dd>{value}{sub && <small title={sub}>{sub}</small>}</dd></div>;
}

/** 한 줄 위치 문장: '전주 행정동 30곳 중 낮은 쪽부터 12번째'. 같은 기준·같은 연도일 때만. */
export function benchmarkText(bench: Benchmark | null | undefined, effort: EffortResult | null | undefined) {
  if (!bench || !effort?.available || effort.baseline_mode !== 'OBSERVED' || bench.basis !== effort.basis) return null;
  const pos = benchmarkPosition(bench, effort.baseline_year, effort.intensity_kwh_per_m2);
  if (!pos) return null;
  return { pos, text: `${pos.rank}/${pos.count}번째`, detail: `${bench.reference_year}년 ${bench.basis_label} 원단위 낮은 쪽부터${pos.quintile ? ` · 5분위 중 ${pos.quintile}분위` : ''}` };
}

export function AreaSummaryBar({ analysis, running, bench }: { analysis: AreaAnalysis | null; running: boolean; bench: Benchmark | null }) {
  const e = analysis?.effort;
  const ok = Boolean(e?.available);
  const position = benchmarkText(bench, e);
  const mix = e?.mix ?? e?.recommended ?? null;
  return <section className="area-summary" aria-label="결과 요약" data-testid="area-summary">
    <nav className="area-steps" aria-label="작업 단계">
      <ol>{AREA_STEPS.map((s, i) => <li key={s.id}><a href={`#${s.id}`} onClick={(event) => { event.preventDefault(); go(s.id); }}><b aria-hidden="true">{i + 1}</b>{s.label}</a></li>)}</ol>
    </nav>
    <dl className="area-kpis" aria-live="polite">
      <Kpi label="구역" value={analysis?.history.area.label ?? '구역을 고르세요'} sub={running ? '계산 중…' : analysis ? `${analysis.history.years[0]}~${analysis.history.years[analysis.history.years.length - 1]}` : undefined} />
      {ok && e ? <>
        <Kpi label="기준 배출" value={t1(e.baseline_kgco2eq)} sub={`${e.baseline_year}년 ${BASELINE_MODE_LABEL[e.baseline_mode ?? 'OBSERVED']} · ${e.basis === 'kcsm' ? '건물 전체(탄소공간지도)' : e.basis === 'buildings' ? '건물 전체' : '공동주택'}${e.fallback_from ? '(자동 전환)' : ''}`} />
        <Kpi label="계획 반영 (대책 없음)" value={t1(e.bau_kgco2eq)} sub={`목표 ${formatMetric(e.target_pct, '%')} 감축선 ${t1(e.target_kgco2eq)}`} />
        <Kpi label="필요 감축량" value={e.already_met ? '불필요' : t1(e.required_reduction_kgco2eq)} sub="연간 · 전력 운영탄소" tone={e.already_met ? 'good' : undefined} />
        <Kpi label={e.mix ? '감축 수단 조합' : '구체적 감축 방안'} value={mix ? t1(mix.total_kgco2eq) : '—'} sub={mix ? (mix.met ? '목표 달성' : `${t1(mix.gap_kgco2eq)} 부족`) : '4단계에서 확인'} tone={mix ? (mix.met ? 'good' : 'warn') : undefined} />
        <Kpi label="같은 시·군 비교" value={position ? position.text : '—'} sub={position ? `원단위 낮은 쪽부터${position.pos.quintile ? ` · ${position.pos.quintile}/5분위` : ''}` : '같은 연도·기준 관측일 때만'} />
      </> : analysis ? <Kpi label="감축 노력" value="계산 근거 없음" sub={e?.reason ?? '목표를 넣으면 계산합니다'} tone="warn" /> : null}
    </dl>
  </section>;
}

export function FallbackNotice({ effort }: { effort: EffortResult | null }) {
  if (!effort?.available || !effort.fallback_from || !effort.basis) return null;
  return <p className="area-fallback" role="note"><b>기준 자동 전환:</b> 요청한 {EFFORT_BASIS_LABEL[effort.fallback_from]} 기준은 {effort.fallback_reason ?? '계산할 근거가 없어'} → {EFFORT_BASIS_LABEL[effort.basis]} 기준으로 계산했습니다.</p>;
}

/** 지붕 태양광 한 줄 상태 문장(U4). 숫자는 엔진 값 그대로, kg → t만. */
export function onsiteText(r: OnsitePlan | undefined, need: number | null): string {
  if (!r) return '';
  switch (r.onsite_status) {
    case 'MET': return `계획 지붕 태양광 ${formatMetric(r.pv_kw, 'kW', 1)}로 모두 메웁니다(여유 ${t1(r.margin_kgco2eq)}).`;
    case 'PARTIAL': return `계획 지붕 태양광 ${formatMetric(r.pv_kw, 'kW', 1)}로 ${formatMetric(r.covered_pct, '%', 1)} — 남는 양 ${r.remaining_is_minimum ? '적어도 ' : ''}${t1(r.remaining_kgco2eq)}(구역 밖 태양광 약 ${formatMetric(r.remaining_offsite_pv_kw, 'kW')} 상당).`;
    case 'UPPER_BOUND_ONLY': return `지붕을 연면적(위 한계)으로 보면 필요한 ${formatMetric(r.pv_needed_kw, 'kW')}가 한도 안입니다. 층수를 넣어야 확정됩니다.`;
    case 'NO_ROOF': return `계획에 새 건물(지붕)이 없어 구역 안 태양광을 놓지 못합니다. 남는 양 ${t1(r.remaining_kgco2eq)}.`;
    case 'NO_YIELD': return `발전량 근거가 없어 태양광 용량으로 바꾸지 못합니다(상쇄할 전력 ${formatMetric(r.offset_kwh, 'kWh')}).`;
    case 'ALREADY_MET': return '목표선 아래라 추가 감축이 필요하지 않습니다.';
    default: return need === null ? '이 계획으로 늘지 않습니다.' : '';
  }
}

/** 줄의 수준 표시(계획 v3): 값 · 추정 범위 · 지표 · 상쇄. 색만이 아니라 글자로. */
const LEVEL_TAG: Record<string, [string, string]> = { VALUE: ['값', 'good'], RANGE: ['추정 범위', 'warn'], INDICATOR: ['지표', 'neutral'], OFFSET: ['상쇄', 'neutral'] };
const tRange = (r: [number | null, number | null] | null | undefined, unit = 't') => {
  if (!r) return '—';
  const [a, b] = r.map((v) => (v === null ? '메움' : formatMetric(toTonnes(v), '', 1, true)));
  return a === b ? `${a} ${unit}` : `${a}~${b} ${unit}`;   // 반올림해 같으면 한 번만
};

/** 추정 범위 한 줄: 결과 범위(추정) + 펼치면 근거 · 계산 · 조건. */
export function EstimateLine({ e }: { e: MeasureEstimate }) {
  const r = e.kgco2eq_range ?? e.kgco2_range ?? null;
  if (!r) return <small className="muted"> — 추정 없음: {e.reason}</small>;
  return <div className="area-estimate"><span className="num">{tRange(r, e.kgco2eq_range ? 'tCO2eq' : 'tCO2')}/년 (추정)</span>
    <details><summary>근거와 계산</summary><ul>{e.chain.map((c, i) => <li key={i}>{c}</li>)}</ul><small>근거: {e.basis}</small>{e.condition && <><br /><small className="muted">조건: {e.condition}</small></>}</details></div>;
}

/** 지붕 태양광 세 수준(계획 v3 E): 지붕 최대(값) · 인증 · 실제 사례(추정). 셋은 더하지 않는다. */
export function PvLevelsTable({ value, lv }: { value: number | null; lv: PvLevels }) {
  const kw = (r: [number, number] | null) => !r ? '—' : r[0] === r[1] ? formatMetric(r[0], 'kW') : `${formatMetric(r[0], 'kW')}~${formatMetric(r[1], 'kW')}`;
  const row = (name: string, l: PvLevels['certified']) => <tr key={name}><th scope="row">{name}</th>
    <td className="num">{kw(l.kw_range)}</td>
    <td className="num">{l.kgco2eq_range ? `${tRange(l.kgco2eq_range, 'tCO2eq')}/년 (추정)` : '—'}</td>
    <td className="muted">추정 · {l.source_type}{l.capped ? ' · 지붕에서 자름' : ''}{l.reason ? ` · ${l.reason}` : ''}</td></tr>;
  return <table className="area-pv-levels" data-testid="area-pv-levels"><caption className="muted">세 수준은 더하지 않아요. 목표 · 추천 방안은 지붕 최대(값)로 계산하고, 인증 · 사례 수준은 추정이에요.{lv.region_rule ? ` ${lv.region_rule}` : ''}</caption>
    <thead><tr><th scope="col">수준</th><th scope="col">용량</th><th scope="col">연 감축</th><th scope="col">종류 · 출처</th></tr></thead><tbody>
    <tr><th scope="row">지붕 최대(지금 값)</th><td className="num">—</td><td className="num">{value !== null ? `${t1(value)}/년` : '—'}</td><td className="muted">값 · 계획 지붕 한도까지</td></tr>
    {row('인증 수준', lv.certified)}{row('실제 사례 수준', lv.cases)}
  </tbody></table>;
}

function LinkItem({ l }: { l: MeasureLink }) {
  const lvl = l.value_status === 'OFFSET' ? 'OFFSET' : (l.level ?? (l.value_status === 'QUANTIFIED' ? 'VALUE' : 'INDICATOR'));
  const [label, tone] = LEVEL_TAG[lvl] ?? LEVEL_TAG.INDICATOR;
  const why = (l.why ?? []).filter((w) => w !== '지역 값을 알 수 없어 기본 순서');
  const hasEstimate = !!(l.estimate && (l.estimate.kgco2eq_range || l.estimate.kgco2_range));
  return <li><span className={`status-tag ${tone}`}>{label}</span> <b>{l.title}</b> · {l.evidence_label}{l.n ? ` (${l.n})` : ''} · {l.group_kind}
    {l.value_status === 'QUANTIFIED' && !l.pv_levels ? <span className="num"> {t1(l.value_kgco2eq)}/년</span> : null}
    {l.pv_levels ? <PvLevelsTable value={l.value_kgco2eq} lv={l.pv_levels} /> : null}
    {l.value_status === 'OFFSET' ? <><span className="num"> {formatMetric(toTonnes(l.offset_kgco2 ?? null), 'tCO2', 1, true)}/년 흡수{l.offset_range_kgco2 ? ` (범위 ${tRange(l.offset_range_kgco2, 'tCO2')})` : ''}</span><small className="muted"><br />{l.offset_text}</small></> : null}
    {hasEstimate && l.estimate ? <> <EstimateLine e={l.estimate} /></> : null}
    {l.value_status === 'INDICATOR_ONLY' && !hasEstimate ? <small className="muted"> — 지표: {l.indicator_text}. {l.no_value_reason}</small> : null}
    {l.condition_text && <small className="muted"><br />{l.condition_text}</small>}
    {why.length > 0 && !(l.condition_text ?? '').includes('이 지역:') ? <small className="muted area-why"><br />이 지역: {why.join(' · ')}</small> : null}</li>;
}

function TargetRow({ t, links }: { t: EffortTarget; links: MeasureLink[] }) {
  const r = t.recommended;
  const mine = links.filter((l) => l.target === t.key);
  return <div className="area-target-basis" data-testid={`area-target-${t.key}`}>
    <h5>{t.label}</h5>
    <p className="detail-figure">{t.required_reduction_kgco2eq !== null ? t1(t.required_reduction_kgco2eq) : t.key === 'plan_added' ? '늘지 않음' : '불필요'}</p>
    <p className="muted">{t.key === 'plan_added' ? '이 계획으로 늘어나는 전력 운영탄소(연간)' : `필요 감축량(연간) = 늘어나는 양 + 기존 건물 몫 ${t1(t.existing_share_kgco2eq)}`}</p>
    {r && <p className={`area-headline ${r.onsite_status === 'MET' ? 'good' : 'warn'}`} data-testid={`area-target-${t.key}-onsite`}>{onsiteText(r, t.required_reduction_kgco2eq)}</p>}
    {r?.capped && r.roof_limit_m2 !== null && <p className="muted">태양광은 계획 지붕 한도({r.roof_limit_basis_label} {formatMetric(r.plan_roof_m2, 'm²')}의 60% = {formatMetric(r.roof_limit_m2, 'm²')}, {formatMetric(r.roof_limit_kw, 'kW', 1)})까지만 셉니다. 필요 용량은 {formatMetric(r.pv_needed_kw, 'kW')}입니다.</p>}
    {mine.length > 0 && <details className="area-measure-links"><summary>이 기준에서 쓸 수 있는 수단 {mine.length}개 (값 · 추정 범위 · 지표 · 상쇄를 따로, 서로 더하지 않음)</summary>
      <ul>{mine.map((l) => <LinkItem key={`${l.key}-${l.attach_to.join()}`} l={l} />)}</ul>
    </details>}
  </div>;
}

/** 목표 기준 둘(U4, 기준 문서 5.9): 개발 증가분을 먼저, 구역 전체 목표를 다음에. 두 값은 더하지 않는다. */
export function TargetBases({ effort }: { effort: EffortResult | null }) {
  const targets = effort?.targets ?? [];
  if (!effort?.available || targets.length === 0) return null;
  const order = ['plan_added', 'area_total'];
  const sorted = [...targets].sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key));
  return <div className="area-target-bases" data-testid="area-target-bases">
    <h4>목표 기준 둘 (나란히 · 서로 더하지 않음)</h4>
    {sorted.map((t) => <TargetRow key={t.key} t={t} links={effort.measure_links ?? []} />)}
    <Combinations effort={effort} />
    <small className="muted">두 기준 모두 같은 기준 건물 · 기준 연도({effort.baseline_year}년) · 전력 계수의 시나리오 값입니다. 전력 운영탄소만(가스 · 열 제외).{effort.measure_links_note ? ` ${effort.measure_links_note}.` : ''}</small>
  </div>;
}

const afterText = (a: Combination['after_pv'] | AfterRange | null, atLeast = false) => {
  if (!a) return '—';
  const pre = atLeast ? '적어도 ' : '';
  if ('kgco2eq_range' in a) {
    const margin = a.margin_kgco2eq_range ? `, 여유 ${tRange(a.margin_kgco2eq_range.map((v) => v ?? null) as [number | null, number | null])}`.replace(/메움/g, '0') : '';
    return a.covered === 'all' ? `모두 메움(추정${margin})` : `${pre}${tRange(a.kgco2eq_range)}${a.covered === 'possible' ? ` (낮은 쪽은 메움${margin})` : ''} (추정)`;
  }
  if (a.covered) return a.margin_kgco2eq != null ? `메움(여유 ${t1(a.margin_kgco2eq)} — ${a.margin_note ?? '필요 용량을 10 kW 단위로 올린 몫'})` : '메움';
  return `${a.at_least ? '적어도 ' : ''}${t1(a.kgco2eq)}`;
};

/** 조합 셋 A · B · C(계획 v3 I): 태양광 수준별로 남는 양. 값과 추정을 한 칸에 더하지 않고, 가스 · CO2 추정은 나란히. */
export function Combinations({ effort }: { effort: EffortResult | null }) {
  const cs = effort?.combinations;
  if (!cs || cs.length === 0) return effort?.combinations_reason ? <p className="muted">{effort.combinations_reason}</p> : null;
  const name: Record<string, string> = { roof_max: 'A 지붕 최대', certified: 'B 인증 수준', cases: 'C 실제 사례 수준' };
  const pvText = (c: Combination) => c.pv.kgco2eq != null ? t1(c.pv.kgco2eq) : c.pv.kgco2eq_range ? `${tRange(c.pv.kgco2eq_range)} (추정)` : (c.pv.reason ?? '—');
  const first = cs[0];
  const green = effort?.measure_estimates?.building_greening;
  const atLeast = (c: Combination) => !!(c.after_pv && 'at_least' in c.after_pv && c.after_pv.at_least);
  const side = [...first.gas_estimates.map((g) => ({ ...g, text: tRange(g.kgco2eq_range ?? null, 'tCO2eq') })),
    ...first.co2_estimates.map((g) => ({ ...g, text: tRange(g.kgco2_range ?? null, 'tCO2') }))];
  return <div className="area-combinations" data-testid="area-combinations">
    <h4>조합 셋 — 개발 증가분 {t1(first.need_kgco2eq)}/년을 무엇으로 얼마나 (전력 운영탄소, tCO2eq)</h4>
    <table><thead><tr><th scope="col">조합</th><th scope="col">태양광</th><th scope="col">태양광 뒤 남는 양</th><th scope="col">옥상녹화 냉방까지(추정)</th></tr></thead>
      <tbody>{cs.map((c) => <tr key={c.key}><th scope="row">{name[c.pv_level]}</th><td className="num">{pvText(c)}</td><td className="num">{afterText(c.after_pv)}</td>
        <td className="num">{c.after_estimates ? afterText(c.after_estimates, atLeast(c)) : '—'}</td></tr>)}</tbody></table>
    {green && <div className="muted" data-testid="area-combinations-green">옥상녹화(최상층): {green.kgco2eq_range ? <EstimateLine e={green} /> : `계산하지 않음 — ${green.reason ?? ''}`}</div>}
    {side.length > 0 && <div className="muted">전력 목표 밖에서 더 줄일 수 있는 양(추정, 빼지 않고 나란히):
      <ul>{side.map((g) => <li key={g.key}>{g.title} {g.text}{g.condition ? <small> — 조건: {g.condition}</small> : null}</li>)}</ul></div>}
    {first.indicators.length > 0 && <p className="muted">이 지역에서 먼저 볼 지표: {first.indicators.map((i) => `${i.title}${i.why.length ? `(${i.why.join(', ')})` : ''}`).join(' · ')}</p>}
  </div>;
}

export function MeasuresPanel({ effort, measures, setMeasures }: { effort: EffortResult | null; measures: MeasuresState; setMeasures: (m: MeasuresState) => void }) {
  const mix = effort?.mix;
  const yieldPerKw = effort?.pv_yield?.kwh_per_kw ?? null;
  const field = (key: keyof MeasuresState, label: string, unit: string, max: number, step: number, hint: string) =>
    <label className="field" key={key}><span>{label}</span><div><input type="number" min={0} max={max} step={step} value={measures[key]} aria-label={label}
      onChange={(ev) => setMeasures({ ...measures, [key]: Math.min(max, Math.max(0, Number(ev.target.value) || 0)) })} /><em>{unit}</em></div><span className="field-hint">{hint}</span></label>;
  const fillWithPv = () => {
    if (!mix || mix.met || !yieldPerKw || !effort?.factor_kgco2eq_per_kwh) return;
    const extra = Math.ceil((mix.gap_kgco2eq / effort.factor_kgco2eq_per_kwh / yieldPerKw) * 10) / 10;
    setMeasures({ ...measures, pv_kw: Math.round((measures.pv_kw + extra) * 10) / 10 });
  };
  const need = mix?.required_kgco2eq ?? 0;
  const share = (kwh: number | null) => (need > 0 && kwh && effort?.factor_kgco2eq_per_kwh ? Math.min(100, (kwh * effort.factor_kgco2eq_per_kwh / need) * 100) : 0);
  const parts = mix ? [{ key: 'new', label: '신축', value: share(mix.new_kwh) }, { key: 'existing', label: '기존 건물', value: share(mix.existing_kwh) }, { key: 'pv', label: '태양광', value: share(mix.pv_kwh) }] : [];
  let left = 100;
  const rec = effort?.recommended ?? null;
  // 자동 방안은 태양광만이라 태양광 칸만 채우고, 사용자가 넣은 신축 · 기존 % 는 그대로 둔다(2026-11-20 점검 B)
  const applyRecommended = () => { if (rec && rec.pv_kw !== null) setMeasures({ ...measures, pv_kw: rec.pv_kw }); };
  return <section className="panel area-measures" aria-label="감축 수단 조합">
    <div className="panel-title"><h3>감축 방안</h3><span className="status-tag neutral">순서대로 더해 필요 감축량을 채움</span></div>
    <TargetBases effort={effort} />
    {effort?.available && !effort.already_met && rec && (rec.steps.length > 0 || !!rec.offset_kwh) && <div className="area-recommended" data-testid="area-recommended">
      <h4>구체적 감축 방안 (자동 계산)</h4>
      {rec.steps.length > 0 && <ol>{rec.steps.map((s) => <li key={s.key}><b>{s.title}</b> — {s.detail}<span className="num">{t1(s.kgco2eq)}/년</span></li>)}</ol>}
      <p className={`area-headline ${rec.met ? 'good' : 'warn'}`}>{rec.met ? `합계 ${t1(rec.total_kgco2eq)}로 필요 감축량 ${t1(rec.required_kgco2eq)}를 채웁니다.` : `합계 ${t1(rec.total_kgco2eq)}로 필요 감축량 ${t1(rec.required_kgco2eq)}의 ${formatMetric(rec.share_pct, '%', 1)}입니다.${rec.offset_kwh ? ` 발전량 근거가 없어 남는 ${formatMetric(rec.offset_kwh, 'kWh')}는 재생에너지 상쇄량으로 적습니다.` : ''}`}</p>
      {rec.roof_over_plan && rec.roof_limit_kw == null && rec.roof_m2 != null && <p className="area-headline warn" data-testid="area-roof-warning">필요한 옥상 약 {formatMetric(rec.roof_m2, 'm²')}가 {rec.plan_roof_basis === 'footprint' ? '계획 건물 지붕(건축면적 합)' : '계획 연면적(1층으로 지어도 지붕은 이보다 작음)'} {formatMetric(rec.plan_roof_m2 ?? 0, 'm²')}보다 큽니다. 모자라는 몫은 구역 안 기존 건물 지붕이나 구역 밖 발전으로 채워야 합니다.</p>}
      {rec.roof_over_plan && rec.roof_limit_kw != null && <p className="area-headline warn" data-testid="area-roof-warning">필요한 태양광 {formatMetric(rec.pv_needed_kw ?? null, 'kW')} 가운데 계획 지붕 한도({rec.roof_limit_basis_label ?? ''} {formatMetric(rec.plan_roof_m2 ?? null, 'm²')}의 60%, {formatMetric(rec.roof_limit_kw ?? null, 'kW', 1)})까지만 셉니다. 남는 양 {rec.remaining_is_minimum ? '적어도 ' : ''}{t1(rec.remaining_kgco2eq)}는 구역 안 기존 건물의 절감 · 기존 건물 지붕 · 구역 밖 발전(약 {formatMetric(rec.remaining_offsite_pv_kw ?? null, 'kW')} 상당)으로 채워야 합니다.</p>}
      {(rec.pv_kw ?? 0) > 0 && <div className="area-measures-actions"><button type="button" className="button small" onClick={applyRecommended}><ListChecks size={14} />태양광 값을 아래 칸에 넣기</button><small className="muted">태양광은 남는 양을 10 kW 단위로 올려 채우되 계획 지붕 한도까지만 센 값입니다(기준 문서 5.15). 아래 칸의 신축·기존 건물 %는 바꾸지 않습니다(넣은 값이 있으면 합계가 필요 감축량을 넘을 수 있음).</small></div>}
    </div>}
    {!effort?.available ? <p className="muted">감축 노력을 계산할 수 있는 구역에서 씁니다.</p> : effort.already_met ? <p className="area-headline good">계획을 반영해도 목표선 아래라 추가 수단이 필요하지 않습니다.</p> : <>
      <div className="field-grid area-measures-form">
        {field('new_efficiency_pct', '신축 건물 전력 절감', '%', 100, 0.1, `신축 부하 ${formatMetric(effort.new_load_kwh, 'kWh/년')} 기준`)}
        {field('existing_efficiency_pct', '기존 건물 전력 절감', '%', 100, 0.1, `기준 부하 ${formatMetric(effort.baseline_kwh, 'kWh/년')} − 철거분 기준`)}
        {field('pv_kw', '태양광 설비', 'kW', 1000000, 10, yieldPerKw ? `kW당 ${formatMetric(yieldPerKw, 'kWh/년')} (${effort.pv_yield?.basis === 'USER' ? '입력값' : '지역 추정'})` : '발전량 근거가 없어 합계에서 빠집니다')}
      </div>
      {mix ? <div className="area-mix" data-testid="area-mix">
        <div className="area-mix-bar" role="img" aria-label={`필요 감축량 대비 ${formatMetric(mix.share_pct, '%', 1)}`}>
          {parts.map((p) => { const w = Math.min(left, p.value); left -= w; return w > 0 ? <span key={p.key} className={`seg-${p.key}`} style={{ width: `${w}%` }} title={`${p.label} ${w.toFixed(1)}%`} /> : null; })}
        </div>
        <ul className="area-mix-legend"><li><i className="seg-new" />신축 {formatMetric(mix.new_kwh, 'kWh')}</li><li><i className="seg-existing" />기존 건물 {formatMetric(mix.existing_kwh, 'kWh')}</li><li><i className="seg-pv" />태양광 {mix.pv_counted ? formatMetric(mix.pv_kwh, 'kWh') : '근거 없음'}</li></ul>
        <p className={`area-headline ${mix.met ? 'good' : 'warn'}`} role="status">
          {mix.met ? `조합으로 연간 ${t1(mix.total_kgco2eq)}를 줄여 필요 감축량 ${t1(mix.required_kgco2eq)}를 채웁니다 (여유 ${t1(-mix.gap_kgco2eq)}).`
            : `조합으로 연간 ${t1(mix.total_kgco2eq)}를 줄입니다. 필요 감축량 ${t1(mix.required_kgco2eq)}의 ${formatMetric(mix.share_pct, '%', 1)}로, ${t1(mix.gap_kgco2eq)}가 남습니다.`}
        </p>
      </div> : <p className="muted">값을 넣으면 수단별 감축량을 더해 필요 감축량 {t1(effort.required_reduction_kgco2eq)}와 비교합니다.</p>}
      <div className="area-measures-actions">
        <button type="button" className="button small" onClick={fillWithPv} disabled={!mix || mix.met || !yieldPerKw}><Sun size={14} />남은 양을 태양광으로 채우기</button>
        <button type="button" className="button ghost small" onClick={() => setMeasures(NO_MEASURES)} disabled={measures === NO_MEASURES}>초기화</button>
      </div>
      <Note label="계산 방식"><p className="muted">도시·군기본계획 수립지침의 탄소중립 계획처럼 수단별 예상 감축량을 더해 목표 달성 여부를 봅니다. 기존 건물 절감은 철거분을 뺀 기준 부하에, 태양광은 kW당 연 발전량에 곱합니다(전력 배출계수 {effort.factor_kgco2eq_per_kwh} kgCO₂eq/kWh).</p></Note>
    </>}
  </section>;
}

export function BenchmarkPanel({ bench, effort, regionName }: { bench: Benchmark | null; effort: EffortResult | null; regionName: string }) {
  if (!bench || !bench.count || bench.min === null || bench.max === null) return null;
  const position = benchmarkText(bench, effort);
  const mine = position ? effort?.intensity_kwh_per_m2 ?? null : null;
  const lo = Math.min(bench.min, mine ?? bench.min); const hi = Math.max(bench.max, mine ?? bench.max);
  const span = hi - lo || 1;
  const x = (v: number) => 12 + ((v - lo) / span) * 576;
  const peers = bench.items.filter((i) => i.year === bench.reference_year && i.kwh_per_m2 !== null);
  return <section className="panel area-benchmark" aria-label="같은 시·군·구 행정동 비교">
    <div className="panel-title"><h3>같은 {regionName} 행정동과 비교</h3><span className="status-tag neutral">{bench.reference_year}년 · {bench.basis_label} · {bench.count}곳</span></div>
    <svg viewBox="0 0 600 64" className="area-benchmark-strip" role="img" aria-label={`행정동 ${bench.count}곳 원단위 ${formatMetric(bench.min, '', 1)}~${formatMetric(bench.max, '', 1)} kWh/m²·년, 중앙값 ${formatMetric(bench.median, '', 1)}${position ? `, 이 구역 ${position.text}` : ''}`}>
      <line x1={12} x2={588} y1={30} y2={30} className="axis" />
      {(bench.quintiles ?? []).map((q) => <line key={q} x1={x(q)} x2={x(q)} y1={20} y2={40} className="tick" />)}
      {bench.median !== null && <line x1={x(bench.median)} x2={x(bench.median)} y1={14} y2={46} className="median" />}
      {peers.map((p) => <circle key={p.code} cx={x(p.kwh_per_m2 as number)} cy={30} r={4.5} className="peer"><title>{`${p.name} ${formatMetric(p.kwh_per_m2, 'kWh/m²', 2)}`}</title></circle>)}
      {mine !== null && <><circle cx={x(mine)} cy={30} r={7} className="mine" /><text x={Math.min(560, Math.max(40, x(mine)))} y={60} textAnchor="middle" className="mine-label">이 구역 {formatMetric(mine, '', 1)}</text></>}
      <text x={12} y={12} className="end">{formatMetric(lo, '', 1)}</text><text x={588} y={12} textAnchor="end" className="end">{formatMetric(hi, '', 1)} kWh/m²·년</text>
    </svg>
    <p className="area-benchmark-text">{position ? <><b>낮은 쪽부터 {position.text}</b> ({position.detail}) · 중앙값 {formatMetric(bench.median, 'kWh/m²·년', 2)}</>
      : <>이 구역은 {effort?.available ? (effort.baseline_mode !== 'OBSERVED' ? '기준 부하가 추정값이라' : effort.basis !== bench.basis ? '감축 기준이 달라' : '기준 연도가 달라') : '관측 원단위가 없어'} 순위를 매기지 않습니다. 중앙값 {formatMetric(bench.median, 'kWh/m²·년', 2)}.</>}</p>
    <Note label="비교 기준"><p className="muted">{bench.note} 비교 대상: 같은 연도에 관측 원단위가 있는 행정동 {bench.count}곳 / 전체 {bench.admin_total}곳.</p></Note>
  </section>;
}
