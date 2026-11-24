"""Local administrative commands. Never prints environment or credential values."""
import argparse,json,hashlib
from pathlib import Path
from sqlalchemy import select,func,text
from .db import Base,engine,Session
from .models import DataSource,Grid,Building,Region,WeatherMonthly,EnergyMonthly,TestbedSector,RawDataAsset,ModelRun
from .catalog import seed_sources
from .settings import DATA_DIR,DEFAULT_YEAR

def init_tables():
    from . import official,kapt,kapt_energy,kma_asos,sgis,sgis_grid,vworld,energy_parcels,sgis_grid_official,regions,national,ordinances,sgis_grid500,regional_stats,team_grid,kcsm100,solar,estimates
    try:from . import imports
    except ImportError:pass
    with engine.begin() as c:c.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
    Base.metadata.create_all(engine)
    from .migrations import apply_migrations
    apply_migrations(engine)
    with Session() as db:
        try:
            from .emissions import ensure_gas_factor
            ensure_gas_factor(db)
        except Exception:db.rollback()

def build_cell_state_command(args):
    """build-cell-state: 칸 · 해 상태 표(팀 변화 모델 변형 H 입력)를 CSV로 쓴다. DB는 읽기만 한다."""
    from .cell_state import build_cell_state,parse_years
    if not args.region:raise SystemExit('--region <5자리 지역 코드>가 필요함')
    years=parse_years(args.years or '2014-2024')
    out=Path(args.out) if args.out else DATA_DIR/'derived'/'cell_state'/args.region/'cell_state.csv'
    if not str(out.resolve()).startswith(str(Path(DATA_DIR).resolve())):raise SystemExit(f'--out은 data 폴더({DATA_DIR}) 아래여야 함(Git에 올리지 않음)')
    with Session() as db:
        table,summary=build_cell_state(db,args.region,years)
    out.parent.mkdir(parents=True,exist_ok=True)
    table.to_csv(out,index=False,encoding='utf-8')
    out.with_suffix('.summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(json.dumps({'out':str(out),'rows':len(table),**summary},ensure_ascii=False,default=str))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['demo','online','status','enrich','collect','collect-history','collect-missing','validate-models','snapshot','llm-dataset','llm-eval','import-sgis-grid','import-sgis-grid500','import-regional-stats','import-team-grid','import-kcsm100',
        'national-admin','national-sgis','national-complexes','national-grid500','national-ordinances','national-all','prepare-region','regions',
        'check-standard','apply-standard','backfill-solar','region-energy-history','region-kapt-history','region-sgis-history','verify-cases','place-parcels','repick-default-grid','estimate-gaps','fetch-kea-rating','prepare-national','build-cell-state','collect-kapt-codes']);parser.add_argument('--year',type=int,default=DEFAULT_YEAR)
    parser.add_argument('--from',dest='from_year',type=int,default=2015);parser.add_argument('--to',dest='to_year',type=int,default=DEFAULT_YEAR)
    parser.add_argument('--datasets',default='',help='comma-separated: sgis,kma_asos,kapt_energy,energy,vworld_zoning,vworld_buildings,vworld_cadastral,building_register');parser.add_argument('--force',action='store_true')
    parser.add_argument('--source',choices=['energy','weather','kapt-energy','kma','sgis','vworld-zoning','vworld-cadastral'])
    parser.add_argument('--scope',choices=['smoke','limited','full'],default='smoke')
    parser.add_argument('--region',default=None,help='prepare-region/validate-models: 5-digit 법정 시·군·구 code (e.g. 41110 수원시)')
    parser.add_argument('--steps',default='',help='prepare-region: comma-separated steps (default: all)')
    parser.add_argument('--no-emd',action='store_true',help='national-sgis: 시군구만 (행정동 생략)')
    parser.add_argument('--model',default=None,help='llm-eval: Ollama model name (default OLLAMA_NARRATIVE_MODEL, then OLLAMA_MODEL)');parser.add_argument('--limit',type=int,default=None);parser.add_argument('--file',default=None)
    parser.add_argument('--years',default=None,help='region-energy-history / region-kapt-history / region-sgis-history: comma-separated years (default 2020 / 2021 / 2015 .. analysis year-1); build-cell-state: 2016-2024 or 2016,2018')
    parser.add_argument('--regions',default=None,help='llm-dataset: comma-separated study regions, first one sampled most (e.g. 52110,52710,11740)')
    parser.add_argument('--csv',action='append',default=[],help='check-standard: a CSV table to check before importing (repeatable)')
    parser.add_argument('--cases',default=None,help='verify-cases: cases file (default backend/cases/simulation_cases.json)')
    parser.add_argument('--only',default='',help='verify-cases: comma-separated case ids')
    parser.add_argument('--record',default=None,help='verify-cases: write this PC\'s results as the expected values to this file (reference PC only)')
    parser.add_argument('--out',default=None,help='verify-cases: write the full comparison (JSON) to this file')
    parser.add_argument('--note',default=None,help='verify-cases --record: data version note stored in the file')
    parser.add_argument('--until',type=int,default=None,help='prepare-national: queue regions ranked up to this (backend/reference/region_priority.csv)')
    parser.add_argument('--start',type=int,default=1,help='prepare-national: first rank to queue (default 1)')
    parser.add_argument('--dry-run',action='store_true',help='prepare-national: list what would be queued')
    parser.add_argument('--cancel',action='store_true',help='prepare-national: stop — regions not started yet are not run (started ones finish)')
    args=parser.parse_args()
    if args.command=='build-cell-state':return build_cell_state_command(args)  # read-only: no table creation, no writes
    init_tables()
    with Session() as db:
        seed_sources(db)
        if args.command in ('demo','snapshot'):
            from .service import dashboard
            if not db.scalar(select(func.count()).select_from(Grid)):
                from .collectors import collect_regions,collect_spatial,collect_weather
                for fn in [collect_regions,collect_spatial,collect_weather]:fn(db)
            if not db.scalar(select(func.count()).select_from(Grid)):raise SystemExit('No verified local geometry available')
            payload=dashboard(db,year=args.year);path=DATA_DIR/'snapshots';path.mkdir(exist_ok=True)
            (path/f'dashboard-{args.year}.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
            manifest=[]
            for f in sorted((DATA_DIR/'raw').rglob('*')):
                if f.is_file():manifest.append({'file':str(f.relative_to(DATA_DIR)),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size})
            (path/'raw-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
            if args.command=='demo':(DATA_DIR/'offline.flag').write_text('Verified local observations only. No outbound API calls.\n',encoding='utf-8')
            print(json.dumps({'status':'prepared','offline_mode':args.command=='demo','raw_files':len(manifest),'energy_records':payload['coverage']['energy_records'],'year':args.year}))
        elif args.command=='online':
            (DATA_DIR/'offline.flag').unlink(missing_ok=True);print('Online collection enabled unless DEMO_OFFLINE_MODE environment forces offline.')
        elif args.command=='status':
            from .service import serialize
            print(json.dumps([serialize(s) for s in db.scalars(select(DataSource))],ensure_ascii=False,indent=2))
        elif args.command=='enrich':
            from .official import collect_register,collect_kma
            for label,fn in [('register',lambda:collect_register(db,'smoke')),('KMA',lambda:collect_kma(db,args.year))]:
                try:print(label,fn())
                except Exception as exc:print(label,'not collected',type(exc).__name__)
            try:
                from .kapt import collect_kapt
                print('Kapt',collect_kapt(db))
            except (ImportError,AttributeError):print('Kapt adapter not installed')
            from .emissions import collect_factors
            print('Factors',collect_factors(db))
        elif args.command=='collect':
            from .tasks import queue_collection
            aliases={'kapt-energy':'kapt_energy','kma':'kma_asos','vworld-zoning':'vworld_zoning','vworld-cadastral':'vworld_cadastral'}
            datasets=[aliases.get(args.source,args.source)] if args.source else ['weather']
            job=queue_collection(db,datasets,f'{args.year}-01',f'{args.year}-12',args.scope);print('job',job.id,job.status)
        elif args.command in ('collect-history','collect-missing'):
            from .history import collect_history
            datasets=[d.strip() for d in args.datasets.split(',') if d.strip()] or None
            result=collect_history(db,args.from_year,args.to_year,datasets=datasets,force=args.force,log=lambda m:print(m,flush=True))
            statuses={}
            for item in result['items'].values():statuses[item['status']]=statuses.get(item['status'],0)+1
            print(json.dumps({'statuses':statuses,'blocked':result['blocked'],'resume_at':result.get('resume_at')},ensure_ascii=False))
        elif args.command=='llm-dataset':
            from .llm_dataset import build_dataset
            regions=[r.strip() or None for r in args.regions.split(',')] if args.regions else None
            print(json.dumps(build_dataset(db,args.from_year,args.to_year,regions=regions,log=lambda m:print(m,flush=True)),ensure_ascii=False))
        elif args.command=='llm-eval':
            from .llm_dataset import evaluate
            print(json.dumps(evaluate(args.file,model=args.model,limit=args.limit,log=lambda m:print(m,flush=True)),ensure_ascii=False))
        elif args.command=='import-sgis-grid':
            from .sgis_grid import import_sgis_grid,meta
            result=import_sgis_grid(db,args.file,force=args.force)
            print(json.dumps(dict(result,loaded={k:meta(db)[k] for k in ('year','cells','stat_rows')}),ensure_ascii=False))
        elif args.command=='import-sgis-grid500':
            # SGIS 500m 격자 통계 (자료제공 신청분): DATA_DIR/raw/sgis_grid_500m/**/<연도>년_<주제>_<블록>_500M.csv
            from .sgis_grid500 import import_sgis_grid500
            result=import_sgis_grid500(db,args.file,force=args.force,log=lambda m:print(m,flush=True))
            print(json.dumps(result,ensure_ascii=False,default=str))
        elif args.command=='import-regional-stats':
            # GIR 지역 온실가스 인벤토리(DATA_DIR/raw/research/gir/regional_*/*.xlsx), 가스공사 시·도 도시가스(DATA_DIR/raw/gas/*.csv)
            from .regional_stats import import_all,row_counts
            result=import_all(db,force=args.force)
            print(json.dumps(dict(result,rows=row_counts(db)),ensure_ascii=False))
        elif args.command=='import-team-grid':
            # 팀 데이터셋(urban-carbon): DATA_DIR/raw/team_urban_carbon/<묶음 날짜>/<5자리 코드>_<도시>/<연도>/grid_500m.csv 등
            from .team_grid import import_team_grid,counts
            result=import_team_grid(db,Path(args.file) if args.file else None,force=args.force,log=lambda m:print(m,flush=True))
            print(json.dumps(dict(result,rows=counts(db)),ensure_ascii=False))
        elif args.command=='import-kcsm100':
            # 선도소프트 탄소공간지도 100m 건물 전기 배출: DATA_DIR/raw/sundosoft_kcsm100/<받은 날>/**/탄소배출_건물_전기_격자_100m_*_<연도>.csv
            from .kcsm100 import import_kcsm100,counts as kcsm_counts
            from .area import forget_inputs
            result=import_kcsm100(db,Path(args.file) if args.file else None,force=args.force,log=lambda m:print(m,flush=True))
            forget_inputs()
            print(json.dumps(dict(result,rows=kcsm_counts(db)),ensure_ascii=False))
        elif args.command=='validate-models':
            from .model_service import model_status
            print(json.dumps(model_status(db,args.year,train=True,region=args.region),ensure_ascii=False,indent=2))
        elif args.command.startswith('national-'):
            from .regions import ensure_default_region
            from . import national
            ensure_default_region(db)
            say=lambda m:print(m,flush=True)
            steps={'national-admin':['admin'],'national-sgis':['sgis'],'national-complexes':['complexes'],'national-grid500':['grid500'],
                   'national-ordinances':['ordinances'],'national-all':['admin','sgis','complexes','grid500','ordinances']}[args.command]
            for step in steps:
                if step=='admin':result=national.collect_admin_units(db,log=say)
                elif step=='sgis':result=national.collect_national_sgis(db,include_emd=not args.no_emd,log=say)
                elif step=='complexes':result=national.collect_national_complexes(db,log=say)
                elif step=='ordinances':
                    from .ordinances import collect_ordinances
                    result=collect_ordinances(db,[args.region] if args.region else None,force=args.force,log=say)
                else:result=national.collect_national_grid500(db,log=say)
                print(json.dumps({step:result},ensure_ascii=False,default=str),flush=True)
        elif args.command=='prepare-region':
            if not args.region:raise SystemExit('--region 코드가 필요합니다 (예: 41110)')
            from .region_prepare import prepare_region
            from .regions import ensure_default_region
            ensure_default_region(db)
            steps=[s.strip() for s in args.steps.split(',') if s.strip()] or None
            result=prepare_region(db,args.region,steps,log=lambda m:print(m,flush=True),force=args.force)
            print(json.dumps({'code':result['code'],'status':result['status'],'datasets':{k:{'status':v.get('status'),'message':v.get('message')} for k,v in (result['datasets'] or {}).items()}},ensure_ascii=False,indent=1))
        elif args.command=='prepare-national':
            # 전국 수집을 순위대로(2026-11-21): --until 34 = 3단계까지. --cancel = 시작 안 한 지역은 돌리지 않음
            from .region_priority import cancel_queued,plan,queue_national
            if args.cancel:
                import os,redis
                connection=redis.Redis.from_url(os.getenv('REDIS_URL','redis://redis:6379/0'))
                print(json.dumps({'stopped':cancel_queued(db,connection,log=lambda m:print(m,flush=True))},ensure_ascii=False))
            else:
                if args.until is None:raise SystemExit('--until 순위가 필요합니다 (예: --until 34 = 3단계까지)')
                if args.dry_run:
                    for row in plan(db,args.until,start=args.start):print(row['rank'],row['tier'],row['region_code'],row['name'],row['complexes'],row['status'],flush=True)
                result=queue_national(db,args.until,start=args.start,dry_run=args.dry_run,log=lambda m:print(m,flush=True))
                print(json.dumps({k:len(v) for k,v in result.items()}|{'missing':result['missing']},ensure_ascii=False))
        elif args.command=='region-energy-history':
            # 준비한 지역의 건축HUB 전 지번 과거 연도 (지역 준비는 분석 연도만 받음). --region 11740,26440 --years 2024,2022
            from .region_prepare import collect_energy_years
            years=[int(y) for y in (args.years or '').split(',') if y.strip()] or list(range(2020,DEFAULT_YEAR))
            for code in [r.strip() for r in (args.region or '').split(',') if r.strip()]:
                print(json.dumps(collect_energy_years(db,code,years,log=lambda m:print(m,flush=True)),ensure_ascii=False,default=str),flush=True)
        elif args.command=='region-kapt-history':
            # 준비한 지역의 K-apt 월별 에너지 과거 연도 (지역 준비는 분석 연도만 받음). --region 52710,41110 --years 2024,2023
            # 일일 한도(개발계정 5,000건)에 걸리면 그 뒤 지역은 묻지 않음: 한도는 키 하나에 걸림
            from .region_prepare import collect_kapt_years
            years=[int(y) for y in (args.years or '').split(',') if y.strip()] or list(range(2021,DEFAULT_YEAR))
            for code in [r.strip() for r in (args.region or '').split(',') if r.strip()]:
                result=collect_kapt_years(db,code,years,log=lambda m:print(m,flush=True))
                print(json.dumps(result,ensure_ascii=False,default=str),flush=True)
                if result.get('stopped') in ('WAITING','BLOCKED','OUTAGE'):
                    break
        elif args.command=='collect-kapt-codes':
            # 분석 표본으로 고른 단지 코드 목록의 K-apt 월별 에너지(지역과 관계없이). --file /data/ops/<목록>.txt --years 2024,2023
            # 받은 달은 건너뛰므로 일일 한도(22)에 걸리면 다음 날 같은 명령을 다시 실행하면 이어 받음
            from .kapt_energy import ProviderOutageError, collect_kapt_energy
            from .cache import ExternalError
            codes=[line.strip() for line in Path(args.file).read_text(encoding='utf-8').splitlines() if line.strip() and not line.startswith('#')]
            years=[int(y) for y in (args.years or '').split(',') if y.strip()]
            if not codes or not years:
                raise SystemExit('collect-kapt-codes: --file(코드 목록)과 --years가 필요합니다')
            for year in years:
                try:
                    stats=collect_kapt_energy(db,year,'full',history=True,codes=codes,retry_rounds=1,retry_wait_s=120,outage_pause_s=300,max_outage_pauses=6,
                                              progress=lambda f,m:print(f'{f:.0%} {m}',flush=True))
                    print(json.dumps({'year':year,**stats},ensure_ascii=False,default=str),flush=True)
                except (ProviderOutageError,ExternalError) as exc:
                    db.rollback()
                    print(json.dumps({'year':year,'stopped':str(exc)},ensure_ascii=False),flush=True)
                    break
        elif args.command=='region-sgis-history':
            # 준비한 지역의 SGIS 행정동 인구·가구·경계 과거 연도 (지역 준비의 sgis_admin 단계는 최신 공표 연도만). --region 41110,36110 --years 2015,2016
            from .region_prepare import collect_sgis_years
            years=[int(y) for y in (args.years or '').split(',') if y.strip()] or list(range(2015,DEFAULT_YEAR))
            for code in [r.strip() for r in (args.region or '').split(',') if r.strip()]:
                print(json.dumps(collect_sgis_years(db,code,years,log=lambda m:print(m,flush=True)),ensure_ascii=False,default=str),flush=True)
        elif args.command=='repick-default-grid':
            # 기본 대상지를 "전력 · 가스가 모두 관측된 격자 중 세대수 최다"로 다시 고름(2026-11-23 D5). 기본은 보기만, --force로 저장
            from .kapt import ApartmentComplex
            from .region_prepare import pick_default_grid
            from .regions import StudyRegion
            codes=[r.strip() for r in (args.region or '').split(',') if r.strip()]
            regions=[r for r in db.scalars(select(StudyRegion).where(StudyRegion.status=='READY')) if not codes or r.code in codes]
            complexes=list(db.scalars(select(ApartmentComplex).where(ApartmentComplex.grid_id.is_not(None))))
            all_complexes=list(db.scalars(select(ApartmentComplex)))  # once for every region (floor areas, households)
            from .regions import region_grid_ids
            from .regions import DEFAULT_REGION
            for region in sorted(regions,key=lambda r:r.code):
                if region.code==DEFAULT_REGION:print(json.dumps({'region':region.code,'skip':'원래 지역은 첫 화면이 시험 대상지(TestbedSector)를 씀'},ensure_ascii=False),flush=True);continue
                ids=region_grid_ids(db,region.code);hh={}
                for c in complexes:
                    if c.grid_id in ids and region.legal_codes and (c.bjd_code or '')[:5] in region.legal_codes:hh[c.grid_id]=hh.get(c.grid_id,0)+(c.households or 0)
                if not hh:print(json.dumps({'region':region.code,'skip':'K-apt 단지 없음'},ensure_ascii=False),flush=True);continue
                grid,reason=pick_default_grid(db,region,hh,args.year,all_complexes)
                changed=grid!=region.default_grid_id
                print(json.dumps({'region':region.code,'before':region.default_grid_id,'after':grid,'changed':changed,'reason':reason,'saved':bool(changed and args.force)},ensure_ascii=False),flush=True)
                if changed and args.force:region.default_grid_id=grid;db.commit()
            if args.force:print('저장함. api가 지역 입력을 메모리에 두므로 api를 다시 켜야 첫 화면에 반영됨',flush=True)
        elif args.command=='place-parcels':
            # 지적도에 없는 건축HUB 계량 지번을 격자에 넣기: 같은 본번 → (그래도 없으면) VWorld 주소 좌표. --region 52110,41110 (없으면 모든 지역)
            from .energy_parcels import place_by_address,place_missing_parcels
            from .regions import get_region
            for code in [r.strip() for r in (args.region or '').split(',') if r.strip()] or [None]:
                region=get_region(db,code) if code else None
                codes=sorted({str(c)[:5] for c in ((region.legal_codes if region else None) or ([code] if code else []))}) or None
                main=place_missing_parcels(db,codes)
                address=place_by_address(db,codes) if codes else {'skipped':'--region 필요(주소 조회는 지역 단위)'}
                print(json.dumps({'region':code,'main_lot':main,'address':address},ensure_ascii=False),flush=True)
        elif args.command=='backfill-solar':
            # ERA5-Land 일사량을 지역마다 받아 태양광 연 발전량 추정에 씀 (docs/DATA_STANDARD.md 5.13)
            from .solar import backfill
            regions=[r.strip() for r in (args.region or '').split(',') if r.strip()] or None
            print(json.dumps(backfill(db,regions=regions,log=lambda m:print(m,flush=True)),ensure_ascii=False,indent=1,default=str))
        elif args.command=='estimate-gaps':
            # docs/DATA_STANDARD.md 4.1: 관측 표는 그대로 두고 빈 자리 추정만 estimated_values에 다시 쓴다
            from .estimates import estimate_region
            from .area import forget_inputs
            for code in [c.strip() for c in (args.region or '').split(',') if c.strip()] or [None]:
                print(json.dumps(estimate_region(db,code,args.to_year,log=lambda m:print(m,flush=True)),ensure_ascii=False,indent=1,default=str),flush=True)
            forget_inputs()
        elif args.command in ('check-standard','apply-standard'):
            # docs/DATA_STANDARD.md: apply brings stored values to the current rule, check counts what does not follow it.
            from .standard import apply_standard,check_standard
            if args.command=='apply-standard':
                print(json.dumps(apply_standard(db,log=lambda m:print(m,flush=True)),ensure_ascii=False,indent=1,default=str))
            report=check_standard(db,csv_paths=args.csv)
            for item in report['items']:
                print(f"[{item['status']:4}] {item['label']}: {item['detail']}",flush=True)
            print(json.dumps({'version':report['version'],'summary':report['summary'],'ok':report['ok']},ensure_ascii=False))
            if args.command=='check-standard' and not report['ok']:raise SystemExit(1)
        elif args.command=='verify-cases':
            # 고정 사례(지역·입력값)를 계산해 기준 PC 값과 비교 (읽기만 함: 시나리오·보고서를 저장하지 않음). docs/USER_MANUAL.md 9절
            from .cases import load,record,verify
            cases=load(args.cases)
            if args.record:
                Path(args.record).write_text(json.dumps(record(db,cases,args.note),ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
                print('기록:',args.record)
            else:
                only={c.strip() for c in args.only.split(',') if c.strip()} or None
                report=verify(db,cases,only)
                if args.out:Path(args.out).write_text(json.dumps(report,ensure_ascii=False,indent=1,default=str),encoding='utf-8')
                if not report['all_match']:raise SystemExit(1)
        elif args.command=='fetch-kea-rating':
            # 효율등급 인증 원본(JSON 쪽)을 DATA_DIR/raw/kea_building_rating/<받은 날>/에 받기만 함. DB에 넣지 않음
            from .settings import offline_mode
            from .kea_rating import fetch_all,default_out_dir,service_key
            if offline_mode():raise SystemExit('오프라인 모드: 외부 요청을 하지 않습니다')
            out=Path(args.file) if args.file else default_out_dir(DATA_DIR)
            print(json.dumps(dict(fetch_all(out,service_key(),log=lambda m:print(m,flush=True)),out=str(out)),ensure_ascii=False))
        elif args.command=='regions':
            from .regions import StudyRegion,region_summary
            print(json.dumps([region_summary(r) for r in db.scalars(select(StudyRegion))],ensure_ascii=False,indent=1,default=str))

if __name__=='__main__':main()
