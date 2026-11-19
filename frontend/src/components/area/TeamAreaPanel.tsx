import { Plus, X } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import { Fold, Note } from '../Fold';
import { api } from '../../lib/api';
import { formatMetric } from '../../lib/format';
import {
  AREA_MAX_CELLS, AREA_MAX_USES, areaSizeLabel, bandText, readingOf, REQUIREMENT, signed, SOURCE_LABEL, statusText, TEAM_USES,
  type TeamAreaResponse, type TeamStatus, type TeamUse,
} from '../../lib/teamModel';

interface UseRow { use: TeamUse; floor: string; dwellings: string }

/**
 * 지역 화면: 고른 구역 전체를 한 개발로 보고 팀 변화 모델로 배출 변화를 추정한다(모델 로드맵 7-B2).
 * 용도별 합계를 구역의 쓸 수 있는 500m 칸에 같게 나눠 칸마다 예측하고 더한다(기록 41절). 이 PC 화면에서만(공개 주소에서는 숨김).
 */
export function TeamAreaPanel({ grids, region, plannedFloor, plannedRemoved }: { grids: string[]; region: string | null; plannedFloor: number; plannedRemoved: number }) {
  const [status, setStatus] = useState<TeamStatus | null>(null);
  const [rows, setRows] = useState<UseRow[]>([{ use: 'residential', floor: String(plannedFloor || ''), dwellings: '' }]);
  const [removedUse, setRemovedUse] = useState<TeamUse>('residential');
  const [removed, setRemoved] = useState(plannedRemoved > 0 ? String(plannedRemoved) : '');
  // 사용자가 이 패널의 첫 줄 연면적이나 철거 연면적을 고치기 전까지는 위 '계획 조건'을 따라간다
  const [synced, setSynced] = useState(true);
  const [yearsAfter, setYearsAfter] = useState(7);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TeamAreaResponse | null>(null);

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
    if (!synced) return;
    setRows((rs) => rs.map((r, i) => (i === 0 ? { ...r, floor: plannedFloor > 0 ? String(plannedFloor) : '' } : r)));
    setRemoved(plannedRemoved > 0 ? String(plannedRemoved) : '');
  }, [synced, plannedFloor, plannedRemoved]);
  useEffect(() => { setResult(null); setError(null); }, [grids]);

  if (status?.status === 'restricted') return null;
  const ready = status?.status === 'ready';
  const newItems = rows.map((r) => ({ use: r.use, floor: Number(r.floor), dwellings: Number(r.dwellings) })).filter((r) => r.floor > 0);
  const removedValue = Number(removed);
  const totalNew = newItems.reduce((a, r) => a + r.floor, 0);
  const differs = Math.round(totalNew) !== Math.round(plannedFloor) || Math.round(removedValue || 0) !== Math.round(plannedRemoved);
  const tooMany = grids.length > AREA_MAX_CELLS;
  const canRun = ready && !busy && grids.length > 0 && !tooMany && (newItems.length > 0 || removedValue > 0);
  const setRow = (i: number, patch: Partial<UseRow>) => {
    if (i === 0 && patch.floor !== undefined) setSynced(false);
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!canRun) return;
    setBusy(true); setError(null); setResult(null);
    try {
      const body = {
        region, grids, years_after: yearsAfter,
        new: newItems.map((r) => ({ use: r.use, floor_area_m2: r.floor, ...(r.use === 'residential' && r.dwellings > 0 ? { dwellings: r.dwellings } : {}) })),
        removed: removedValue > 0 ? [{ use: removedUse, floor_area_m2: removedValue }] : [],
      };
      setResult(await api<TeamAreaResponse>('/team-model/predict-area', { method: 'POST', body: JSON.stringify(body) }));
    } catch (e) {
      setError(e instanceof Error ? e.message : '예측하지 못했습니다');
    } finally { setBusy(false); }
  }

  const c = result?.combined;
  const area = result?.area;
  const used = area?.cells_used.length ?? 0;
  const skipped = area?.cells_skipped ?? [];
  const nearest = (area?.cells_used ?? []).filter((u) => u.start === 'nearest');
  const empty = (area?.cells_used ?? []).filter((u) => u.start === 'empty');
  const startOf = new Map((area?.cells_used ?? []).map((u) => [u.grid, u]));
  const first = result?.results[0];
  const dev = status?.accuracy?.development;
  const size = used ? areaSizeLabel(used) : null;
  const sizeRow = size ? dev?.rows.find((row) => row.band.includes(size)) : undefined;
  const meets = sizeRow ? sizeRow.median_error <= REQUIREMENT.median_error && sizeRow.within_50pct >= REQUIREMENT.within_50pct : null;
  const warnings = result ? [...new Set(result.results.flatMap((r) => [...(r.warnings ?? []), ...(r.out_of_range ?? []).map((t) => `학습 범위 밖: ${t}`)]))] : [];

  return <Fold title="팀 변화 모델로 이 구역 개발의 배출 변화 보기" hint="구역의 500m 칸을 한 개발로 예측 · 이 PC 화면에서만" testId="team-area-fold"
    figures={c ? <>{signed(c.change_tco2e)} tCO₂e/년 · 칸 {used}개</> : undefined}>
  <section className="panel team-area-panel" aria-label="이 구역 개발의 배출 변화 (팀 변화 모델)" data-testid="team-area-panel">
    <div className="panel-title"><h3>팀 변화 모델: 이 구역 개발의 배출 변화</h3><small className="muted">추정 · 탄소공간지도 건물 배출 기준</small></div>
    <p className="muted" role="status" data-testid="team-area-status">{statusText(status)}</p>
    <p className="muted" data-testid="team-area-cells">
      이 구역의 500m 칸 <b>{grids.length}개</b>(지도의 점선 칸)를 한 개발로 봅니다. 용도별 연면적 합계를 칸마다 같게 나눠 예측하고 더합니다.
    </p>
    <p className="muted" data-testid="team-area-fit-note">
      구역은 개발 부지에 맞게 고르세요. 개발이 없는 칸의 작은 변화는 모델이 맞히지 못해, 넓은 구역에 작은 계획을 나누면 칸마다 오차가 더해집니다.
    </p>
    {tooMany && <p className="form-error" role="alert" data-testid="team-area-too-many">칸이 {grids.length}개라 평가한 가장 큰 개발({AREA_MAX_CELLS}칸)보다 큽니다. 반경을 줄이거나 직접 그리기로 개발 부지만 골라 주세요.</p>}
    {grids.length === 0 && <p className="form-error" role="alert">이 구역에 중심이 들어오는 500m 칸이 없습니다. 구역을 조금 넓혀 주세요.</p>}
    <form className="team-area-form" onSubmit={(e) => void submit(e)} aria-label="구역 개발 계획 입력">
      <div className="team-area-rows">
        {rows.map((r, i) => <div className="team-area-row" key={i} data-testid="team-area-row">
          <label className="area-select"><span>신축 용도{rows.length > 1 ? ` ${i + 1}` : ''}</span><select value={r.use} onChange={(e) => setRow(i, { use: e.target.value as TeamUse })}>{TEAM_USES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          <label className="area-select narrow"><span>연면적 합계</span><div className="with-unit"><input type="number" min={0} step={1000} inputMode="numeric" value={r.floor} onChange={(e) => setRow(i, { floor: e.target.value })} placeholder="예: 120000" /><em>m²</em></div></label>
          {r.use === 'residential' && <label className="area-select narrow"><span>세대수 (선택)</span><div className="with-unit"><input type="number" min={0} step={10} inputMode="numeric" value={r.dwellings} onChange={(e) => setRow(i, { dwellings: e.target.value })} placeholder="자동" /><em>세대</em></div></label>}
          {i > 0 && <button type="button" className="button ghost small" aria-label={`용도 ${i + 1} 빼기`} onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}><X size={14} /></button>}
        </div>)}
        {rows.length < AREA_MAX_USES && <button type="button" className="button ghost small" onClick={() => setRows((rs) => [...rs, { use: 'commercial', floor: '', dwellings: '' }])}><Plus size={14} />용도 추가 (복합 개발)</button>}
      </div>
      <div className="team-area-row">
        <label className="area-select"><span>철거 용도</span><select value={removedUse} onChange={(e) => setRemovedUse(e.target.value as TeamUse)}>{TEAM_USES.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label className="area-select narrow"><span>철거 연면적</span><div className="with-unit"><input type="number" min={0} step={1000} inputMode="numeric" value={removed} onChange={(e) => { setSynced(false); setRemoved(e.target.value); }} placeholder="0" /><em>m²</em></div></label>
        <label className="area-select narrow"><span>몇 년 뒤</span><select value={yearsAfter} onChange={(e) => setYearsAfter(Number(e.target.value))}>{[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((y) => <option key={y} value={y}>{y}년 뒤</option>)}</select><small className="muted">평가한 개발 기간 중앙값 7년</small></label>
      </div>
      <p className="muted team-area-sync" data-testid="team-area-sync">
        {synced && !differs ? '위 계획 조건의 연면적을 그대로 씁니다.' : <>위 계획 조건과 다릅니다(신축 {formatMetric(totalNew, 'm²')} · 철거 {formatMetric(removedValue || 0, 'm²')} / 위 계획 {formatMetric(plannedFloor, 'm²')} · {formatMetric(plannedRemoved, 'm²')}). <button type="button" className="button ghost small" onClick={() => setSynced(true)}>위 계획 값으로</button></>}
      </p>
      <button type="submit" className="button small primary" disabled={!canRun}>{busy ? `예측 중… (칸 ${grids.length}개)` : '이 구역 배출 변화 예측'}</button>
    </form>
    {error && <p className="form-error" role="alert">{error}</p>}
    {c && area && first && <div className="team-model-result" data-testid="team-area-result">
      {(nearest.length > 0 || empty.length > 0 || skipped.length > 0) && <p className={skipped.length * 2 > area.cells_total ? 'form-error' : 'muted'} data-testid="team-area-skipped">
        칸 {area.cells_total}개 중 기준 해({area.year}년) 상태로 {used - nearest.length - empty.length}개
        {nearest.length > 0 && <>, 그 해 자료가 없어 그 칸의 가장 가까운 해 상태로 {nearest.length}개(추정)</>}
        {empty.length > 0 && <>, 건물이 없는 빈 땅으로 보고 {empty.length}개(추정)</>}
        {skipped.length > 0 && <>, 기준 해 자료가 없거나 결함이 있어 뺀 칸 {skipped.length}개</>}를 썼습니다. 연면적은 쓴 칸 {used}개에 같게 나눴습니다.
        {skipped.length * 2 > area.cells_total && ' 빠진 칸이 절반을 넘어 결과가 구역 전체를 대표하지 못할 수 있습니다.'}
      </p>}
      <p className="detail-figure">{signed(c.change_tco2e)}<span className="unit">tCO₂e/년 ({area.year}→{area.year + (first.after_year - first.before_year)}년, 칸 {used}개 합계)</span></p>
      <p className="muted" data-testid="team-area-meaning">기준 해({area.year}년) 상태에서 이 계획을 넣었을 때 칸 {used}개의 건물 배출이 {first.after_year - first.before_year}년 동안 바뀌는 양입니다. 계획 밖 변화(이미 짓던 건물이 차는 것 등)도 함께 들어 있습니다(평가한 실제 개발 변화와 같은 기준).</p>
      {readingOf(c.change_tco2e) === 'direction'
        ? <p className="muted">1,000 tCO₂e보다 작은 변화라 값보다 방향({c.change_tco2e >= 0 ? '늘어남' : '줄어듦'})만 읽습니다{dev ? `(${dev.small})` : ''}.</p>
        : bandText(c.band) && <p className="muted">{bandText(c.band)} · 개발 단위 교차검증 잔차</p>}
      {sizeRow && readingOf(c.change_tco2e) === 'value' && <p className="muted" data-testid="team-area-size-accuracy">
        이 크기({size} 개발)의 실제 성능: 오차 중앙값 {sizeRow.median_error.toFixed(2)} · ±50% 안 {Math.round(sizeRow.within_50pct * 100)}%
        {' '}/ 요구 수준 {REQUIREMENT.median_error.toFixed(2)} · {Math.round(REQUIREMENT.within_50pct * 100)}% {meets ? '(충족)' : '(미달 — 범위를 함께 읽을 것)'}
      </p>}
      <dl className="fact-list">
        <div className="fact"><dt>칸마다 넣은 값</dt><dd>{area.per_cell.new.map((it) => `${TEAM_USES.find(([k]) => k === it.use)?.[1] ?? it.use} ${formatMetric(it.floor_area_m2, 'm²')}${it.dwellings ? ` · ${formatMetric(it.dwellings, '세대')}` : ''}`).join(' + ') || '—'}{area.per_cell.removed.length ? ` / 철거 ${area.per_cell.removed.map((it) => formatMetric(it.floor_area_m2, 'm²')).join(' + ')}` : ''}</dd></div>
        <div className="fact"><dt>개발 전 배출 (칸 합)</dt><dd>{formatMetric(result.results.reduce((a, r) => a + r.emission_before_tco2e, 0), 'tCO₂eq', 0)}</dd></div>
        {Object.keys(c.sources_tco2e ?? {}).length > 0 && <div className="fact"><dt>에너지원별 구성</dt><dd>{Object.entries(c.sources_tco2e ?? {}).map(([k, v]) => `${SOURCE_LABEL[k] ?? k} ${signed(v)}`).join(' · ')}{dev && <><br /><small className="muted">{dev.electricity}</small></>}</dd></div>}
      </dl>
      {warnings.length > 0 && <ul className="team-model-warnings">{warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
      <details data-testid="team-area-cells-table"><summary>칸별 예측 {used}개{skipped.length ? ` · 뺀 칸 ${skipped.length}개` : ''}</summary>
        <div className="table-wrap"><table>
          <thead><tr><th>칸</th><th>시작 상태</th><th className="num">개발 전 배출</th><th className="num">변화 예측</th></tr></thead>
          <tbody>{result.results.map((r) => { const u = startOf.get(r.grid ?? ''); return <tr key={r.grid ?? r.cell}><td>{r.grid ?? r.cell}</td>
            <td>{r.before_year}년{u?.start === 'nearest' ? ' (가까운 해, 추정)' : u?.start === 'empty' ? ' (빈 땅으로 봄, 추정)' : ''}</td>
            <td className="num">{formatMetric(r.emission_before_tco2e, '', 0)}</td><td className="num">{signed(r.change_tco2e)}</td></tr>; })}
            {skipped.map((s) => <tr key={s.grid} className="muted"><td>{s.grid}</td><td colSpan={3}>뺌: {s.reason}</td></tr>)}</tbody>
        </table></div>
      </details>
    </div>}
    <Note label="추정 방식"><p className="muted">탄소공간지도 건물 배출(전기·가스·지역난방)의 변화를 팀 데이터셋 42개 지역으로 학습한 모델이 칸마다 추정해 더한 값입니다. 합계를 칸에 같게 나누는 방식은 과거 여러 칸 개발에서 칸별 실제 배분과 비슷하게 맞혔습니다(오차 0.22 대 0.23). 관측과 섞지 않으며, 학습 표에 국토통계지도 값이 있어 이 PC 화면에서만 보입니다.</p></Note>
  </section>
  </Fold>;
}
