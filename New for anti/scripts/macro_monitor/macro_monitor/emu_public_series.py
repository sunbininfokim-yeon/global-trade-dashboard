"""Euro area: the ECB Data Portal and Eurostat (both keyless), BIS for the effective exchange rate.

Composition. Bulgaria joined in 2026 (EA21). Series are the changing-composition euro area where one
exists (Eurostat geo=EA for HICP, EA21 for the current account, ECB U2), so history does not break.

HICP moved to ECOICOP ver. 2 in 2026: the old datasets (prc_hicp_manr, ECB ICP) stop at 2025-12, and
the live one is Eurostat prc_hicp_minr (coicop18 TOTAL / TOT_X_NRG_FOOD).

Not here, and why: APP/PEPP split, TLTRO, TPI (no single keyless series mapped), negotiated wages (the
ECB series stops at 2025-Q3), HCOB PMIs and IFO (licensed), bank lending survey, CDS.
"""

from __future__ import annotations

from . import us_public_series as ups
from .world_public_series import Card, card, monthly_last, spread_bp

GDP_SOURCE = "eurostat:namq_10_gdp"


def _ecb_net(f):
    pepp = dict(f.get("ecb_prog", "PEPP")["net"])
    return [(d, (v + pepp.get(d, 0.0)) * 1e-3) for d, v in f.get("ecb_prog", "APP")["net"]]
_ECB = "https://data.ecb.europa.eu/data/datasets/{ds}"
_ESTAT = "https://ec.europa.eu/eurostat/databrowser/view/{ds}/default/table"
_HICP = "unit=RCH_A&geo=EA&coicop18={c}"
_GDP = "geo=EA&unit={u}&s_adj=SCA&na_item=B1GQ"
_CA = "geo=EA21&partner=EXT_EA21&bop_item=CA&stk_flow=BAL&s_adj=NSA&sector10=S1&sectpart=S1&currency=MIO_EUR"

CARDS: list[Card] = [
    card("deposit_facility", "monthly", "%", "pct2", "수신금리 DFR",
         "ECB 예금금리(DFR) -- 현재 정책 기조를 결정하는 금리입니다. 각 달 말, 최신 점은 최근 영업일. ECB FM.",
         "ecb:FM.DFR", _ECB.format(ds="FM"), lambda f: monthly_last(f.get("ecb", "FM", "D.U2.EUR.4F.KR.DFR.LEV"))),
    card("mro_rate", "monthly", "%", "pct2", "MRO 레포금리",
         "ECB 주요 재융자 금리(MRO)입니다. ECB FM.", "ecb:FM.MRR_FR", _ECB.format(ds="FM"),
         lambda f: monthly_last(f.get("ecb", "FM", "D.U2.EUR.4F.KR.MRR_FR.LEV"))),
    card("mlf_rate", "monthly", "%", "pct2", "한계대출금리",
         "ECB 한계대출금리(MLF)입니다. ECB FM.", "ecb:FM.MLFR", _ECB.format(ds="FM"),
         lambda f: monthly_last(f.get("ecb", "FM", "D.U2.EUR.4F.KR.MLFR.LEV"))),
    card("bund_10y", "monthly", "%", "pct2", "Bund 10년",
         "독일 국채 10년 수익률 월평균(ECB 장기금리 통계, 수렴기준 금리)입니다.", "ecb:IRS.DE", _ECB.format(ds="IRS"),
         lambda f: f.get("ecb", "IRS", "M.DE.L.L40.CI.0000.EUR.N.Z")),
    card("btp_10y", "monthly", "%", "pct2", "BTP 10년",
         "이탈리아 국채 10년 수익률 월평균(ECB 장기금리 통계)입니다.", "ecb:IRS.IT", _ECB.format(ds="IRS"),
         lambda f: f.get("ecb", "IRS", "M.IT.L.L40.CI.0000.EUR.N.Z")),
    card("btp_bund_spread", "monthly", "bp", "bp0", "BTP−Bund 스프레드",
         "이탈리아 − 독일 10년 수익률 월평균 차이(bp)입니다. 유로존 분절 위험의 대표 지표.", "ecb:IRS.IT-DE", _ECB.format(ds="IRS"),
         lambda f: spread_bp(f.get("ecb", "IRS", "M.IT.L.L40.CI.0000.EUR.N.Z"), f.get("ecb", "IRS", "M.DE.L.L40.CI.0000.EUR.N.Z"))),
    card("hicp_yoy", "monthly", "%", "pct1", "HICP YoY",
         "유로존 조화소비자물가(HICP) 전년 동월 대비입니다. Eurostat prc_hicp_minr(ECOICOP 2판).",
         "eurostat:prc_hicp_minr", _ESTAT.format(ds="prc_hicp_minr"),
         lambda f: f.get("eurostat", "prc_hicp_minr", _HICP.format(c="TOTAL"))),
    card("core_hicp_yoy", "monthly", "%", "pct1", "근원 HICP",
         "HICP(에너지·식품·주류·담배 제외) 전년 동월 대비입니다. Eurostat prc_hicp_minr.",
         "eurostat:prc_hicp_minr", _ESTAT.format(ds="prc_hicp_minr"),
         lambda f: f.get("eurostat", "prc_hicp_minr", _HICP.format(c="TOT_X_NRG_FOOD"))),
    card("m3_vs_2019", "monthly", "%", "pct1", "M3 vs 2019-12",
         "(현재 M3 − 2019-12 M3) / 2019-12 M3 × 100. M3 잔액(계절조정), ECB BSI.", "ecb:BSI.M30", _ECB.format(ds="BSI"),
         lambda f: ups.vs_base(f.get("ecb", "BSI", "M.U2.Y.V.M30.X.1.U2.2300.Z01.E"), "2019-12-01")),
    card("m3_yoy", "monthly", "%", "pct1", "M3 전년비",
         "M3 연간 증가율(ECB 공식, 계절조정)입니다. ECB BSI.", "ecb:BSI.M30.A", _ECB.format(ds="BSI"),
         lambda f: f.get("ecb", "BSI", "M.U2.Y.V.M30.X.I.U2.2300.Z01.A"), category="liquidity"),
    card("ecb_total_assets", "weekly", "tn_eur", "tn_eur2", "ECB 총자산",
         "유로시스템 통합 대차대조표 총자산(주간, 조 유로)입니다. ECB ILM.", "ecb:ILM.T000000", _ECB.format(ds="ILM"),
         lambda f: ups.scale(f.get("ecb", "ILM", "W.U2.C.T000000.Z5.Z01"), 1e-6)),
    card("gdp_qoq", "quarterly", "%", "pct1", "실질GDP QoQ",
         "유로존 실질GDP(연쇄가격, 계절·영업일조정) 전기 대비 %입니다(연율 아님). Eurostat namq_10_gdp.",
         "eurostat:namq_10_gdp", _ESTAT.format(ds="namq_10_gdp"),
         lambda f: f.get("eurostat", "namq_10_gdp", _GDP.format(u="CLV_PCH_PRE"))),
    card("gdp_yoy", "quarterly", "%", "pct1", "실질GDP YoY",
         "유로존 실질GDP 전년 동기 대비입니다. Eurostat namq_10_gdp.", "eurostat:namq_10_gdp",
         _ESTAT.format(ds="namq_10_gdp"), lambda f: f.get("eurostat", "namq_10_gdp", _GDP.format(u="CLV_PCH_SM"))),
    card("current_account", "monthly", "bn_eur", "bn1eurs", "경상수지",
         "유로존(EA21, 구성 변화 반영) 대외 경상수지(월, 원계열, 십억 유로)입니다. Eurostat ei_bpm6ca_m.",
         "eurostat:ei_bpm6ca_m", _ESTAT.format(ds="ei_bpm6ca_m"),
         lambda f: ups.scale(f.get("eurostat", "ei_bpm6ca_m", _CA), 1e-3), chart="bar"),
    card("app_balance", "monthly", "tn_eur", "tn_eur2", "APP 잔액",
         "자산매입프로그램(APP: PSPP·CSPP·CBPP3·ABSPP) 월말 보유액(장부가, 조 유로)입니다. ECB APP 이력 CSV.",
         "ecb:APP_breakdown_history", "https://www.ecb.europa.eu/mopo/implement/app/html/index.en.html",
         lambda f: ups.scale(f.get("ecb_prog", "APP")["holdings"], 1e-6)),
    card("pepp_balance", "monthly", "tn_eur", "tn_eur2", "PEPP 잔액",
         "팬데믹 긴급매입(PEPP) 월말 보유액(장부가, 조 유로)입니다. ECB PEPP 이력 CSV.",
         "ecb:PEPP_breakdown_history", "https://www.ecb.europa.eu/mopo/implement/pepp/html/index.en.html",
         lambda f: ups.scale(f.get("ecb_prog", "PEPP")["holdings"], 1e-6)),
    card("ecb_bond_ops", "monthly", "bn_eur", "bn1eurs", "APP/PEPP 순매입 (월)",
         "APP + PEPP 월 순매입(장부가, 십억 유로)입니다. 음수 = 만기 미재투자에 따른 축소(QT).",
         "ecb:APP+PEPP", "https://www.ecb.europa.eu/mopo/implement/app/html/index.en.html",
         lambda f: _ecb_net(f), chart="bar"),
    card("eur_eer", "monthly", "index", "num1", "유로 EER",
         "유로 실질실효환율(BIS 광의 바스켓, 2020=100)입니다. 오르면 유로 강세.", "bis:WS_EER:M.R.B.XM",
         "https://data.bis.org/topics/EER", lambda f: f.get("bis", "M.R.B.XM")),
]

ups._FORMATS.update({
    "tn_eur2": lambda v: f"€{v:,.2f}T",
    "bn1eurs": lambda v: f"+€{v:,.1f}B" if v >= 0 else f"-€{-v:,.1f}B",
})
