"""Israel: Bank of Israel SDMX (edge.boi.gov.il, keyless) and FRED (OECD).

Not here, and why: current account, reserves and BOI total assets (BOI SDMX codes not mapped yet),
fiscal balance and debt ratio (annual; the sovereign fiscal pipeline covers debt), PMI, CDS.
"""

from __future__ import annotations

from . import us_public_series as ups
from .world_public_series import Card, card

GDP_SOURCE = "boi:NA:CHAINED_GDP_Q_FP_SA"
_BOI = "https://www.boi.org.il/en/economic-roles/statistics/"

CARDS: list[Card] = [
    card("boi_rate", "monthly", "%", "pct2", "BOI 정책금리",
         "이스라엘 초단기(익일) 금리 월평균입니다(OECD 집계, FRED IRSTCI01ILM156N). 이스라엘은행 기준금리를 따라 움직입니다.",
         "fred:IRSTCI01ILM156N", "https://fred.stlouisfed.org/series/IRSTCI01ILM156N", lambda f: f.get("fred", "IRSTCI01ILM156N")),
    card("bond_2y", "monthly", "%", "pct2", "셰켈 국채 2년",
         "명목 무이표 국채 2년 수익률 월평균입니다(이스라엘은행 수익률곡선 ZC_TSB_ZND_02Y_MA).", "boi:ZCM", _BOI,
         lambda f: f.get("boi", "ZCM", "ZC_TSB_ZND_02Y_MA")),
    card("bond_10y", "monthly", "%", "pct2", "셰켈 국채 10년",
         "명목 무이표 국채 10년 수익률 월평균입니다(이스라엘은행 수익률곡선 ZC_TSB_ZND_10Y_MA).", "boi:ZCM", _BOI,
         lambda f: f.get("boi", "ZCM", "ZC_TSB_ZND_10Y_MA")),
    card("cpi_yoy", "monthly", "%", "pct1", "CPI YoY",
         "소비자물가(일반지수) 전년 동월 대비입니다(중앙통계국 발표, 이스라엘은행 CP_PCHYTY).", "boi:PRI:CP_PCHYTY", _BOI,
         lambda f: f.get("boi", "PRI", "CP_PCHYTY")),
    card("core_cpi_yoy", "monthly", "%", "pct1", "CPI(에너지 제외) YoY",
         "에너지를 뺀 소비자물가 전년 동월 대비입니다(이스라엘은행 PT_NO_EN_PCHYTY).", "boi:PRI:PT_NO_EN_PCHYTY", _BOI,
         lambda f: f.get("boi", "PRI", "PT_NO_EN_PCHYTY")),
    card("m2_yoy", "monthly", "%", "pct1", "M2 전년비",
         "통화량 M2(월평균) 전년 동월 대비입니다. 이스라엘은행 MAG_RDB_M2_MA.", "boi:MAG:MAG_RDB_M2_MA", _BOI,
         lambda f: ups.pct_change(f.get("boi", "MAG", "MAG_RDB_M2_MA"), 12)),
    card("m2_vs_2019", "monthly", "%", "pct1", "M2 vs 2019-12",
         "(현재 M2 − 2019-12 M2) / 2019-12 M2 × 100. 이스라엘은행 MAG_RDB_M2_MA(월평균).", "boi:MAG:MAG_RDB_M2_MA", _BOI,
         lambda f: ups.vs_base(f.get("boi", "MAG", "MAG_RDB_M2_MA"), "2019-12-01")),
    card("gdp_qoq", "quarterly", "%", "pct1", "실질GDP QoQ",
         "실질GDP(연쇄가격, 계절조정) 전기 대비 %입니다(연율 아님). 이스라엘은행 국민계정 CHAINED_GDP_Q_FP_SA.",
         "boi:NA", _BOI, lambda f: ups.pct_change(f.get("boi", "NA", "CHAINED_GDP_Q_FP_SA"), 1)),
    card("gdp_yoy", "quarterly", "%", "pct1", "실질GDP YoY",
         "실질GDP(연쇄가격, 계절조정) 전년 동기 대비입니다. 이스라엘은행 국민계정.",
         "boi:NA", _BOI, lambda f: ups.pct_change(f.get("boi", "NA", "CHAINED_GDP_Q_FP_SA"), 4)),
    card("unemployment", "monthly", "%", "pct1", "실업률",
         "실업률(계절조정)입니다. OECD 집계, FRED LRUNTTTTILM156S.", "fred:LRUNTTTTILM156S",
         "https://fred.stlouisfed.org/series/LRUNTTTTILM156S", lambda f: f.get("fred", "LRUNTTTTILM156S")),
]
