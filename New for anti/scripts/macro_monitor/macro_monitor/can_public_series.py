"""Canada: Bank of Canada Valet and Statistics Canada WDS (both keyless), FRED for the US 2-year.

Not here, and why: Teranet HPI and Ivey PMI (licensed), WCS crude (no free daily series found),
household debt/income and foreign securities flows (StatCan tables not yet mapped), CDS.
"""

from __future__ import annotations

from . import us_public_series as ups
from .world_public_series import Card, card, money, monthly_last, monthly_mean, spread_bp

GDP_SOURCE = "statcan:v62305752"
_BOC = "https://www.bankofcanada.ca/rates/"
_SC = "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid={pid}"
BN_CAD = money("C$", 1)
BN0_CAD = money("C$", 0, signed=False)

def _gdp_per_capita(f):
    pop = dict(f.get("statcan", 1))
    per = [(d, v / pop[d]) for d, v in f.get("statcan", 62305752) if d in pop]
    return ups.pct_change(per, 4)


CARDS: list[Card] = [
    card("boc_overnight", "monthly", "%", "pct2", "BOC Overnight",
         "캐나다은행 기준금리(익일물 목표)입니다. 차트는 각 달 말, 최신 점은 최근 영업일. BoC Valet V39079.",
         "boc:V39079", _BOC + "interest-rates/canadian-interest-rates/", lambda f: monthly_last(f.get("boc", "V39079"))),
    card("bond_2y", "monthly", "%", "pct2", "GoC 2년",
         "캐나다 국채 2년 벤치마크 수익률입니다. 각 달 마지막 영업일, 최신 점은 최근 영업일. BoC Valet.",
         "boc:BD.CDN.2YR.DQ.YLD", _BOC + "interest-rates/canadian-bonds/",
         lambda f: monthly_last(f.get("boc", "BD.CDN.2YR.DQ.YLD"))),
    card("bond_10y", "monthly", "%", "pct2", "GoC 10년",
         "캐나다 국채 10년 벤치마크 수익률입니다. 각 달 마지막 영업일, 최신 점은 최근 영업일. BoC Valet.",
         "boc:BD.CDN.10YR.DQ.YLD", _BOC + "interest-rates/canadian-bonds/",
         lambda f: monthly_last(f.get("boc", "BD.CDN.10YR.DQ.YLD"))),
    card("us_ca_2y_spread", "monthly", "bp", "bp0", "미−캐 2Y 스프레드",
         "미 국채 2년(FRED DGS2) − 캐나다 2년(BoC) 월평균(bp)입니다. 양수면 미국 금리가 높아 CAD에 약세 압력.",
         "fred:DGS2-boc", "https://fred.stlouisfed.org/series/DGS2",
         lambda f: spread_bp(monthly_mean(f.get("fred", "DGS2")), monthly_mean(f.get("boc", "BD.CDN.2YR.DQ.YLD")))),
    card("cpi_yoy", "monthly", "%", "pct1", "CPI YoY",
         "소비자물가(전 품목, 원계열) 전년 동월 대비입니다. StatCan 발표치를 캐나다은행이 게시(BoC Valet).",
         "boc:STATIC_TOTALCPICHANGE", _BOC + "price-indexes/cpi/", lambda f: f.get("boc", "STATIC_TOTALCPICHANGE")),
    card("cpi_trim", "monthly", "%", "pct1", "CPI-trim",
         "캐나다은행 기조물가 CPI-trim 전년 동월 대비입니다. BoC Valet.",
         "boc:CPI_TRIM", _BOC + "price-indexes/cpi/", lambda f: f.get("boc", "CPI_TRIM")),
    card("cpi_median", "monthly", "%", "pct1", "CPI-median",
         "캐나다은행 기조물가 CPI-median 전년 동월 대비입니다. BoC Valet.",
         "boc:CPI_MEDIAN", _BOC + "price-indexes/cpi/", lambda f: f.get("boc", "CPI_MEDIAN")),
    card("m3_yoy", "monthly", "%", "pct1", "M3 전년비",
         "통화량 M3(총액, 계절조정) 전년 동월 대비입니다. BoC Valet V41552794.",
         "boc:V41552794", "https://www.bankofcanada.ca/rates/banking-and-financial-statistics/",
         lambda f: ups.pct_change(f.get("boc", "V41552794"), 12)),
    card("m3_vs_2019", "monthly", "%", "pct1", "M3 vs 2019-12",
         "(현재 M3 − 2019-12 M3) / 2019-12 M3 × 100. BoC Valet V41552794(계절조정).",
         "boc:V41552794", "https://www.bankofcanada.ca/rates/banking-and-financial-statistics/",
         lambda f: ups.vs_base(f.get("boc", "V41552794"), "2019-12-01")),
    card("boc_total_assets", "weekly", "bn_cad", BN0_CAD, "BOC 총자산",
         "캐나다은행 대차대조표 총자산(주간, 십억 캐나다달러)입니다. BoC Valet V36610.",
         "boc:V36610", "https://www.bankofcanada.ca/rates/banking-and-financial-statistics/",
         lambda f: ups.scale(f.get("boc", "V36610"), 1e-3)),
    card("unemployment", "monthly", "%", "pct1", "실업률",
         "실업률(15세 이상, 계절조정)입니다. StatCan 노동력조사 14-10-0287, v2062815.",
         "statcan:v2062815", _SC.format(pid="1410028701"), lambda f: f.get("statcan", 2062815)),
    card("employment_change", "monthly", "k_jobs", "k0s", "고용 증감",
         "취업자(계절조정) 전월 대비 증감(천 명)입니다. StatCan 14-10-0287, v2062811.",
         "statcan:v2062811", _SC.format(pid="1410028701"),
         lambda f: ups.scale(ups.diff(f.get("statcan", 2062811)), 1e-3), chart="bar"),
    card("gdp_qoq", "quarterly", "%", "pct1", "실질GDP QoQ",
         "실질GDP(연쇄 2017년 가격, 계절조정) 전기 대비 %입니다(연율 아님). StatCan 36-10-0104, v62305752.",
         "statcan:v62305752", _SC.format(pid="3610010401"), lambda f: ups.pct_change(f.get("statcan", 62305752), 1)),
    card("gdp_yoy", "quarterly", "%", "pct1", "실질GDP YoY",
         "실질GDP(연쇄 2017년 가격, 계절조정) 전년 동기 대비입니다. StatCan 36-10-0104, v62305752.",
         "statcan:v62305752", _SC.format(pid="3610010401"), lambda f: ups.pct_change(f.get("statcan", 62305752), 4)),
    card("gdp_per_capita_yoy", "quarterly", "%", "pct1", "1인당 실질GDP YoY",
         "실질GDP(v62305752) ÷ 분기 인구추계(v1)의 전년 동기 대비입니다. 총량 GDP와 갈리면 이민 주도 성장.",
         "statcan:v62305752/v1", _SC.format(pid="1710000901"), lambda f: _gdp_per_capita(f)),
    card("current_account", "quarterly", "bn_cad", BN_CAD, "경상수지",
         "경상수지(분기, 계절조정, 십억 캐나다달러)입니다. StatCan 36-10-0018, v61915304.",
         "statcan:v61915304", _SC.format(pid="3610001801"), lambda f: ups.scale(f.get("statcan", 61915304), 1e-9)),
    card("ca_trade_balance", "monthly", "bn_cad", BN_CAD, "무역수지",
         "상품 무역수지(국제수지 기준, 계절조정, 월, 십억 캐나다달러)입니다. StatCan 12-10-0011, v87008984.",
         "statcan:v87008984", _SC.format(pid="1210001101"), lambda f: ups.scale(f.get("statcan", 87008984), 1e-9),
         chart="bar"),
]
