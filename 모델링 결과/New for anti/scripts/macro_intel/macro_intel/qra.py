"""Parse U.S. Treasury Marketable Borrowing / QRA HTML (and optional PDF text)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


# e.g. "expects to borrow $739 billion in privately-held net marketable debt,
# assuming an end-of-September cash balance of $950 billion"
_BORROW_SENT = re.compile(
    r"During the (?P<period>[A-Za-z]+–[A-Za-z]+ \d{4}|[A-Za-z]+-[A-Za-z]+ \d{4}) quarter,?\s+"
    r"Treasury expects to borrow \$(?P<borrow>[\d,\.]+)\s*billion in privately-held net marketable debt,?\s+"
    r"assuming an end-of-(?P<cash_month>[A-Za-z]+) cash balance of \$(?P<cash>[\d,\.]+)\s*billion\."
    r"(?:\s+The borrowing estimate is \$(?P<vs>[\d,\.]+)\s*billion (?P<vs_dir>higher|lower) than[^\.]+\.)?",
    re.I,
)

# Past quarter realization
_BORROWED_SENT = re.compile(
    r"During the (?P<period>[A-Za-z]+–[A-Za-z]+ \d{4}|[A-Za-z]+-[A-Za-z]+ \d{4}) quarter,?\s+"
    r"Treasury borrowed \$(?P<borrow>[\d,\.]+)\s*billion in privately-held net marketable debt"
    r"(?: and ended the quarter with a cash balance of \$(?P<cash>[\d,\.]+)\s*billion)?\.",
    re.I,
)

_VS_PRIOR = re.compile(
    r"borrowing estimate is \$(?P<vs>[\d,\.]+)\s*billion (?P<dir>higher|lower)",
    re.I,
)

_PDF_HREF = re.compile(r'href="([^"]+\.pdf[^"]*)"', re.I)


def _bn(s: str) -> float:
    return float(s.replace(",", ""))


@dataclass
class QraQuarter:
    period: str
    kind: str  # estimate | actual
    net_borrowing_bn: float
    end_cash_balance_bn: Optional[float] = None
    vs_prior_bn: Optional[float] = None  # positive = higher than prior announce


@dataclass
class QraParse:
    title: str
    url: str
    text_chars: int
    quarters: List[QraQuarter] = field(default_factory=list)
    pdf_urls: List[str] = field(default_factory=list)
    signals: List[str] = field(default_factory=list)
    raw_matches: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


def is_qra_document(title: str, text: str, patterns: Dict[str, Any]) -> bool:
    blob = f"{title}\n{text[:4000]}"
    for t in patterns.get("title_any", []):
        if t.lower() in blob.lower():
            return True
    return False


def parse_qra_html(
    html_text: str,
    *,
    url: str,
    title: str = "",
    base_for_pdf: str = "https://home.treasury.gov",
) -> QraParse:
    from .httputil import absolutize, html_to_text

    plain = html_to_text(html_text)
    title = title or ""
    result = QraParse(title=title, url=url, text_chars=len(plain))

    for href in _PDF_HREF.findall(html_text):
        if "Sources-Uses" in href or "Marketable" in href or "Refunding" in href or "QRA" in href.upper():
            result.pdf_urls.append(absolutize(base_for_pdf, href))
        elif href.endswith(".pdf") and "system/files" in href:
            # keep treasury system PDFs on the page
            full = absolutize(base_for_pdf, href)
            if full not in result.pdf_urls:
                result.pdf_urls.append(full)

    for m in _BORROW_SENT.finditer(plain):
        gd = m.groupdict()
        vs = None
        if gd.get("vs"):
            vs = _bn(gd["vs"])
            if gd.get("vs_dir", "").lower() == "lower":
                vs = -vs
        q = QraQuarter(
            period=gd["period"].replace("-", "–"),
            kind="estimate",
            net_borrowing_bn=_bn(gd["borrow"]),
            end_cash_balance_bn=_bn(gd["cash"]) if gd.get("cash") else None,
            vs_prior_bn=vs,
        )
        result.quarters.append(q)
        result.raw_matches.append(m.group(0)[:240])

    for m in _BORROWED_SENT.finditer(plain):
        gd = m.groupdict()
        # skip if already have estimate for same period
        period = gd["period"].replace("-", "–")
        if any(q.period == period and q.kind == "estimate" for q in result.quarters):
            continue
        result.quarters.append(
            QraQuarter(
                period=period,
                kind="actual",
                net_borrowing_bn=_bn(gd["borrow"]),
                end_cash_balance_bn=_bn(gd["cash"]) if gd.get("cash") else None,
            )
        )
        result.raw_matches.append(m.group(0)[:240])

    # If structured sentences missed vs_prior, try free-standing phrases near period
    if result.quarters and all(q.vs_prior_bn is None for q in result.quarters if q.kind == "estimate"):
        for m in _VS_PRIOR.finditer(plain):
            vs = _bn(m.group("vs"))
            if m.group("dir").lower() == "lower":
                vs = -vs
            for q in result.quarters:
                if q.kind == "estimate" and q.vs_prior_bn is None:
                    q.vs_prior_bn = vs
                    break

    # Signals
    for q in result.quarters:
        if q.kind != "estimate":
            continue
        if q.vs_prior_bn is not None:
            if q.vs_prior_bn >= 25:
                result.signals.append("qra_net_borrowing_up")
            elif q.vs_prior_bn <= -25:
                result.signals.append("qra_net_borrowing_down")
        if q.end_cash_balance_bn is not None:
            if q.end_cash_balance_bn >= 900:
                result.signals.append("tga_cash_high")
            elif q.end_cash_balance_bn <= 500:
                result.signals.append("tga_cash_low")

    # dedupe signals keep order
    seen = set()
    uniq = []
    for s in result.signals:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    result.signals = uniq
    return result


def qra_to_ticker_item(parsed: QraParse) -> Dict[str, Any]:
    """Commodity-ticker-compatible item for the red strip."""
    est = [q for q in parsed.quarters if q.kind == "estimate"]
    if est:
        parts = []
        for q in est[:2]:
            bit = f"{q.period} 민간보유 순발행 추정 ${q.net_borrowing_bn:g}B"
            if q.end_cash_balance_bn is not None:
                bit += f" (기말 현금 ${q.end_cash_balance_bn:g}B)"
            if q.vs_prior_bn is not None:
                arrow = "▲" if q.vs_prior_bn > 0 else "▼"
                bit += f" 직전대비 {arrow}${abs(q.vs_prior_bn):g}B"
            parts.append(bit)
        ko = " | ".join(parts)
        ko = f"[QRA] {ko}"
    else:
        ko = f"[QRA] {parsed.title or 'Marketable Borrowing Estimates'}"

    return {
        "id": f"qra-{abs(hash(parsed.url)) % (10**12)}",
        "published_at": None,
        "source": {
            "id": "us_treasury",
            "name": "U.S. Treasury",
            "region": "west",
            "slant": None,
        },
        "url": parsed.url,
        "category": "liquidity_official",
        "commodities": [],
        "title": {
            "original": parsed.title or "Treasury Marketable Borrowing Estimates",
            "original_lang": "en",
            "ko": ko,
        },
        "summary": (parsed.raw_matches[0] if parsed.raw_matches else "")[:280],
        "scores": {
            "commodity": 0,
            "diplomacy": 0,
            "region_weight": 1.0,
            "freshness": 1.0,
            "final": 9.5,
        },
        "rank_reasons": ["event:qra"] + parsed.signals,
        "translation_status": "ok",
        "event_type": "qra",
    }
