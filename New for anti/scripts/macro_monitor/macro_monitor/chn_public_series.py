"""China: IMF data portal (CPI, reserves, goods trade) and CFETS (Loan Prime Rate). Keyless.

Not here, and why: the NBS site answers 403 from here and PBOC has no keyless data API reachable here,
so M1/M2/TSF, PPI, PMIs, property data, youth unemployment, RRR and OMO stay without a source; the
10-year CGB (ChinaBond needs a session), CDS and the dollar high-yield spreads have no free series.
"""

from __future__ import annotations

from . import us_public_series as ups
from .world_public_series import IMF_CPI_YOY, IMF_RESERVES, IMF_URL, Card, card, imf_trade_balance, monthly_last

_CFETS = "https://www.chinamoney.com.cn/english/bmklpr/"

CARDS: list[Card] = [
    card("cpi_yoy", "monthly", "%", "pct1", "CPI YoY",
         "소비자물가 전년 동월 대비입니다. IMF 데이터포털 CPI(국가통계국 발표 기반).", "imf:CPI", IMF_URL,
         lambda f: f.get("imf", "CPI", "CHN", IMF_CPI_YOY)),
    card("lpr_1y", "monthly", "%", "pct2", "1년 LPR",
         "대출우대금리(LPR) 1년, 매월 20일 고시입니다. 중국외환교역센터(CFETS).", "cfets:LPR1Y", _CFETS,
         lambda f: monthly_last(f.get("lpr", "1Y"))),
    card("lpr_5y", "monthly", "%", "pct2", "5년 LPR",
         "대출우대금리(LPR) 5년 초과 -- 주택담보대출 기준, 매월 20일 고시입니다. CFETS.", "cfets:LPR5Y", _CFETS,
         lambda f: monthly_last(f.get("lpr", "5Y"))),
    card("fx_reserves", "monthly", "bn_usd", "bn0usd", "외환보유액",
         "외환보유액(금 시가 포함, 월말, 십억 달러)입니다. IMF 국제유동성 통계.", "imf:IL:TRGMV_REVS", IMF_URL,
         lambda f: ups.scale(f.get("imf", "IL", "CHN", IMF_RESERVES), 1e-9)),
    card("cn_trade_balance", "monthly", "bn_usd", "bn1usds", "무역수지",
         "상품 수출(FOB) − 수입(CIF), 월, 십억 달러입니다. IMF 상품교역 통계(해관총서 기반, 원계열).", "imf:ITG", IMF_URL,
         lambda f: imf_trade_balance(f, "CHN"), chart="bar", category="fx"),
]
