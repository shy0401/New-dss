"""배출계수: 전력은 GIR 승인 계수(원문 증빙 확인), 도시가스는 GIR 승인 국가 고유 CO₂ 계수로 만든 계수.

도시가스 계수 (근거: docs/DATA_STANDARD.md 5.5):
  CO₂: 온실가스종합정보센터 2021년 승인 국가 온실가스 배출계수(수정본) 연료연소 1A, 도시가스(LNG) 15.236 tC/TJ
       → × 44/12 = 55,865.3 kgCO₂/TJ (순발열량 기준. 2022~2025년 승인에서 바뀌지 않음, 원문 data/raw/research/gir/b56_2_*).
  CH₄·N₂O: 고정연소 국가 고유 계수가 없어(국가 고유 CH₄·N₂O는 도로수송만) IPCC 2006 2권 2장 표 2.4·2.5 상업·주거 부문 천연가스
       기본값 CH₄ 5 · N₂O 0.1 kg/TJ, GWP는 AR5(CH₄ 28 · N₂O 265; GIR 2025 승인 전력 CO2eq 0.4330이 같은 GWP로 합산됨)
  → 56,031.8 kgCO₂eq/TJ(순발열량) = 0.20171 kgCO₂eq/kWh(순발열량 기준 kWh).
  건축HUB 가스 kWh는 에너지 사용량이므로 총발열량 기준(정부 별표 '연료별 국가 고유 발열량 및 배출계수' 각주: 배출량 산정은
  순발열량, 에너지 사용량 집계는 총발열량; 도시가스 요금은 2012-07부터 열량(MJ) 기준)으로 보고, 에너지법 시행규칙 에너지열량
  환산기준(2022-11) 도시가스(LNG) 순/총발열량 38.5/42.7 MJ/Nm³로 맞춰 0.20171 × 38.5/42.7 = 0.1819 kgCO₂eq/kWh.
"""
import json
from .models import EmissionFactor,DataSource
from .collectors import RAW,record_asset,update_source,client

GIR_URL='https://www.gir.go.kr/home/board/read.do?boardId=82&boardMasterId=2&menuId=36'
IPCC_URL='https://www.ipcc-nggip.iges.or.jp/public/2006gl/vol2.html'
GAS_FACTOR_ID='gir-2021-city-gas-lng'
OLD_GAS_FACTOR_IDS=('rule-city-gas-ipcc2006-gcv',)          # 2026-11-18 이전의 가정 계수(IPCC 기본 CO₂ 56,100) 행
GAS_CO2_TC_PER_TJ=15.236                                    # GIR 2021 승인, 도시가스(LNG), 순발열량 기준
GAS_CH4_KG_PER_TJ, GAS_N2O_KG_PER_TJ = 5, 0.1               # IPCC 2006 2권 2장 표 2.4(상업)·2.5(주거) 천연가스 기본값
GWP_CH4, GWP_N2O = 28, 265                                  # AR5
GAS_NCV_MJ_PER_NM3, GAS_GCV_MJ_PER_NM3 = 38.5, 42.7         # 에너지법 시행규칙 에너지열량환산기준(2022-11) 도시가스(LNG)
GAS_CO2EQ_KG_PER_TJ=round(GAS_CO2_TC_PER_TJ*44/12*1000+GAS_CH4_KG_PER_TJ*GWP_CH4+GAS_N2O_KG_PER_TJ*GWP_N2O,1)   # 56,031.8
GAS_NCV_FACTOR=round(GAS_CO2EQ_KG_PER_TJ*3.6e-6,5)          # 0.20171 kgCO2eq/kWh (순발열량 기준 kWh)
GAS_FACTOR=round(GAS_NCV_FACTOR*GAS_NCV_MJ_PER_NM3/GAS_GCV_MJ_PER_NM3,4)   # 0.1819 kgCO2eq/kWh (총발열량 기준 kWh, 적용값)
GAS_FACTOR_NOTE=(f'GIR 2021 승인 국가 고유 배출계수 도시가스(LNG) CO2 {GAS_CO2_TC_PER_TJ} tC/TJ(= {GAS_CO2_TC_PER_TJ*44/12*1000:,.1f} kgCO2/TJ, 순발열량) + '
                 f'IPCC 2006 주거·상업 CH4 {GAS_CH4_KG_PER_TJ} · N2O {GAS_N2O_KG_PER_TJ} kg/TJ, AR5 GWP(28·265) → {GAS_CO2EQ_KG_PER_TJ:,.1f} kgCO2eq/TJ. '
                 '건축HUB 가스 kWh(에너지 사용량, 총발열량 기준)에 에너지열량환산기준 순/총발열량 38.5/42.7 MJ/Nm3로 맞춤. '
                 f'순발열량 기준 kWh이면 {GAS_NCV_FACTOR:.4f}.')

def ensure_gas_factor(db):
    """Register the city-gas factor (GIR national CO2 factor) and drop the earlier assumed rule row."""
    for old in OLD_GAS_FACTOR_IDS:
        row=db.get(EmissionFactor,old)
        if row is not None: db.delete(row)
    db.merge(EmissionFactor(id=GAS_FACTOR_ID,energy_type='GAS',factor=GAS_FACTOR,factor_unit='kgCO2eq/kWh',reference_year=2021,
                            source='도시가스 국가 고유 배출계수 (GIR 2021 승인 CO2 15.236 tC/TJ · IPCC 2006 CH4·N2O · 에너지열량환산기준)',source_url=GIR_URL,
                            effective_from='2000-01-01',notes=GAS_FACTOR_NOTE))
    db.commit()
    return GAS_FACTOR

# 이전 공표 전력 배출계수 (소비단). 공표일부터 다음 공표 전까지의 계산 연도에 쓴다(factors_for: 그해 말까지 공표된 것 중 최신).
# 원문 PDF는 data/raw/research/gir/b<게시물>_*.pdf, 확인용 텍스트(pdftotext -layout)는 같은 이름의 .txt.
HISTORIC_ELECTRICITY = (
    {"id": "gir-2018-approved-consumption", "board": 44, "factor": 0.4594, "reference_year": 2018, "effective_from": "2019-01-02",
     "evidence": ("0.4567", "0.0036", "0.0085", "소비단"),
     "source": "GIR 2018 승인 국가고유 배출계수 / 전력 소비단",
     "notes": "게시일 2019-01-02. 원문은 CO2 0.4567 t/MWh, CH4 0.0036 kg/MWh, N2O 0.0085 kg/MWh만 있어 CO2eq는 "
              "당시 지침('96 IPCC, SAR)의 GWP(CH4 21, N2O 310)로 합산한 값(0.45941). 2019~2021년 계산에 적용."},
    {"id": "gir-2021-approved-consumption", "board": 56, "factor": 0.4781, "reference_year": 2021, "effective_from": "2022-01-10",
     "evidence": ("0.4781", "소비단"),
     "source": "GIR 2021 승인 국가 온실가스 배출계수 / 전력 소비단",
     "notes": "게시일 2022-01-10(수정본). CO2eq 0.4781 tCO2eq/MWh. 2022~2024년 계산에 적용(2024 승인 계수는 2025-03-31 공표)."},
)
# The rule (docs/DATA_STANDARD.md 5.4): a year is calculated with the latest GIR approval published by its 31 December.
# When an approval publishes a single-year and a multi-year average value, the average is used (the 2024 approval,
# 0.4541, is itself built on 2020~2022 statistics). 2025 승인 (2025-12-18): '21~'23 평균 0.4330; 단년 2023 0.4173 is 3.6% lower.
HISTORIC_ELECTRICITY = HISTORIC_ELECTRICITY + (
    {"id": "gir-2025-approved-consumption", "board": 86, "factor": 0.4330, "reference_year": 2025, "effective_from": "2025-12-18",
     "evidence": ("0.4330", "0.4173", "소비단", "평균"),
     "source": "GIR 2025 승인 국가 온실가스 배출계수 / 전력 소비단 ('21~'23 평균)",
     "notes": "게시일 2025-12-18. 소비단 CO2eq: 2023년 단년 0.4173, 2021~2023년 평균 0.4330 tCO2eq/MWh. 같은 회차의 다년 평균을 쓰는 규칙에 따라 "
              "0.4330을 2025년 계산에 적용(그해 말까지 공표된 최신 승인 계수)."},
)
# Calculation year → factor, the same schedule the database holds (factors_for); used where no session is at hand.
ELECTRICITY_SCHEDULE = (("2019-01-02", 0.4594), ("2022-01-10", 0.4781), ("2025-03-31", 0.4541), ("2025-12-18", 0.4330))


def electricity_factor_for_year(year: int) -> float | None:
    """GIR consumption-side factor (kgCO2eq/kWh) for a calculation year; None before 2019 (no approval text here)."""
    chosen = None
    for published, factor in ELECTRICITY_SCHEDULE:
        if published <= f"{int(year)}-12-31":
            chosen = factor
    return chosen


def _gir_evidence(board):
    folder=RAW/'research'/'gir'
    for txt in sorted(folder.glob(f'b{board}_*.txt')):
        pdf=txt.with_suffix('.pdf')
        if pdf.exists():return pdf,txt.read_text(encoding='utf-8',errors='replace')
    return None,None


def collect_historic_factors(db):
    """Register the older GIR electricity factors whose PDF and text evidence are in data/raw/research/gir."""
    registered=[]
    for item in HISTORIC_ELECTRICITY:
        pdf,text=_gir_evidence(item['board'])
        if not pdf:continue
        if not all(s in text for s in item['evidence']):raise ValueError(f"배출계수 증빙 불일치: {pdf.name}")
        url=f"https://www.gir.go.kr/home/board/read.do?boardId={item['board']}&boardMasterId=2&menuId=36"
        db.merge(EmissionFactor(id=item['id'],energy_type='ELECTRICITY',factor=item['factor'],factor_unit='kgCO2eq/kWh',reference_year=item['reference_year'],
                                source=item['source'],source_url=url,effective_from=item['effective_from'],notes=item['notes']+' tCO2eq/MWh = kgCO2eq/kWh.'))
        registered.append(item['id'])
    db.commit()
    return registered


def collect_factors(db):
    path=RAW/'research'/'gir_2024_approved_electricity_factors.pdf'
    evidence=RAW/'research'/'gir_2024_approved_electricity_factors.txt'
    if not path.exists() or not evidence.exists():
        source=db.get(DataSource,'factors');source.status='MANUAL_DOWNLOAD_REQUIRED';source.source_url=GIR_URL;source.quality='GIR 원문 PDF와 검증 텍스트 필요';db.commit();return 0
    text=evidence.read_text(encoding='utf-8')
    if not all(s in text for s in ['0.4541','소비단','2024']):raise ValueError('배출계수 증빙 불일치')
    db.merge(EmissionFactor(id='gir-2024-approved-consumption',energy_type='ELECTRICITY',factor=.4541,factor_unit='kgCO2eq/kWh',reference_year=2024,source='GIR 2024 승인 국가 온실가스 배출계수 / 소비단',source_url=GIR_URL,effective_from='2025-03-31',notes='공표일 2025-03-31; 통계기간 2020–2022. 별도 법적 발효일 미제시. 2025 전체 비교에 회고적으로 동일 계수를 적용하는 프로젝트 방법이며, 2025 실측 전력계통 계수라는 뜻이 아님. tCO2eq/MWh = kgCO2eq/kWh.'))
    record_asset(db,'factors',{'path':str(path),'url':GIR_URL,'timestamp':path.stat().st_mtime},1,'2024 승인 /2020–2022 통계/2025-03-31 공표')
    source=db.get(DataSource,'factors');source.source_url=GIR_URL;source.reference_period='2024 승인 / 2025-03-31 공표';source.limitation=f'전기 소비단 0.4541 kgCO2eq/kWh (GIR 승인). 도시가스는 GIR 승인 국가 고유 계수로 만든 {GAS_FACTOR} kgCO2eq/kWh (총발열량 기준 kWh; 순발열량 기준이면 {GAS_NCV_FACTOR:.4f}).'
    ensure_gas_factor(db)
    historic=collect_historic_factors(db)
    if historic:
        source=db.get(DataSource,'factors')
        source.reference_period='2018·2021·2024·2025 승인 (공표일부터 적용)'
        source.limitation=(f'전기 소비단: 2019~2021년 0.4594(2018 승인, CO2eq 환산), 2022~2024년 0.4781(2021 승인), 2025년 0.4330(2025 승인 21~23 평균, 2025-12-18 공표) kgCO2eq/kWh. '
                           f'규칙: 그해 말까지 공표된 최신 승인 계수(docs/DATA_STANDARD.md 5.4). 도시가스는 GIR 승인 국가 고유 계수로 만든 {GAS_FACTOR} kgCO2eq/kWh(5.5).')
    update_source(db,'factors',2+len(historic),2+len(historic),status='PARTIAL',quality='전기 GIR 승인 계수(공표 회차별) / 가스 GIR 승인 국가 고유 CO2 계수(2021 승인) + IPCC 2006 CH4·N2O',missing=0)
    return 1+len(historic)
