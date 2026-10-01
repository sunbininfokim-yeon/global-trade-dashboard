"""China: IMF data portal (CPI, reserves, goods trade) and CFETS (Loan Prime Rate). Keyless.

Not here, and why: the NBS site answers 403 from here and PBOC has no keyless data API reachable here,
so M1/M2/TSF, PPI, PMIs, property data, youth unemployment, RRR and OMO stay without a source; the
10-year CGB (ChinaBond needs a session), CDS and the dollar high-yield spreads have no free series.
"""

from __future__ import annotations

from . import us_public_series as ups
from .world_public_series import imf_current_account, IMF_CPI_YOY, IMF_RESERVES, IMF_URL, Card, card, imf_trade_balance, monthly_last

_CFETS = "https://www.chinamoney.com.cn/english/bmklpr/"


def _cfets(f, name: str):
    """CFETS month-end series from the cache (refreshed once per run, see cn_cfets.py)."""
    from datetime import date
    from . import cn_cfets
    if ("cfets",) not in f._cache:
        cache = cn_cfets.load_cache()
        if cn_cfets.refresh(cache, date.today()):
            cn_cfets.save_cache(cache)
        f._cache[("cfets",)] = cache
    return cn_cfets.points(f._cache[("cfets",)], name)


def _us_cn_spread(f):
    from .world_public_series import monthly_mean, spread_bp
    cn, _ = _cfets(f, "cgb10")
    return spread_bp(monthly_last(f.get("fred", "DGS10"))[0], cn)

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
    card("current_account", "quarterly", "bn_usd", "bn1usds", "경상수지",
         "경상수지(분기, 십억 달러)입니다. IMF 국제수지 통계(BPM6).", "imf:BOP:CAB", IMF_URL,
         imf_current_account("CHN")),    card("bond_10y", "monthly", "%", "pct2", "중국 10년 국채",
         "중국 국채 10년 만기수익률(중앙결산공사 수익률곡선, 각 달 마지막 영업일)입니다. CFETS 게시.", "cfets:CYCC000:10Y", _CFETS,
         lambda f: _cfets(f, "cgb10")),
    card("us_chn_10y_spread", "monthly", "bp", "bp0", "미−중 10Y 스프레드",
         "미 국채 10년(FRED DGS10) − 중국 국채 10년(CFETS), 각 달 말 기준(bp)입니다. 양수 확대 = 위안 약세 압력.",
         "fred:DGS10-cfets", _CFETS, _us_cn_spread),
    card("pboc_fixing", "monthly", "FX", "fx4", "PBOC 고시환율",
         "인민은행 USD/CNY 기준환율(중간가), 각 달 마지막 고시일입니다. CFETS.", "cfets:ccpr:USD/CNY", _CFETS,
         lambda f: _cfets(f, "fixing")),
    card("cfets_rmb", "monthly", "index", "num1", "CFETS 위안지수",
         "CFETS 위안화 통화바스켓 지수(주간 고시, 각 달 마지막 값)입니다. 오르면 위안 강세.", "cfets:rmbidx", _CFETS,
         lambda f: _cfets(f, "rmbidx")),
]
