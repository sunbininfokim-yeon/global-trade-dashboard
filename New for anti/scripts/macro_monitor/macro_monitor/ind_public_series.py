"""India: IMF data portal (CPI, reserves, broad money, goods trade) and FRED (OECD rates). Keyless.

Not here, and why: RBI DBIE and MOSPI have no keyless API reachable here for these series; LAF, CRR,
WPI, PMIs, vehicle sales, bank credit and FPI flows have no free series; CDS.
"""

from __future__ import annotations

from . import us_public_series as ups
from .world_public_series import (IMF_BROAD_MONEY, IMF_CPI_YOY, IMF_RESERVES, IMF_URL, Card, card,
                                  imf_trade_balance)

CARDS: list[Card] = [
    card("cpi_yoy", "monthly", "%", "pct1", "CPI YoY",
         "소비자물가(전국) 전년 동월 대비입니다. IMF 데이터포털 CPI(인도 통계부 발표 기반).", "imf:CPI", IMF_URL,
         lambda f: f.get("imf", "CPI", "IND", IMF_CPI_YOY)),
    card("rbi_repo", "monthly", "%", "pct2", "RBI Repo",
         "은행 간 콜금리 월평균입니다(OECD 집계, FRED IRSTCI01INM156N). RBI 레포금리를 따라 움직이며 레포금리 자체는 아닙니다.",
         "fred:IRSTCI01INM156N", "https://fred.stlouisfed.org/series/IRSTCI01INM156N", lambda f: f.get("fred", "IRSTCI01INM156N")),
    card("bond_10y", "monthly", "%", "pct2", "G-Sec 10년",
         "인도 국채 10년 수익률 월평균입니다(OECD 집계, FRED INDIRLTLT01STM).", "fred:INDIRLTLT01STM",
         "https://fred.stlouisfed.org/series/INDIRLTLT01STM", lambda f: f.get("fred", "INDIRLTLT01STM")),
    card("fx_reserves", "monthly", "bn_usd", "bn0usd", "외환보유액",
         "외환보유액(금 시가 포함, 월말, 십억 달러)입니다. IMF 국제유동성 통계.", "imf:IL:TRGMV_REVS", IMF_URL,
         lambda f: ups.scale(f.get("imf", "IL", "IND", IMF_RESERVES), 1e-9)),
    card("m3_yoy", "monthly", "%", "pct1", "M3 전년비",
         "광의통화(IMF 기준, 계절조정 -- 인도 M3에 해당) 전년 동월 대비입니다. IMF 통화금융통계.", "imf:MFS_DC:DCORP_L_BM", IMF_URL,
         lambda f: ups.pct_change(f.get("imf", "MFS_DC", "IND", IMF_BROAD_MONEY), 12)),
    card("m3_vs_2019", "monthly", "%", "pct1", "M3 vs 2019-12",
         "(현재 광의통화 − 2019-12) / 2019-12 × 100. IMF 통화금융통계(계절조정).", "imf:MFS_DC:DCORP_L_BM", IMF_URL,
         lambda f: ups.vs_base(f.get("imf", "MFS_DC", "IND", IMF_BROAD_MONEY), "2019-12-01")),
    card("in_trade_balance", "monthly", "bn_usd", "bn1usds", "무역수지",
         "상품 수출(FOB) − 수입(CIF), 월, 십억 달러입니다. IMF 상품교역 통계(원계열).", "imf:ITG", IMF_URL,
         lambda f: imf_trade_balance(f, "IND"), chart="bar", category="fx"),
]
