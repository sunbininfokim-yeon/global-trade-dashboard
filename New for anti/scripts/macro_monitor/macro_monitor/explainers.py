"""Country indicator explainers (limitations.kind = explainers).

UI panel title: 「지표 설명 (<국가>)」. Describes what each key chip measures —
not inference caveats.
"""

from __future__ import annotations

from typing import Any


def _pack(country_ko: str, items: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "title_ko": f"지표 설명 ({country_ko})",
        "kind": "explainers",
        "items": items,
    }


def _item(id_: str, title_ko: str, body_ko: str) -> dict[str, str]:
    return {"id": id_, "title_ko": title_ko, "body_ko": body_ko}


# Shared building blocks (country-specific wording still preferred when kit differs)
_ELEC = _item(
    "electricity_generation",
    "발전량",
    "연간 총발전량(TWh, Ember). 클릭 시 연료별 에너지 믹스 비중.",
)
_RATINGS = _item(
    "sovereign_ratings",
    "국가신용등급",
    "S&P · Moody's · Fitch 장기외화 등급. 칩은 3사 한 줄 요약.",
)
_CDS = _item(
    "sovereign_cds_5y",
    "5년 국채 CDS",
    "달러표시 국채 신용부도스왑. 시장이 매긴 국가 신용위험 프리미엄.",
)


USA_EXPLAINERS = _pack(
    "미국",
    [
        _item(
            "tga",
            "TGA 잔고",
            "Treasury General Account — 재무부가 연준에 둔 정부 운영현금. "
            "잔고↑는 시중 은행 준비금·유동성을 흡수하는 쪽으로 읽힌다. "
            "출처: Fiscal Data Daily Treasury Statement(Operating Cash Balance).",
        ),
        _item(
            "qra_issuance",
            "QRA 발행 (만기별)",
            "재무부 Quarterly Refunding Announcement. 순발행·현금 가정·만기별 "
            "T-Bill(무이표)·Note/Bond(이표) 스케줄. 클릭 시 전분 실적·직전 예측·당기 비교와 "
            "만기 바/표를 본다.",
        ),
        _item(
            "fed_ust_holdings",
            "연준 보유국채 (SOMA)",
            "시장 금리(3M·2Y·10Y)가 아니라 연준 대차대조표에 쌓인 국채 잔고($B). "
            "잔존만기 ≤1y / 1–5 / 5–10 / >10 스택으로 표시한다.",
        ),
        _item(
            "net_liquidity",
            "순유동성",
            "Fed 총자산 − TGA − ON RRP (조 달러). 시스템 유동성 대략치.",
        ),
        _item(
            "bond_yields",
            "국채 금리 3M·2Y·10Y",
            "시장 수익률(FRED). SOMA 보유잔고와 별개 슬롯.",
        ),
        _item(
            "hy_oas",
            "High Yield OAS",
            "투기등급 회사채 신용스프레드. 위험선호·신용여건 지표.",
        ),
        _item(
            "fedwatch",
            "FedWatch",
            "다음 FOMC에서 기준금리 경로 확률(동결·±25·±50bp 등). "
            "칩은 최고확률 한 줄, 차트는 결과별 바.",
        ),
        _item(
            "gdp",
            "실질GDP",
            "칩은 YoY | QoQ(비연율). BEA. 클릭 시 YoY↔QoQ 토글·기여도 components.",
        ),
        _item(
            "inflation",
            "물가 (CPI·Core·Trimmed·BEI)",
            "메인 스토리 CPI/Core CPI + Dallas Trimmed Mean. BEI는 10Y 하나. "
            "Core PCE는 참고(칩 비표시). 클릭 시 부문 기여도.",
        ),
        _item(
            "nfp",
            "비농업고용",
            "월별 증감(천 명). 신뢰도 낮고 개정 폭이 큼 — Claims·실업과 교차확인.",
        ),
        _item(
            "fiscal_dts_mts",
            "Fiscal Data (DTS·MTS)",
            "일별: 운영현금(TGA)·시중성 국채 발행/상환. "
            "월별: 세입·세출·재정적자(MTS). 연방 재정 흐름의 공식 표.",
        ),
        _ELEC,
    ],
)


JPN_EXPLAINERS = _pack(
    "일본",
    [
        _item(
            "boj_total_assets",
            "BOJ 총자산",
            "일본은행 대차대조표 규모. JGB·ETF·J-REIT 매입의 결과물. "
            "자산/GDP·YoY와 함께 유동성 탭의 중심.",
        ),
        _item(
            "boj_jgb_share",
            "JGB BOJ 보유비율",
            "유통 국채 중 일본은행 보유 비중. YCC·대규모 매입의 흔적.",
        ),
        _item(
            "boj_etf_holdings",
            "BOJ 보유 ETF",
            "중앙은행이 상장 ETF를 대량 보유한 유일한 주요국 사례. "
            "잔고·시장 비중을 추적한다.",
        ),
        _item(
            "call_rate",
            "무담보콜금리",
            "일본의 단기 정책금리 벤치마크. BOJ 목표 구간의 실현치.",
        ),
        _item(
            "jgb_curve",
            "JGB 2Y·10Y·30Y",
            "국채 수익률 곡선. 초장기(30Y)와 10Y−2Y·30Y−10Y 스프레드로 기울기를 본다.",
        ),
        _item(
            "usdjpy",
            "USD/JPY · 개입",
            "달러–엔. 외환보유·월간 개입액·엔 REER·IMM 순투기포지션과 함께 읽는다.",
        ),
        _item(
            "nikkei",
            "Nikkei · TOPIX",
            "대표 주가지수. 외국인 순매수·Nikkei VI(변동성)가 보조.",
        ),
        _item(
            "gdp",
            "실질GDP",
            "YoY | QoQ. 캐빈닛 오피스. 춘투 임금·실질임금·유효구인배율이 노동 쪽 보조.",
        ),
        _item(
            "inflation_jp",
            "물가 (근원·근원근원·도쿄·CGPI)",
            "전국 근원 CPI(신선식품 제외), 근원-근원(식료·에너지 제외), "
            "선행 성격의 도쿄 CPI, 기업물가 CGPI.",
        ),
        _RATINGS,
        _CDS,
        _ELEC,
    ],
)


UK_EXPLAINERS = _pack(
    "영국",
    [
        _item(
            "boe_total_assets",
            "BOE 총자산 · APF",
            "영란은행 BS와 Asset Purchase Facility(길트) 잔고. "
            "매입·매도(런오프)는 boe_gilt_ops.",
        ),
        _item(
            "bank_rate",
            "Bank Rate · SONIA",
            "정책금리(Bank Rate)와 무담보 오버나이트 SONIA. 단기 통화정책 스탠스.",
        ),
        _item(
            "gilt_curve",
            "Gilt 2Y·10Y·30Y",
            "영국 국채 곡선. Gilt−Bund 10Y는 유로존 대비 프리미엄.",
        ),
        _item(
            "m4",
            "M4",
            "광의통화. vs 2019·전년비로 유동성 팽창을 추적.",
        ),
        _item(
            "gbpusd",
            "GBP/USD · REER",
            "달러–파운드와 실질실효환율. EUR/GBP도 교차로 함께 본다.",
        ),
        _item(
            "ftse",
            "FTSE 100 · 250",
            "대형(해외매출 비중 큼)·중형(내수 비중 큼) 지수. 내수·해외를 구분할 때 유용.",
        ),
        _item(
            "gdp",
            "실질GDP · AWE · 실업",
            "GDP YoY|QoQ, 평균임금(AWE, 보너스 포함/제외), 실업·비경제활동비율.",
        ),
        _item(
            "inflation_uk",
            "CPI · Core · 서비스 · RPI",
            "헤드라인·근원 CPI, 서비스 물가, 주택·모기지 관련 RPI.",
        ),
        _RATINGS,
        _CDS,
        _ELEC,
    ],
)


CN_EXPLAINERS = _pack(
    "중국",
    [
        _item(
            "tsf_m2",
            "TSF · M1 · M2 · RRR",
            "사회융자총량(TSF) YoY, M1/M2와 M1−M2 스프레드, 지급준비율(RRR), OMO 순공급. "
            "신용·유동성 정책의 핵심.",
        ),
        _item(
            "lpr",
            "LPR 1Y · 5Y",
            "대출우대금리. 1년은 단기 대출, 5년은 모기지·장기 투자 벤치마크.",
        ),
        _item(
            "credit_spreads_cn",
            "LGFV · 부동산 HY 스프레드",
            "지방융자플랫폼(LGFV) 신용스프레드와 달러 부동산 하이일드. "
            "암묵보증·디폴트 리스크 온도계.",
        ),
        _item(
            "usdcny",
            "USD/CNY · CNH · CFETS",
            "역내 CNY, 역외 CNH, PBOC 고시환율, CFETS 위안지수, 외환보유액.",
        ),
        _item(
            "equity_cn",
            "A주 · H주 · 북·남향",
            "상해종합·CSI300(A), HSCEI(H). 후·선강통 북향·남향 자금 흐름.",
        ),
        _item(
            "growth_cn",
            "GDP · PMI · 부동산 · 청년실업",
            "공식 GDP YoY, NBS/Caixin PMI, 신규주택가격·부동산 FAI, 청년실업. "
            "커창지수는 전력·운송·대출 합성 대안 경기.",
        ),
        _item(
            "inflation_cn",
            "CPI · PPI",
            "소비자물가와 생산자물가. 디플레·디플레이션 압력은 PPI에서 먼저 보이는 경우가 많다.",
        ),
        _RATINGS,
        _CDS,
        _ELEC,
    ],
)


EZ_EXPLAINERS = _pack(
    "유로존",
    [
        _item(
            "ecb_bs",
            "ECB 총자산 · APP · PEPP · TLTRO",
            "유로시스템 BS, 자산매입(APP)·팬데믹 매입(PEPP) 잔액, TLTRO 상환. "
            "순매입은 ecb_bond_ops.",
        ),
        _item(
            "ecb_rates",
            "DFR · MRO · MLF",
            "수신금리(DFR)·메인 레포(MRO)·한계대출(MLF). 유로존 정책금리 코리도.",
        ),
        _item(
            "btp_bund",
            "Bund · BTP · 스프레드 · TPI",
            "독일·이탈리아 10Y와 BTP−Bund. TPI 가동 여부는 분절화 대응 신호.",
        ),
        _item(
            "m3_ez",
            "M3",
            "유로존 광의통화 vs 2019·전년비.",
        ),
        _item(
            "eurusd",
            "EUR/USD · EER",
            "달러–유로와 유로 실효환율. EUR/GBP·EUR/JPY 교차도 포함.",
        ),
        _item(
            "equity_ez",
            "Stoxx50 · DAX · CAC · Banks",
            "유로존·독일·프랑스 대표지수와 은행주(Euro Stoxx Banks).",
        ),
        _item(
            "gdp_ez",
            "GDP · PMI · IFO · BLS",
            "유로존 GDP, HCOB 제조·서비스 PMI, 독일 IFO, 은행대출태도(BLS).",
        ),
        _item(
            "hicp",
            "HICP · 근원 · 협약임금",
            "조화소비자물가(HICP)·근원, 협약임금 상승률.",
        ),
        _RATINGS,
        _CDS,
        _ELEC,
    ],
)


RU_EXPLAINERS = _pack(
    "러시아",
    [
        _item(
            "nwf_fx",
            "NWF · 외환보유",
            "국가복지기금(NWF) 유동자산, 총·접근가능 외환보유, 동결 비중. "
            "제재·접근성 제약이 핵심.",
        ),
        _item(
            "cbr_key_rate",
            "CBR 기준금리 · OFZ",
            "중앙은행 키레이트, OFZ 10Y, 입찰 커버. 긴축·재정조달 압력.",
        ),
        _item(
            "usdrub",
            "USD/RUB · CNY/RUB · Urals",
            "달러·위안 대비 루블, Urals−Brent 할인. 자본통제 하에서 읽는다.",
        ),
        _item(
            "moex",
            "MOEX · RTS",
            "루블·달러 표시 주식지수.",
        ),
        _item(
            "gdp_ru",
            "GDP · 실업 · 노동부족",
            "실질GDP, 실업률, 노동력 부족지수. 군수·재정 투입이 GDP를 밀어 올릴 수 있다.",
        ),
        _item(
            "inflation_ru",
            "CPI · Core · 기대인플레",
            "헤드라인·근원 CPI와 가계 기대인플레.",
        ),
        _RATINGS,
        _CDS,
        _ELEC,
    ],
)


HK_EXPLAINERS = _pack(
    "홍콩",
    [
        _item(
            "aggregate_balance",
            "총결제잔액 (Aggregate Balance)",
            "은행간 결제 시스템 잔액. LERS 하에서 유동성·금리 압력의 핵심 온도계.",
        ),
        _item(
            "hk_base_rate",
            "Base Rate · HIBOR",
            "HKMA Base Rate와 HIBOR 1M/3M. 연준 연동 + HIBOR−SOFR 스프레드.",
        ),
        _item(
            "usdhkd",
            "USD/HKD",
            "달러 페그(LERS) 밴드 안의 현물. 보유액·CNH와 함께.",
        ),
        _item(
            "hsi",
            "항셍 · HSCEI · 항셍테크 · CCL",
            "HSI(본토 기업 비중 큼), H주, 테크, CCL 주택지수.",
        ),
        _item(
            "gdp_hk",
            "GDP · 소매 · 무역",
            "실질GDP, 소매판매 YoY, 수출입 YoY.",
        ),
        _item(
            "composite_cpi",
            "종합 CPI",
            "홍콩 종합 소비자물가.",
        ),
        _RATINGS,
        _CDS,
        _ELEC,
    ],
)


SG_EXPLAINERS = _pack(
    "싱가포르",
    [
        _item(
            "sgd_neer",
            "S$NEER · 밴드",
            "MAS는 금리가 아니라 명목실효환율(S$NEER) 밴드로 정책을 운용. "
            "기울기·폭이 스탠스.",
        ),
        _item(
            "sora",
            "SORA · SGS",
            "오버나이트 SORA와 국채(SGS) 2Y/10Y. SORA는 주로 미 금리에 연동. "
            "SOFR−SORA 스프레드 포함.",
        ),
        _item(
            "mas_liquidity",
            "OFR · 총유동성 · M2",
            "MAS 외환보유(OFR), 총유동성, M2. 자산관리 허브 성격의 예금도 포함될 수 있다.",
        ),
        _item(
            "usdsgd",
            "USD/SGD",
            "달러–싱가포르달러.",
        ),
        _item(
            "sti",
            "STI · S-REIT · 주택",
            "Straits Times Index, REIT 지수, 민간주택가격.",
        ),
        _item(
            "nodx",
            "NODX · GDP · PMI",
            "비석유국내수출(NODX), GDP, SIPMM PMI.",
        ),
        _item(
            "mas_core",
            "MAS Core · CPI",
            "정책이 보는 근원인플레(MAS Core)와 헤드라인 CPI(COE·임대 등 포함).",
        ),
        _RATINGS,
        _CDS,
        _ELEC,
    ],
)


ZA_EXPLAINERS = _pack(
    "남아공",
    [
        _item(
            "fiscal_za",
            "재정수지 · 부채/GDP",
            "재정적자(또는 흑자)/GDP와 국가부채/GDP.",
        ),
        _item(
            "sarb_repo",
            "SARB Repo · SAGB",
            "남아프리카준비은행 정책금리와 국채 10Y.",
        ),
        _item(
            "usdzar",
            "USD/ZAR · 원자재",
            "랜드 환율과 금·백금·석탄 가격. 수출·경상과 함께.",
        ),
        _item(
            "load_shedding",
            "Load Shedding",
            "전력 제한공급(정전) 시간. 생산·물류의 실물 제약.",
        ),
        _item(
            "jse",
            "JSE Top 40 · 외국인 흐름",
            "주식지수, 외국인 국채비중·주식순매수.",
        ),
        _item(
            "gdp_za",
            "GDP · Absa PMI · 실업",
            "실질GDP, 제조 PMI, 실업률(구조적으로 높은 편).",
        ),
        _item(
            "inflation_za",
            "CPI · Core",
            "헤드라인·근원 소비자물가.",
        ),
        _RATINGS,
        _item(
            "za_cds_5y",
            "5년 국채 CDS",
            "남아공 달러 CDS. 재정·원자재·정치 리스크를 반영.",
        ),
        _ELEC,
    ],
)


IN_EXPLAINERS = _pack(
    "인도",
    [
        _item(
            "rbi_repo",
            "RBI Repo · LAF · CRR",
            "정책금리(Repo), 유동성조정창구(LAF) 잔고, 지급준비율(CRR).",
        ),
        _item(
            "m3_in",
            "M3 · 은행신용",
            "광의통화와 은행신용 YoY.",
        ),
        _item(
            "usdinr",
            "USD/INR · 외환보유 · CAD",
            "루피 환율, 외환보유액, 경상수지/GDP(CAD).",
        ),
        _item(
            "nifty",
            "Nifty · Sensex · FPI",
            "대표 주가지수와 외국인 포트폴리오(FPI) 순유입.",
        ),
        _item(
            "gdp_in",
            "GDP · PMI · 이륜·트랙터",
            "실질GDP, 제조·서비스 PMI, 농촌·소비 대리변수(이륜차·트랙터 판매).",
        ),
        _item(
            "inflation_in",
            "CPI · WPI",
            "소비자물가(식료 비중 큼)와 도매물가(WPI).",
        ),
        _RATINGS,
        _CDS,
        _ELEC,
    ],
)


KR_EXPLAINERS = _pack(
    "한국",
    [
        _item(
            "bok_base_rate",
            "한은 기준금리 · 한미 금리차",
            "한국은행 기준금리와 미국과의 금리 역전(갭). KTB 3Y·국고 10Y가 곡선.",
        ),
        _item(
            "bok_bs_m2",
            "한은 총자산 · M2 · 가계신용 · PF",
            "중앙은행 BS, M2, 가계신용(잔액·YoY), 부동산 PF 잔액·연체율.",
        ),
        _item(
            "credit_kr",
            "회사채 AA · CP 스프레드",
            "우량 회사채·기업어음 신용스프레드. 시장 신용여건.",
        ),
        _item(
            "usdkrw",
            "USD/KRW · 보유액 · 개입",
            "원/달러, 외환보유, 월간 개입 추정, 미 재무부 환율관찰 지정 여부.",
        ),
        _item(
            "kospi",
            "KOSPI · KOSDAQ · 외국인 · VKOSPI",
            "대표·벤처 지수, 외국인 주식순매수, 변동성(VKOSPI).",
        ),
        _item(
            "semi_export",
            "반도체·총수출 · GDP",
            "반도체 수출 YoY·총수출 YoY가 성장 키. GDP YoY|QoQ, CCSI·BSI·산업생산.",
        ),
        _item(
            "inflation_kr",
            "CPI · Core · 기대인플레",
            "헤드라인·근원 CPI와 한은 기대인플레이션.",
        ),
        _RATINGS,
        _CDS,
        _ELEC,
    ],
)


CA_EXPLAINERS = _pack(
    "캐나다",
    [
        _item(
            "boc_overnight",
            "BOC Overnight · 미−캐 2Y",
            "캐나다은행 정책금리와 미국−캐나다 2Y 스프레드. GoC 2Y·10Y 곡선.",
        ),
        _item(
            "hh_debt_ca",
            "가계부채/소득 · M3 · BOC BS",
            "가계부채 대비 가처분소득, M3, 중앙은행 총자산.",
        ),
        _item(
            "usdcad",
            "USD/CAD · WCS",
            "달러–캐나다달러, WCS 원유·WTI 스프레드, 무역수지.",
        ),
        _item(
            "tsx",
            "S&P/TSX · 외국인 증권",
            "대표 주가지수와 외국인 유가증권 순투자.",
        ),
        _item(
            "gdp_ca",
            "GDP · 1인당 · 고용 · Teranet",
            "총량·1인당 실질GDP, Ivey PMI, 실업·고용증감, Teranet 주택가격.",
        ),
        _item(
            "inflation_ca",
            "CPI · trim · median",
            "헤드라인과 BOC가 보는 CPI-trim·CPI-median.",
        ),
        _RATINGS,
        _CDS,
        _ELEC,
    ],
)


AU_EXPLAINERS = _pack(
    "호주",
    [
        _item(
            "rba_cash_rate",
            "RBA Cash Rate · ACGB",
            "정책금리와 국채 3Y·10Y, 미−호 10Y 스프레드.",
        ),
        _item(
            "hh_debt_au",
            "가계부채/소득 · M3 · RBA BS",
            "가계 레버리지, M3, 준비은행 총자산.",
        ),
        _item(
            "audusd",
            "AUD/USD · 철광·원료탄",
            "호주달러와 철광석·원료탄 가격, 무역수지. 원자재 통화 성격.",
        ),
        _item(
            "asx200",
            "ASX 200 · VIX",
            "대표 주가지수와 ASX 변동성.",
        ),
        _item(
            "gdp_au",
            "GDP · 1인당 · 주택 · 고용",
            "총량·1인당 GDP, CoreLogic 주택·건축승인, 실업·고용증감.",
        ),
        _item(
            "inflation_au",
            "CPI · 월간 · Trimmed Mean",
            "분기 CPI, 월간 CPI, RBA가 중시하는 Trimmed Mean.",
        ),
        _RATINGS,
        _CDS,
        _ELEC,
    ],
)


CH_EXPLAINERS = _pack(
    "스위스",
    [
        _item(
            "snb_bs",
            "SNB 총자산 · 외환 · Sight Deposits",
            "스위스국민은행 BS, 외환보유, 시중은행 요구불예금(Sight). "
            "환율방어 개입의 잔영.",
        ),
        _item(
            "snb_policy_rate",
            "SNB Policy Rate · CH−Bund",
            "정책금리와 스위스−독일 10Y 스프레드.",
        ),
        _item(
            "chf",
            "EUR/CHF · USD/CHF · REER",
            "안전자산 프랑 환율과 실질실효환율. 월간 개입 추정 포함.",
        ),
        _item(
            "smi",
            "SMI · 금융주",
            "Swiss Market Index와 은행·금융주. 구성 기업 매출은 해외 비중이 큼.",
        ),
        _item(
            "gdp_ch",
            "GDP · KOF · PMI",
            "실질GDP, KOF 선행지수, procure.ch PMI.",
        ),
        _item(
            "cpi_ch",
            "CPI",
            "스위스 소비자물가.",
        ),
        _RATINGS,
        _CDS,
        _ELEC,
    ],
)


BR_EXPLAINERS = _pack(
    "브라질",
    [
        _item(
            "fiscal_br",
            "기초재정수지 · 부채/GDP",
            "Primary fiscal balance/GDP와 국가부채/GDP. 재정 규칙·신뢰의 핵심.",
        ),
        _item(
            "selic_rate",
            "SELIC · 국채 10Y",
            "중앙은행 정책금리(SELIC)와 장기 국채 수익률.",
        ),
        _item(
            "usdbrl",
            "USD/BRL · 원자재 · 보유액",
            "헤알 환율, 철광·대두·원유, 외환보유·경상수지.",
        ),
        _item(
            "ibovespa",
            "Ibovespa · 외국인 유입",
            "대표 주가지수와 외국인 포트폴리오 순유입.",
        ),
        _item(
            "gdp_br",
            "GDP · IBC-Br · PMI · 실업",
            "실질GDP, 월간 경기(IBC-Br), 제조·서비스 PMI, 실업률.",
        ),
        _item(
            "ipca",
            "IPCA · IPCA-15",
            "공식 소비자물가와 중순 선행(IPCA-15).",
        ),
        _RATINGS,
        _item(
            "br_cds_5y",
            "5년 국채 CDS",
            "브라질 달러 CDS.",
        ),
        _ELEC,
    ],
)


VN_EXPLAINERS = _pack(
    "베트남",
    [
        _item(
            "sbv_rates",
            "SBV 재융자·할인 · 시중금리",
            "중앙은행 재융자·할인율과 시중 예금·대출금리.",
        ),
        _item(
            "credit_quota",
            "신용증가 한도 · M2",
            "연간 신용 쿼터와 M2. 금리와 별도로 실물 자금 공급을 제약할 수 있다.",
        ),
        _item(
            "usdvnd",
            "USD/VND · 보유액 · 무역",
            "동 환율(관리변동), 외환보유, 무역수지·경상.",
        ),
        _item(
            "fdi_vn",
            "FDI · VN-Index",
            "FDI 등록·실행액과 주식지수. 수출의 상당 부분이 FDI 기업.",
        ),
        _item(
            "export_vn",
            "수출 · GDP · PMI · IP",
            "수출 YoY, GDP, 제조 PMI, 산업생산.",
        ),
        _item(
            "cpi_vn",
            "CPI",
            "소비자물가.",
        ),
        _RATINGS,
        _CDS,
        _ELEC,
    ],
)


KZ_EXPLAINERS = _pack(
    "카자흐스탄",
    [
        _item(
            "nfrk",
            "NFRK 국가기금 · M3",
            "국가기금(NFRK) 자산과 M3. 자원 수입의 재정·저축 버퍼.",
        ),
        _item(
            "nbk_base_rate",
            "NBK Base Rate · 국채 10Y",
            "정책금리와 장기 국채.",
        ),
        _item(
            "usdkzt",
            "USD/KZT · RUB/KZT · 원자재",
            "텡게 환율, 루블 교차, 원유·CPC Blend·우라늄.",
        ),
        _item(
            "kase",
            "KASE · FDI",
            "주식지수와 FDI 순유입.",
        ),
        _item(
            "gdp_kz",
            "GDP · 광업·제조 생산",
            "실질GDP와 산업·광업·제조업 생산 YoY.",
        ),
        _item(
            "cpi_kz",
            "CPI",
            "소비자물가. 수입·루블 경로 영향이 큰 편.",
        ),
        _RATINGS,
        _CDS,
        _ELEC,
    ],
)


TW_EXPLAINERS = _pack(
    "대만",
    [
        _item(
            "cbc_discount",
            "CBC 할인율 · 국채 10Y · M2",
            "중앙은행 할인율, 국채 10Y, M2·초과저축률.",
        ),
        _item(
            "usdtwd",
            "USD/TWD · 생보 헤지 · 보유액",
            "대만달러, 생명보험 해외자산·환헤지비율, 외환보유·개입, 경상/GDP.",
        ),
        _item(
            "taiex",
            "가권(TAIEX) · 외국인",
            "대표 주가지수와 외국인 순매수. IT·AI 비중이 큼.",
        ),
        _item(
            "export_tw",
            "수출 · 수출주문 · GDP · PMI",
            "수출·수출주문 YoY, GDP, 제조 PMI. 반도체·전자 사이클 민감.",
        ),
        _item(
            "inflation_tw",
            "CPI · Core",
            "헤드라인·근원 소비자물가.",
        ),
        _RATINGS,
        _CDS,
        _ELEC,
    ],
)


IL_EXPLAINERS = _pack(
    "이스라엘",
    [
        _item(
            "boi_rate",
            "BOI 정책금리 · 국채 2Y·10Y",
            "이스라엘은행 정책금리와 국채 곡선.",
        ),
        _item(
            "fiscal_il",
            "재정수지 · 부채/GDP · BOI BS · M2",
            "재정·부채 비율, 중앙은행 총자산, M2·외환보유.",
        ),
        _item(
            "usdils",
            "USD/ILS",
            "셰켈 환율. 지정학 뉴스에 민감.",
        ),
        _item(
            "ta125",
            "TA-125",
            "텔아비브 대표 주가지수.",
        ),
        _item(
            "high_tech_export",
            "하이테크 수출 · GDP · 실업",
            "하이테크 수출 YoY, 실질GDP, 실업률.",
        ),
        _item(
            "inflation_il",
            "CPI · Core",
            "헤드라인·근원 소비자물가.",
        ),
        _RATINGS,
        _CDS,
        _ELEC,
    ],
)


KIT_EXPLAINERS: dict[str, dict[str, Any]] = {
    "us_macro_benchmark_v1": USA_EXPLAINERS,
    "jp_macro_v1": JPN_EXPLAINERS,
    "uk_macro_v1": UK_EXPLAINERS,
    "cn_macro_v1": CN_EXPLAINERS,
    "ez_macro_v1": EZ_EXPLAINERS,
    "ru_macro_v1": RU_EXPLAINERS,
    "hk_macro_v1": HK_EXPLAINERS,
    "sg_macro_v1": SG_EXPLAINERS,
    "za_macro_v1": ZA_EXPLAINERS,
    "in_macro_v1": IN_EXPLAINERS,
    "kr_macro_v1": KR_EXPLAINERS,
    "ca_macro_v1": CA_EXPLAINERS,
    "au_macro_v1": AU_EXPLAINERS,
    "ch_macro_v1": CH_EXPLAINERS,
    "br_macro_v1": BR_EXPLAINERS,
    "vn_macro_v1": VN_EXPLAINERS,
    "kz_macro_v1": KZ_EXPLAINERS,
    "tw_macro_v1": TW_EXPLAINERS,
    "il_macro_v1": IL_EXPLAINERS,
}
