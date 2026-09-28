"""Observed public series for the USA indicators that were still fixture_synth.

Every value here is a published observation or an arithmetic transform of one (a year-over-year
change of an official index, a month-on-month difference), fetched keyless from FRED's CSV endpoint
-- which republishes the Fed, BLS, BEA, Cleveland Fed and Atlanta Fed series used -- or from the
Fed's own H.4.1 release (FIMA repo, see h41_fima.py). Nothing is estimated: a series that cannot be
fetched leaves the previous card as it was.

What is deliberately not here: ISM PMIs, CDS and CME FedWatch are licensed or scraping-forbidden and
are dropped from the pack elsewhere (paid_only), not replaced with something that looks similar.
"""

from __future__ import annotations

import calendar
import csv
import io
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
USER_AGENT = "macro-monitor/1.0 (+https://github.com/sunbininfokim-yeon/global-trade-dashboard)"

Points = list[tuple[str, float]]     # (ISO date of the observation, value), ascending


def fetch_fred(series_id: str, *, timeout: int = 40, tries: int = 3) -> Points:
    """All observations of a FRED series (missing '.' entries skipped)."""
    url = FRED_CSV.format(sid=series_id)
    last: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8")
            return parse_fred_csv(text, series_id)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"FRED {series_id}: {last}")


def parse_fred_csv(text: str, series_id: str = "") -> Points:
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2 or len(rows[0]) < 2:
        raise ValueError(f"unexpected FRED csv for {series_id}: {text[:80]!r}")
    out: Points = []
    for row in rows[1:]:
        if len(row) < 2 or row[1] in ("", "."):
            continue
        out.append((row[0], float(row[1])))
    if not out:
        raise ValueError(f"FRED {series_id} has no observations")
    return out


# --------------------------------------------------------------------------
# Transforms (each returns a new series)
# --------------------------------------------------------------------------

def scale(points: Points, factor: float) -> Points:
    return [(d, v * factor) for d, v in points]


def diff(points: Points) -> Points:
    return [(points[i][0], points[i][1] - points[i - 1][1]) for i in range(1, len(points))]


def pct_change(points: Points, lag: int) -> Points:
    """Percent change against the observation `lag` places earlier (12 monthly, 4 quarterly, 1 for QoQ)."""
    return [(points[i][0], (points[i][1] / points[i - lag][1] - 1) * 100)
            for i in range(lag, len(points)) if points[i - lag][1]]


def vs_base(points: Points, base_date: str) -> Points:
    base = next((v for d, v in points if d == base_date), None)
    if not base:
        raise ValueError(f"no observation on the base date {base_date}")
    return [(d, (v / base - 1) * 100) for d, v in points if d >= base_date]


# --------------------------------------------------------------------------
# Presentation
# --------------------------------------------------------------------------

def month_end(iso: str) -> str:
    y, m = int(iso[:4]), int(iso[5:7])
    return f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"


def quarter_end(iso: str) -> str:
    y, m = int(iso[:4]), int(iso[5:7])
    qm = ((m - 1) // 3 + 1) * 3
    return f"{y:04d}-{qm:02d}-{calendar.monthrange(y, qm)[1]:02d}"


def quarter_label(iso: str) -> str:
    return f"{iso[:4]}Q{(int(iso[5:7]) - 1) // 3 + 1}"


_WINDOWS = {"monthly": (60, 120), "quarterly": (20, 40), "weekly": (261, 522)}
_DATE = {"monthly": month_end, "quarterly": quarter_end, "weekly": lambda d: d}


def history_block(points: Points, cadence: str) -> dict[str, Any]:
    dates = _DATE[cadence]
    out = {}
    for key, n in zip(("5y", "10y"), _WINDOWS[cadence]):
        tail = points[-n:]
        out[key] = {"dates": [dates(d) for d, _ in tail], "values": [round(v, 4) for _, v in tail]}
    return out


def _fmt_pct1(v: float) -> str:
    return f"{v:.1f}%"


def _fmt_k0(v: float) -> str:
    return f"{v:,.0f}K"


def _fmt_bn2(v: float) -> str:
    return f"${v:,.2f}B"


def _fmt_mn0(v: float) -> str:
    return f"${v:,.0f}M"


def _fmt_krw_tn1(v: float) -> str:
    return f"{v:,.1f}조원"


_FORMATS: dict[str, Callable[[float], str]] = {"pct1": _fmt_pct1, "k0": _fmt_k0, "bn2": _fmt_bn2, "mn0": _fmt_mn0,
                                               "krw_tn1": _fmt_krw_tn1}


@dataclass(frozen=True)
class Spec:
    id: str
    cadence: str                 # weekly | monthly | quarterly
    unit: str
    fmt: str
    note_ko: str
    source: str                  # short label shown in the drawer meta line
    source_urls: tuple[str, ...]
    refresh_tier: str
    label_ko: str | None = None
    chart_type: str | None = None
    asof_is_retrieval: bool = False     # a nowcast carries no publication date of its own: the day it was read


def _fred_urls(*ids: str) -> tuple[str, ...]:
    return tuple(f"https://fred.stlouisfed.org/series/{i}" for i in ids)


SPECS: dict[str, Spec] = {s.id: s for s in [
    Spec("fima_repo", "weekly", "mn_usd", "mn0",
         "연준 H.4.1 표1 '레포 → 외국 공적기관' 수요일 잔액(백만 달러)입니다. FIMA 레포 창구를 쓴 규모이며 급증하면 역외 달러 경색 징후입니다. 평소엔 0~수 백만 달러라 사실상 이용 없음입니다.",
         "fed:H.4.1", ("https://www.federalreserve.gov/releases/h41/",), "weekly", chart_type="line"),
    Spec("discount_window", "weekly", "bn_usd", "bn2",
         "연준 H.4.1 '대출 → 1차 신용(primary credit)' 수요일 잔액, 재할인창구의 대부분입니다. 급증하면 은행 자금 압박 징후입니다.",
         "fred:WLCFLPCL", _fred_urls("WLCFLPCL"), "weekly", chart_type="line"),
    Spec("m2_yoy", "monthly", "%", "pct1",
         "M2 통화량(계절조정)의 전년 같은 달 대비 증가율입니다. 연준 M2SL을 그대로 나눈 값입니다.",
         "fred:M2SL", _fred_urls("M2SL"), "monthly", chart_type="line"),
    Spec("m2_vs_2019", "monthly", "%", "pct1",
         "(현재 M2 − 2019-12 M2) / 2019-12 M2 × 100. 연준 M2SL(계절조정) 기준입니다.",
         "fred:M2SL", _fred_urls("M2SL"), "monthly", chart_type="line"),
    Spec("nfp", "monthly", "k", "k0",
         "비농업 취업자수의 전월 대비 증감(천 명, 계절조정). BLS 원계열(PAYEMS)의 차이이며 이후 개정될 수 있습니다. 실업률·청구건수와 교차 확인하세요.",
         "fred:PAYEMS", _fred_urls("PAYEMS"), "monthly", chart_type="line"),
    Spec("gdp_yoy", "quarterly", "%", "pct1",
         "실질 GDP(연쇄 2017 달러, 계절조정)의 전년 같은 분기 대비 증가율입니다. BEA 실질 GDP 수준(GDPC1)에서 계산했습니다.",
         "fred:GDPC1", _fred_urls("GDPC1"), "quarterly", chart_type="line"),
    Spec("gdp_qoq", "quarterly", "%", "pct1",
         "실질 GDP의 직전 분기 대비 증가율입니다(연율 환산 아님, 연율은 약 4배). BEA 실질 GDP 수준(GDPC1)에서 계산했습니다.",
         "fred:GDPC1", _fred_urls("GDPC1"), "quarterly", chart_type="line"),
    Spec("gdpnow", "quarterly", "%", "pct1",
         "애틀랜타 연은 GDPNow의 현재 분기 실질 GDP 성장률 추정(연율, %)입니다. 통계 발표가 나올 때마다 바뀌고, 지난 분기 값은 그 분기의 마지막 추정입니다. 공식 GDP가 아니며 gdp_qoq(비연율)와 척도가 다릅니다.",
         "fred:GDPNOW", _fred_urls("GDPNOW"), "daily", chart_type="line", asof_is_retrieval=True),
    Spec("trimmed_mean_cpi", "monthly", "%", "pct1",
         "클리블랜드 연은 절사평균 CPI(상·하위 16% 품목 제외)의 전년 대비 증가율입니다. 일시적 급등락 품목을 빼고 기조를 봅니다.",
         "fred:TRMMEANCPIM159SFRBCLE", _fred_urls("TRMMEANCPIM159SFRBCLE"), "monthly", chart_type="line",
         label_ko="Cleveland Fed 절사평균 CPI YoY"),
    Spec("export_price_yoy", "monthly", "%", "pct1",
         "BLS 수출물가지수(전 품목)의 전년 같은 달 대비 증가율입니다.",
         "fred:IQ", _fred_urls("IQ"), "monthly", chart_type="line"),
    Spec("import_price_yoy", "monthly", "%", "pct1",
         "BLS 수입물가지수(전 품목)의 전년 같은 달 대비 증가율입니다.",
         "fred:IR", _fred_urls("IR"), "monthly", chart_type="line"),
]}


def build_patch(spec: Spec, points: Points, *, retrieved_at: str, asof: str | None = None) -> dict[str, Any]:
    """The fields a real series puts on an indicator. Change-vs-1M/1Y percentages are cleared: a
    'relative change' of a growth rate or of a month-on-month difference is not a meaningful number."""
    if not points:
        raise ValueError(f"{spec.id}: no observations")
    last_date, last = points[-1]
    dates = _DATE[spec.cadence]
    ref = quarter_label(last_date) if spec.cadence == "quarterly" else (
        last_date[:7] if spec.cadence == "monthly" else last_date)
    display = _FORMATS[spec.fmt](last)
    if spec.asof_is_retrieval:
        # GDPNow's observation date is the start of the quarter it is about (and its period end is
        # in the future); what it is "as of" is the day it was read.
        asof = retrieved_at[:10]
    patch: dict[str, Any] = {
        "value": round(last, 4),
        "display": display,
        "display_chip": display,
        "asof": asof or dates(last_date),
        "observed_at": asof or dates(last_date),
        "reference_period": ref,
        "unit": spec.unit,
        "format": spec.fmt,
        "source": spec.source,
        "source_urls": list(spec.source_urls),
        "quality": "live",
        "data_status": "live",
        "history": history_block(points, spec.cadence),
        "change_1m_pct": None,
        "change_1y_pct": None,
        "note_ko": spec.note_ko,
        "refresh_tier": spec.refresh_tier,
        "retrieved_at": retrieved_at,
    }
    if spec.chart_type:
        patch["chart_type"] = spec.chart_type
    if spec.label_ko:
        patch["label_ko"] = spec.label_ko
    return patch


def series_for(spec_id: str, fred: Callable[[str], Points], fima_weeks: Points | None = None) -> Points:
    """The transformed observations behind one indicator."""
    if spec_id == "fima_repo":
        if not fima_weeks:
            raise ValueError("no FIMA repo history collected")
        return list(fima_weeks)                               # already $ millions
    if spec_id == "discount_window":
        return scale(fred("WLCFLPCL"), 0.001)
    if spec_id == "m2_yoy":
        return pct_change(fred("M2SL"), 12)
    if spec_id == "m2_vs_2019":
        return vs_base(fred("M2SL"), "2019-12-01")
    if spec_id == "nfp":
        return diff(fred("PAYEMS"))
    if spec_id == "gdp_yoy":
        return pct_change(fred("GDPC1"), 4)
    if spec_id == "gdp_qoq":
        return pct_change(fred("GDPC1"), 1)
    if spec_id == "gdpnow":
        return fred("GDPNOW")
    if spec_id == "trimmed_mean_cpi":
        return fred("TRMMEANCPIM159SFRBCLE")
    if spec_id == "export_price_yoy":
        return pct_change(fred("IQ"), 12)
    if spec_id == "import_price_yoy":
        return pct_change(fred("IR"), 12)
    raise KeyError(spec_id)


# --------------------------------------------------------------------------
# Applying to the pack
# --------------------------------------------------------------------------

LEGACY_SYNTHETIC = ("qra_coupon_bn", "qra_bill_bn")     # hidden duplicates of qra_issuance's own components
_CHIP_FIELDS = ("value", "display", "asof", "observed_at", "source", "data_status", "change_1m_pct", "change_1y_pct", "chart_type")


def _data_of(patch: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in patch.items() if k != "retrieved_at"}


def apply_patch(ind: dict[str, Any], patch: dict[str, Any]) -> bool:
    """Write the patch onto an indicator. `retrieved_at` only moves when something else changed, so
    an unchanged day is not a commit. Returns True when the indicator changed."""
    changed = any(ind.get(k) != v for k, v in _data_of(patch).items())
    if not changed:
        return False
    ind.update(patch)
    return True


def sync_chips(usa: dict[str, Any], by_id: dict[str, dict[str, Any]], touched: set[str]) -> None:
    """Chips and headlines are projections of indicators; carry over what the drawer and chip read."""
    for chips in (usa.get("categories") or {}).values():
        for chip in chips:
            src = by_id.get(chip.get("id"))
            if src and chip["id"] in touched:
                for k in _CHIP_FIELDS:
                    if k in src:
                        chip[k] = src.get(k)
                if src.get("label_ko"):
                    chip["label_ko"] = src["label_ko"]
                chip["note_ko"] = src.get("note_ko")
    for h in usa.get("headlines") or []:
        src = by_id.get(h.get("id"))
        if src and h["id"] in touched:
            h["display"] = src.get("display")
            h["data_status"] = src.get("data_status")
            if src.get("label_ko"):
                h["label_ko"] = src["label_ko"]


def remove_indicator(country: dict[str, Any], indicator_id: str) -> bool:
    """Drop a card outright -- for a fixture that turned out to have no free source at all (a rate
    or an amount both left demo forever is worse than one that says nothing), rather than renaming
    it into something else. Idempotent: a second call on an id that is already gone changes nothing."""
    indicators = country.get("indicators") or []
    before = len(indicators)
    country["indicators"] = [i for i in indicators if i.get("id") != indicator_id]
    changed = len(country["indicators"]) != before
    for cat, chips in list((country.get("categories") or {}).items()):
        kept = [c for c in chips if c.get("id") != indicator_id]
        if len(kept) != len(chips):
            country["categories"][cat] = kept
            changed = True
    headlines = country.get("headlines") or []
    kept_h = [h for h in headlines if h.get("id") != indicator_id]
    if len(kept_h) != len(headlines):
        country["headlines"] = kept_h
        changed = True
    return changed


def refresh_status_summary(country: dict[str, Any]) -> None:
    """The per-country badge counts (live / demo / ...) are read from the indicators; they went stale
    when cards were replaced by real series without touching them."""
    out: dict[str, int] = {}
    for ind in country.get("indicators") or []:
        status = str(ind.get("data_status") or "unknown")
        out[status] = out.get(status, 0) + 1
    country["data_status_summary"] = out


def apply_gdp_composite(by_id: dict[str, dict[str, Any]], retrieved_at: str) -> bool:
    """The 'gdp' chip is YoY | QoQ; rebuild it from the two real series it is made of."""
    gdp, yoy, qoq = by_id.get("gdp"), by_id.get("gdp_yoy"), by_id.get("gdp_qoq")
    if not (gdp and yoy and qoq and yoy.get("quality") == "live" and qoq.get("quality") == "live"):
        return False

    def mode(label: str, src: dict[str, Any]) -> dict[str, Any]:
        return {"label_ko": label, "id": src["id"], "value": src["value"], "display": src["display"],
                "unit": "%", "history": src["history"]}

    patch = {
        "value": yoy["value"],
        "display": f"{yoy['display']} | {qoq['display']}",
        "asof": yoy["asof"],
        "observed_at": yoy["observed_at"],
        "reference_period": yoy["reference_period"],
        "source": "fred:GDPC1",
        "source_urls": yoy["source_urls"],
        "quality": "live",
        "data_status": "live",
        "change_1m_pct": None,
        "change_1y_pct": None,
        "modes": {"yoy": mode("YoY", yoy), "qoq": {**mode("QoQ", qoq), "note_ko": "분기 대비 % (연율 환산 아님)"}},
        "retrieved_at": retrieved_at,
    }
    changed = any(gdp.get(k) != v for k, v in _data_of(patch).items())
    if changed:
        gdp.update(patch)
    return changed


def apply_all(usa: dict[str, Any], patches: dict[str, dict[str, Any]], *, retrieved_at: str) -> dict[str, Any]:
    """Apply indicator patches, drop the legacy synthetic duplicates, rebuild the GDP composite and
    resync chips. Returns {'changed': [...], 'removed': [...]}."""
    by_id = {i["id"]: i for i in usa["indicators"]}
    changed = [k for k, p in patches.items() if k in by_id and apply_patch(by_id[k], p)]
    if apply_gdp_composite(by_id, retrieved_at):
        changed.append("gdp")
    removed = []
    for legacy in LEGACY_SYNTHETIC:
        if legacy in by_id:
            usa["indicators"] = [i for i in usa["indicators"] if i["id"] != legacy]
            for cat in (usa.get("categories") or {}):
                usa["categories"][cat] = [c for c in usa["categories"][cat] if c.get("id") != legacy]
            removed.append(legacy)
    by_id = {i["id"]: i for i in usa["indicators"]}
    sync_chips(usa, by_id, set(changed))
    before = dict(usa.get("data_status_summary") or {})
    refresh_status_summary(usa)
    return {"changed": changed, "removed": removed, "summary_changed": before != usa["data_status_summary"]}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
