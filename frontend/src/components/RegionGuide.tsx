import { ProvenanceBadge } from './ProvenanceBadge';
import type { AreaAnalysis, AreaRegionGuide } from '../lib/area';

/** 지역 가이드: 설계기준 지역 구분(고시) · 평년 기후(전주 대비) · 기준 배출 방향(추정, 예측 아님) · 지자체 기본계획 건물 과제(계획값). 감축률 보정에는 쓰지 않는다. */
export function RegionGuidePanel({ analysis, guide }: { analysis?: AreaAnalysis; guide?: AreaRegionGuide | null }) {
  // 지역 시뮬레이션은 분석 결과의 가이드를, 전국 지역 화면은 시군구 상세의 가이드를 넘긴다(2026-11-20)
  const g = guide ?? analysis?.history.region_guide;
  if (!g) return null;
  const c = g.climate;
  const signed = (v: number | null | undefined) => (v == null ? '자료 없음' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1)}%`);
  const ratio = (v: number | null | undefined) => (v == null ? '자료 없음' : `${v.toFixed(2)}배`);
  const direction = (v: number | null | undefined) => (v == null ? '' : v > 0 ? '전주보다 높은 쪽' : v < 0 ? '전주보다 낮은 쪽' : '기준 지역(전주)');
  return <section className="panel area-region-guide" aria-label="지역 기후·지자체 계획 가이드" data-testid="area-region-guide">
    <div className="panel-title"><h3>지역 기후·지자체 계획 가이드 ({g.name})</h3><ProvenanceBadge kind="estimated" detail="방향 참고, 예측 아님" /></div>
    <div className="table-wrap"><table>
      <thead><tr><th>항목</th><th className="num">이 지역</th><th>읽는 법</th><th>출처</th></tr></thead>
      <tbody>
        <tr><td>설계기준 지역 구분</td><td className="num">{g.design_zone}</td><td>표준지표 지역 {g.standard_zone ?? '없음(맞대지 않음)'} · 지역 구분마다 외벽·창 단열 기준이 다릅니다</td><td><small>{g.sources.zone}</small></td></tr>
        {c ? <>
          <tr><td>평년 여름·겨울 평균기온</td><td className="num">{c.summer_mean_c?.toFixed(1)}℃ · {c.winter_mean_c?.toFixed(1)}℃</td><td>기상 지점 {c.station} ({c.mapping})</td><td><small>{g.sources.climate}</small></td></tr>
          <tr><td>난방도일 · 냉방도일 (전주 = 1)</td><td className="num">{ratio(c.hdd_ratio)} · {ratio(c.cdd_ratio)}</td><td>1보다 크면 전주보다 난방(냉방)이 더 필요합니다. 평년 일평균으로 계산해 비로만 읽습니다</td><td><small>{g.sources.climate}</small></td></tr>
          <tr data-testid="region-guide-emission"><td>공동주택 기준 배출 방향 (가이드)</td><td className="num">{signed(c.guide_emission_change_pct)}</td><td>{direction(c.guide_emission_change_pct)} · 전기 {signed(c.guide_electricity_change_pct)}, 가스 {signed(c.guide_gas_change_pct)}{c.within_our_data ? '' : ' · 우리 단지 자료 범위 밖의 기후'}</td><td><small>추정(전주 단지 용도 몫 × 도일 비)</small></td></tr>
        </> : <tr><td>평년 기후</td><td className="num">자료 없음</td><td>이 지역은 기상 지점에 연결하지 못했습니다(확인 필요). 0이 아니라 빈칸입니다</td><td><small>{g.sources.climate}</small></td></tr>}
        {g.heat_stats && <tr data-testid="region-guide-heat-stats"><td>아파트 에너지 중 지역난방 열 (통계)</td>
          <td className="num">{g.heat_stats.district_heat_share_pct != null ? `${g.heat_stats.district_heat_share_pct.toFixed(1)}%` : '통계에 없음'}</td>
          <td>{g.heat_stats.district_heat_share_pct != null ? `${g.heat_stats.year}년 시군구 아파트 전체 에너지(TOE) 가운데 지역난방 열의 몫입니다` : `${g.heat_stats.year}년 통계에 이 지역 아파트의 지역난방 열 사용이 적혀 있지 않습니다(0이 아니라 빈칸)`}{g.heat_stats.parts ? ` · ${g.heat_stats.parts.length}개 구를 더함` : ''}. 난방 방식을 가르지 않는 시군구 합계라 단지별 난방 방식(아래 K-apt 줄)과 다를 수 있습니다</td>
          <td><small>{g.heat_stats.source}</small></td></tr>}
        {g.heating && <tr data-testid="region-guide-heating"><td>공동주택 난방 방식 (세대 비율)</td>
          <td className="num">{g.heating.kinds.map((k) => `${k.kind.replace('난방', '')} ${k.household_share_pct == null ? `${k.complexes}곳(세대수 없음)` : k.household_share_pct > 0 && k.household_share_pct < 0.5 ? '1% 미만' : `${k.household_share_pct.toFixed(0)}%`}`).join(' · ')}</td>
          <td>K-apt 단지 {g.heating.complexes}곳{g.heating.unknown_complexes ? `(난방 방식 미상 ${g.heating.unknown_complexes}곳 제외)` : ''}. {g.heating.reading}</td>
          <td><small>{g.heating.source}</small></td></tr>}
        {g.solar !== undefined && <tr data-testid="region-guide-solar"><td>지붕 태양광 발전량 (kW당 연)</td>
          <td className="num">{g.solar ? `${Math.round(g.solar.yield_kwh_per_kw).toLocaleString('ko-KR')} kWh` : '자료 없음'}</td>
          <td>{g.solar ? `${g.solar.year}년 수평면 일사량 ${Math.round(g.solar.irradiation_kwh_m2).toLocaleString('ko-KR')} kWh/m²${g.solar.source_type === 'FALLBACK' ? '(대체 자료: 재분석)' : g.solar.source_type === 'OFFICIAL' ? '(관측)' : ''} × 성능비 ${g.solar.performance_ratio.toFixed(2)}(발전량은 추정, 경사 보정 없음). 감축 방안의 태양광 용량은 이 값으로 계산합니다` : '이 지역은 12개월이 다 있는 일사 자료가 없어 계산하지 않았습니다'}
            {c?.sunshine_hours_year != null ? ` · 평년 일조 ${Math.round(c.sunshine_hours_year).toLocaleString('ko-KR')}시간` : ''}{c?.sunshine_hours_year != null && g.reference?.sunshine_hours_year != null ? `(전주 ${Math.round(g.reference.sunshine_hours_year).toLocaleString('ko-KR')}시간)` : ''}</td>
          <td><small>{g.solar ? g.solar.source : '—'}{c?.sunshine_hours_year != null ? ` · ${g.sources.climate}` : ''}</small></td></tr>}
        {g.cooling && <tr data-testid="region-guide-cooling"><td>냉방 쪽 수단</td>
          <td className="num">{g.cooling.items.length}개</td>
          <td>{g.cooling.items.map((i) => `${i.label}(${i.use})`).join(' · ')}. {g.cooling.reading}</td>
          <td><small>감축 수단 목록 · 감축 근거표</small></td></tr>}
        {g.plans.map((p) => <tr key={p.code}><td>{p.region} 기본계획 건물 과제</td><td className="num">{p.tasks}개</td><td>{p.groups.slice(0, 4).map((x) => `${x.label} ${x.tasks}`).join(' · ')}{p.groups.length > 4 ? ' 등' : ''}</td><td><small>{p.plan}</small></td></tr>)}
      </tbody>
    </table></div>
    {g.plans.length > 0 && <details className="method-note"><summary>과제 이름 보기</summary>{g.plans.map((p) => <div key={p.code}><b>{p.region}</b><ul>{p.task_names.map((t, i) => <li key={`${p.code}-${i}`}>{t}</li>)}</ul></div>)}</details>}
    <ul className="area-industry-notes">
      <li>{g.value_kinds}. 감축률 보정이나 필요 감축량 계산에는 쓰지 않습니다.</li>
      <li>{g.check}</li>
      {g.rate_note && <li data-testid="region-guide-rate-note">{g.rate_note}.</li>}
      <li>지자체 과제의 감축량은 지자체 자체 평가 계획값이고 지역마다 기준(한 해 · 누적)이 달라 더하거나 견주지 않습니다.</li>
    </ul>
  </section>;
}
