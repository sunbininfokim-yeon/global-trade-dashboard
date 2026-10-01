"""United Kingdom: Bank of England IADB and ONS time series (both keyless), BIS for the REER, FRED for
the Bund leg of the spread.

Not here, and why: gilt 2y/30y and the 10y-2y spread (no IADB par-yield code found for those tenors),
BoE total assets / APF / market-stabilisation facility (not mapped in IADB yet), S&P Global PMIs
(licensed), CDS.
"""

from __future__ import annotations

from . import us_public_series as ups
from .world_public_series import Card, card, money, monthly_last, monthly_mean, spread_bp

GDP_SOURCE = "ons:ihyq+ihyr"
_BOE = "https://www.bankofengland.co.uk/boeapps/database/"
_ONS = "https://www.ons.gov.uk/"
BN_GBP = money("£", 1)
_CPI = "economy/inflationandpriceindices/timeseries/{s}/mm23"
_LMS = "employmentandlabourmarket/{p}/timeseries/{s}/lms"


CARDS: list[Card] = [
    card("bank_rate", "monthly", "%", "pct2", "Bank Rate",
         "영란은행 기준금리(Bank Rate)입니다. 차트는 각 달 말, 최신 점은 최근 영업일. BoE IADB IUDBEDR.",
         "boe:IUDBEDR", _BOE, lambda f: monthly_last(f.get("boe", "IUDBEDR"))),
    card("sonia", "monthly", "%", "pct2", "SONIA",
         "파운드 익일물 금리 SONIA입니다. 각 달 마지막 영업일, 최신 점은 최근 영업일. BoE IADB IUDSOIA.",
         "boe:IUDSOIA", _BOE, lambda f: monthly_last(f.get("boe", "IUDSOIA"))),
    card("bond_10y", "monthly", "%", "pct2", "Gilt 10년",
         "영국 국채 10년 명목 par 수익률(영란은행 추정 곡선)입니다. 각 달 마지막 영업일. BoE IADB IUDMNPY.",
         "boe:IUDMNPY", _BOE, lambda f: monthly_last(f.get("boe", "IUDMNPY"))),
    card("gilt_bund_10y", "monthly", "bp", "bp0", "Gilt−Bund 10Y",
         "영국 10년(BoE par, 월평균) − 독일 10년(OECD 월평균, FRED IRLTLT01DEM156N), bp입니다.",
         "boe:IUDMNPY-fred:IRLTLT01DEM156N", "https://fred.stlouisfed.org/series/IRLTLT01DEM156N",
         lambda f: spread_bp(monthly_mean(f.get("boe", "IUDMNPY")), f.get("fred", "IRLTLT01DEM156N"))),
    card("m4_vs_2019", "monthly", "%", "pct1", "M4 vs 2019-12",
         "(현재 M4 − 2019-12 M4) / 2019-12 M4 × 100. M4 잔액(계절조정), BoE IADB LPMAUYN.",
         "boe:LPMAUYN", _BOE, lambda f: ups.vs_base(monthly_last(f.get("boe", "LPMAUYN"))[0], "2019-12-01")),
    card("m4_yoy", "monthly", "%", "pct1", "M4 전년비",
         "M4 잔액(계절조정) 전년 동월 대비입니다. BoE IADB LPMAUYN.",
         "boe:LPMAUYN", _BOE, lambda f: ups.pct_change(monthly_last(f.get("boe", "LPMAUYN"))[0], 12), category="liquidity"),
    card("cpi_yoy", "monthly", "%", "pct1", "CPI YoY",
         "소비자물가(CPI) 전년 동월 대비입니다. ONS D7G7.", "ons:d7g7", _ONS + _CPI.format(s="d7g7"),
         lambda f: f.get("ons", _CPI.format(s="d7g7"))),
    card("core_cpi_yoy", "monthly", "%", "pct1", "근원 CPI YoY",
         "근원 CPI(에너지·식품·주류·담배 제외) 전년 동월 대비입니다. ONS DKO8.", "ons:dko8", _ONS + _CPI.format(s="dko8"),
         lambda f: f.get("ons", _CPI.format(s="dko8"))),
    card("services_cpi", "monthly", "%", "pct1", "서비스 물가",
         "CPI 서비스 전년 동월 대비입니다. 영란은행이 가장 주시하는 국내 물가 압력. ONS D7NN.",
         "ons:d7nn", _ONS + _CPI.format(s="d7nn"), lambda f: f.get("ons", _CPI.format(s="d7nn"))),
    card("rpi_yoy", "monthly", "%", "pct1", "RPI YoY",
         "소매물가(RPI) 전년 동월 대비입니다. 물가연동 길트 기준. ONS CZBH.", "ons:czbh", _ONS + _CPI.format(s="czbh"),
         lambda f: f.get("ons", _CPI.format(s="czbh"))),
    card("unemployment", "monthly", "%", "pct1", "실업률",
         "실업률(16세 이상, 계절조정, 3개월 이동)입니다. ONS MGSX.", "ons:mgsx",
         _ONS + _LMS.format(p="peoplenotinwork/unemployment", s="mgsx"),
         lambda f: f.get("ons", _LMS.format(p="peoplenotinwork/unemployment", s="mgsx"))),
    card("inactivity_rate", "monthly", "%", "pct1", "비경제활동비율",
         "비경제활동비율(16-64세, 계절조정)입니다. ONS LF2S.", "ons:lf2s",
         _ONS + _LMS.format(p="peoplenotinwork/economicinactivity", s="lf2s"),
         lambda f: f.get("ons", _LMS.format(p="peoplenotinwork/economicinactivity", s="lf2s"))),
    card("awe_incl_bonus", "monthly", "%", "pct1", "AWE 보너스포함",
         "주당 평균임금(전체, 보너스 포함) 3개월 평균 전년 대비입니다. ONS KAC3.", "ons:kac3",
         _ONS + _LMS.format(p="peopleinwork/earningsandworkinghours", s="kac3"),
         lambda f: f.get("ons", _LMS.format(p="peopleinwork/earningsandworkinghours", s="kac3"))),
    card("awe_ex_bonus", "monthly", "%", "pct1", "AWE 보너스제외",
         "주당 평균임금(정규급여, 보너스 제외) 3개월 평균 전년 대비입니다. ONS KAI9.", "ons:kai9",
         _ONS + _LMS.format(p="peopleinwork/earningsandworkinghours", s="kai9"),
         lambda f: f.get("ons", _LMS.format(p="peopleinwork/earningsandworkinghours", s="kai9"))),
    card("gdp_qoq", "quarterly", "%", "pct1", "실질GDP QoQ",
         "실질GDP(연쇄가격, 계절조정) 전기 대비 %입니다(연율 아님). ONS IHYQ.", "ons:ihyq",
         _ONS + "economy/grossdomesticproductgdp/timeseries/ihyq/qna",
         lambda f: f.get("ons", "economy/grossdomesticproductgdp/timeseries/ihyq/qna")),
    card("gdp_yoy", "quarterly", "%", "pct1", "실질GDP YoY",
         "실질GDP(연쇄가격, 계절조정) 전년 동기 대비입니다. ONS IHYR.", "ons:ihyr",
         _ONS + "economy/grossdomesticproductgdp/timeseries/ihyr/qna",
         lambda f: f.get("ons", "economy/grossdomesticproductgdp/timeseries/ihyr/qna")),
    card("current_account", "quarterly", "bn_gbp", BN_GBP, "경상수지",
         "경상수지(분기, 계절조정, 십억 파운드)입니다. ONS HBOP.", "ons:hbop",
         _ONS + "economy/nationalaccounts/balanceofpayments/timeseries/hbop/pnbp",
         lambda f: ups.scale(f.get("ons", "economy/nationalaccounts/balanceofpayments/timeseries/hbop/pnbp"), 1e-3)),
    card("gbp_reer", "monthly", "index", "num1", "파운드 REER",
         "파운드 실질실효환율(BIS 광의 바스켓, 2020=100)입니다. 오르면 파운드 강세.", "bis:WS_EER:M.R.B.GB",
         "https://data.bis.org/topics/EER", lambda f: f.get("bis", "M.R.B.GB")),
]
