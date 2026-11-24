"""감축 수단 목록: 태양광·히트펌프 말고도 공동주택 신축·재개발에서 실제로 쓰는 수단과 그 근거 (기준 문서 5.15).

사다리(reduction_plan.building_plan)는 실측 지표가 있고 서로 겹치지 않는 수단만 차례로 더한다. 여기서는 그 밖의 수단까지
한 표로 두고, 수단마다 '대책 없음에 그 수단 하나만 적용했을 때' 줄어드는 양을 따로 계산한다(서로 더하지 않는다: 같은 에너지를
두 번 줄이게 되므로). 계산 근거가 계획안에 없는 수단(공용부 조명 전력량, 승강기 대수 등)은 지표만 적고 값을 지어내지 않는다.

근거 유형: measured 실측(계량·고지서) · agency 기관 실적 · calc 설계·계산(LCA·시뮬레이션) · claim 기업 발표 · assumed 가정.
실측·기관 실적이 아닌 값은 '참고'이며 사다리에 넣지 않는다. 값과 출처는 docs/REDUCTION_INDICATORS.md, DATA_STANDARD 5.15와 같아야 한다.
"""
from __future__ import annotations

from typing import Any

EVIDENCE_LABEL = {"measured": "실측", "agency": "기관 실적", "calc": "설계·계산", "claim": "기업 발표", "assumed": "가정"}
USE_LABEL = {"ladder": "기본 방안(사다리)", "alone": "따로 본 값", "indicator": "지표만", "embodied": "시공 단계(내재탄소)"}
BASE_LABEL = {"gas": "가스 사용량", "electricity": "전력 사용량", "total": "총에너지(전력·가스에 같은 비율로 적용)",
              "pv": "옥상 면적 → 발전량", "green": "녹지 면적", "embodied": "자재 생산 단계 배출", "readymix": "레미콘 몫의 배출"}

# 시공 단계 내재탄소 (참고 계산). 국내 공동주택 27개 단지 282동(2009~10년 설계)의 자재 생산 단계 평균, 산업연관분석법.
EMBODIED_KG_PER_M2 = 445.4
EMBODIED_RANGE_KG_PER_M2 = (340.3, 586.0)
EMBODIED_READYMIX_SHARE = 0.149   # 같은 논문의 주요 자재 평균: 레미콘 66.358 ÷ 아파트 445.412 kgCO2/m²

S_PAIR = ("K-apt 개별난방 단지 117쌍 짝 비교(이 도구, 2026-11-20 다시 계산)", "docs/REDUCTION_INDICATORS.md")
S_ZEB_RULE = ("민간 공동주택 에너지 성능 기준 강화(2025-06-30 시행), 칸(kharn) 2025", "https://www.kharn.kr/mobile/article.html?no=28053")
S_ZEB_LAW = ("에너지절약형 친환경주택의 건설기준(국토교통부고시 제2025-313호), 국가법령정보센터", "https://www.law.go.kr/행정규칙/에너지절약형친환경주택의건설기준")
S_HOUSING_ACT = ("주택법 시행령 제27조(사업계획의 승인), 국가법령정보센터", "https://www.law.go.kr/법령/주택법시행령/제27조")
S_ZEB_COST = ("제로에너지 아파트 적용 기술과 공사비, 한국경제 2025-05", "https://www.hankyung.com/article/202505204728i")
S_AGE = ("준공 시기·효율등급별 공동주택 실사용량 분석, 2016", "https://koreascience.kr/article/JAKO201610235351582.pdf")
S_GRADE = ("효율등급 취득·미취득 단지 1차에너지, 2014", "https://www.koreascience.or.kr/article/JAKO201403460493027.pdf")
S_FORUM = ("ZEB·그린리모델링 제도와 실적 정리, 칸(kharn) 2026-09", "https://www.kharn.kr/mobile/article.html?no=31811")

MEASURES: tuple[dict[str, Any], ...] = (
    # ------------------------------------------------------------------ 설계·외피
    {"key": "envelope", "group": "설계·외피", "title": "단열·창호 기준 강화", "use": "ladder", "phase": "operation",
     "base": "gas", "value": 0.137, "range": (0.098, 0.173), "evidence": "measured", "n": "국내 117쌍", "apply": "신축·재개발",
     "what": "외벽·지붕 단열, 로이 복층·삼중 창호, 기밀 문을 지금 기준(2017년 이후 준공 수준)으로 짓는다.",
     "cost": "주택건설사업계획 승인 대상 공동주택(30세대 이상, 일부 단지형 연립·다세대는 50세대)은 2025-06-30 이후 승인 신청분부터 단위면적당 1차에너지소요량 100 kWh/m²·년 미만 또는 사양 기준(창·벽체 단열, 창·현관문 기밀 1등급 등) 중 하나를 지켜야 한다(국토교통부고시 제2025-313호 제7조, 주택법 시행령 제27조). 84 m² 세대당 추가 공사비 약 130만 원(국토부 추산)·293만 원 이상(업계 추산), 에너지비 연 약 22만 원 절감(회수 5~6년, 정부 추정).",
     "note": "같은 시군구·세대수 구간에서 준공 시기만 다른 단지의 차이라 보일러·환기 변화도 섞여 있다. 관리비 부과 면적당 값이다(연면적당 −33.9%는 새 단지의 난방하지 않는 면적 때문에 과대). 짝의 86%가 전북이고, 같은 비교에서 전기는 방향이 분명하지 않았다.",
     "sources": (S_PAIR, S_ZEB_LAW, S_HOUSING_ACT, S_ZEB_RULE, S_ZEB_COST)},
    {"key": "new_build_package", "indicator": "총 최종에너지 −11.4% (−12.1~−5.9%, 준공 시기 비교)", "group": "설계·외피", "title": "신축 통합 기준(ZEB 5등급 수준·효율등급 인증)", "use": "indicator", "phase": "operation",
     "base": None, "value": 0.114, "range": (0.059, 0.121), "evidence": "measured", "n": "국내 2곳(원문과 맞는 행)", "apply": "신축·재개발",
     "what": "단열·창호·기밀·고효율 설비·조명밀도·열회수 환기를 인증 기준에 맞춰 한꺼번에 적용한다.",
     "cost": "ZEB 인증 건물은 용적률·높이 완화(최대 15%)와 취득세 감면(15~20%) 대상.",
     "note": "원문과 맞는 근거는 준공(사업승인) 시기 비교 2곳(수도권 264단지 −12.1 · −11.4%, 서울 109단지 −5.9%)뿐이고 열 + 전기 총에너지 값이다. 전기가 줄었다는 원문은 없고, 이 도구의 실측(짝 비교 세대 전기, 효율등급 인증 단지 전기 +0.6%)도 전기 차이를 확인하지 못해 전력에 곱하지 않는다. 단열·창호 단계(같은 시기 비교)와 겹친다(2026-11-20).",
     "sources": (S_AGE, S_GRADE, ("효율등급 1+·1등급 대 비인증 단지, Energy and Buildings 2021", "https://www.sciencedirect.com/science/article/abs/pii/S0378778821004527"), S_FORUM)},
    {"key": "passive_package", "indicator": "총에너지 −50% (−94~−37.6%, 국외 일반 신축 대비)", "group": "설계·외피", "title": "패시브 수준 외피(고단열·고기밀·열교 차단·열회수 환기)", "use": "indicator", "phase": "operation",
     "base": None, "value": 0.50, "range": (0.376, 0.94), "evidence": "measured", "n": "16건(국외)", "apply": "신축",
     "what": "난방 요구량 15 kWh/m²·년 수준으로 외피와 환기를 설계한다. 일반 신축 대비 총에너지 −50%(16건), 난방 열만 보면 −80%(13건, −95~−68%).",
     "cost": "추가 공사비 0~8%(국외 사업 보고: CEPHEUS 약 8%, 미국 0~5%).",
     "note": "난방 비중이 큰 나라의 공동주택 실측이라 국내 계획안의 전력·가스에 그대로 곱하지 않는다. 국내 단지의 계량 사례는 찾지 못했다(확인 필요). 설계로 예측한 절감 가운데 실제로 나타난 몫은 0.24~0.95였다.",
     "sources": (("EU CEPHEUS 패시브하우스 14개 사업 실측", "https://www.proklima-hannover.de/infothek/studien-projekte/cepheus/cepheus_38_final_publical_report.pdf"),
                 ("패시브동과 인접 일반동 실측, Buildings 2024", "https://www.mdpi.com/2075-5309/14/6/1866"),
                 ("영국 저에너지 주택 성능 격차 메타연구, eceee 2019", "https://www.eceee.org/library/conference_proceedings/eceee_Summer_Studies/2019/8-buildings-technologies-and-systems-beyond-energy-efficiency/meta-study-of-the-energy-performance-gap-in-uk-low-energy-housing/"))},
    {"key": "window_retrofit", "indicator": "총에너지 −16% · 난방 가스 −24.3% (교체 전 대비)", "group": "설계·외피", "title": "고성능 창호 교체(기존 건물)", "use": "indicator", "phase": "operation",
     "base": None, "value": None, "range": None, "evidence": "measured", "n": "국내 2건", "apply": "리모델링",
     "what": "기존 단창·복층창을 로이 복층·삼중창으로 바꾼다. 총에너지 −16%(고양시), 난방 가스 −24.3%(단창에 복층 내창 추가).",
     "cost": "회수기간 7.0년(할인, 중앙값)·약 11년. 감축비용 중앙값 약 352 USD/tCO2e(고양시 사례).",
     "note": "기존 건물을 남기는 리모델링에 쓰는 지표다. 새로 짓는 계획안은 단열·창호 단계에 이미 들어 있다. 난방 가스 실측 절감(−24.3%)은 예측(−50.7%)의 절반이었다.",
     "sources": (("창호 교체 공동주택 실측과 감축비용, Buildings 2026", "https://www.mdpi.com/2075-5309/16/1/71"),
                 ("단창에 복층 내창을 더한 단지의 가스 실측, 2018", "https://koreascience.kr/article/JAKO201819352298542.pdf"))},
    {"key": "shading", "indicator": "냉방 부하 −34.5% (−41.6~−8.9%)", "group": "설계·외피", "title": "외부 차양·일사 조절", "use": "indicator", "phase": "operation",
     "base": None, "value": 0.345, "range": (0.089, 0.416), "evidence": "calc", "n": "국내 4건", "apply": "신축·리모델링",
     "what": "외부 블라인드·수평 차양으로 여름 일사를 막는다. 냉방 부하 −34.5%(계산 중앙값).",
     "cost": "확인 필요.",
     "note": "계산값뿐이라 지표로 쓰지 않는다. 고정 차양은 난방을 2.5~11.0% 늘린다(같은 계산). 냉방 전력이 전체 전력에서 차지하는 몫이 계획안에 없다.",
     "sources": (("외부·내부 블라인드 냉방 부하 계산, 2012", "https://koreascience.or.kr/article/JAKO201223451901408.page"),
                 ("외부 수평 차양 길이별 냉난방 계산, 2017", "https://koreascience.kr/article/JAKO201719363528372.pdf"))},
    # ------------------------------------------------------------------ 설비
    {"key": "heat_recovery_ventilation", "indicator": "총에너지 −3.5% (−6~−1%, ECO2 계산)", "group": "설비", "title": "열회수 환기장치(전열교환기) 운전", "use": "indicator", "phase": "operation",
     "base": None, "value": 0.035, "range": (0.01, 0.06), "evidence": "calc", "n": "국내 1건(ECO2 계산)", "apply": "신축·재개발",
     "what": "환기로 버리는 열을 되찾는다. 자연환기 대비 −1~−6%(실제 단지 사양을 넣은 ECO2 계산, 등급용 1차에너지 소요량. 실측 아님).",
     "cost": "사양 기준을 고른 공동주택은 환기장치의 난방 열교환효율 75% 이상(국토교통부고시 제2025-313호 제7조제1항제2호 차목). 1차에너지소요량 기준을 고르면 따로 정하지 않는다.",
     "note": "세대가 끄면 효과가 없다. 실제 운전에서 잰 전열교환효율은 35~83%였다(국내 실험주택). 단열·창호 단계와 겹칠 수 있다.",
     "sources": (("전열교환 · 바닥 · 자연환기 공동주택의 ECO2 1차에너지 소요량 비교, 2015", "https://koreascience.or.kr/article/JAKO201506050646242.pdf"),
                 ("공동주택 환기시스템 실제 운전 전열교환성능, 2017", "https://koreascience.kr/article/JAKO201718851432631.pdf"), S_ZEB_LAW)},
    {"key": "home_energy_display", "indicator": "전력 −11.7% (−15.9~−7.5%, 설치 전후 · 대조군 없음)", "group": "설비", "title": "세대 에너지 표시장치·스마트미터(IHD·HEMS)", "use": "indicator", "phase": "operation",
     "base": None, "value": 0.117, "range": (0.075, 0.159), "evidence": "measured", "n": "국내 2개 지역(1건)", "apply": "신축·재개발·기존",
     "what": "세대가 실시간 사용량과 요금을 보게 한다. 설치 전후 가구 전력 −15.9%(청주)·−7.5%(서울).",
     "cost": "확인 필요. 국외 스마트미터 초기 보급은 전기 −2.3%·가스 −1.5%로 더 작았다.",
     "note": "설치는 설비 사양이고 효과는 세대가 보고 줄이는 행동을 거쳐 나서, 에너지 절약 운영처럼 계획안에 값을 내지 않는다(2026-11-20, 근거표 판단 '따로 추천 안 함'). 근거는 2010년 64가구 · 겨울 2개월 설치 전후 비교 1건이고 대조군 · 기온 보정이 없다. 에너지 절약 운영과 같은 종류(계량·행동)라 함께 더하지 않는다.",
     "sources": (("스마트미터와 세대 표시장치 설치 전후 전력, 2010", "https://koreascience.kr/article/JAKO201015233334329.pdf"),
                 ("영국 스마트미터 초기 보급 평가, 2015", "https://assets.publishing.service.gov.uk/government/uploads/system/uploads/attachment_data/file/407568/8_Synthesis_FINAL_25feb15.pdf"))},
    # 2026-11-22 근거 점검: 앞의 "−40% (−82.5~−10%), 국내 5건"은 근거표 '조명·승강기' 묶음의 중앙값이라 조명이 아닌 행
    # (02-025 공용에너지 전체 −10%, 02-034 승강기 회생제동 −20%, 02-026 세대당 공용전기 −82%)이 섞였음 → 조명만 잰 두 행으로
    # (02-028 LED 형광등 대비 최대 −40%, 02-075 LED+디밍 조명 에너지 약 −83%/−82%의 대표값 −82.5%)
    {"key": "common_lighting", "indicator": "그 조명 전기 −40% (LED) ~ −82.5% (LED+디밍)", "group": "설비", "title": "공용부 조명 LED·동작감지 디밍(지하주차장·계단)", "use": "indicator", "phase": "operation",
     "base": None, "value": 0.40, "range": (0.40, 0.825), "evidence": "agency", "n": "국내 2건(조명만)", "apply": "신축·재개발·기존",
     "what": "24시간 켜 두는 지하주차장·계단 조명을 LED와 동작감지 디밍으로 바꾼다. 그 조명 전기의 −40%(LED, 형광등 대비 최대), LED+디밍 약 −82.5%.",
     "cost": "회수 1.1~1.2년(2,198세대 단지 2.2억 원·월 1,700만 원 절감, 다른 단지 1.4억 원·14개월).",
     "note": "단지 전체 전력이 아니라 그 조명 전기의 퍼센트다. 공용 조명 전력량이 계획안에 없어 값은 계산하지 않는다. 2025-06-30 기준은 조명밀도 8 → 6 W/m².",
     "sources": (("서울시 LED 조명 보급(형광등 대비 최대 40%)", "https://news.seoul.go.kr/env/?p=34631"),
                 ("서울신문 지하주차장 LED+디밍(조명 에너지 약 −83%), 2019", "https://m.go.seoul.co.kr/news/2019/05/15/20190515022001"),
                 ("서울시 아파트 공용전기 컨설팅(65개 단지, 회수 기간), 2014", "https://news.seoul.go.kr/env/archives/37314"),
                 ("서울시 지하주차장 LED 사례(투자 · 회수 14개월)", "https://news.seoul.go.kr/env/archives/31229"))},
    {"key": "elevator_regeneration", "indicator": "대당 연 0.39~0.57 tCO2 · 승강기 전력 −10~−30%", "group": "설비", "title": "승강기 회생제동장치", "use": "indicator", "phase": "operation",
     "base": None, "value": None, "range": None, "evidence": "agency", "n": "서울 117대", "apply": "신축·재개발·기존",
     "what": "승강기가 내려올 때 버리는 전기를 되돌려 쓴다. 대당 연 0.39 t(서울시 전망 계수)~0.57 t(배출권 승인 168 t ÷ 117대 ÷ 2.5년, 계산), 승강기 전력의 10~30%.",
     "cost": "설치비 대당 약 110만 원, 공용 전기료 대당 월 3~4만 원 절감(15층 이상) → 회수 2.3~3.1년(계산).",
     "note": "대당 값이라 승강기 대수가 있어야 계산한다(계획안 입력에 없음). 신축 승강기의 기본 사양인지는 확인 필요.",
     "sources": (("서울시 승강기 회생제동장치 배출권 승인", "https://news.seoul.go.kr/citybuild/archives/517382"),
                 ("서울시 승강기 회생제동장치 전기료 점검", "https://news.seoul.go.kr/citybuild/?p=505612"))},
    {"key": "condensing_boiler", "indicator": "가스 −20% (−28.4~−20%, 교체 전·유사 단지 대비)", "group": "설비", "title": "콘덴싱·캐스케이드 보일러", "use": "indicator", "phase": "operation",
     "base": None, "value": 0.20, "range": (0.20, 0.284), "evidence": "agency", "n": "국내 2건", "apply": "기존(교체)",
     "what": "열효율 92% 이상 보일러로 바꾼다. 가스 −20%(캐스케이드, 유사 단지 비교)·최대 −28.4%(일반 보일러 교체, 환경부·서울시).",
     "cost": "가구당 연 약 13만 원 절감(서울시).",
     "note": "2020-04-03부터 대기관리권역에서는 콘덴싱(1종) 보일러만 판매·설치할 수 있어 신축은 기준에 들어 있다. 단열·창호 단계의 실측 차이에도 섞여 있다.",
     "sources": (("서울시 친환경 보일러 보급", "https://news.seoul.go.kr/env/archives/503465"),
                 ("가정용 친환경보일러 설치 의무화 안내(2020-04-03 시행)", "https://gangdong.go.kr/web/newportal/contents/gdp_005_004_011_001"),
                 ("LH 캐스케이드 보일러·통합배관", "https://www.nocutnews.co.kr/news/6426598"))},
    {"key": "district_heating_control", "indicator": "지역난방 난방 열 −15.7% (−15.7~−6.9%)", "group": "설비", "title": "지역난방 단지 난방 제어(외기온 예측제어·스마트 통합배관)", "use": "indicator", "phase": "operation",
     "base": None, "value": 0.157, "range": (0.069, 0.157), "evidence": "measured", "n": "국내 2건", "apply": "신축·기존(지역난방)",
     "what": "단지 기계실의 2차측 공급수 온도를 외기 예보로 조절한다. 난방 −15.7%(고정 설정 대비, 540세대 실증)·−7.1%(외기 보상 제어 대비). 통합배관 시범 3개 단지는 난방·급탕 −6.9%(인근 단지 비교, 칸 2025-11). 같은 통합배관을 다른 보도는 약 −9%로 적음(근거표 13-008, 노컷뉴스).",
     "cost": "통합배관은 공사비도 7.7% 줄어드는 것으로 분석(추정).",
     "note": "지역난방 열의 퍼센트다. 이 도구의 계획안은 전력·가스로 계산하므로 값을 내지 않는다(지역난방 열 자료 없음).",
     "sources": (("지역난방 2차측 공급수 온도 제어 실증, 2015", "https://koreascience.kr/article/JAKO201509364589215.pdf"),
                 ("LH 스마트 통합배관 실증, 칸(kharn) 2025-11 — 근거표에 아직 행 없음(원문 확인 뒤 추가)", "https://www.kharn.kr/mobile/article.html?no=29260"),
                 ("캐스케이드 · 통합배관 보도(통합배관 약 −9%), 노컷뉴스", "https://www.nocutnews.co.kr/news/6426598"))},
    # ------------------------------------------------------------------ 운영
    {"key": "operation", "indicator": "전력 −4.8% (−5.08~−4.5%, 입주 뒤 행동)", "group": "운영", "title": "에너지 절약 운영(계량·제어·행동)", "use": "indicator", "phase": "operation",
     "base": None, "value": 0.048, "range": (0.045, 0.0508), "evidence": "measured", "n": "2건(원문과 맞는 행, 국내 1)", "apply": "신축·재개발·기존",
     "what": "사용량 피드백, 이웃 비교 고지서, 에너지캐시백·절전소 같은 주민 참여, 공용부 운전 시간 조정.",
     "cost": "설비 투자 없이 가능. 에너지캐시백 성공 단지 평균 −4.9%, 주민 참여 절전소 −5.1%(기관 실적).",
     "note": "입주 뒤 행동이라 계획 단계의 감축 방안(사다리 · 지역 자동 방안)에는 넣지 않는다(2026-11-20). 참여율에 따라 달라진다. 캐시백에 성공한 가구는 43.3%였다.",
     "sources": (("피드백 현장실험, Fraunhofer ISI 2012", "https://www.isi.fraunhofer.de/content/dam/isi/dokumente/sustainability-innovation/2012/WP08-2012_Feedback-effects_Energy-Policy.pdf"),
                 ("이웃 비교 고지서, MIT CEEPR", "https://ceepr.mit.edu/workingpaper/social-norms-and-energy-conservation"),
                 ("서울시 에너지자립마을 절전소", "https://news.seoul.go.kr/env/archives/38528"),
                 ("에너지캐시백 참여 실적, 아시아경제 2023-07", "https://www.asiae.co.kr/en/article/2023072310332184784"))},
    # ------------------------------------------------------------------ 재생·상쇄
    {"key": "rooftop_pv", "indicator": "옥상의 60% · 10 m²/kW × 지역 발전량", "group": "재생·상쇄", "title": "지붕 태양광", "use": "ladder", "phase": "operation",
     "base": "pv", "value": None, "range": None, "evidence": "assumed", "n": None, "apply": "신축·재개발·기존",
     "what": "옥상의 60%에 10 m²/kW로 놓고 지역 일사량으로 발전량을 낸다. 자체 소비를 넘는 발전은 감축에 넣지 않는다.",
     "cost": "확인 필요(단가 근거 없음).",
     "note": "고층 아파트는 옥상이 좁아 옥상 태양광만으로는 에너지자립률 약 7% 수준이라는 보고가 있다.",
     "sources": (S_FORUM,)},
    {"key": "greenery", "indicator": "녹지 1 m²에 연 1.0 kgCO2 (8.8~15.9 t/ha)", "group": "재생·상쇄", "title": "녹지·조경 흡수(상쇄)", "use": "ladder", "phase": "offset",
     "base": "green", "value": None, "range": None, "evidence": "assumed", "n": None, "apply": "신축·재개발",
     "what": "녹지 1 m²에 연 1.0 kgCO2(1 ha에 10 t)를 흡수한다고 본다. 줄이는 것이 아니라 메우는 것이라 따로 적는다.",
     "cost": "확인 필요.",
     "note": "숲 기준 계수(20년생 8.8~15.9 t/ha)의 낮은 쪽이고, 국내 조경 식재지 실측(식재 면적당 연 0.38~2.37 kgCO2/m², 탄소 1.04~6.47 t/ha 환산) 범위 안이다. 분모가 부지 전체인 값(공공용지 0.24, 공동주택 단지 약 0.40 kgCO2/m²)과는 견주지 않는다. 새로 심은 조경수는 수령 10년까지 그루당 흡수가 작아 계획 초기에는 더 작을 수 있다(2026-11-20 본문 확인).",
     "sources": (("국립산림과학원 표준 탄소흡수량", "docs/REDUCTION_INDICATORS.md"), ("도시공원 식재유형별 탄소 저장 · 흡수, 식재 면적당", "https://koreascience.kr/article/JAKO201416743150056.pdf"), ("조경수 수령별 탄소흡수(직접 수확 기반)", "https://koreascience.kr/article/JAKO201732863553302.pdf"))},
)

# 시공 단계(내재탄소) 수단: 모두 설계·계산 또는 발표 값이라 참고로만 쓴다. base 'embodied' = 자재 생산 단계 전체, 'readymix' = 레미콘 몫.
EMBODIED_MEASURES: tuple[dict[str, Any], ...] = (
    {"key": "low_carbon_concrete", "title": "저탄소 콘크리트(고로슬래그·플라이애시 치환)", "base": "readymix", "value": 0.1205, "range": (0.078, 0.163),
     "evidence": "calc", "n": "국내 2건", "apply": "신축·재개발",
     "what": "시멘트 일부를 고로슬래그·플라이애시로 바꾼다. 콘크리트 배출 −7.8%(단지 전 물량 계산)~−16.3%(말뚝, m³ 기준). 기업 발표는 −40~−60%.",
     "cost": "확인 필요.",
     "note": "레미콘 몫(자재 생산 단계의 14.9%)에만 적용한 값이다. 발표값(−40~−60%)은 검증된 계산이 아니라 넣지 않았다. 초기 강도·동절기 양생 조건 확인이 필요하다.",
     "sources": (("용인 공동주택 에코멘트 배합 물량 기반 산정, 2011", "https://koreascience.kr/article/JAKO201123153958559.pdf"),
                 ("고로슬래그 PHC 말뚝 LCA, 콘크리트학회지 2016", "https://koreascience.kr/article/JAKO201620136946695.pdf"),
                 ("탄소저감 콘크리트 환경성적표지 인증(최대 54%), 한국경제 2025-10", "https://www.hankyung.com/article/202510275081i"))},
    {"key": "modular", "title": "모듈러(공장 제작) 공법", "base": "embodied", "value": 0.351, "range": (0.351, 0.37),
     "evidence": "calc", "n": "국내 2건", "apply": "신축(중·저층)",
     "what": "유닛을 공장에서 만들어 현장에서 쌓는다. 생산 단계 −35.1~−37%, 전과정 60년 −18.5~−20.7%(RC 설계안 대비 LCA).",
     "cost": "공사비는 RC보다 28% 높다는 기관 자료가 있다. 공기는 약 30% 줄어든다는 보도.",
     "note": "국내 준공 사례는 13층 이하 임대·기숙사 위주다. 13층을 넘는 계획안에는 값을 계산하지 않는다.",
     "sources": (("모듈러 공동주택과 RC 공동주택 전과정 비교, 대한건축학회논문집 2023", "https://koreascience.or.kr/article/JAKO202318839456382.page"),
                 ("철골 모듈러 공공임대 100세대 LCA, 건설관리 2023", "https://koreascience.or.kr/article/JAKO202315958721150.pdf"),
                 ("LH 모듈러 주택 현황과 공사비, 2023", "https://koreascience.kr/article/JAKO202315958719205.pdf"),
                 ("용인 영덕 경기행복주택(13층 모듈러)", "https://www.hyundaimotorgroup.com/ko/story/CONT0000000000094114"))},
    {"key": "frame_system", "indicator": "지상 골조 자재 배출 −24.4% (−30.6~−24.4%)", "title": "구조 방식 전환(벽식 → 기둥·보 라멘)", "base": None, "value": 0.244, "range": (0.244, 0.306),
     "evidence": "calc", "n": "국내 1건", "apply": "신축·재개발",
     "what": "벽식 실시설계를 라멘으로 바꾸면 지상 골조 자재의 CO2가 −24.4%(무량판 대비 −30.6%). 콘크리트 0.614 → 0.460 m³/m².",
     "cost": "초기 공사비 +18%, 50년 생애주기비용 −7%(리모델링이 쉬워져서, 다른 연구).",
     "note": "지상 골조 자재만 본 값이라 전체 내재탄소에 곱할 수 없다. 라멘은 기밀이 나빠 난방 요구량이 11.5% 많다는 계산도 있다.",
     "sources": (("벽식·무량판·라멘 3개 동 골조 CO2 비교, 한국건축시공학회 2010", "https://koreascience.kr/article/JAKO201026039609506.pdf"),
                 ("라멘과 벽식 생애주기비용, 2014", "https://koreascience.kr/article/JAKO201436351075349.pdf"))},
    {"key": "keep_structure", "indicator": "전생애 배출 −4.1~−10% (재건축 대비)", "title": "골조를 남기는 리모델링(전면 재건축 대신)", "base": None, "value": 0.07, "range": (0.041, 0.10),
     "evidence": "calc", "n": "국내 1건", "apply": "재개발 대안 비교",
     "what": "노후 공동주택을 허물지 않고 골조를 남겨 고친다. 전생애 CO2가 재건축보다 4.1~10% 적다(85 m² 세대 기준 LCA).",
     "cost": "확인 필요.",
     "note": "운영 단계까지 넣은 전생애 값이다. 세대수를 늘리는 재개발과는 사업 목적이 달라 그대로 견줄 수 없다.",
     "sources": (("노후 공동주택 재건축과 리모델링 CO2 비교, 한국건설관리학회 2014", "https://koreascience.or.kr/article/JAKO201406366998639.page?lang=en"),)},
)

S_EMBODIED = ("공동주택 27개 단지 282동 자재 생산 단계 CO2, KIEAE 2013", "https://koreascience.kr/article/JAKO201301369228070.pdf")


def _signed(pct: float) -> str:
    """줄어드는 퍼센트를 '−12.3', 늘어나는 것(음수)을 '+6.7'로."""
    return ("+" if pct < 0 else "−") + f"{abs(pct):g}"


def indicator_text(m: dict[str, Any]) -> str:
    """지표 한 칸: 무엇의 몇 퍼센트(범위). 계획안의 양에 곱하지 않는 지표는 목록에 적어 둔 문장을 쓴다."""
    if m.get("indicator"):
        return m["indicator"]
    value, rng = m["value"], m["range"]
    text = f"{BASE_LABEL[m['base']]} {_signed(value * 100)}%"
    if rng and rng[0] != rng[1]:
        text += f" ({_signed(max(rng) * 100)}~{_signed(min(rng) * 100)}%)"
    return text


def _public(m: dict[str, Any]) -> dict[str, Any]:
    """화면·문서용 한 줄: 지표를 퍼센트로, 출처를 [{label, url}]로."""
    value, rng = m.get("value"), m.get("range")
    return {"indicator_text": indicator_text(m),"key": m["key"], "group": m.get("group", "시공·자재"), "title": m["title"], "use": m.get("use", "embodied"), "use_label": USE_LABEL[m.get("use", "embodied")],
            "phase": m.get("phase", "embodied"), "base": m.get("base"), "base_label": BASE_LABEL.get(m.get("base") or ""),
            "value_pct": round(value * 100, 2) if value is not None else None,
            "range_pct": [round(rng[0] * 100, 2), round(rng[1] * 100, 2)] if rng else None,
            "evidence": m["evidence"], "evidence_label": EVIDENCE_LABEL[m["evidence"]], "n": m.get("n"), "apply": m.get("apply"),
            "what": m["what"], "cost": m.get("cost"), "note": m.get("note"),
            "sources": [{"label": label, "url": url} for label, url in m.get("sources", ())]}


def catalog() -> dict[str, Any]:
    """수단 목록 전체(운영 단계 + 시공 단계)와 내재탄소 기준값, 감축 근거표 요약(수단별 행 · 출처 · 등급, 도구 수단에 없는 묶음)."""
    from .measure_catalog import LEVEL_LABEL, group_status
    from .reference_tables import evidence_summary
    ev = evidence_summary()

    def with_evidence(m: dict[str, Any]) -> dict[str, Any]:
        return {**_public(m), "evidence_table": ev["by_measure"].get(m["key"])}
    return {"measures": [with_evidence(m) for m in MEASURES], "embodied_measures": [with_evidence(m) for m in EMBODIED_MEASURES],
            "evidence_table": {"rows": ev["rows"], "unlinked_groups": ev["unlinked_groups"], "note": ev["note"]},
            "embodied_basis": {"kg_per_m2": EMBODIED_KG_PER_M2, "range_kg_per_m2": list(EMBODIED_RANGE_KG_PER_M2), "readymix_share_pct": round(EMBODIED_READYMIX_SHARE * 100, 1),
                               "source": {"label": S_EMBODIED[0], "url": S_EMBODIED[1]}},
            "evidence_labels": EVIDENCE_LABEL, "use_labels": USE_LABEL,
            # 2026-11-25(계획 v3 A): 근거표 묶음 32개의 지금 수준 · 목표 수준 · 근거 상태(measure_catalog)
            "groups": list(group_status()), "level_labels": LEVEL_LABEL}


def measure_table(electricity_kwh: float, gas_kwh: float | None, fe: float, fg: float | None,
                  pv: dict[str, Any] | None = None, green: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """수단마다 '대책 없음'에 그 수단 하나만 적용했을 때의 연 감축량(kg). 서로 더하지 않는다.

    값이 None인 줄은 계산 근거가 계획안에 없다는 뜻이며(``reason``), 0으로 채우지 않는다. 범위에서 음수는 늘어남을 뜻한다.
    """
    e_carbon = electricity_kwh * fe
    g_carbon = gas_kwh * fg if gas_kwh is not None and fg else None
    total = e_carbon + (g_carbon or 0.0)
    rows: list[dict[str, Any]] = []
    for m in MEASURES:
        row = _public(m)
        base, value, rng = m["base"], m.get("value"), m.get("range")
        kg: float | None = None
        range_kg: list[float] | None = None
        reason: str | None = None
        if base == "gas":
            if g_carbon is None:
                reason = "가스 사용량 또는 가스 배출계수가 없습니다."
            else:
                kg, range_kg = g_carbon * value, [g_carbon * rng[0], g_carbon * rng[1]]
        elif base == "electricity":
            kg, range_kg = e_carbon * value, [e_carbon * rng[0], e_carbon * rng[1]]
        elif base == "total":
            kg, range_kg = total * value, [total * rng[0], total * rng[1]]
        elif base == "pv":
            if pv and pv.get("kwh"):
                kg = min(pv["kwh"], electricity_kwh) * fe
            else:
                reason = "옥상 면적 또는 발전량 근거가 없습니다."
        elif base == "green":
            if green and green.get("uptake_kg"):
                kg, range_kg = green["uptake_kg"], list(green.get("range_kg") or []) or None
            else:
                reason = "녹지 면적이 없습니다."
        else:
            reason = "계획안에 계산 근거가 없어 지표만 적습니다."
        row.update({"alone_kg": round(kg, 1) if kg is not None else None,
                    "alone_pct": round(kg / total * 100, 1) if kg is not None and total > 0 else None,
                    "alone_range_kg": [round(v, 1) for v in range_kg] if range_kg else None, "reason": reason})
        rows.append(row)
    return rows


MODULAR_MAX_FLOORS = 13   # 국내 모듈러 공동주택 준공 사례의 최고 층수(용인 영덕 경기행복주택 13층). 이보다 높은 계획안에는 값을 내지 않는다


def embodied(floor_area_m2: float | None, annual_operation_kg: float | None = None, floors: float | None = None) -> dict[str, Any] | None:
    """시공 단계 내재탄소 (참고 계산): 지상 연면적 × 국내 공동주택 자재 생산 단계 평균. 연면적이 없으면 None."""
    if not floor_area_m2 or floor_area_m2 <= 0:
        return None
    kg = floor_area_m2 * EMBODIED_KG_PER_M2
    range_kg = [floor_area_m2 * v for v in EMBODIED_RANGE_KG_PER_M2]
    options = []
    for m in EMBODIED_MEASURES:
        row = _public(m)
        base = {"embodied": kg, "readymix": kg * EMBODIED_READYMIX_SHARE}.get(m["base"] or "")
        if m["key"] == "modular" and floors and floors > MODULAR_MAX_FLOORS:
            row.update({"reduction_kg": None, "reduction_range_kg": None, "reduction_pct": None,
                        "reason": f"국내 준공 사례가 {MODULAR_MAX_FLOORS}층까지라 {floors:g}층 계획안에는 값을 계산하지 않습니다."})
        elif base is None:
            row.update({"reduction_kg": None, "reduction_range_kg": None, "reduction_pct": None, "reason": "전체 내재탄소에 곱할 수 없는 지표라 값은 계산하지 않습니다."})
        else:
            r = base * m["value"]
            row.update({"reduction_kg": round(r, 1), "reduction_range_kg": [round(base * v, 1) for v in m["range"]],
                        "reduction_pct": round(r / kg * 100, 1), "reason": None})
        options.append(row)
    return {"floor_area_m2": round(floor_area_m2, 1), "kg_per_m2": EMBODIED_KG_PER_M2, "range_kg_per_m2": list(EMBODIED_RANGE_KG_PER_M2),
            "carbon_kg": round(kg, 1), "range_kg": [round(v, 1) for v in range_kg],
            "years_of_operation": round(kg / annual_operation_kg, 1) if annual_operation_kg and annual_operation_kg > 0 else None,
            "readymix_share_pct": round(EMBODIED_READYMIX_SHARE * 100, 1), "options": options,
            "source": {"label": S_EMBODIED[0], "url": S_EMBODIED[1]},
            "basis": "지상 연면적 × 국내 공동주택 자재 생산 단계 평균(27개 단지 282동, 2009~10년 설계, 산업연관분석). 시공·운송·해체, 지하주차장·부대시설은 들어 있지 않습니다."}


def embodied_text(e: dict[str, Any] | None) -> str | None:
    """보고서 5절 내재탄소 첫 줄 (엔진 값 그대로)."""
    if not e:
        return None
    text = (f"지상 연면적 {e['floor_area_m2']:,.0f} m² × {e['kg_per_m2']:,.1f} kgCO2/m² = 약 {e['carbon_kg'] / 1000:,.0f} t"
            f" (범위 {e['range_kg'][0] / 1000:,.0f}~{e['range_kg'][1] / 1000:,.0f} t)")
    if e.get("years_of_operation"):
        text += f", 대책 없는 연간 운영탄소의 {e['years_of_operation']:.1f}년치"
    return text + "입니다. 한 번 배출되며 운영 단계 감축으로 줄지 않습니다(자재 생산 단계, 참고 계산)."


GROUP_KIND = {"예": "계획 단계 밖", "따로 추천 안 함": "설비 사양(상위 수단의 구성 요소)"}
NO_VALUE_REASON = {
    "envelope": "가스 지표(단열·창호)라 이 계산(전력 운영탄소)에는 값이 없습니다. 가스까지 본 값은 3D 계획안 검토 보고서에 있습니다",
    "greenery": "구역 계획 입력에 녹지 면적이 없어 값이 없습니다",
}


def _no_value_reason(key: str, status: str | None) -> str:
    if key == "rooftop_pv":
        return {"NO_YIELD": "발전량 근거가 없어 태양광 값이 없습니다(상쇄할 전력량만 적음)",
                "NO_ROOF": "계획에 새 건물(지붕)이 없어 값이 없습니다",
                "UPPER_BOUND_ONLY": "지붕을 연면적(위 한계)으로만 알아 값을 확정하지 않습니다"}.get(status or "", "이 기준에서는 줄일 양이 없습니다")
    return NO_VALUE_REASON.get(key, "지표만 있는 수단입니다. 근거표 행의 값을 계획안에 곱하지 않습니다")


def _groups_of(key: str) -> list[str]:
    """도구 수단 하나에 근거로 연결된 근거표 묶음(수단_ID)."""
    from .measure_catalog import group_status
    return [g["group"] for g in group_status() if key in g["tool_measures"]]


def greenery_offset(green_area_m2: float | None) -> dict[str, Any] | None:
    """계획 녹지 면적의 연 흡수(상쇄) — 3D 계획안 검토와 같은 상수 · 범위(``reduction_plan``). 면적이 없거나 0이면 None.

    줄이는 것이 아니라 메우는 값이라 목표 · 추천 방안 · 다른 수단의 합계에 넣지 않는다(기록 2026-11-25-greenery-area-input.md)."""
    if not green_area_m2 or not green_area_m2 > 0:   # None · 0 · NaN
        return None
    from .reduction_plan import GREEN_UPTAKE_KG_PER_M2, GREEN_UPTAKE_RANGE_T_PER_HA
    kg = round(green_area_m2 * GREEN_UPTAKE_KG_PER_M2, 1)
    if kg <= 0:   # 반올림해 0이 되는 아주 작은 면적은 값이 아님(0을 지어내지 않음)
        return None
    return {"area_m2": round(green_area_m2, 1), "kgco2": kg,
            "range_kgco2": [round(green_area_m2 * t / 10, 1) for t in GREEN_UPTAKE_RANGE_T_PER_HA],
            "text": (f"녹지 {green_area_m2:,.0f} m² × 연 {GREEN_UPTAKE_KG_PER_M2:.1f} kgCO2/m² = {kg / 1000:,.1f} tCO2 흡수 — "
                     "상쇄(줄이는 것이 아니라 메움). 목표 · 추천 방안 · 다른 수단 합계에 넣지 않음")}


# 2026-11-25(계획 v3 E): 지붕 태양광의 인증 · 실제 사례 수준(세대당 kW). 기록 2026-11-25-pv-three-levels.md
PV_KW_PER_HOUSEHOLD_CERTIFIED = (0.20, 0.61)   # 공식 자료: ZEB 인증사례집 2024(옥상 · 5등급 · 190세대 이상 0.20~0.59, 계산), LH 인천검단 0.383, LH 5등급 수준 약 0.61(계산)
PV_KW_PER_HOUSEHOLD_CASES = (0.13, 0.64)       # 기사: 올림픽파크포레온 1,536 kW ÷ 12,032세대 = 0.128, 힐스테이트 검단 웰카운티 옥상 981 kW ÷ 1,535 = 0.639
PV_LEVEL_BASIS = {
    "certified": ("공식 자료", "신축 ZEB 인증 공동주택의 세대당 태양광 0.20~0.61 kW(한국부동산원 ZEB 인증사례집 2024 주거 사례 계산, LH 인천검단 AA10-2 0.383 kW)"),
    "cases": ("기사", "실제 신축 단지 보도의 세대당 태양광 0.13~0.64 kW(올림픽파크포레온 0.128 — 옥상만인지 확인 필요, 힐스테이트 검단 웰카운티 옥상 0.639, 공식 자료로 교차 확인 안 됨)"),
}
PV_REGION_RULE = {
    "11": "서울: 녹색건축물 설계기준(서울특별시고시 제2023-555호, 2024-01-01 시행) 민간 주거 신재생 의무 2024년 9.5~10.5%(세대 규모별), 해마다 +0.5%p(2026년 10.5~11.5%) — 지표 문장, 값에 쓰지 않음",
    "50": "제주: 녹색건축물 설계기준(제주특별자치도 고시 제2025-160호, 2025-07-01 게재) 민간 공동주택 신재생 의무 8~12%(세대 규모 · 연도별, 2025~2027) — 지표 문장, 값에 쓰지 않음",
}
PV_UPPER_BOUND_NOTE = "지붕을 연면적(위 한계)으로만 알아 이 용량이 지붕에 들어가는지 모름 — 층수나 동별 건축면적을 넣으면 발전량 · 감축량을 계산"


def pv_levels(households: float | None, kwh_per_kw: float | None, factor_kgco2eq_per_kwh: float,
              roof_limit_kw: float | None, region_code: str | None, roof_basis: str | None = None) -> dict[str, Any]:
    """지붕 태양광의 인증 · 실제 사례 수준(추정 범위): 세대 수 × 세대당 kW → 지역 발전량 → 전력 계수. 지붕 한도로 자름.

    지붕 최대(지금 값)와 더하지 않고, 목표 · 추천 방안 계산에 쓰지 않는다. 세대 수가 없으면 값 없이 이유만.
    지붕이 연면적 위 한계(``floor_area_upper_bound``)뿐이면 kW 범위만 내고 발전량 · 감축량은 비운다(지붕 최대 줄과 같은 판단)."""
    upper = roof_basis == "floor_area_upper_bound"
    out: dict[str, Any] = {"households": households if households and households > 0 else None, "kwh_per_kw": kwh_per_kw,
                           "roof_limit_kw": roof_limit_kw, "roof_limit_basis": roof_basis}
    for level, rng in (("certified", PV_KW_PER_HOUSEHOLD_CERTIFIED), ("cases", PV_KW_PER_HOUSEHOLD_CASES)):
        source_type, basis = PV_LEVEL_BASIS[level]
        row: dict[str, Any] = {"data_class": "ESTIMATED", "source_type": source_type, "basis": basis, "kw_per_household": list(rng),
                               "kw_range": None, "kwh_range": None, "kgco2eq_range": None, "capped": False, "reason": None}
        if not households or households <= 0:
            row["reason"] = "세대 수가 없어 계산하지 않음(계획 평가의 주거 용도 줄에 세대 수를 넣으면 계산)"
        elif roof_limit_kw is not None and roof_limit_kw <= 0:
            row["reason"] = "계획 지붕 한도가 0이라 계산하지 않음"
        else:
            raw = [households * k for k in rng]
            cap = None if upper else roof_limit_kw
            fitted = [min(v, cap) if cap is not None else v for v in raw]
            row.update(kw_range=[round(v, 1) for v in fitted], capped=cap is not None and raw[1] > cap)
            if upper:
                row["reason"] = PV_UPPER_BOUND_NOTE
            elif kwh_per_kw:
                kwh = [v * kwh_per_kw for v in fitted]
                row.update(kwh_range=[round(v, 1) for v in kwh], kgco2eq_range=[round(v * factor_kgco2eq_per_kwh, 1) for v in kwh])
        out[level] = row
    out["region_rule"] = PV_REGION_RULE.get(str(region_code or "")[:2])
    return out


def applicable_measures(targets: list[dict[str, Any]], added_m2: float, district_share_pct: float | None,
                        cooling_reading: str | None, green_area_m2: float | None = None,
                        pv_levels: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Recommendation lines of the area screen ↔ the measures usable under the site's conditions (U4, 2026-11-23, 5.15).

    Only the rooftop PV line has a reduction value (this calculation's own PV); greenery carries a separate offset
    (kgCO2, value_status OFFSET) only when the plan gives a green area (2026-11-25); every other measure is an indicator with its
    evidence (measures list + evidence table summary), never multiplied into the plan. Existing-building measures go
    to the whole-area target only; district heating control only where the region has district-heated households;
    operation (after move-in behaviour) is folded as outside the planning stage."""
    from .measure_catalog import measure_level
    from .reference_tables import evidence_summary
    ev = evidence_summary()["by_measure"]
    green = greenery_offset(green_area_m2)
    out: list[dict[str, Any]] = []
    for t in targets:
        rec = t.get("recommended") or {}
        pv_c = rec.get("pv_kgco2eq") or None   # 0 kg is not a value (no roof / no yield)
        for m in MEASURES:
            if m.get("phase") != "operation" and m["key"] != "greenery":
                continue
            apply = m.get("apply") or ""
            new_ok = added_m2 > 0 and any(w in apply for w in ("신축", "재개발"))
            existing_ok = any(w in apply for w in ("기존", "리모델링"))
            if m["key"] == "rooftop_pv":
                attach = ["pv_onsite"]
            else:
                attach = (["remaining_new"] if new_ok else []) + (["remaining_existing"] if existing_ok and t["key"] == "area_total" else [])
            if not attach:
                continue
            if m["key"] == "district_heating_control" and not district_share_pct:
                continue
            table = ev.get(m["key"])
            top = table["exclusion"][0]["value"] if table and table.get("exclusion") else None
            quantified = m["key"] == "rooftop_pv" and pv_c is not None and rec.get("onsite_status") in ("MET", "PARTIAL")
            condition = None
            if m["key"] == "envelope" and district_share_pct:
                condition = f"이 지역 공동주택 세대의 {district_share_pct:,.1f}%가 지역난방입니다. 지표의 근거는 개별난방 단지 짝 비교입니다"
            elif m["key"] == "shading" and cooling_reading:
                condition = cooling_reading
            out.append({"target": t["key"], "key": m["key"], "title": m["title"], "group": m.get("group"), "attach_to": attach,
                        "value_status": "QUANTIFIED" if quantified else "INDICATOR_ONLY",
                        "value_kgco2eq": pv_c if quantified else None,
                        "no_value_reason": None if quantified else _no_value_reason(m["key"], rec.get("onsite_status")),
                        "indicator_text": indicator_text(m), "evidence": m["evidence"], "evidence_label": EVIDENCE_LABEL[m["evidence"]],
                        "n": m.get("n"), "apply": apply, "evidence_table": table,
                        "group_kind": GROUP_KIND.get(top or "", "계획 수단"), "condition_text": condition,
                        # 2026-11-25(계획 v3 A): 이 줄의 수준(값 / 지표)과 근거 묶음(근거표 수단_ID). 계산 · 순서는 그대로
                        "level": measure_level(m["key"], quantified), "evidence_groups": _groups_of(m["key"])})
            if m["key"] == "rooftop_pv" and pv_levels is not None:
                out[-1]["pv_levels"] = {k: (dict(v) if isinstance(v, dict) else v) for k, v in pv_levels.items()}   # 2026-11-25(계획 v3 E): 인증 · 사례 수준(추정, 합계 밖), 줄마다 복사
            if m["key"] == "greenery" and green:
                # 2026-11-25(계획 v3 D): 계획 녹지 면적이 있으면 상쇄 값. 감축(kgCO2eq) 칸이 아니라 따로 둔 흡수(kgCO2) 칸에만 —
                # value_status "OFFSET"이라 감축 값 줄(QUANTIFIED)과 섞이지 않고, 어떤 합계에도 넣지 않음(독립 검토 반영)
                out[-1].update({"value_status": "OFFSET", "offset_kgco2": green["kgco2"], "offset_range_kgco2": green["range_kgco2"],
                                "offset_text": green["text"], "no_value_reason": green["text"], "level": measure_level(m["key"], True)})
    return out
