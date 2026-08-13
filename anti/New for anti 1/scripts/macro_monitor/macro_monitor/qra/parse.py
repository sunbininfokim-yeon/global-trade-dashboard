"""Parse Treasury QRA HTML: net borrowing estimates + policy stance + auction sizes."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

# Month–Month YYYY with optional spaces around dash (en/em/hyphen)
_PERIOD = r"(?P<period>[A-Za-z]+\s*[–—-]\s*[A-Za-z]+\s+\d{4})"

# Estimate: borrow OR pay down; billion OR trillion; optional footnote markers
_BORROW_SENT = re.compile(
    rf"During the {_PERIOD} quarter,?\s+"
    r"Treasury expects to (?P<dir>borrow|pay down)\s+"
    r"\$(?P<borrow>[\d,\.]+)\s*(?P<bunit>billion|trillion)\s+"
    r"in\s+privately-?\s*held net marketable debt,?\s+"
    r"assuming an end-of-(?P<cash_month>[A-Za-z]+) cash balance of\s+"
    r"\$(?P<cash>[\d,\.]+)\s*(?P<cunit>billion|trillion)"
    r"(?:\s*\[[^\]]+\])?",
    re.I,
)

_BORROWED_SENT = re.compile(
    rf"During the {_PERIOD} quarter,?\s+"
    r"Treasury borrowed\s+"
    r"\$(?P<borrow>[\d,\.]+)\s*(?P<bunit>billion|trillion)\s+"
    r"in\s+privately-?\s*held net marketable debt"
    r"(?:\s+and ended the quarter with a cash balance of\s+"
    r"\$(?P<cash>[\d,\.]+)\s*(?P<cunit>billion|trillion))?"
    r"(?:\s*\[[^\]]+\])?",
    re.I,
)

_VS_PRIOR = re.compile(
    r"borrowing estimate is \$(?P<vs>[\d,\.]+)\s*(?P<unit>billion|trillion)\s+(?P<dir>higher|lower)",
    re.I,
)

# Refunding auction sizes in policy statement
_AUCTION_SIZE = re.compile(
    r"A\s+(?P<tenor>\d+-year)\s+(?P<kind>note|bond|TIPS|FRN)[^\.]{0,80}?"
    r"(?:in the amount of|of)\s+\$(?P<amt>[\d,\.]+)\s*billion",
    re.I,
)

_BILL_STANCE = [
    (
        "increase",
        re.compile(
            r"(?:increase|increasing|expand|enlarge).{0,40}(?:bill|bills).{0,40}auction sizes?"
            r"|bill.{0,40}auction sizes?.{0,40}(?:increase|increasing|expand)"
            r"|further increases? to (?:benchmark )?bills?",
            re.I,
        ),
    ),
    (
        "maintain",
        re.compile(
            r"maintain(?:ing)? (?:current )?auction sizes? in (?:benchmark )?bills?"
            r"|maintain(?:ing)? current (?:bill )?auction sizes?",
            re.I,
        ),
    ),
    (
        "reduce",
        re.compile(
            r"(?:reduc(?:e|ing|tions?)|decreas).{0,40}(?:bill|bills).{0,40}auction"
            r"|(?:bill|bills).{0,40}auction.{0,40}(?:reduc|decreas)",
            re.I,
        ),
    ),
]

# Prefer forward-looking increases/changes over near-term "maintain" when both appear.
_COUPON_STANCE = [
    (
        "increase_bias",
        re.compile(
            r"potential (?:future )?increases? to nominal coupon"
            r"|evaluate potential future increases? to nominal coupon",
            re.I,
        ),
    ),
    (
        "change_bias",
        re.compile(
            r"potential (?:future )?changes? to nominal coupon"
            r"|evaluate potential future changes? to nominal coupon",
            re.I,
        ),
    ),
    (
        "maintain",
        re.compile(
            r"maintain(?:ing)? nominal coupon and FRN auction sizes?"
            r"|anticipates maintaining nominal coupon",
            re.I,
        ),
    ),
]


def _money(s: str, unit: str) -> float:
    v = float(s.replace(",", ""))
    u = (unit or "billion").lower()
    if u.startswith("trillion"):
        return v * 1000.0
    return v


def _norm_period(p: str) -> str:
    p = re.sub(r"\s*[–—-]\s*", "–", p)
    return re.sub(r"\s+", " ", p).strip()


def html_to_text(html: str) -> str:
    t = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    t = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", t)
    t = re.sub(r"(?is)<[^>]+>", " ", t)
    t = (
        t.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&ndash;", "–")
        .replace("&#8211;", "–")
        .replace("&mdash;", "—")
    )
    return re.sub(r"\s+", " ", t).strip()


@dataclass
class QuarterFact:
    period: str
    kind: str  # estimate | actual
    net_borrowing_bn: float
    end_cash_balance_bn: Optional[float] = None
    vs_prior_bn: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AuctionSize:
    tenor: str
    instrument: str
    amount_bn: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DocParse:
    url: str
    kind: str
    year: Optional[int]
    quarter: Optional[int]
    title: str
    text_chars: int
    quarters: List[QuarterFact] = field(default_factory=list)
    auctions: List[AuctionSize] = field(default_factory=list)
    bill_stance: Optional[str] = None
    coupon_stance: Optional[str] = None
    stance_snippets: List[str] = field(default_factory=list)
    raw_matches: List[str] = field(default_factory=list)
    parse_ok: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _title_from_html(html: str) -> str:
    m = re.search(r"<title>([^<]+)</title>", html, re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def parse_financing_estimates(
    html: str, *, url: str = "", year: Optional[int] = None, quarter: Optional[int] = None
) -> DocParse:
    plain = html_to_text(html)
    title = _title_from_html(html)
    result = DocParse(
        url=url,
        kind="financing_estimates",
        year=year,
        quarter=quarter,
        title=title,
        text_chars=len(plain),
    )

    for m in _BORROW_SENT.finditer(plain):
        gd = m.groupdict()
        amt = _money(gd["borrow"], gd["bunit"])
        if (gd.get("dir") or "").lower() == "pay down":
            amt = -amt
        cash = _money(gd["cash"], gd["cunit"])
        result.quarters.append(
            QuarterFact(
                period=_norm_period(gd["period"]),
                kind="estimate",
                net_borrowing_bn=amt,
                end_cash_balance_bn=cash,
            )
        )
        result.raw_matches.append(m.group(0)[:280])

    for m in _BORROWED_SENT.finditer(plain):
        gd = m.groupdict()
        period = _norm_period(gd["period"])
        if any(q.period == period and q.kind == "estimate" for q in result.quarters):
            continue
        cash = None
        if gd.get("cash"):
            cash = _money(gd["cash"], gd.get("cunit") or "billion")
        result.quarters.append(
            QuarterFact(
                period=period,
                kind="actual",
                net_borrowing_bn=_money(gd["borrow"], gd["bunit"]),
                end_cash_balance_bn=cash,
            )
        )
        result.raw_matches.append(m.group(0)[:280])

    # Attach first vs-prior figure to first estimate lacking one
    for m in _VS_PRIOR.finditer(plain):
        vs = _money(m.group("vs"), m.group("unit"))
        if m.group("dir").lower() == "lower":
            vs = -vs
        for q in result.quarters:
            if q.kind == "estimate" and q.vs_prior_bn is None:
                q.vs_prior_bn = vs
                break

    result.parse_ok = bool(result.quarters)
    return result


def parse_policy_statement(
    html: str, *, url: str = "", year: Optional[int] = None, quarter: Optional[int] = None
) -> DocParse:
    plain = html_to_text(html)
    title = _title_from_html(html)
    result = DocParse(
        url=url,
        kind="official_remarks",
        year=year,
        quarter=quarter,
        title=title,
        text_chars=len(plain),
    )

    for m in _AUCTION_SIZE.finditer(plain):
        result.auctions.append(
            AuctionSize(
                tenor=m.group("tenor").lower(),
                instrument=m.group("kind").lower(),
                amount_bn=float(m.group("amt").replace(",", "")),
            )
        )
        result.raw_matches.append(m.group(0)[:200])

    for name, rx in _BILL_STANCE:
        m = rx.search(plain)
        if m:
            result.bill_stance = name
            result.stance_snippets.append(m.group(0)[:200])
            break

    for name, rx in _COUPON_STANCE:
        m = rx.search(plain)
        if m:
            result.coupon_stance = name
            result.stance_snippets.append(m.group(0)[:200])
            break

    result.parse_ok = bool(result.auctions or result.bill_stance or result.coupon_stance)
    return result


def parse_doc(
    html: str, *, kind: str, url: str = "", year: Optional[int] = None, quarter: Optional[int] = None
) -> DocParse:
    if kind == "financing_estimates":
        return parse_financing_estimates(html, url=url, year=year, quarter=quarter)
    return parse_policy_statement(html, url=url, year=year, quarter=quarter)
