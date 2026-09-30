"""Kazakhstan: IMF data portal (CPI, reserves, broad money, goods trade) and the World Bank Pink Sheet.
Keyless.

Not here, and why: the National Bank's base rate, NFRK assets and KASE (no keyless data API mapped),
industrial production, CPC Blend and uranium prices (no free series), the 10-year bond, CDS.
"""

from __future__ import annotations

from . import us_public_series as ups
from .world_public_series import (IMF_BROAD_MONEY, IMF_CPI_YOY, IMF_RESERVES, IMF_URL, Card, card,
                                  imf_trade_balance)

CARDS: list[Card] = [
    card("cpi_yoy", "monthly", "%", "pct1", "CPI YoY",
         "소비자물가 전년 동월 대비입니다. IMF 데이터포털 CPI(카자흐 통계청 발표 기반, 몇 달 늦게 반영).", "imf:CPI", IMF_URL,
         lambda f: f.get("imf", "CPI", "KAZ", IMF_CPI_YOY)),
    card("m3_yoy", "monthly", "%", "pct1", "M3 전년비",
         "광의통화(IMF 기준, 계절조정) 전년 동월 대비입니다. IMF 통화금융통계.", "imf:MFS_DC:DCORP_L_BM", IMF_URL,
         lambda f: ups.pct_change(f.get("imf", "MFS_DC", "KAZ", IMF_BROAD_MONEY), 12)),
    card("m3_vs_2019", "monthly", "%", "pct1", "M3 vs 2019-12",
         "(현재 광의통화 − 2019-12) / 2019-12 × 100. IMF 통화금융통계.", "imf:MFS_DC:DCORP_L_BM", IMF_URL,
         lambda f: ups.vs_base(f.get("imf", "MFS_DC", "KAZ", IMF_BROAD_MONEY), "2019-12-01")),
    card("kz_fx_reserves", "monthly", "bn_usd", "bn0usd", "외환보유액",
         "국제준비자산(금 시가 포함, 월말, 십억 달러)입니다. IMF 국제유동성 통계. 국부펀드(NFRK)는 별도.", "imf:IL:TRGMV_REVS", IMF_URL,
         lambda f: ups.scale(f.get("imf", "IL", "KAZ", IMF_RESERVES), 1e-9), category="fx"),
    card("kz_trade_balance", "monthly", "bn_usd", "bn1usds", "무역수지",
         "상품 수출(FOB) − 수입(CIF), 월, 십억 달러입니다. IMF 상품교역 통계(원계열).", "imf:ITG", IMF_URL,
         lambda f: imf_trade_balance(f, "KAZ"), chart="bar", category="fx"),
    card("crude_oil", "monthly", "usd_bbl", "usd1", "Brent",
         "브렌트유(달러/배럴, 월평균)입니다. 세계은행 Pink Sheet. 카자흐 원유(CPC Blend)는 브렌트 대비 할인 거래.",
         "worldbank:pinksheet", "https://www.worldbank.org/en/research/commodity-markets",
         lambda f: f.get("pink")["Crude oil, Brent"]),
]
