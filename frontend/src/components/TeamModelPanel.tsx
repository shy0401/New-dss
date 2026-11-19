import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { Note } from './Fold';
import { api } from '../lib/api';
import { formatMetric } from '../lib/format';
import {
  bandText, caseError, readingOf, REQUIREMENT, signed, siteLabel, SOURCE_LABEL, statusText, TEAM_USES, USE_CLASS_LABEL,
  type TeamCellResponse, type TeamPredictResponse, type TeamPrediction, type TeamStatus, type TeamUse,
} from '../lib/teamModel';

/** 격자 상세: 이 500m 칸의 개발 사례(탄소공간지도 실제 변화와 팀 모델 점수)와, 개발 계획을 넣었을 때 팀 변화 모델의 배출 변화 추정. 이 PC 화면에서만. */
export function TeamModelPanel({ gridId, region }: { gridId: string; region: string | null }) {
  const [status, setStatus] = useState<TeamStatus | null>(null);
  const [cell, setCell] = useState<TeamCellResponse | null>(null);
  const [use, setUse] = useState<TeamUse>('residential');
  const [floor, setFloor] = useState('');
  const [dwellings, setDwellings] = useState('');
  const [removed, setRemoved] = useState('');
  // 평가한 개발 기간(착공 전 → 준공 뒤)의 중앙값 7년(docs/TEAM_DATASET.md 7.3절). 서비스 기본값과 같음
  const [yearsAfter, setYearsAfter] = useState(7);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TeamPredictResponse | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () => api<TeamStatus>('/team-model/status').then((s) => {
      if (!alive) return;
      setStatus(s);
      if (s.status === 'training' || s.status === 'starting') window.setTimeout(load, 15000);
    }).catch(() => { if (alive) setStatus({ status: 'off' }); });
    load();
    return () => { alive = false; };
  }, []);
  useEffect(() => {
    if (!/^cell_\d+_\d+$/.test(gridId)) return undefined;
    const controller = new AbortController(); setCell(null); setResult(null); setError(null);
    api<TeamCellResponse>(`/team-model/cell?grid=${encodeURIComponent(gridId)}${region ? `&region=${region}` : ''}`, { signal: controller.signal })
      .then(setCell).catch(() => { if (!controller.signal.aborted) setCell(null); });
    return () => controller.abort();
  }, [gridId, region]);

  const ready = status?.status === 'ready';
  const floorValue = Number(floor); const removedValue = Number(removed); const dwellingValue = Number(dwellings);
  const canRun = ready && !busy && ((floor !== '' && floorValue > 0) || (removed !== '' && removedValue > 0));
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!canRun) return;
    setBusy(true); setError(null); setResult(null);
    try {
      const plan = {
        grid: gridId, years_after: yearsAfter,
        new: floorValue > 0 ? [{ use, floor_area_m2: floorValue, ...(use === 'residential' && dwellingValue > 0 ? { dwellings: dwellingValue } : {}) }] : [],
        removed: removedValue > 0 ? [{ use: 'residential' as const, floor_area_m2: removedValue }] : [],
      };
      setResult(await api<TeamPredictResponse>('/team-model/predict', { method: 'POST', body: JSON.stringify({ region: cell?.model_region ?? region, plans: [plan] }) }));
    } catch (e) {
      setError(e instanceof Error ? e.message : '예측하지 못했습니다');
    } finally { setBusy(false); }
  }

  const cases = cell?.cases ?? [];
  const scored = cases.filter((c) => c.model);
  const shownCases = scored.length ? scored : cases.filter((c) => c.pair_usable === true || c.pair_usable === 'True').slice(-3);
  const r: TeamPrediction | undefined = result?.results[0];
  const dev = status?.accuracy?.development;
  // 이 패널의 계획은 칸 하나 = 1칸 개발. 그 크기 개발의 실제 성능을 결과 옆에 요구 수준과 함께 보여 줌(미달이면 미달이라고)
  const sizeRow = dev?.rows.find((row) => row.band.includes('1칸'));
  const meets = sizeRow ? sizeRow.median_error <= REQUIREMENT.median_error && sizeRow.within_50pct >= REQUIREMENT.within_50pct : null;
  return <section className="detail-section team-model-panel" aria-label="개발 변화 예측 (팀 변화 모델)" data-testid="team-model-panel">
    <h3>개발 변화 예측 <small>팀 변화 모델 7차 · 추정{cell?.dataset ? ` · ${cell.dataset.replace(/^\d{5}_/, '')} 표` : ''}</small></h3>
    <p className="muted" role="status" data-testid="team-model-status">{statusText(status)}</p>
    {shownCases.length > 0 && <>
      <h3 className="sub">이 칸의 개발 사례 <small>탄소공간지도 실제 변화{scored.length ? ' · 모델이 그 사례를 보지 않고 낸 예측' : ''}</small></h3>
      <div className="table-wrap"><table className="team-cases" data-testid="team-model-cases">
        <thead><tr><th>전→후</th><th>부지</th><th className="num">실제 변화</th><th className="num">모델 예측</th><th className="num">오차</th></tr></thead>
        <tbody>{shownCases.map((c) => { const err = caseError(c.model); return <tr key={`${c.before_year}-${c.after_year}-${c.development_id ?? ''}`}>
          <td>{c.before_year}→{c.after_year}</td><td>{siteLabel(c.site_kind)}</td>
          <td className="num">{signed(c.model?.actual_tco2e ?? c.buildings_tco2e_change ?? null)}</td>
          <td className="num">{c.model ? <>{signed(c.model.pred_tco2e)}<small> {c.model.set === 'test' ? '시험' : '교차검증'}</small></> : '—'}</td>
          <td className="num">{err === null ? '—' : `${Math.round(err * 100)}%`}</td>
        </tr>; })}</tbody>
      </table></div>
    </>}
    <form className="team-model-form" onSubmit={(e) => void submit(e)} aria-label="개발 계획 입력">
      <label className="area-select"><span>신축 용도</span><select value={use} onChange={(e) => setUse(e.target.value as TeamUse)}>{TEAM_USES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
      <label className="area-select narrow"><span>신축 연면적</span><div className="with-unit"><input type="number" min={0} step={1000} inputMode="numeric" value={floor} onChange={(e) => setFloor(e.target.value)} placeholder="예: 120000" /><em>m²</em></div></label>
      {use === 'residential' && <label className="area-select narrow"><span>세대수 (선택)</span><div className="with-unit"><input type="number" min={0} step={10} inputMode="numeric" value={dwellings} onChange={(e) => setDwellings(e.target.value)} placeholder="자동" /><em>세대</em></div></label>}
      <label className="area-select narrow"><span>철거 연면적 (주거)</span><div className="with-unit"><input type="number" min={0} step={1000} inputMode="numeric" value={removed} onChange={(e) => setRemoved(e.target.value)} placeholder="0" /><em>m²</em></div></label>
      <label className="area-select narrow"><span>몇 년 뒤</span><select value={yearsAfter} onChange={(e) => setYearsAfter(Number(e.target.value))}>{[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((y) => <option key={y} value={y}>{y}년 뒤</option>)}</select><small className="muted">평가한 개발 기간 중앙값 7년</small></label>
      <button type="submit" className="button small primary" disabled={!canRun}>{busy ? '예측 중…' : '배출 변화 예측'}</button>
    </form>
    <p className="muted" data-testid="team-model-area-link">여러 칸에 걸친 개발은 <Link to="/area">지역 시뮬레이션</Link>에서 구역을 골라 한 개발로 예측합니다.</p>
    {error && <p className="muted" role="alert">{error}</p>}
    {r && <div className="team-model-result" data-testid="team-model-result">
      <p className="detail-figure">{signed(r.change_tco2e)}<span className="unit">tCO₂e/년 ({r.before_year}→{r.after_year}년)</span></p>
      {readingOf(r.change_tco2e) === 'direction'
        ? <p className="muted">1,000 tCO₂e보다 작은 변화라 값보다 방향({r.change_tco2e >= 0 ? '늘어남' : '줄어듦'})만 읽습니다{dev ? `(${dev.small})` : '(팀 시험에서 이 크기는 오차 중앙값 2.4)'}.</p>
        : bandText(r.band) && <p className="muted">{bandText(r.band)}</p>}
      {sizeRow && readingOf(r.change_tco2e) === 'value' && <p className="muted" data-testid="team-model-size-accuracy">
        이 크기(1칸 개발)의 실제 성능: 오차 중앙값 {sizeRow.median_error.toFixed(2)} · ±50% 안 {Math.round(sizeRow.within_50pct * 100)}%
        {' '}/ 요구 수준 {REQUIREMENT.median_error.toFixed(2)} · {Math.round(REQUIREMENT.within_50pct * 100)}% {meets ? '(충족)' : '(미달 — 범위를 함께 읽을 것)'}
      </p>}
      <dl className="fact-list">
        <div className="fact"><dt>개발 전 배출 ({r.before_year}년)</dt><dd>{formatMetric(r.emission_before_tco2e, 'tCO₂eq', 0)}</dd></div>
        <div className="fact"><dt>연면적 (추정)</dt><dd>{formatMetric(r.floor_area_before_m2, '')} → {formatMetric(r.floor_area_after_m2, 'm²')}</dd></div>
        <div className="fact"><dt>부지 · 계획 용도</dt><dd>{siteLabel(r.site_kind)} · {USE_CLASS_LABEL[r.use_class] ?? r.use_class}</dd></div>
        {Object.keys(r.sources_tco2e ?? {}).length > 0 && <div className="fact"><dt>에너지원별 구성</dt><dd>{Object.entries(r.sources_tco2e).map(([k, v]) => `${SOURCE_LABEL[k] ?? k} ${signed(v)}`).join(' · ')}{dev && <><br /><small className="muted">{dev.electricity}</small></>}</dd></div>}
        {Object.keys(r.attribution ?? {}).length > 0 && <div className="fact"><dt>요인별 기여</dt><dd>{Object.entries(r.attribution).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 3).map(([k, v]) => `${k} ${signed(v)}`).join(' · ')}</dd></div>}
      </dl>
      {[...(r.warnings ?? []), ...(r.out_of_range ?? []).map((t) => `학습 범위 밖: ${t}`)].length > 0 && <ul className="team-model-warnings">{[...(r.warnings ?? []), ...(r.out_of_range ?? []).map((t) => `학습 범위 밖: ${t}`)].map((w) => <li key={w}>{w}</li>)}</ul>}
      {(r.filled ?? []).length > 0 && <details><summary>계획에 없어 자동으로 채운 값 {r.filled.length}개</summary><ul>{r.filled.map((f) => <li key={f}>{f}</li>)}</ul></details>}
      <p className="muted" data-testid="team-model-compare-note">계획안끼리 비교할 때: 연면적을 늘린 만큼의 예측 반응이 실제 사례 평균의 약 60%(주거)라, 안 사이의 차이를 실제보다 작게 볼 수 있습니다.</p>
    </div>}
    {status?.accuracy && (dev
      ? <details className="team-model-accuracy"><summary>이 모델이 맞히는 정도 (개발 단위 · 학습에 없던 지역)</summary>
        <p className="muted">{dev.basis}</p>
        <div className="table-wrap"><table>
          <thead><tr><th>평가</th><th className="num">개발</th><th className="num">오차 중앙값</th><th className="num">±50% 안</th><th className="num">예측 합 ÷ 실제 합</th></tr></thead>
          <tbody>{dev.rows.map((a) => <tr key={a.band}><td>{a.band}</td><td className="num">{a.cases}</td><td className="num">{a.median_error.toFixed(2)}</td><td className="num">{Math.round(a.within_50pct * 100)}%</td><td className="num">{a.sum_ratio.toFixed(2)}</td></tr>)}</tbody>
        </table></div>
        <p className="muted">용도별(교차검증): {dev.by_use}. {dev.electricity}. {dev.small}. {dev.band_coverage}. {dev.requirement}.</p>
      </details>
      : <details className="team-model-accuracy"><summary>이 모델이 맞히는 정도 (학습에 없던 10개 지역 153사례)</summary>
        <div className="table-wrap"><table>
          <thead><tr><th>실제 변화 크기</th><th className="num">사례</th><th className="num">오차 중앙값</th><th className="num">±50% 안</th><th className="num">예측 합 ÷ 실제 합</th></tr></thead>
          <tbody>{status.accuracy.test.map((a) => <tr key={a.band}><td>{a.band}{a.note ? <small> · {a.note}</small> : null}</td><td className="num">{a.cases}</td><td className="num">{a.median_error}</td><td className="num">{Math.round(a.within_50pct * 100)}%</td><td className="num">{a.sum_ratio}</td></tr>)}</tbody>
        </table></div>
        <p className="muted">용도별(42곳 교차검증, 1천 이상): {status.accuracy.by_use}. {status.accuracy.band_coverage}. 출처: {status.accuracy.source}.</p>
      </details>)}
    <Note label="추정 방식"><p className="muted">탄소공간지도 건물 배출(전기·가스·지역난방)의 변화를 팀 데이터셋 42개 지역으로 학습한 모델이 추정한 값입니다. 관측과 섞지 않고 다른 기준의 감축 계산에도 넣지 않습니다. 학습 표에 국토통계지도 값이 있어 이 PC 화면에서만 보입니다.</p></Note>
  </section>;
}
