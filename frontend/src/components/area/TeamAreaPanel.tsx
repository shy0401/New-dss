import { RotateCcw } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Note } from '../Fold';
import { ProvenanceBadge } from '../ProvenanceBadge';
import { api, ApiError } from '../../lib/api';
import { formatMetric } from '../../lib/format';
import {
  AREA_MAX_CELLS, areaSizeLabel, bandText, readingOf, REQUIREMENT, signed, SOURCE_LABEL, statusText, TEAM_USES,
  type TeamAreaItem, type TeamAreaResponse, type TeamStatus,
} from '../../lib/teamModel';

/**
 * 지역 화면: 고른 구역 전체를 한 개발로 보고 팀 변화 모델로 배출 변화를 추정한다(모델 로드맵 7-B2).
 * 용도별 합계를 구역의 쓸 수 있는 500m 칸에 같게 나눠 칸마다 예측하고 더한다(기록 41절). 이 PC 화면에서만.
 * U3 S5(2026-11-23): 입력 폼은 '계획 넣기' 한 곳으로 옮겼고, 이 카드는 그 계획을 받아 빠른 답 뒤에 스스로 예측한다(설계 Q1 가).
 * 예측은 구역 칸 · 용도 줄 · 몇 년 뒤가 바뀔 때만 다시 묻는다(목표 % · 기준 건물 · 발전량은 예측과 무관).
 */
/** 변화 모델이 답하지 못할 때 대신 보일 값: 이 계획으로 늘어나는 전력 운영탄소(원단위 기반 계산, U4 `plan_added`). */
export interface IntensityFallback { netAddedKgco2eq: number | null; baselineYear: number | null }

/** `/api/team-model/predict-area` 본문: 방금 계산한(빠른 답이 돌아온) 계획 그대로. */
export interface TeamAreaRequest { region: string | null; grids: string[]; new: TeamAreaItem[]; removed: TeamAreaItem[]; years_after: number }

export interface TeamAreaState {
  status: TeamStatus | null;
  busy: boolean;
  result: TeamAreaResponse | null;
  error: string | null;
  /** 오류의 HTTP 상태(404 = 이 지역 · 칸은 팀 표 밖이라 다시 물어도 같음). */
  errorStatus: number | null;
  retry: () => void;
}

/** 예측을 묻지 않는 까닭(물을 수 있으면 null). */
export function teamAreaBlocker(request: TeamAreaRequest | null): string | null {
  if (!request) return null;
  if (!request.new.length && !request.removed.length) return '용도를 고른 신축 · 철거 줄이 없어 변화 모델을 돌리지 않았습니다(용도를 짐작해 채우지 않음). 위 계획 넣기에서 줄마다 용도를 고르세요.';
  if (request.grids.length === 0) return '이 구역에 중심이 들어오는 500m 칸이 없습니다. 구역을 조금 넓혀 주세요.';
  if (request.grids.length > AREA_MAX_CELLS) return `칸이 ${request.grids.length}개라 평가한 가장 큰 개발(${AREA_MAX_CELLS}칸)보다 큽니다. 반경을 줄이거나 직접 그리기로 개발 부지만 골라 주세요.`;
  return null;
}

/** 모델 상태를 읽고, 계획(요청)이 바뀌면 한 번 예측한다. 앞 요청의 늦은 답은 버린다. */
export function useTeamAreaPrediction(request: TeamAreaRequest | null): TeamAreaState {
  const [status, setStatus] = useState<TeamStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<TeamAreaResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [attempt, setAttempt] = useState(0);
  const revision = useRef(0);

  useEffect(() => {
    let alive = true;
    const load = () => api<TeamStatus>('/team-model/status').then((s) => {
      if (!alive) return;
      setStatus(s);
      if (s.status === 'training' || s.status === 'starting') window.setTimeout(load, 15000);
    }).catch(() => { if (alive) setStatus({ status: 'off' }); });
    load();
    return () => { alive = false; revision.current++; };
  }, []);

  const ready = status?.status === 'ready';
  const key = request ? JSON.stringify(request) : '';
  useEffect(() => {
    const id = ++revision.current;
    setResult(null); setError(null); setErrorStatus(null);
    if (!ready || !request || teamAreaBlocker(request)) { setBusy(false); return; }
    setBusy(true);
    api<TeamAreaResponse>('/team-model/predict-area', { method: 'POST', body: key })
      .then((r) => { if (id === revision.current) setResult(r); })
      .catch((e) => {
        if (id !== revision.current) return;
        setError(e instanceof Error ? e.message : '예측하지 못했습니다');
        setErrorStatus(e instanceof ApiError ? e.status : null);
      })
      .finally(() => { if (id === revision.current) setBusy(false); });
  }, [ready, key, attempt]); // eslint-disable-line react-hooks/exhaustive-deps

  return { status, busy, result, error, errorStatus, retry: () => setAttempt((a) => a + 1) };
}

/** 세 범위 표의 변화 모델 칸 한 줄(값은 모델 응답 그대로, 1,000 tCO₂e 미만은 방향만). */
export function teamScopeText(team: TeamAreaState, request: TeamAreaRequest | null): string {
  if (team.status?.status === 'restricted') return '이 PC 화면에서만 냅니다(공개 주소에서는 내지 않음)';
  if (!request) return '자료 없음';
  if (teamAreaBlocker(request)) return '돌리지 않음(아래 카드의 까닭)';
  if (!team.status) return '모델 상태 확인 중…';
  if (team.status.status !== 'ready') return statusText(team.status);
  if (team.busy) return '예측 중…';
  if (team.error) return `예측 없음: ${team.error}`;
  const c = team.result?.combined;
  if (!c) return '자료 없음';
  if (readingOf(c.change_tco2e) === 'direction') return `${c.change_tco2e >= 0 ? '늘어나는' : '줄어드는'} 방향(1,000 tCO₂e 미만이라 값은 읽지 않음)`;
  const band = bandText(c.band);
  return `${signed(c.change_tco2e)} tCO₂e/년${band ? ` (${band})` : ''}`;
}

export function TeamAreaPanel({ team, request, fallback = null }: { team: TeamAreaState; request: TeamAreaRequest | null; fallback?: IntensityFallback | null }) {
  const { status, busy, result, error, errorStatus, retry } = team;
  const grids = request?.grids ?? [];
  const blocked = teamAreaBlocker(request);
  const fallbackBox = fallback && fallback.netAddedKgco2eq !== null && <div className="team-model-result" data-testid="team-area-fallback">
    <p className="muted">변화 모델 예측 대신(다른 범위): 원단위 기반 계산</p>
    <p className="detail-figure">{signed(fallback.netAddedKgco2eq / 1000, 1)}<span className="unit">tCO₂e/년 · 전력 운영탄소만{fallback.baselineYear ? ` · ${fallback.baselineYear}년 관측 원단위` : ''}</span></p>
    <p className="muted">위 세 범위 표의 '원단위 기반 계획 배출'과 같은 값입니다(계획 연면적 × 관측 원단위 × 전력 계수). 변화 모델(탄소공간지도 건물 배출: 전기 · 가스 · 지역난방)과는 범위가 달라 서로 견주거나 더하지 않습니다.</p>
  </div>;

  if (status?.status === 'restricted') return <section className="panel team-area-panel" aria-label="이 구역 개발의 배출 변화 (팀 변화 모델)" data-testid="team-area-panel">
    <div className="panel-title"><h3>팀 변화 모델</h3></div>
    <p className="muted" data-testid="team-area-status">{statusText(status)}</p>
    {fallbackBox}
  </section>;

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
  const direction = c ? readingOf(c.change_tco2e) === 'direction' : false;
  const years = first ? first.after_year - first.before_year : null;

  return <section className="panel team-area-panel" aria-label="이 구역 개발의 배출 변화 (팀 변화 모델)" data-testid="team-area-panel">
    <div className="panel-title"><h3>팀 변화 모델: 이 구역 개발의 배출 변화</h3><div className="badge-row"><ProvenanceBadge kind="scenario" detail="학습 모델 추정" /><small className="muted">탄소공간지도 건물 배출 기준 · 이 PC 화면에서만</small></div></div>
    <p className="muted" role="status" data-testid="team-area-status">{busy ? `예측 중… (칸 ${grids.length}개, 보통 13~29초)` : statusText(status)}</p>
    <p className="muted" data-testid="team-area-cells">
      이 구역의 500m 칸 <b>{grids.length}개</b>(지도의 점선 칸)를 한 개발로 봅니다. 위 계획의 용도별 연면적 합계를 칸마다 같게 나눠 예측하고 더합니다{request ? ` · ${request.years_after}년 뒤` : ''}. 층수 · 동수 · 건축면적은 변화 모델에 쓰이지 않습니다.
    </p>
    <p className="muted" data-testid="team-area-fit-note">
      구역은 개발 부지에 맞게 고르세요. 개발이 없는 칸의 작은 변화는 모델이 맞히지 못해, 넓은 구역에 작은 계획을 나누면 칸마다 오차가 더해집니다.
    </p>
    {blocked && <p className="form-error" role="alert" data-testid={grids.length > AREA_MAX_CELLS ? 'team-area-too-many' : 'team-area-blocked'}>{blocked}</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
    {error && errorStatus !== 404 && <button type="button" className="button ghost small" onClick={retry}><RotateCcw size={14} />다시 예측</button>}
    {!busy && !c && status !== null && fallbackBox}
    {c && area && first && <div className="team-model-result" data-testid="team-area-result">
      {(nearest.length > 0 || empty.length > 0 || skipped.length > 0) && <p className={skipped.length * 2 > area.cells_total ? 'form-error' : 'muted'} data-testid="team-area-skipped">
        칸 {area.cells_total}개 중 기준 해({area.year}년) 상태로 {used - nearest.length - empty.length}개
        {nearest.length > 0 && <>, 그 해 자료가 없어 그 칸의 가장 가까운 해 상태로 {nearest.length}개(추정)</>}
        {empty.length > 0 && <>, 건물이 없는 빈 땅으로 보고 {empty.length}개(추정)</>}
        {skipped.length > 0 && <>, 기준 해 자료가 없거나 결함이 있어 뺀 칸 {skipped.length}개</>}를 썼습니다. 연면적은 쓴 칸 {used}개에 같게 나눴습니다.
        {skipped.length * 2 > area.cells_total && ' 빠진 칸이 절반을 넘어 결과가 구역 전체를 대표하지 못할 수 있습니다.'}
      </p>}
      <p className="detail-figure">{direction ? (c.change_tco2e >= 0 ? '늘어나는 방향' : '줄어드는 방향') : signed(c.change_tco2e)}<span className="unit">{direction ? '' : 'tCO₂e/년 '}({area.year}→{area.year + (years ?? 0)}년, 칸 {used}개 합계)</span></p>
      <p className="muted" data-testid="team-area-meaning">기준 해({area.year}년) 상태에서 이 계획을 넣었을 때 칸 {used}개의 건물 배출이 {years}년 동안 바뀌는 양입니다. 계획 밖 변화(이미 짓던 건물이 차는 것 등)도 함께 들어 있습니다(평가한 실제 개발 변화와 같은 기준).</p>
      {direction
        ? <p className="muted">1,000 tCO₂e보다 작은 변화라 값과 구간은 적지 않고 방향({c.change_tco2e >= 0 ? '늘어남' : '줄어듦'})만 읽습니다{dev ? `(${dev.small})` : ''}.</p>
        : bandText(c.band) && <p className="muted">{bandText(c.band)} · 개발 단위 교차검증 잔차</p>}
      {sizeRow && !direction && <p className="muted" data-testid="team-area-size-accuracy">
        이 크기({size} 개발)의 실제 성능: 오차 중앙값 {sizeRow.median_error.toFixed(2)} · ±50% 안 {Math.round(sizeRow.within_50pct * 100)}%
        {' '}/ 요구 수준 {REQUIREMENT.median_error.toFixed(2)} · {Math.round(REQUIREMENT.within_50pct * 100)}% {meets ? '(충족)' : '(미달 — 범위를 함께 읽을 것)'}
      </p>}
      <dl className="fact-list">
        <div className="fact"><dt>칸마다 넣은 값</dt><dd>{area.per_cell.new.map((it) => `${TEAM_USES.find(([k]) => k === it.use)?.[1] ?? it.use} ${formatMetric(it.floor_area_m2, 'm²')}${it.dwellings ? ` · ${formatMetric(it.dwellings, '세대')}` : ''}`).join(' + ') || '—'}{area.per_cell.removed.length ? ` / 철거 ${area.per_cell.removed.map((it) => formatMetric(it.floor_area_m2, 'm²')).join(' + ')}` : ''}</dd></div>
        <div className="fact"><dt>개발 전 배출 (칸 합)</dt><dd>{formatMetric(result.results.reduce((a, r) => a + r.emission_before_tco2e, 0), 'tCO₂eq', 0)}</dd></div>
        {!direction && Object.keys(c.sources_tco2e ?? {}).length > 0 && <div className="fact"><dt>에너지원별 구성</dt><dd>{Object.entries(c.sources_tco2e ?? {}).map(([k, v]) => `${SOURCE_LABEL[k] ?? k} ${signed(v)}`).join(' · ')}{dev && <><br /><small className="muted">{dev.electricity}</small></>}</dd></div>}
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
  </section>;
}
