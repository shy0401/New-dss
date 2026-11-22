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

# 지역난방 열 배출계수 (기준 문서 5.16, 2026-11-20). 한국지역난방공사 공표 지사별 계수(kg/TJ, "지역난방용 열 사용에 대한 온실가스
# 배출량 산정시 사용"), 원본 data/raw/kdhc_emission_factors/2026-11-20/ (공공데이터포털 15090320, sha256 6c45b8f2…).
# 값은 원본 그대로 (CO2, CH4, N2O). CO2eq = CO2 + CH4×28 + N2O×265 (AR5, 가스와 같음), kg/kWh = kg/TJ × 3.6e-6.
KDHC_URL='https://www.data.go.kr/data/15090320/fileData.do'
KDHC_HEAT_KG_PER_TJ = {
    "세종": {2025: (40026, 0.7199, 0.072), 2024: (42672, 0.7667, 0.0767), 2023: (41305, 0.742, 0.0742), 2022: (42750, 0.766, 0.0766),
             2021: (41356, 0.7436, 0.0743), 2020: (41478, 0.7449, 0.0745), 2019: (44477, 0.7987, 0.0798), 2018: (43105, 0.7753, 0.0775),
             2017: (43811, 0.793, 0.0793), 2016: (46025, 0.8254, 0.0826), 2015: (45105, 0.8102, 0.0815)},
    "수도권연계": {2025: (36136, 0.6569, 0.0667), 2024: (35058, 0.634, 0.064), 2023: (35991, 0.6519, 0.0661), 2022: (37317, 0.6777, 0.0689),
               2021: (35936, 0.6534, 0.0661), 2020: (34771, 0.6316, 0.0638), 2019: (35257, 0.6466, 0.0662), 2018: (35825, 0.665, 0.0701),
               2017: (37003, 0.7323, 0.086), 2016: (36912, 0.7479, 0.0904), 2015: (37697, 0.7608, 0.0894)},
    "대구": {2025: (36543, 3.8276, 0.486), 2024: (48249, 2.5138, 0.3705), 2023: (53392, 6.2051, 0.9549), 2022: (57447, 5.0108, 0.832),
             2021: (52792, 5.4446, 0.8832), 2020: (47746, 6.6648, 1.0377), 2019: (41243, 6.4941, 1.0044), 2018: (44563, 5.8476, 0.9124),
             2017: (38242, 6.1174, 0.9275), 2016: (39256, 7.4262, 1.0931), 2015: (37707, 8.1003, 1.1708)},
    "양산": {2025: (36782, 0.6583, 0.0658), 2024: (35444, 0.6346, 0.0635), 2023: (43042, 0.7686, 0.0769), 2022: (50642, 0.9027, 0.0903),
             2021: (48312, 0.8612, 0.0861), 2020: (48507, 0.8647, 0.0865), 2019: (48733, 0.8687, 0.0869), 2018: (49916, 0.8898, 0.089),
             2017: (48865, 0.871, 0.0871), 2016: (46697, 0.8324, 0.0832), 2015: (46491, 0.8287, 0.0829)},
    # 2026-11-22 (기준 문서 5.16 · 판 1.49): 같은 원본 CSV의 김해 · 광주전남 지사 열(스크립트로 옮김, 양산 열로 옮김 방식 대조)
    "김해": {2025: (52282, 0.9319, 0.0932), 2024: (35747, 0.6372, 0.0637), 2023: (35595, 0.6345, 0.0635), 2022: (37342, 0.6656, 0.0666),
             2021: (35513, 0.633, 0.0633), 2020: (34879, 0.6217, 0.0622), 2019: (34638, 0.6174, 0.0617), 2018: (36492, 0.6505, 0.065),
             2017: (35713, 0.6366, 0.0637), 2016: (36140, 0.6442, 0.0644), 2015: (36156, 0.6445, 0.0644)},
    "광주전남": {2025: (40980, 15.325, 2.0285), 2024: (34068, 16.9847, 2.2506), 2023: (41830, 13.93, 1.8397), 2022: (52803, 4.7098, 0.5981),
               2021: (57456, 4.4617, 0.5625), 2020: (59672, 1.2953, 0.1374), 2019: (59805, 1.066, 0.1066), 2018: (59665, 1.0635, 0.1064),
               2017: (63095, 3.3508, 0.4136), 2016: (59188, 1.055, 0.1055), 2015: (77793, 2.8135, 0.5341)},
}
# 분석 지역 → 열 공급 지사. 그 시군구의 지역난방 공급 지역이 모두 한 지사로 원문 확인된 곳만(기준 문서 5.16):
# 세종 = 세종지사, 수원 = 수도권 연계지사(수원 · 광교 지사 포함, 공사 온실가스 통계 페이지),
# 대구 달서 = 대구지사(성서 · 대곡 · 용산 · 장기지구), 양산 = 양산지사(물금 · 사송지구) — 한국에너지공단 2021 집단에너지사업 편람
# 「집단에너지 지역지정 현황(지역별)」. 사업자가 둘 이상(성남: 분당 · 판교 한난 + 위례 나래에너지서비스)인 곳, 지정 지역이 없는
# 곳(제주)은 없음(None) → 열 탄소를 계산하지 않고 가정 문장만. 계수가 공표되지 않은 사업자(남양주 별내에너지 등)는 아래
# HEAT_SUPPLIER_OTHER의 대체 계수로 계산(2026-11-21부터, 기준 문서 5.16)
# 2026-11-22 새 상세 수집 지역(같은 편람 Ⅵ장 지역지정 현황 161~167쪽 · 표 II-2 공급 중인 사업장 13~14쪽 · 사업자 소개):
# 고양(고양 · 삼송원흥) · 강남(수서 · 일원 · 남서울 · 강남보금자리) · 용인(용인 · 서천) · 파주(교하 · 운정) = 수도권 연계지사
# (공사 온실가스 통계 페이지: 수원 · 중앙 · 파주 · 용인 · 화성 · 강남 · 분당 · 판교 · 삼송 · 고양 · 광교 · 동탄지사),
# 김해(대청 · 유하 · 관동) = 김해지사, 나주(광주 · 전남 혁신도시) = 광주전남지사. '미정' 지정 지역(고양 장항 · 일산테크노밸리,
# 용인 언남)은 2020년에 공급하는 사업자가 없어 세지 않음
HEAT_SUPPLIER_BRANCH = {"36110": "세종", "41110": "수도권연계", "27290": "대구", "48330": "양산",
                        "41280": "수도권연계", "11680": "수도권연계", "41460": "수도권연계", "41480": "수도권연계",
                        "48250": "김해", "12170": "광주전남"}

# 공급자가 편람으로 확인됐으나 공표 열 배출계수가 없는 사업자(기준 문서 5.16, 2026-11-21): 지자체 온실가스 배출량 산정지침 Ver4.1의
# 지역난방 열 간접배출계수 공통값 0.1226 tCO2eq/Gcal(2007 · 2008년 전국 집단에너지시설 평균, 한국환경공단)을 대체(SUBSTITUTE)로.
# 값 · 뜻은 서울시 온실가스 인벤토리 2021 · 2022년도분 표와 탄소공간지도(국토교통부) 산정방법으로 확인(지침 원문 공식 사본은 확인 필요).
# 2026-11-22 새 상세 수집 지역(편람 같은 쪽 · 사업자 소개, 공표 계수는 웹 검색 · 사업자 누리집에서 못 찾음):
# GS파워 안양 사업장 공급구역 "안양, 군포, 과천, 의왕" · 부천 사업장(중동 · 상동 · 옥길), 서울에너지공사(양천 목동 · 신정),
# 나래에너지서비스(하남 미사 · 감일 · 현안 · 위례 일부), 인천종합에너지(연수 송도), 안산도시개발(안산 고잔 · 신길, 반월공업단지
# 지에스이앤알은 산업단지라 뺌), 디에스파워(오산 운암 · 세교 · 세교2), 내포그린에너지(홍성 내포신도시), 삼천리(광명 역세권 ·
# 소하 · 신촌 · 하안13단지), 대성에너지(달성 죽곡 1 · 2 · 세천)
HEAT_SUPPLIER_OTHER = {"11740": "나래에너지서비스", "26440": "부산도시가스", "52140": "전북집단에너지", "41360": "별내에너지",
                       "41290": "GS파워", "41410": "GS파워", "41170": "GS파워", "41430": "GS파워", "41190": "GS파워",
                       "11470": "서울에너지공사", "41450": "나래에너지서비스", "28185": "인천종합에너지", "41270": "안산도시개발",
                       "41370": "디에스파워", "44800": "내포그린에너지", "41210": "삼천리", "27710": "대성에너지"}
LOCAL_GUIDELINE_HEAT_TCO2EQ_PER_GCAL = 0.1226
KWH_PER_GCAL = 1163.0                       # 1 Gcal = 4.1868 GJ = 1,163 kWh
LOCAL_GUIDELINE_HEAT_KG_PER_KWH = round(LOCAL_GUIDELINE_HEAT_TCO2EQ_PER_GCAL * 1000 / KWH_PER_GCAL, 4)   # 0.1054


# 사업자가 둘 이상인 시군구는 법정동마다 공급자(2026-11-22, 기준 문서 5.16 · 판 1.52). 편람 지구 이름과 그 동 K-apt 지역난방 단지
# 이름이 맞는 동만 적는다(예: 창곡동 "LH위례31단지" ↔ 나래 위례신도시). 적지 않은 동(성남 대장 · 신흥 · 금광 · 고등 · 복정 등 2020년
# 뒤 개발지, 화성 병점구 · 봉담 상리 · 내리 · 향남 구문천리)의 단지가 대상지에 있으면 계산하지 않는다(공급자 모름).
# 이름이 한국지역난방공사 지사(KDHC_HEAT_KG_PER_TJ)면 공표값, 아니면 대체 계수. 송파는 장지동에 한난 장지지구와 나래 위례가 섞이고
# 잠실이 편람 지정 목록에 없어 동으로 못 가름 → 적지 않음(보류 그대로)
_BUNDANG = "수도권연계"   # 한난 분당 · 판교 · 동탄 지사는 수도권 연계지사(공사 온실가스 통계 페이지)
HEAT_SUPPLIER_BY_DONG = {
    "41130": {   # 성남: 분당 신도시 · 판교 · 도촌 = 한난, 위례(창곡동) = 나래에너지서비스
        **{bjd: _BUNDANG for bjd in ("4113510100", "4113510200", "4113510300", "4113510500", "4113510600", "4113510700",
                                     "4113511100", "4113511400",                       # 분당 · 수내 · 정자 · 서현 · 이매 · 야탑 · 금곡 · 구미
                                     "4113510800", "4113510900", "4113511000", "4113511500",   # 판교 · 삼평 · 백현 · 운중
                                     "4113310700")},                                   # 중원구 도촌동
        "4113110800": "나래에너지서비스"},                                             # 수정구 창곡동(위례)
    "41590": {   # 화성: 동탄 = 한난, 송산그린시티(새솔동) = 안산도시개발, 남양뉴타운 · 향남 1 · 2 · 봉담2 · 비봉 = 휴세스
        **{bjd: _BUNDANG for bjd in ("4159710100", "4159710200", "4159710300", "4159710500", "4159710600", "4159710800",
                                     "4159710900", "4159711000", "4159711100", "4159711200", "4159711500")},   # 동탄구 11개 동
        "4159110100": "안산도시개발",                                                  # 새솔동(송산그린시티)
        **{bjd: "휴세스" for bjd in ("4159125621",                                    # 남양읍 남양리(남양뉴타운)
                                     "4159125324", "4159125326", "4159125339",         # 향남읍 상신 · 하길 · 행정리(향남2지구)
                                     "4159325023",                                     # 봉담읍 수영리(봉담2지구)
                                     "4159332024", "4159332025")}},                    # 비봉면 삼화 · 구포리(화성 비봉지구)
}


def _published_factor(branch: str, year: int) -> dict | None:
    values = (KDHC_HEAT_KG_PER_TJ.get(branch) or {}).get(int(year))
    if not values:
        return None
    co2, ch4, n2o = values
    per_tj = co2 + ch4 * GWP_CH4 + n2o * GWP_N2O
    return {"branch": branch, "supplier": "한국지역난방공사", "factor_kind": "PUBLISHED", "year": int(year),
            "kg_per_kwh": round(per_tj * 3.6e-6, 4), "co2eq_kg_per_tj": round(per_tj, 1),
            "source": f"한국지역난방공사 {branch}지사 {int(year)}년 공표 열 배출계수(공공데이터포털 15090320)"}


def _substitute_factor(supplier: str, year: int) -> dict:
    return {"branch": supplier, "supplier": supplier, "factor_kind": "SUBSTITUTE", "year": int(year),
            "kg_per_kwh": LOCAL_GUIDELINE_HEAT_KG_PER_KWH, "co2eq_kg_per_tj": None,
            "source": (f"대체 계수: {supplier}의 공표 열 배출계수가 없어 지자체 온실가스 배출량 산정지침 공통값 "
                       f"{LOCAL_GUIDELINE_HEAT_TCO2EQ_PER_GCAL} tCO2eq/Gcal(2007 · 2008년 전국 평균, 공급자 값 아님)")}


def _named_factor(name: str, year: int) -> dict | None:
    return _published_factor(name, year) if name in KDHC_HEAT_KG_PER_TJ else _substitute_factor(name, year)


def district_heat_factor(region_code: str | None, year: int, district_bjd: dict | None = None) -> dict | None:
    """지역난방 열 1 kWh의 kgCO2eq.

    한국지역난방공사 지사가 공급하면 그 지사 · 그해 공표값(그해 값이 없으면 None, 가까운 해로 채우지 않음). 공표 계수가 없는
    사업자(``HEAT_SUPPLIER_OTHER``)는 지자체 산정지침 공통값을 대체로(연도와 상관없이 같은 값). 공급자를 모르면 None.
    사업자가 둘 이상인 시군구(``HEAT_SUPPLIER_BY_DONG``)는 대상지 지역난방 단지의 법정동(``district_bjd`` = {법정동 10자리:
    연면적})마다 공급자를 찾아 연면적 가중 평균. 한 단지라도 공급자를 모르면 None."""
    code = str(region_code or "")
    by_dong = HEAT_SUPPLIER_BY_DONG.get(code)
    if by_dong is not None:
        if not district_bjd:
            return None
        parts = []
        for bjd, weight in district_bjd.items():
            name = by_dong.get(str(bjd)[:10])
            factor = _named_factor(name, year) if name else None
            if not factor:
                return None
            parts.append((factor, float(weight) if weight and weight > 0 else 1.0))
        total = sum(w for _, w in parts)
        kinds = {f["factor_kind"] for f, _ in parts}
        names = sorted({f["branch"] for f, _ in parts})
        sources = list(dict.fromkeys(f["source"] for f, _ in parts))
        return {"branch": " · ".join(names), "supplier": " · ".join(sorted({f["supplier"] for f, _ in parts})),
                "factor_kind": kinds.pop() if len(kinds) == 1 else "MIXED", "year": int(year),
                "kg_per_kwh": round(sum(f["kg_per_kwh"] * w for f, w in parts) / total, 4), "co2eq_kg_per_tj": None,
                "source": ("대상지 단지의 법정동별 공급자를 연면적으로 가중: " if len(names) > 1 else "") + " / ".join(sources)}
    branch = HEAT_SUPPLIER_BRANCH.get(code)
    if branch:
        return _published_factor(branch, year)
    supplier = HEAT_SUPPLIER_OTHER.get(code)
    if supplier:
        return _substitute_factor(supplier, year)
    return None


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
