"""Australia: the ABS Data API (data.api.abs.gov.au, SDMX), FRED and the World Bank Pink Sheet. Keyless.

  cpi_yoy              CPI, all groups, YoY (monthly CPI)           ABS CPI 3.10001.10.50.M
  monthly_cpi          CPI, all groups s.a., MoM                    ABS CPI 2.999901.20.50.M
  trimmed_mean_cpi     trimmed mean, YoY                            ABS CPI 3.999902.20.50.M
  unemployment         unemployment rate, s.a.                      ABS LF M13.3.1599.20.AUS.M
  employment_change    employed persons, s.a., monthly change       ABS LF M3.3.1599.20.AUS.M
  gdp_qoq, gdp_yoy     real GDP, chain volume, s.a.                 ABS ANA_AGG M1.GPM.20.AUS.Q
  gdp_per_capita_yoy   real GDP per capita, s.a., YoY               ABS ANA_AGG M1.GPM_PCA.20.AUS.Q
  current_account      current account balance, s.a., quarterly     ABS BOP 1.100.20.Q
  au_trade_balance     balance on goods, s.a., monthly              ABS ITGS M1.170.20.AUS.M
  building_approvals   dwelling units approved (original)           ABS BA_GCCSA 1.1.9.TOT.100.10.AUS.M
  rba_cash_rate        interbank overnight (cash) rate, monthly     FRED IRSTCI01AUM156N (OECD)
  bond_10y             10-year government bond yield, monthly avg   FRED IRLTLT01AUM156N (OECD)
  us_au_10y_spread     US 10y minus AU 10y, monthly averages        FRED IRLTLT01USM156N, IRLTLT01AUM156N
  iron_ore             iron ore CFR China, $/dmt, monthly average   World Bank Pink Sheet
  au_coal              Newcastle thermal coal, $/t, monthly average World Bank Pink Sheet (was 'coking_coal':
                       the Pink Sheet has no coking-coal price, so the card now says what it shows)

Terms: ABS material is CC BY 4.0 (attribution). The source line is on the panel.

Not here, and why: the RBA's own tables (cash rate target, M3, balance sheet, household debt ratio,
3-year ACGB) -- rba.gov.au answers 403 from here; FRED's OECD M3 for Australia stops in 2023-11.
CoreLogic's index is proprietary; CDS has no free series.
"""

from __future__ import annotations

import csv
import io
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from . import kr_public_series as krs
from . import us_public_series as ups
from .us_public_series import Points, Spec

UA = "macro-monitor/1.0 (+https://github.com/sunbininfokim-yeon/global-trade-dashboard)"
ABS_DATA = "https://data.api.abs.gov.au/rest/data/ABS,{flow}/{key}?startPeriod={start}&format=csvfile"
ABS_PAGE = "https://www.abs.gov.au/statistics/{path}"
RENAMES = {"coking_coal": "au_coal"}

ups._FORMATS.update({
    "pct1": lambda v: f"{v:.1f}%",
    "pct2": lambda v: f"{v:.2f}%",
    "bp0": lambda v: f"{v:+.0f}bp" if v else "0bp",
    "k0s": lambda v: f"{v:+,.0f}K",
    "k1u": lambda v: f"{v:,.1f}K",
    "bn1aud": lambda v: f"A${v:,.1f}B" if v >= 0 else f"-A${-v:,.1f}B",
    "usd0": lambda v: f"${v:,.0f}",
    "num1": lambda v: f"{v:,.1f}",
})

# spec id -> (dataflow,version, key, start)
ABS_SERIES: dict[str, tuple[str, str, str]] = {
    "cpi_yoy": ("CPI,2.0.0", "3.10001.10.50.M", "2015-01"),
    "monthly_cpi": ("CPI,2.0.0", "2.999901.20.50.M", "2015-01"),
    "trimmed_mean_cpi": ("CPI,2.0.0", "3.999902.20.50.M", "2015-01"),
    "unemployment": ("LF,1.0.0", "M13.3.1599.20.AUS.M", "2015-01"),
    "employment_change": ("LF,1.0.0", "M3.3.1599.20.AUS.M", "2015-01"),
    "gdp": ("ANA_AGG,1.0.0", "M1.GPM.20.AUS.Q", "2014-Q1"),
    "gdp_per_capita": ("ANA_AGG,1.0.0", "M1.GPM_PCA.20.AUS.Q", "2014-Q1"),
    "current_account": ("BOP,1.0.0", "1.100.20.Q", "2014-Q1"),
    "au_trade_balance": ("ITGS,1.2.0", "M1.170.20.AUS.M", "2015-01"),
    "building_approvals": ("BA_GCCSA,1.0.0", "1.1.9.TOT.100.10.AUS.M", "2015-01"),
}


def _get(url: str, *, timeout: int = 120, tries: int = 3) -> str:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8-sig")
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"{url[:80]}: {last}")


def period_key(p: str) -> str | None:
    if len(p) == 7 and p[4] == "-" and p[5] == "Q":
        return f"{p[:4]}-{(int(p[6]) - 1) * 3 + 1:02d}-01"
    if len(p) == 7 and p[4] == "-":
        return p + "-01"
    return None


def parse_abs_csv(text: str) -> Points:
    """TIME_PERIOD/OBS_VALUE of an ABS 'csvfile' response (one series), scaled by nothing."""
    if text.startswith("NoRecordsFound") or "TIME_PERIOD" not in text[:2000]:
        raise ValueError(f"no ABS records: {text[:60]!r}")
    out: Points = []
    for row in csv.DictReader(io.StringIO(text)):
        d = period_key(row.get("TIME_PERIOD", ""))
        if d and row.get("OBS_VALUE") not in (None, ""):
            out.append((d, float(row["OBS_VALUE"])))
    if not out:
        raise ValueError("ABS series has no observations")
    return sorted(out)


def fetch_abs(name: str) -> Points:
    flow, key, start = ABS_SERIES[name]
    return parse_abs_csv(_get(ABS_DATA.format(flow=flow, key=key, start=start)))


def spread_bp(a: Points, b: Points) -> Points:
    """a − b in basis points, for the months both have."""
    b_by = dict(b)
    return [(d, (v - b_by[d]) * 100) for d, v in a if d in b_by]


_WB = "https://www.worldbank.org/en/research/commodity-markets"


def _s(id_: str, cadence: str, unit: str, fmt: str, label: str, note: str, source: str, url: str,
       chart: str = "line") -> Spec:
    return Spec(id_, cadence, unit, fmt, note, source, (url,), cadence, label_ko=label, chart_type=chart)


_CPI = ABS_PAGE.format(path="economy/price-indexes-and-inflation/consumer-price-index-australia/latest-release")
_LF = ABS_PAGE.format(path="labour/employment-and-unemployment/labour-force-australia/latest-release")
_NA = ABS_PAGE.format(path="economy/national-accounts/australian-national-accounts-national-income-expenditure-and-product/latest-release")

SPECS: dict[str, Spec] = {s.id: s for s in [
    _s("cpi_yoy", "monthly", "%", "pct1", "CPI YoY",
       "소비자물가(전 품목) 전년 동월 대비입니다. 호주 통계청(ABS)은 2025년 말부터 월간 CPI를 본 지표로 발표합니다. ABS Data API CPI.",
       "abs:CPI", _CPI),
    _s("monthly_cpi", "monthly", "%", "pct1", "월간 CPI MoM(SA)",
       "소비자물가(전 품목, 계절조정) 전월 대비 %입니다. ABS Data API CPI.",
       "abs:CPI", _CPI),
    _s("trimmed_mean_cpi", "monthly", "%", "pct1", "Trimmed Mean CPI",
       "절사평균 CPI(계절조정) 전년 동월 대비입니다. RBA가 가장 중시하는 기조 물가, 상하위 15% 절사. ABS Data API CPI.",
       "abs:CPI", _CPI),
    _s("unemployment", "monthly", "%", "pct1", "실업률",
       "실업률(15세 이상, 계절조정)입니다. ABS 노동력 조사. 해석 앵커 ≈4.0–5.0%.",
       "abs:LF", _LF),
    _s("employment_change", "monthly", "k_jobs", "k0s", "고용 증감",
       "취업자 수(계절조정) 전월 대비 증감(천 명)입니다. 이민 유입과 일자리 흡수의 괴리를 봅니다. ABS 노동력 조사.",
       "abs:LF", _LF, chart="bar"),
    _s("gdp_qoq", "quarterly", "%", "pct1", "실질GDP QoQ",
       "실질GDP(연쇄가격, 계절조정) 전기 대비 %입니다(연율 아님). ABS 국민계정 ANA_AGG.",
       "abs:ANA_AGG", _NA),
    _s("gdp_yoy", "quarterly", "%", "pct1", "실질GDP YoY",
       "실질GDP(연쇄가격, 계절조정) 전년 동기 대비입니다. ABS 국민계정 ANA_AGG.",
       "abs:ANA_AGG", _NA),
    _s("gdp_per_capita_yoy", "quarterly", "%", "pct1", "1인당 실질GDP YoY",
       "1인당 실질GDP(계절조정) 전년 동기 대비입니다. 총량 GDP와 갈리면 이민 주도 성장입니다. ABS 국민계정 ANA_AGG.",
       "abs:ANA_AGG", _NA),
    _s("current_account", "quarterly", "bn_aud", "bn1aud", "경상수지",
       "경상수지(분기, 계절조정, 십억 호주달러)입니다. ABS 국제수지.",
       "abs:BOP", ABS_PAGE.format(path="economy/international-trade/balance-payments-and-international-investment-position-australia/latest-release")),
    _s("au_trade_balance", "monthly", "bn_aud", "bn1aud", "무역수지(상품)",
       "상품 무역수지(월, 계절조정, 십억 호주달러)입니다. ABS 국제상품교역 ITGS.",
       "abs:ITGS", ABS_PAGE.format(path="economy/international-trade/international-trade-goods/latest-release"), chart="bar"),
    _s("building_approvals", "monthly", "k_units", "k1u", "건축승인",
       "주거용 건축승인 호수(천 호, 원계열 -- 계절조정 아님)입니다. 주택 공급·건설 투자의 선행 지표. ABS 건축승인.",
       "abs:BA_GCCSA", ABS_PAGE.format(path="industry/building-and-construction/building-approvals-australia/latest-release"), chart="bar"),
    _s("rba_cash_rate", "monthly", "%", "pct2", "RBA Cash Rate",
       "은행 간 익일물(cash) 금리 월평균입니다(OECD 집계, FRED IRSTCI01AUM156N). RBA 현금금리 목표를 따라 움직입니다. RBA 사이트는 여기서 접근이 막혀 원표를 쓰지 못했습니다.",
       "fred:IRSTCI01AUM156N", "https://fred.stlouisfed.org/series/IRSTCI01AUM156N"),
    _s("bond_10y", "monthly", "%", "pct2", "ACGB 10년",
       "호주 국채 10년 수익률 월평균입니다(OECD 집계, FRED IRLTLT01AUM156N).",
       "fred:IRLTLT01AUM156N", "https://fred.stlouisfed.org/series/IRLTLT01AUM156N"),
    _s("us_au_10y_spread", "monthly", "bp", "bp0", "미−호 10Y 스프레드",
       "미 국채 10년 − 호주 국채 10년 월평균(bp, OECD 집계, FRED)입니다. 음수면 호주 금리가 더 높습니다. AUD 방향의 참고 지표.",
       "fred:IRLTLT01USM156N-IRLTLT01AUM156N", "https://fred.stlouisfed.org/series/IRLTLT01AUM156N"),
    _s("iron_ore", "monthly", "usd_t", "usd0", "철광석",
       "철광석(중국 CFR 현물, 달러/건조톤, 월평균)입니다. 세계은행 Pink Sheet. 호주 수출 1위 품목, 중국 철강·부동산과 연동.",
       "worldbank:pinksheet", _WB),
    _s("au_coal", "monthly", "usd_t", "usd0", "호주 연료탄",
       "호주 뉴캐슬 연료탄(달러/톤, 월평균)입니다. 세계은행 Pink Sheet 'Coal, Australian'. 원료탄(제철용) 가격은 무료 공개 계열이 없어 연료탄으로 대신합니다.",
       "worldbank:pinksheet", _WB),
]}


@dataclass
class Sources:
    abs_: Callable[[str], Points] = fetch_abs
    fred: Callable[[str], Points] = ups.fetch_fred
    pink: Callable[[], dict[str, Points]] | None = None
    _cache: dict[str, Any] = field(default_factory=dict)

    def get(self, kind: str, name: str) -> Any:
        key = f"{kind}:{name}"
        if key not in self._cache:
            if kind == "abs":
                self._cache[key] = self.abs_(name)
            elif kind == "fred":
                self._cache[key] = self.fred(name)
            else:
                if self.pink is None:
                    from .za_public_series import fetch_pink_sheet
                    self.pink = fetch_pink_sheet
                self._cache[key] = self.pink()
        return self._cache[key]


def series_for(spec_id: str, src: Sources) -> Points:
    if spec_id in ("cpi_yoy", "monthly_cpi", "trimmed_mean_cpi", "unemployment"):
        return src.get("abs", spec_id)
    if spec_id == "employment_change":
        return ups.diff(src.get("abs", "employment_change"))
    if spec_id in ("gdp_qoq", "gdp_yoy"):
        return ups.pct_change(src.get("abs", "gdp"), 1 if spec_id == "gdp_qoq" else 4)
    if spec_id == "gdp_per_capita_yoy":
        return ups.pct_change(src.get("abs", "gdp_per_capita"), 4)
    if spec_id in ("current_account", "au_trade_balance"):
        return ups.scale(src.get("abs", spec_id), 1e-3)                  # A$ million -> billion
    if spec_id == "building_approvals":
        return ups.scale(src.get("abs", spec_id), 1e-3)                  # units -> thousands
    if spec_id == "rba_cash_rate":
        return src.get("fred", "IRSTCI01AUM156N")
    if spec_id == "bond_10y":
        return src.get("fred", "IRLTLT01AUM156N")
    if spec_id == "us_au_10y_spread":
        return spread_bp(src.get("fred", "IRLTLT01USM156N"), src.get("fred", "IRLTLT01AUM156N"))
    if spec_id in ("iron_ore", "au_coal"):
        return src.get("pink", "")["Iron ore, cfr spot" if spec_id == "iron_ore" else "Coal, Australian"]
    raise KeyError(spec_id)


def build_patch(spec_id: str, points: Points, *, retrieved_at: str) -> dict[str, Any]:
    from .za_public_series import with_gaps
    spec = SPECS[spec_id]
    return ups.build_patch(spec, with_gaps(points, 3 if spec.cadence == "quarterly" else 1), retrieved_at=retrieved_at)


def apply_all(aus: dict[str, Any], patches: dict[str, dict[str, Any]], *, retrieved_at: str) -> dict[str, Any]:
    from . import jp_public_series as jps
    for old, new in RENAMES.items():
        if new in patches:
            krs.rename_indicator(aus, old, new, {})
    by_id = {i["id"]: i for i in aus["indicators"]}
    changed = [k for k, p in patches.items() if k in by_id and ups.apply_patch(by_id[k], p)]
    for k in changed:
        by_id[k].pop("analog_ko", None)
    if jps.apply_gdp_composite(by_id, retrieved_at, source="abs:ANA_AGG"):
        changed.append("gdp")
    ups.sync_chips(aus, by_id, set(changed))
    units = krs.sync_chip_units(aus, by_id, {k for k in patches if k in by_id})
    before = dict(aus.get("data_status_summary") or {})
    ups.refresh_status_summary(aus)
    return {"changed": changed, "summary_changed": units or before != aus["data_status_summary"]}
