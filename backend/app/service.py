from sqlalchemy import select,func
from .models import *
from .domain import nullable_sum,carbon_kg,month_range

def serialize(row):
    result={}
    for col in row.__table__.columns:
        if col.key=='geom':continue
        value=getattr(row,col.key)
        result[col.key]=value.isoformat() if isinstance(value,datetime) else value
    return result

def factors_for(db,year=2025):
    return {r.energy_type:serialize(r) for r in db.scalars(select(EmissionFactor).where(EmissionFactor.effective_from<=f'{year}-12-31').order_by(EmissionFactor.reference_year,EmissionFactor.effective_from))}

def monthly_energy(db,grid_id=None,year=2025,clause=None):
    # Summed in SQL: the city-wide 건축HUB collection holds hundreds of thousands of rows per year.
    # SUM ignores NULL and returns NULL when no value is known, like nullable_sum.
    # ``clause``: SQL condition limiting the rows to one study region (``Scope.legal_clause``).
    query=select(EnergyMonthly.use_ym,EnergyMonthly.energy_type,func.sum(EnergyMonthly.usage_kwh),func.count()).where(EnergyMonthly.use_ym.between(f'{year}01',f'{year}12'))
    if grid_id: query=query.where(EnergyMonthly.grid_id==grid_id)
    if clause is not None: query=query.where(clause)
    sums={(ym,typ):(total,count) for ym,typ,total,count in db.execute(query.group_by(EnergyMonthly.use_ym,EnergyMonthly.energy_type))}
    factors=factors_for(db,year);result=[]
    for ym in month_range(f'{year}-01',f'{year}-12'):
        record={'use_ym':ym}
        for typ,key in [('ELECTRICITY','electricity_kwh'),('GAS','gas_kwh')]:
            total,count=sums.get((ym,typ),(None,0))
            record[key]=float(total) if total is not None else None
            record[typ.lower()+'_records']=int(count)
        e=carbon_kg(record['electricity_kwh'],factors.get('ELECTRICITY'));g=carbon_kg(record['gas_kwh'],factors.get('GAS'))
        record['electricity_carbon_kg']=e;record['gas_carbon_kg']=g
        record['carbon_kg']=e+g if e is not None and g is not None else None
        result.append(record)
    return result

_POOLED={}

def heating_group(heating_type):
    """'district' for 지역난방 (heat bought from a network: little gas), 'individual' otherwise, None when unknown."""
    text=str(heating_type or '').strip()
    if not text or text=='-':return None
    return 'district' if '지역' in text else 'individual'

def grid_heating(complexes):
    """Heating group of a grid from its complexes, weighted by floor area (None: no complex with a known type)."""
    weights={}
    for c in complexes:
        group=heating_group(getattr(c,'heating_type',None));area=getattr(c,'gross_floor_area_m2',None) or 0
        if group:weights[group]=weights.get(group,0)+(area if area>0 else 1)
    if not weights:return None
    return max(weights,key=weights.get)

def heating_share(complexes):
    """대상지 단지의 지역난방 비중(연면적 가중, %). 난방 방식을 아는 단지가 없으면 None(0이 아님). 2026-11-20

    지역난방 열의 탄소는 계수가 없어 계산 밖이라(기준 문서 5.14 · 5.15), 비중을 계획안 가정 문장에 적는 데 쓴다."""
    weights={};known=unknown=0;district_bjd={}
    for c in complexes:
        group=heating_group(getattr(c,'heating_type',None))
        if not group:unknown+=1;continue
        known+=1;area=getattr(c,'gross_floor_area_m2',None) or 0
        weights[group]=weights.get(group,0)+(area if area>0 else 1)
        if group=='district':   # 사업자가 둘 이상인 시군구는 법정동마다 공급자(기준 문서 5.16, 2026-11-22)
            bjd=str(getattr(c,'bjd_code',None) or '')[:10]
            district_bjd[bjd]=district_bjd.get(bjd,0)+(area if area>0 else 1)
    total=sum(weights.values())
    if not total:return None
    return {'district_share_pct':round(weights.get('district',0)/total*100,1),'complexes':known,'unknown_complexes':unknown,
            'district_bjd':district_bjd}

def district_heating_note(share):
    """지역난방 비중이 0보다 큰 대상지의 가정 문장(계산 엔진 문장, 숫자는 이 함수 인자와 상수에서만)."""
    if not share or not share.get('district_share_pct'):return None
    from .reduction_plan import ENVELOPE_GAS_SAVING
    return (f"대상지 격자에서 난방 방식을 아는 K-apt 단지 {share['complexes']}곳 중 연면적 {share['district_share_pct']:.0f}%가 지역난방입니다. "
            "지역난방 열의 탄소는 배출계수가 없어 이 계산에 들어가지 않아 그만큼 운영탄소가 작게 잡힙니다"
            "(지역난방 단지의 건축HUB 가스 원단위는 개별난방 단지의 약 20분의 1). "
            f"단열·창호 가스 절감({ENVELOPE_GAS_SAVING*100:.1f}%)의 근거도 개별난방 단지입니다.")

def _gas_per_m2(base):
    """평균 원단위의 연 가스 kWh/m². 12개월 가스가 다 있어야 값(아니면 None, 0이 아님)."""
    if not base or not base.get('area_m2'):return None
    gas=[r.get('gas_kwh') for r in base.get('monthly') or []]
    if len(gas)<12 or any(g is None for g in gas):return None
    return sum(gas)/base['area_m2']

def district_heat_estimate(db,year,sc,region_code,share,floor_area_m2):
    """지역난방 열(추정, 기준 문서 5.16): 계획 연면적 × 대상지 지역난방 연면적 비중 × 열 원단위 × 공급 지사 계수.

    열 원단위 = 같은 지역 · 같은 해 개별난방 단지 평균 가스 원단위 − 지역난방 단지 평균 가스 원단위(가정: 지역난방 단지가 사는 열 ≈
    개별난방 단지가 가스로 쓰는 열). 지사 계수 · 두 원단위 · 비중 중 하나라도 없으면 None(가정 문장만)."""
    from .emissions import district_heat_factor
    if not share or not share.get('district_share_pct') or not floor_area_m2:return None
    factor=district_heat_factor(region_code,year,share.get('district_bjd'))
    if not factor:return None
    individual=_gas_per_m2(pooled_baseline(db,year,sc,'individual'))
    district=_gas_per_m2(pooled_baseline(db,year,sc,'district'))
    if individual is None or district is None or individual<=district:return None
    intensity=individual-district
    heat_kwh=float(floor_area_m2)*share['district_share_pct']/100*intensity
    return {'data_class':'ESTIMATED','heat_kwh':round(heat_kwh,1),'carbon_kg':round(heat_kwh*factor['kg_per_kwh'],1),
            'heat_kwh_per_m2':round(intensity,1),'individual_gas_kwh_per_m2':round(individual,1),'district_gas_kwh_per_m2':round(district,1),
            'district_share_pct':share['district_share_pct'],'floor_area_m2':round(float(floor_area_m2),1),'year':year,
            'factor_kg_per_kwh':factor['kg_per_kwh'],'branch':factor['branch'],'source':factor['source'],
            'supplier':factor.get('supplier'),'factor_kind':factor.get('factor_kind')}

def district_heat_text(est):
    """계산 엔진 문장(숫자는 est에서만)."""
    label={'SUBSTITUTE':'지역난방 열(추정, 대체 계수)','MIXED':'지역난방 열(추정, 일부 대체 계수)'}.get(est.get('factor_kind'),'지역난방 열(추정)')
    return (f"{label}: 연 {est['heat_kwh']:,.0f} kWh = 계획 연면적 {est['floor_area_m2']:,.0f} m² × 지역난방 비중 {est['district_share_pct']:.0f}% × "
            f"열 원단위 {est['heat_kwh_per_m2']:.1f} kWh/m²({est['year']}년 같은 지역 개별난방 단지 가스 {est['individual_gas_kwh_per_m2']:.1f} − "
            f"지역난방 단지 가스 {est['district_gas_kwh_per_m2']:.1f}, 가정). 탄소는 연 {est['carbon_kg']/1000:,.1f} tCO2eq"
            f"({est['source']} {est['factor_kg_per_kwh']:.4f} kgCO2eq/kWh). 관측 전력·가스 합계에 섞지 않고 따로 적으며, 감축 단계(단열·창호 등)는 열에 적용하지 않았습니다.")

def pooled_baseline(db,year,sc=None,heating=None):
    """Consistent baseline over every K-apt-linked parcel of a region (``sc``; None = all regions).

    Used when the selected grid has no parcel observed in all 12 months: the plan is then scaled with the
    region's pooled observed intensity (ESTIMATED), never with zeros."""
    from .grid_metrics import consistent_baseline,validated_complex_areas
    from .kapt import ApartmentComplex
    code=EnergyMonthly.raw_record['kapt_code'].as_string()
    query=select(EnergyMonthly.energy_type,EnergyMonthly.use_ym,EnergyMonthly.usage_kwh,code).where(EnergyMonthly.use_ym.between(f'{year}01',f'{year}12'),EnergyMonthly.usage_kwh.is_not(None),code.is_not(None))
    if sc is not None:query=query.where(sc.legal_clause(EnergyMonthly.sigungu_code))
    try:rows=[{'energy_type':t,'use_ym':ym,'usage_kwh':v,'kapt_code':c} for t,ym,v,c in db.execute(query)]
    except Exception:
        db.rollback();return None
    complexes=list(db.scalars(select(ApartmentComplex)))
    if heating:
        # 지역난방 단지는 가스를 거의 쓰지 않는다(수원 2025 중앙값 3.0 vs 개별난방 71.8 kWh/m²): 같은 난방 방식끼리만 평균
        allowed={c.kapt_code for c in complexes if heating_group(c.heating_type)==heating}
        rows=[r for r in rows if r['kapt_code'] in allowed]
    key=(sc.code if sc is not None else '*',year,heating,len(rows),sum(r['usage_kwh'] for r in rows))
    if key in _POOLED:return _POOLED[key]
    areas,_=validated_complex_areas(complexes)
    base=consistent_baseline(rows,month_range(f'{year}-01',f'{year}-12'),areas,{c.kapt_code:c.households for c in complexes}) if rows else None
    if len(_POOLED)>32:_POOLED.clear()
    _POOLED[key]=base
    return base

def baseline_estimate(db,year,sc,factors,grid_id=None):
    """Pooled baseline for a grid without its own: the region first, then every prepared region.

    The pool keeps the grid's heating group (its complexes' 난방방식) when it is known, because a region that mixes
    지역난방 and 개별난방 (수원: 258 vs 188 complexes) has two gas intensities 20× apart."""
    from .regions import DEFAULT_REGION,scope
    from .kapt import ApartmentComplex
    region=sc if sc is not None else scope(db,DEFAULT_REGION)
    heating=grid_heating(db.scalars(select(ApartmentComplex).where(ApartmentComplex.grid_id==grid_id)).all()) if grid_id else None
    mixed=None
    if not heating:
        groups=[heating_group(c.heating_type) for c in db.scalars(select(ApartmentComplex)) if region.owns_complex(c.bjd_code,c.grid_id)]
        known=[g for g in groups if g]
        if known and 0.1<=sum(g=='district' for g in known)/len(known)<=0.9:mixed=True
    for basis,target in (('REGION_POOLED',region),('ALL_REGIONS_POOLED',None)):
        base=pooled_baseline(db,year,target,heating)
        if base:
            monthly=[]
            for r in base['monthly']:
                e=carbon_kg(r['electricity_kwh'],factors.get('ELECTRICITY'));g=carbon_kg(r['gas_kwh'],factors.get('GAS'))
                monthly.append(dict(r,electricity_carbon_kg=e,gas_carbon_kg=g,carbon_kg=e+g if e is not None and g is not None else None))
            label=f'{region.short} 관측 공동주택 평균 원단위' if basis=='REGION_POOLED' else '준비된 모든 지역의 관측 공동주택 평균 원단위'
            if heating:label+=f" ({'지역난방' if heating=='district' else '개별·중앙난방'} 단지끼리)"
            elif mixed:label+=' (지역난방·개별난방 단지가 섞인 평균: 가스는 난방 방식에 따라 크게 다름)'
            return {'basis':basis,'label':label,'area_m2':base['area_m2'],'parcels':len(base['parcels']),'energy_types':base['energy_types'],'monthly':monthly,'data_class':'ESTIMATED',
                    'heating':heating,'heating_mixed':bool(mixed)}
    return None

def region_sector(db,sc):
    """Default 대상지 of a study region: the original testbed sector, or the region's default grid."""
    if sc is None or sc.is_default:
        return db.get(TestbedSector,'prototype')
    if not sc.default_grid_id:return None
    return TestbedSector(id=f'region:{sc.code}',grid_id=sc.default_grid_id,name=f'{sc.short} 기본 대상지',area_m2=250000,
                         reason='지역 준비 때 K-apt 세대수가 가장 많은 격자(없으면 지역 중심 격자)로 정한 기본 대상지',candidates=[],metadata_json={})

def sources_for(db,year=2025):
    """The data-source rows the dashboard and /api/sources show (catalogue + quality for ``year``).

    Kept apart from ``dashboard`` so that the title block, which asks for the sources on every screen,
    does not make the server compute the whole dashboard (monthly energy, baselines, weather) each time."""
    rows=[]
    for r in db.scalars(select(DataSource).where(DataSource.status!='REPLACED')):
        s=serialize(r)
        try:
            from .quality import dataset_quality
            s['quality_scores']=dataset_quality(db,r.id,year)
        except ImportError:pass
        rows.append(s)
    return rows

def dashboard(db,grid_id=None,year=2025,region=None):
    from .regions import scope,weather_rows
    sc=scope(db,region) if region is not None else None
    sector=region_sector(db,sc);selected=serialize(sector) if sector else None
    selected_grid=grid_id or (sector.grid_id if sector else None)
    if grid_id and (not sector or grid_id!=sector.grid_id):
        grid=db.get(Grid,grid_id)
        # Named by its place (전주시 송천1동 일대) for the screens and reports; the cell id is in grid_id.
        from .overlays import grid_admin_rows,place_label
        selected=dict(id=grid_id,grid_id=grid_id,name=place_label(grid_admin_rows(db,grid_id),sc.short if sc else None),area_m2=250000,reason='사용자가 선택한 500m 분석 격자') if grid else None
    monthly=monthly_energy(db,selected_grid,year) if selected_grid else []
    clause=sc.legal_clause(EnergyMonthly.sigungu_code) if sc else None
    regional=monthly_energy(db,year=year,clause=clause)
    totals={k:nullable_sum(r[k] for r in monthly) for k in ['electricity_kwh','gas_kwh','carbon_kg']}
    coverage={typ:sum(row[key] is not None for row in monthly) for typ,key in [('electricity_months','electricity_kwh'),('gas_months','gas_kwh')]}
    within=EnergyMonthly.use_ym.between(f'{year}01',f'{year}12')
    if clause is not None:within=within & clause
    count=db.scalar(select(func.count()).select_from(EnergyMonthly).where(within));matched=db.scalar(select(func.count()).select_from(EnergyMonthly).where(within,EnergyMonthly.grid_id.is_not(None)))
    meta=(sector.metadata_json or {}) if sector and selected_grid==sector.grid_id else {}
    area=meta.get('baseline_floor_area_m2') if meta.get('baseline_year')==year else None
    from .grid_metrics import consistent_baseline,grid_energy_intensity
    from .kapt import ApartmentComplex
    observed=db.scalars(select(EnergyMonthly).where(within,EnergyMonthly.grid_id==selected_grid,EnergyMonthly.usage_kwh.is_not(None))).all() if selected_grid else []
    observed_rows=[{'grid_id':o.grid_id,'energy_type':o.energy_type,'use_ym':o.use_ym,'usage_kwh':o.usage_kwh,'kapt_code':(o.raw_record or {}).get('kapt_code'),'matched_gross_floor_area_m2':(o.raw_record or {}).get('matched_gross_floor_area_m2')} for o in observed]
    # Scenario baseline: one fixed parcel set observed in all 12 months, with its own floor area.
    from .grid_metrics import validated_complex_areas
    # 2026-11-23 U1: one read of the five columns used (was two full reads of 22k complexes with their JSON columns)
    from sqlalchemy.orm import load_only
    slim=list(db.scalars(select(ApartmentComplex).options(load_only(ApartmentComplex.kapt_code,ApartmentComplex.gross_floor_area_m2,
        ApartmentComplex.households,ApartmentComplex.management_area_m2,ApartmentComplex.name))))
    area_by_code,area_issues=validated_complex_areas(slim)
    all_households={row.kapt_code:row.households for row in slim}
    base=consistent_baseline(observed_rows,month_range(f'{year}-01',f'{year}-12'),area_by_code,all_households) if observed_rows else None
    factors=factors_for(db,year)
    if observed_rows:area=base['area_m2'] if base else None
    baseline_monthly=monthly
    if base:
        baseline_monthly=[]
        for r in base['monthly']:
            e=carbon_kg(r['electricity_kwh'],factors.get('ELECTRICITY'));g=carbon_kg(r['gas_kwh'],factors.get('GAS'))
            baseline_monthly.append(dict(r,electricity_carbon_kg=e,gas_carbon_kg=g,carbon_kg=e+g if e is not None and g is not None else None))
        names={row.kapt_code:row.name for row in db.scalars(select(ApartmentComplex).where(ApartmentComplex.kapt_code.in_(base['parcels']+base['excluded_parcels'])))}
        base['parcel_names']=[names.get(code,code) for code in base['parcels']];base['excluded_names']=[names.get(code,code) for code in base['excluded_parcels']]
    households_by_code={row.kapt_code:row.households for row in db.scalars(select(ApartmentComplex).where(ApartmentComplex.grid_id==selected_grid))} if selected_grid else {}
    intensity=grid_energy_intensity(observed_rows,households_by_code,area_by_code).get(selected_grid,{}) if selected_grid else {}
    observed_codes={row['kapt_code'] for row in observed_rows if row['kapt_code']}
    grid_area_issues=[dict(issue,kapt_code=code) for code,issue in area_issues.items() if code in observed_codes]
    e_int=intensity.get('ELECTRICITY') or {}
    base_totals={k:nullable_sum(r[k] for r in baseline_monthly) for k in ['electricity_kwh','gas_kwh','carbon_kg']} if base else {'electricity_kwh':None,'gas_kwh':None,'carbon_kg':None}
    estimate=baseline_estimate(db,year,sc,factors,selected_grid) if not base and selected_grid else None
    population=meta.get('population');households=meta.get('households')
    source_rows=sources_for(db,year)
    quality_score={'coverage_score':(coverage['electricity_months']+coverage['gas_months'])/24,'completeness_score':(coverage['electricity_months']+coverage['gas_months'])/24,'temporal_score':(coverage['electricity_months']+coverage['gas_months'])/24,'spatial_match_score':matched/count if count else None}
    known=[v for v in quality_score.values() if v is not None];quality_score['overall']=sum(known)/len(known) if known else None
    return dict(selected_sector=selected,year=year,**totals,current_far=meta.get('observed_current_far'),current_bcr=meta.get('observed_current_bcr'),households=households,population=population,gross_floor_area_m2=area,developable_site_area_m2=meta.get('site_area_m2'),legal_far_limit=None,legal_bcr_limit=None,legal_status='법적 상한 미확정',quality='에너지 실측 확보·공간매칭 필요' if count==0 else '공간매칭된 관측 / 표본 범위 확인',quality_scores=quality_score,monthly=monthly,weather=[serialize(r) for r in weather_rows(db,sc.code if sc else None,f'{year}01',f'{year}12')],region={'code':sc.code,'name':sc.name,'short_name':sc.short} if sc else None,sources=source_rows,coverage=dict(**coverage,total_months=12,energy_records=count,matched_records=matched),regional_monthly=regional,regional_totals={k:nullable_sum(r[k] for r in regional) for k in totals},carbon_status='공식 배출계수 확인 필요' if not factors else '전력 GIR 승인 계수 · 가스 가정 계수(IPCC 2006)' if (factors.get('GAS') or {}).get('id','').startswith('rule-') else '전력 GIR 승인 계수 · 가스 GIR 승인 국가 고유 계수 / 미확보 에너지원은 제외',electricity_carbon_kg=nullable_sum(r.get('electricity_carbon_kg') for r in monthly),gas_carbon_kg=nullable_sum(r.get('gas_carbon_kg') for r in monthly),baseline_floor_area_m2=area,baseline_monthly=baseline_monthly,baseline_scope={k:base[k] for k in ['parcels','parcel_names','energy_types','excluded_parcels','excluded_names','area_m2']} if base else None,baseline_basis='GRID_OBSERVED' if base else estimate['basis'] if estimate else None,baseline_estimate=estimate,carbon_factors={k:{'factor':v['factor'],'unit':v['factor_unit'],'source':v['source'],'notes':v['notes'],'assumed':v['id'].startswith('rule-')} for k,v in factors.items()},floor_area_issues=grid_area_issues,baseline_totals=base_totals,normalized={'energy_kwh_per_m2':(base_totals['electricity_kwh']+base_totals['gas_kwh'])/area if base and area and base_totals['electricity_kwh'] is not None and base_totals['gas_kwh'] is not None else None,'energy_kwh_per_person':(base_totals['electricity_kwh']+base_totals['gas_kwh'])/population if base and population and base_totals['electricity_kwh'] is not None and base_totals['gas_kwh'] is not None else None,'co2eq_kg_per_m2':base_totals['carbon_kg']/area if base and area and base_totals['carbon_kg'] is not None else None,'co2eq_kg_per_person':base_totals['carbon_kg']/population if base and population and base_totals['carbon_kg'] is not None else None,'electricity_kwh_per_m2':e_int.get('kwh_per_m2'),'electricity_matched_floor_area_m2':e_int.get('area_m2'),'electricity_kwh_per_household':e_int.get('kwh_per_household'),'electricity_households':e_int.get('households'),'electricity_complete_parcels':e_int.get('complete_parcels') or 0,'electricity_area_parcels':e_int.get('area_parcels') or 0,'electricity_household_parcels':e_int.get('household_parcels') or 0,'electricity_observed_parcels':e_int.get('observed_parcels') or 0,'electricity_suspect_parcels':e_int.get('suspect_parcels') or 0,'electricity_carbon_kg_per_m2':carbon_kg(e_int.get('kwh_per_m2'),factors.get('ELECTRICITY'))},annual_complete={'electricity':coverage['electricity_months']==12,'gas':coverage['gas_months']==12},scope='격자에 좌표 매칭된 관측 지번 합계. 격자 전체 건물의 총소비를 의미하지 않습니다.',observations_label='OBSERVED',metadata_label='CALCULATED')
