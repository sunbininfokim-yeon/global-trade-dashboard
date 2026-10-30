"""Indonesia: Statistics Indonesia's WebAPI (BPS, needs a key), FRED and Yahoo.

  cpi_yoy             CPI YoY, national (2022=100)             BPS var 2249, region 151 'INDONESIA'
  gdp_qoq, gdp_yoy    real GDP (2010 prices), by expenditure    BPS var 1956, row 800, quarters 31-34
  unemployment        open unemployment rate (Feb/Aug survey)   BPS var 543, region 9999
  bi_rate             BI Rate                                   BPS var 379 (Bank Indonesia's, as BPS carries it)
  m2_yoy, m2_vs_2019  money supply M2                           BPS var 123, row 8
  export_id           goods exports, US$ bn, monthly            BPS var 196
  trade_balance       goods trade balance, US$ bn, monthly      BPS var 498
  fx_reserves         reserves excluding gold, US$ bn           FRED TRESEGIDM052N (IMF IFS)
  usdidr, jci         USD/IDR, Jakarta Composite                Yahoo (live_catalog.py)

The key. BPS issues a personal key and the repository is public, so it is never written anywhere: it is
read from the BPS_API_KEY environment variable (a GitHub Actions secret), or locally from
~/.config/bps.env. It rides in the request path, so no request URL is ever logged or put in an error
message, and the cards link to BPS's public pages, not to API URLs. Without a key the run leaves the
existing cards as they are.

Attribution. Using the BPS API comes with showing "이 서비스는 BPS API를 사용합니다" on the Indonesia panel;
it is in config/source_notices_v1.json (IDN).

Indonesia was not in the fixture pack; ensure_country() adds it with only these observed cards -- there
is no synthetic card to replace.

Not here, and why: Bank Indonesia's own site (bi.go.id) does not answer from here, so the 10-year
yield, core inflation and BI's balance sheet have no source; FRED's OECD 10-year for Indonesia would not
download either. PMI and CDS have no free series.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

from . import kr_public_series as krs
from . import us_public_series as ups
from .us_public_series import Points, Spec

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
BPS_DATA = "https://webapi.bps.go.id/v1/api/list/model/data/lang/eng/domain/0000/var/{var}/th/{th}/key/{key}/"
HISTORY_FROM = 2015
KEY_FILE = Path.home() / ".config" / "bps.env"

# (var, region row, period codes -> month). BPS keys its cells as region+var+turvar+year+period.
MONTHS = {m: m for m in range(1, 13)}
QUARTERS = {31: 1, 32: 4, 33: 7, 34: 10}
SURVEYS = {189: 2, 190: 8}                     # the labour force survey runs in February and August
BPS_SERIES: dict[str, tuple[int, int, dict[int, int]]] = {
    "cpi_yoy": (2249, 151, MONTHS),
    "gdp": (1956, 800, QUARTERS),
    "unemployment": (543, 9999, SURVEYS),
    "bi_rate": (379, 1, MONTHS),
    "m2": (123, 8, MONTHS),
    "export_id": (196, 9999, MONTHS),
    "trade_balance": (498, 9999, MONTHS),
}

ups._FORMATS.update({
    "pct1": lambda v: f"{v:.1f}%",
    "pct2": lambda v: f"{v:.2f}%",
    "bn1usd": lambda v: f"${v:,.1f}B",
    "bn1usds": lambda v: f"+${v:,.1f}B" if v >= 0 else f"-${-v:,.1f}B",
    "bn0usd": lambda v: f"${v:,.0f}B",
})


def api_key() -> str | None:
    key = os.environ.get("BPS_API_KEY", "").strip()
    if not key and KEY_FILE.exists():
        for line in KEY_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("BPS_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("'\"")
    return key or None


def _get_json(var: int, th: str, key: str, *, tries: int = 3) -> dict[str, Any]:
    url = BPS_DATA.format(var=var, th=th, key=key)
    last = ""
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            last = type(exc).__name__
        time.sleep(2 * (attempt + 1))
    # Never the URL: the key is in its path.
    raise RuntimeError(f"BPS var {var} th {th}: {last}")


def year_chunks(first: int, last: int, size: int = 3) -> list[str]:
    """BPS answers at most three years per request; its year codes are year - 1900."""
    out = []
    y = first
    while y <= last:
        z = min(y + size - 1, last)
        out.append(f"{y - 1900}:{z - 1900}")
        y = z + 1
    return out


def parse_bps(doc: dict[str, Any], var: int, region: int, periods: dict[int, int]) -> Points:
    if doc.get("status") != "OK" or doc.get("data-availability") != "available":
        raise ValueError(f"BPS var {var}: {doc.get('message') or doc.get('data-availability')}")
    cells = doc.get("datacontent") or {}
    turvar = str((doc.get("turvar") or [{"val": "0"}])[0]["val"])
    out: Points = []
    for year in doc.get("tahun") or []:
        for code, month in periods.items():
            v = cells.get(f"{region}{var}{turvar}{year['val']}{code}")
            if v is not None and v != "":
                out.append((f"{year['label']}-{month:02d}-01", float(v)))
    return out


def fetch_bps(name: str, key: str, today: date | None = None,
              get: Callable[[int, str, str], dict[str, Any]] = _get_json) -> Points:
    var, region, periods = BPS_SERIES[name]
    last_year = (today or date.today()).year
    pts: dict[str, float] = {}
    for th in year_chunks(HISTORY_FROM, last_year):
        doc = get(var, th, key)
        if doc.get("data-availability") == "list-not-available":
            continue                                         # e.g. the running year before its first release
        pts.update(parse_bps(doc, var, region, periods))
        time.sleep(0.3)
    if not pts:
        raise ValueError(f"BPS var {var}: no observations")
    return sorted(pts.items())


_BPS = "https://www.bps.go.id/en/statistics-table?subject={s}"


def _s(id_: str, cadence: str, unit: str, fmt: str, label: str, note: str, source: str, url: str,
       chart: str = "line") -> Spec:
    return Spec(id_, cadence, unit, fmt, note, source, (url,), cadence, label_ko=label, chart_type=chart)


SPECS: dict[str, Spec] = {s.id: s for s in [
    _s("cpi_yoy", "monthly", "%", "pct1", "CPI YoY",
       "소비자물가 전년 동월 대비(전국, 2022=100, 150개 도시)입니다. 인도네시아 통계청(BPS) WebAPI.",
       "bps:2249", "https://www.bps.go.id/en/subject/3/inflation.html"),
    _s("gdp_qoq", "quarterly", "%", "pct1", "실질GDP QoQ",
       "실질GDP(2010년 가격, 지출 측) 전기 대비 %입니다. BPS는 계절조정 계열을 내지 않아 원계열끼리 나눈 값이라 분기마다 계절성이 크게 섞입니다(1분기 음수가 흔함). 추세는 YoY로 보세요. BPS WebAPI.",
       "bps:1956", "https://www.bps.go.id/en/subject/11/gross-domestic-product--expenditure-.html"),
    _s("gdp_yoy", "quarterly", "%", "pct1", "실질GDP YoY",
       "실질GDP(2010년 가격, 지출 측) 전년 동기 대비입니다. BPS 공식 성장률과 같은 정의. BPS WebAPI.",
       "bps:1956", "https://www.bps.go.id/en/subject/11/gross-domestic-product--expenditure-.html"),
    _s("unemployment", "quarterly", "%", "pct1", "실업률",
       "개방실업률(15세 이상)입니다. 노동력조사가 2월·8월 두 번이라 반년 간격 점만 있습니다(빈 분기는 비워 둡니다). BPS WebAPI.",
       "bps:543", "https://www.bps.go.id/en/subject/6/employment.html"),
    _s("bi_rate", "monthly", "%", "pct2", "BI Rate",
       "인도네시아 중앙은행(BI) 기준금리, 월말 기준입니다. BI 사이트는 여기서 접근이 안 돼 BPS가 게재한 표를 씁니다(BPS WebAPI).",
       "bps:379", "https://www.bps.go.id/en/subject/13/finance.html"),
    _s("m2_yoy", "monthly", "%", "pct1", "M2 전년비",
       "통화량 M2 전년 동월 대비입니다(BI 통계를 BPS가 게재). BPS WebAPI.",
       "bps:123", "https://www.bps.go.id/en/subject/13/finance.html"),
    _s("m2_vs_2019", "monthly", "%", "pct1", "M2 vs 2019-12",
       "(현재 M2 − 2019-12 M2) / 2019-12 M2 × 100. BPS WebAPI.",
       "bps:123", "https://www.bps.go.id/en/subject/13/finance.html"),
    _s("export_id", "monthly", "bn_usd", "bn1usd", "수출",
       "상품 수출액(월, 십억 달러, 원계열)입니다. 카드를 열면 월별 막대 아래 전년 동월 대비 선이 함께 나옵니다. 석탄·팜유·니켈 가공품 비중이 큽니다. BPS WebAPI.",
       "bps:196", "https://www.bps.go.id/en/subject/8/exports.html", chart="bar"),
    _s("trade_balance", "monthly", "bn_usd", "bn1usds", "무역수지",
       "상품 무역수지(월, 십억 달러)입니다. BPS WebAPI.",
       "bps:498", "https://www.bps.go.id/en/subject/8/exports.html", chart="bar"),
    _s("fx_reserves", "monthly", "bn_usd", "bn0usd", "외환보유액",
       "외환보유액(금 제외, 월말, 십억 달러)입니다. IMF 국제금융통계, FRED TRESEGIDM052N. BI 발표 총액(금 포함)보다 약간 작습니다.",
       "fred:TRESEGIDM052N", "https://fred.stlouisfed.org/series/TRESEGIDM052N"),
]}
YOY_LINE = {"export_id"}

# Cards a new Indonesia gets, in tab order: (id, category). Yahoo cards are filled by live_overlay.
LAYOUT: list[tuple[str, str]] = [
    ("m2_yoy", "liquidity"), ("m2_vs_2019", "liquidity"),
    ("bi_rate", "rates"), ("sovereign_ratings", "rates"),
    ("usdidr", "fx"), ("fx_reserves", "fx"), ("trade_balance", "fx"),
    ("jci", "equity"),
    ("gdp", "growth"), ("export_id", "growth"), ("unemployment", "growth"),
    ("cpi_yoy", "inflation"),
]
GDP_UI = {"dual": ["yoy", "qoq"], "default": "yoy", "dual_ids": {"yoy": "gdp_yoy", "qoq": "gdp_qoq"}}
HEADLINES = ["gdp_yoy", "cpi_yoy", "bi_rate", "usdidr", "jci", "sovereign_ratings"]
YAHOO_CARDS = {
    "usdidr": ("fx", "USD/IDR", "FX", "number0", "환율(루피아/달러)입니다. Yahoo 시세, 월말 값."),
    "jci": ("equity", "JCI(자카르타 종합)", "index", "number0", "자카르타 종합지수(IDX Composite) 월말 종가입니다. Yahoo 시세."),
}
NEWS = {
    "cpi_yoy": "Indonesia inflation BPS consumer prices",
    "gdp": "Indonesia GDP growth BPS",
    "bi_rate": "Bank Indonesia BI rate decision",
    "usdidr": "rupiah dollar Bank Indonesia",
    "jci": "Jakarta Composite Index IDX stocks",
    "export_id": "Indonesia exports coal palm oil nickel",
}

COUNTRY_META = {
    "iso3": "IDN", "iso2": "ID", "name_ko": "인도네시아", "name_en": "Indonesia",
    "aliases": ["Indonesia", "Republic of Indonesia"], "currency": "IDR",
    "coords": {"lat": -2.5, "lon": 118.0}, "kit": "id_macro_v1", "benchmark": False, "featured": True,
    "active_categories": ["liquidity", "rates", "fx", "equity", "growth", "inflation"],
    "purpose_ko": "원자재 수출(석탄·팜유·니켈) · 내수 소비 · BI 루피아 방어. 루피아와 BI Rate, 수출이 핵심.",
    "limitations": {"title_ko": "지표 분석·추론의 한계 (인도네시아)", "items": [
        {"id": "gdp_qoq_seasonal", "title_ko": "분기 GDP 계절성",
         "body_ko": "BPS는 계절조정 GDP를 발표하지 않는다. 전기 대비는 원계열끼리 나눈 값이라 1분기 마이너스·2분기 플러스가 반복된다. 경기 판단은 전년 동기 대비로 한다."},
        {"id": "commodity_export", "title_ko": "수출 ↔ 원자재 가격",
         "body_ko": "수출액은 석탄·팜유·니켈 가격에 크게 좌우된다. 수출 증가를 물량·경쟁력 개선으로 바로 읽으면 오류다."},
        {"id": "bi_fx_defense", "title_ko": "BI Rate ↔ 환율 방어",
         "body_ko": "BI는 물가만큼 루피아 안정을 보고 금리를 움직인다. 금리 동결·인상을 내수 과열 신호로 읽으면 안 된다."},
    ]},
}


@dataclass
class Sources:
    key: str | None = field(default_factory=api_key)
    bps: Callable[[str, str], Points] | None = None
    fred: Callable[[str], Points] = ups.fetch_fred
    _cache: dict[str, Points] = field(default_factory=dict)

    def series(self, name: str) -> Points:
        if name not in self._cache:
            if self.bps is not None:
                self._cache[name] = self.bps(name, self.key or "")
            else:
                if not self.key:
                    raise RuntimeError("no BPS_API_KEY")
                self._cache[name] = fetch_bps(name, self.key)
        return self._cache[name]


def series_for(spec_id: str, src: Sources) -> Points:
    if spec_id in ("cpi_yoy", "unemployment", "bi_rate"):
        return src.series(spec_id)
    if spec_id in ("gdp_qoq", "gdp_yoy"):
        return ups.pct_change(src.series("gdp"), 1 if spec_id == "gdp_qoq" else 4)
    if spec_id == "m2_yoy":
        return ups.pct_change(src.series("m2"), 12)
    if spec_id == "m2_vs_2019":
        return ups.vs_base(src.series("m2"), "2019-12-01")
    if spec_id in ("export_id", "trade_balance"):
        return ups.scale(src.series(spec_id), 1e-3)                 # US$ million -> billion
    if spec_id == "fx_reserves":
        return ups.scale(src.fred("TRESEGIDM052N"), 1e-3)
    raise KeyError(spec_id)


def build_patch(spec_id: str, points: Points, *, retrieved_at: str) -> dict[str, Any]:
    from .za_public_series import with_gaps
    spec = SPECS[spec_id]
    patch = ups.build_patch(spec, with_gaps(points, 3 if spec.cadence == "quarterly" else 1), retrieved_at=retrieved_at)
    if spec_id == "unemployment":
        survey = points[-1][0]                                     # "2026-02-01", the survey month, not a quarter
        patch["reference_period"] = survey[:7]
        patch["asof"] = patch["observed_at"] = ups.month_end(survey)
    if spec_id in YOY_LINE:
        patch["yoy_line"] = True
    return patch


def _empty_history() -> dict[str, dict[str, list]]:
    return {"5y": {"dates": [], "values": []}, "10y": {"dates": [], "values": []}}


def ensure_country(pack: dict[str, Any]) -> dict[str, Any]:
    """Indonesia's country block, created on first use with only the cards listed in LAYOUT. Cards are
    added empty and filled by apply_all / the Yahoo overlay; one that never gets data is removed again
    (prune_empty), so the panel never shows a card without an observation."""
    idn = next((c for c in pack["countries"] if c.get("iso3") == "IDN"), None)
    if idn is None:
        idn = {**json.loads(json.dumps(COUNTRY_META)), "asof": None, "headlines": [], "categories": {},
               "indicators": [], "data_status_summary": {}}
        pack["countries"].append(idn)
    for card_id, (cat, label, unit, fmt, note) in YAHOO_CARDS.items():
        if not any(i["id"] == card_id for i in idn["indicators"]):
            idn["indicators"].append({"id": card_id, "category": cat, "label_ko": label, "unit": unit, "format": fmt,
                                      "history": _empty_history(), "data_status": "pending", "quality": "pending",
                                      "chart_type": "line", "note_ko": note, "value": None, "display": None,
                                      "refresh_tier": "market_daily", "news_query": NEWS.get(card_id)})
    if not any(i["id"] == "sovereign_ratings" for i in idn["indicators"]):
        # filled by live_overlay from Wikipedia's S&P / Moody's / Fitch table (ratings_wiki.WIKI_NAMES)
        idn["indicators"].append({"id": "sovereign_ratings", "category": "rates", "label_ko": "국가신용등급",
                                  "unit": "rating", "format": "rating", "history": _empty_history(),
                                  "data_status": "live_latest", "quality": "pending", "chart_type": "status",
                                  "value": None, "display": None, "refresh_tier": "event"})
    if not any(i["id"] == "gdp" for i in idn["indicators"]):
        idn["indicators"].append({"id": "gdp", "category": "growth", "label_ko": "실질GDP", "unit": "%", "format": "pct1",
                                  "history": {}, "data_status": "pending", "quality": "pending", "chart_type": "line",
                                  "refresh_tier": "quarterly", "note_ko": "칩: YoY | QoQ (QoQ는 비연율·원계열)",
                                  "news_query": NEWS["gdp"], "derived": True, "ui": GDP_UI})
    for card_id, cat in LAYOUT:
        chips = idn["categories"].setdefault(cat, [])
        if not any(c["id"] == card_id for c in chips):
            spec = SPECS.get(card_id)
            label = spec.label_ko if spec else (YAHOO_CARDS[card_id][1] if card_id in YAHOO_CARDS
                                                else "국가신용등급" if card_id == "sovereign_ratings" else "실질GDP")
            chip = {"id": card_id, "label_ko": label, "unit": spec.unit if spec else ("%" if card_id == "gdp" else None)}
            if card_id == "gdp":
                chip["ui"] = GDP_UI
            chips.append(chip)
    index = pack.setdefault("countries_index", [])
    if isinstance(index, list) and not any(c.get("iso3") == "IDN" for c in index):
        index.append({k: COUNTRY_META[k] for k in ("iso3", "iso2", "name_ko", "name_en", "aliases", "coords", "kit",
                                                   "benchmark", "featured", "active_categories")})
    return idn


def sync_headlines(idn: dict[str, Any]) -> None:
    by_id = {i["id"]: i for i in idn["indicators"]}
    heads = []
    for hid in HEADLINES:
        ind = by_id.get(hid)
        if ind and ind.get("display"):
            heads.append({"id": hid, "category": ind["category"], "label_ko": ind["label_ko"],
                          "display": ind.get("display_chip") or ind["display"], "data_status": ind.get("data_status")})
    idn["headlines"] = heads
    dated = [i.get("asof") for i in idn["indicators"] if i.get("asof") and i.get("data_status") == "live"]
    idn["asof"] = max(dated) if dated else None


def prune_empty(idn: dict[str, Any]) -> list[str]:
    """Cards that still have no observation are taken out (and their chips), never shown empty."""
    gone = [i["id"] for i in idn["indicators"] if i.get("value") is None and i["id"] != "gdp"]
    if not any(i["id"] == "gdp" and i.get("modes") for i in idn["indicators"]):
        gone.append("gdp")
    idn["indicators"] = [i for i in idn["indicators"] if i["id"] not in gone]
    for cat, chips in idn["categories"].items():
        idn["categories"][cat] = [c for c in chips if c["id"] not in gone]
    return gone


def apply_all(idn: dict[str, Any], patches: dict[str, dict[str, Any]], *, retrieved_at: str) -> dict[str, Any]:
    from . import jp_public_series as jps
    for spec_id in patches:
        cat = next((c for i, c in LAYOUT if i == spec_id), "growth")
        ups.ensure_card(idn, spec_id, cat, SPECS[spec_id])
        ind = next(i for i in idn["indicators"] if i["id"] == spec_id)
        ind.setdefault("news_query", NEWS.get(spec_id))
    # gdp_yoy / gdp_qoq are the composite chip's two modes, not chips of their own
    for cat, chips in idn["categories"].items():
        idn["categories"][cat] = [c for c in chips if c["id"] not in ("gdp_yoy", "gdp_qoq")]
    by_id = {i["id"]: i for i in idn["indicators"]}
    changed = [k for k, p in patches.items() if ups.apply_patch(by_id[k], p)]
    if jps.apply_gdp_composite(by_id, retrieved_at, source="bps:1956"):
        changed.append("gdp")
    ups.sync_chips(idn, by_id, set(changed))
    units = krs.sync_chip_units(idn, by_id, set(patches))
    before = (dict(idn.get("data_status_summary") or {}), list(idn.get("headlines") or []))
    sync_headlines(idn)
    ups.refresh_status_summary(idn)
    return {"changed": changed,
            "summary_changed": units or before != (idn["data_status_summary"], idn["headlines"])}
