"""Vietnam: IMF data portal (CPI, reserves, goods trade). Keyless.

Not here, and why: GSO does not resolve and the SBV site rejects requests from here, so money supply,
policy rates, credit quota, FDI, industrial production (IMF's stops in 2025-03) and deposit/lending
rates have no source; PMI (licensed), CDS.
"""

from __future__ import annotations

from . import us_public_series as ups
from .world_public_series import IMF_CPI_YOY, IMF_RESERVES, IMF_URL, Card, card, imf_trade_balance

CARDS: list[Card] = [
    card("cpi_yoy", "monthly", "%", "pct1", "CPI YoY",
         "소비자물가 전년 동월 대비입니다. IMF 데이터포털 CPI(베트남 통계청 발표 기반).", "imf:CPI", IMF_URL,
         lambda f: f.get("imf", "CPI", "VNM", IMF_CPI_YOY)),
    card("fx_reserves", "monthly", "bn_usd", "bn0usd", "외환보유액",
         "외환보유액(금 시가 포함, 월말, 십억 달러)입니다. IMF 국제유동성 통계.", "imf:IL:TRGMV_REVS", IMF_URL,
         lambda f: ups.scale(f.get("imf", "IL", "VNM", IMF_RESERVES), 1e-9)),
    card("vn_trade_balance", "monthly", "bn_usd", "bn1usds", "무역수지",
         "상품 수출(FOB) − 수입(CIF), 월, 십억 달러입니다. IMF 상품교역 통계(원계열).", "imf:ITG", IMF_URL,
         lambda f: imf_trade_balance(f, "VNM"), chart="bar"),
]
