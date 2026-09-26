"""RSS / Atom / list-page fetching for official commodity report publishers.

Deliberately a separate copy of the parsing that `official_reports/fetch.py`
does rather than an import of it. That pipeline reads macro and finance feeds
where the item body is a press-release blurb; this one keeps the body -- the
summary is the product here, not a scoring input -- so it reads
`content:encoded`, prefers the longest available text, and carries the
per-source commodity/country priors that tagging needs. Sharing the module
would mean one of the two pipelines constantly bending the other's parser.
"""

from __future__ import annotations

import email.utils
import hashlib
import re
import ssl
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

_TAG_RE = re.compile(r"<[^>]+>", re.S)
_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.I | re.S)
_WS_RE = re.compile(r"\s+")

# Summaries are quoted, not republished: a headline plus a few sentences is
# the fair-use shape the ticker already uses, and the card links out for the
# rest. 600 chars is roughly the first two paragraphs of a USDA release.
SUMMARY_CHARS = 600


@dataclass
class RawReport:
    """One publication as the feed described it, before any tagging."""

    source_id: str
    agency: str
    agency_ko: str
    url: str
    title: str
    summary: str
    published_at: Optional[str]
    lang: str = "en"
    weight: float = 1.0
    # Priors from the source catalog, used only where the text itself is silent.
    default_country: Optional[str] = None
    commodity_hint: List[str] = field(default_factory=list)
    scope_hint: str = "country"


def strip_html(doc: str) -> str:
    doc = _SCRIPT_RE.sub(" ", doc)
    doc = _TAG_RE.sub(" ", doc)
    return _WS_RE.sub(" ", unescape(doc)).strip()


def fetch_text(url: str, *, user_agent: str, timeout: float = 22.0) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, "
            "text/xml, text/html, */*",
            "Accept-Language": "en,pt;q=0.8,es;q=0.8,fr;q=0.6",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
        raw = resp.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def clip(text: str, limit: int = SUMMARY_CHARS) -> str:
    """Trim to `limit` on a word boundary, marking that there is more.

    Cutting mid-word reads as a broken feed rather than an excerpt, and the
    card gives no other signal that the agency wrote more than this.
    """
    text = text.strip()
    if len(text) <= limit:
        return text
    head = text[:limit]
    cut = head.rfind(" ")
    # No space in 600 chars means a CJK body, where every position is a word
    # boundary anyway.
    return (head[:cut] if cut > limit * 0.6 else head).rstrip(" ,;:.-") + "…"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def parse_date(raw: str) -> Optional[str]:
    if not raw:
        return None
    raw = raw.strip()
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        pass
    try:
        dt = email.utils.parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError):
        return None


def _raw_from(source: Dict[str, Any], **kw: Any) -> RawReport:
    return RawReport(
        source_id=source["id"],
        agency=source.get("agency", source["id"]),
        agency_ko=source.get("agency_ko", source.get("agency", source["id"])),
        lang=source.get("lang", "en"),
        weight=float(source.get("weight", 1.0)),
        default_country=source.get("default_country") or None,
        commodity_hint=list(source.get("commodity_hint") or []),
        scope_hint=source.get("scope_hint", "country"),
        **kw,
    )


def parse_feed(body: str, source: Dict[str, Any], max_items: int = 40) -> List[RawReport]:
    """RSS 2.0, RDF and Atom, whichever the publisher happens to serve."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []
    root_l = _local(root.tag).lower()
    if root_l in {"rss", "rdf"}:
        channel = next((c for c in list(root) if _local(c.tag) == "channel"), root)
        entries = [c for c in list(channel) if _local(c.tag) == "item"]
        # RDF (RSS 1.0) hangs <item> off the root, not off <channel>.
        if not entries:
            entries = [c for c in list(root) if _local(c.tag) == "item"]
    elif root_l == "feed":
        entries = [c for c in list(root) if _local(c.tag) == "entry"]
    else:
        return []

    items: List[RawReport] = []
    for el in entries[:max_items]:
        title = link = pub = ""
        bodies: List[str] = []
        for child in list(el):
            name = _local(child.tag)
            text = "".join(child.itertext()).strip()
            if name == "title":
                title = text
            elif name in {"description", "summary", "encoded", "content"}:
                # Keep every candidate: a feed that carries both a one-line
                # <description> and a full <content:encoded> should give the
                # card the longer one, and which element that is varies by
                # publisher.
                if text:
                    bodies.append(text)
            elif name == "link":
                link = child.attrib.get("href") or text or link
            elif name in {"pubDate", "published", "updated", "date"} and not pub:
                pub = text
        title = strip_html(title)
        summary = strip_html(max(bodies, key=len) if bodies else "")
        if not title or not link:
            continue
        # Feeds that repeat the headline as the body add nothing to the card.
        if summary.lower().startswith(title.lower()):
            summary = summary[len(title):].strip(" -–—:·")
        # RSS 2.0 technically requires <link> to be an absolute URL, but not
        # every publisher's feed generator honors that -- EIA's press feed
        # emits "/pressroom/releases/press589.php" with no scheme or host.
        # Left as-is, that string is a relative path on *this* site, not
        # theirs, and the card's "원문으로 이동" link 404s on our own domain.
        # The feed's own URL is the base every publisher's relative link is
        # actually relative to, since it lives on the same site as the pages
        # it points at.
        absolute_url = urljoin(source.get("url", ""), link.strip())
        items.append(
            _raw_from(
                source,
                title=title,
                url=absolute_url,
                summary=clip(summary),
                published_at=parse_date(pub),
            )
        )
    return items


def parse_html_list(body: str, source: Dict[str, Any]) -> List[RawReport]:
    """Link harvest for publishers with no feed (WASDE, OPEC press room…).

    No summary: a list page carries headlines and hrefs, and guessing a body
    out of the surrounding markup produced navigation chrome more often than
    prose. The card renders headline-only rows for these, which is exactly
    what the source actually published.
    """
    cfg = source.get("html") or {}
    base = cfg.get("base") or source.get("url") or ""
    href_re = cfg.get("item_href_re") or r"[^\"']+"
    max_items = int(cfg.get("max_items") or 20)
    pattern = re.compile(rf"href=[\"']({href_re})[\"'][^>]*>(.{{0,200}}?)</a>", re.I | re.S)

    items: List[RawReport] = []
    seen = set()
    for href, inner in pattern.findall(body):
        full = urljoin(base, href)
        key = full.split("?", 1)[0].rstrip("/").lower()
        if key in seen:
            continue
        title = strip_html(inner)
        if len(title) < 12:
            # Icon-only or "read more" links: fall back to the slug, which for
            # these publishers is a readable title.
            title = re.sub(r"[-_]+", " ", full.rsplit("/", 1)[-1].split(".")[0]).strip()
        if len(title) < 12:
            continue
        seen.add(key)
        items.append(
            _raw_from(source, title=title, url=full, summary="", published_at=None)
        )
        if len(items) >= max_items:
            break
    return items


_GAIN_CARD_SPLIT_RE = re.compile(r"(?=<time\s+datetime=[\"'])", re.I)
_GAIN_DATETIME_RE = re.compile(r"<time\s+datetime=[\"']([^\"']+)[\"']", re.I)
_GAIN_LINK_RE = re.compile(r'<a\s+href=["\']([^"\']+)["\'][^>]*class=["\'][^"\']*c-card__url[^"\']*["\']', re.I)
_GAIN_TITLE_RE = re.compile(r'c-card__title[^>]*>(.*?)</h3>', re.I | re.S)
_GAIN_SUMMARY_RE = re.compile(r'c-card__content[^>]*>(.*?)</div>', re.I | re.S)


def parse_fas_gain_cards(body: str, source: Dict[str, Any], max_items: int = 40) -> List[RawReport]:
    """USDA FAS GAIN attaché reports (fas.usda.gov/data/search, report_type:10251).

    Moved off gain.fas.usda.gov in 2026; the replacement is a Drupal 10
    Views+Facets listing that server-renders each result as a `.c-card`
    block -- date, title, link and a real summary paragraph are all present
    in the raw HTML, so this is a scrape rather than an API client. Cards
    nest divs too deeply for one balanced-tag regex to bound reliably, so
    the body is cut on every `<time datetime="` boundary (one per card,
    confirmed from a real page source) and each chunk mined independently.
    """
    cfg = source.get("html") or {}
    base = cfg.get("base") or source.get("url") or ""
    chunks = _GAIN_CARD_SPLIT_RE.split(body)[1:]  # [0] is the page header, before any card

    items: List[RawReport] = []
    seen = set()
    for chunk in chunks:
        dt_m = _GAIN_DATETIME_RE.search(chunk)
        link_m = _GAIN_LINK_RE.search(chunk)
        title_m = _GAIN_TITLE_RE.search(chunk)
        if not link_m or not title_m:
            continue
        full = urljoin(base, link_m.group(1))
        key = full.split("?", 1)[0].rstrip("/").lower()
        if key in seen:
            continue
        title = strip_html(title_m.group(1))
        if not title:
            continue
        summary_m = _GAIN_SUMMARY_RE.search(chunk)
        summary = clip(strip_html(summary_m.group(1))) if summary_m else ""
        seen.add(key)
        items.append(
            _raw_from(
                source,
                title=title,
                url=full,
                summary=summary,
                published_at=parse_date(dt_m.group(1)) if dt_m else None,
            )
        )
        if len(items) >= max_items:
            break
    return items


def fetch_source(
    source: Dict[str, Any], *, user_agent: str, timeout: float, max_items: int
) -> Dict[str, Any]:
    sid = source["id"]
    try:
        body = fetch_text(source["url"], user_agent=user_agent, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 -- one dead publisher must not fail the build
        return {"source_id": sid, "ok": False, "items": [], "count": 0,
                "error": f"{type(exc).__name__}: {exc}"}

    kind = source.get("kind", "rss")
    if kind == "rss":
        low = body[:4000].lower()
        if "<rss" not in low and "<feed" not in low and "<rdf" not in low:
            # Agencies answer a retired feed URL with their 200-OK homepage,
            # which parses as zero items and looks like a quiet week.
            return {"source_id": sid, "ok": False, "items": [], "count": 0,
                    "error": "not_a_feed_payload"}
        items = parse_feed(body, source, max_items=max_items)
    elif kind == "eia_wpsr_archive":
        items = parse_eia_wpsr_archive(body, source)
    elif kind == "html_list":
        items = parse_html_list(body, source)
    elif kind == "fas_gain_cards":
        items = parse_fas_gain_cards(body, source, max_items=max_items)
    else:
        return {"source_id": sid, "ok": False, "items": [], "count": 0,
                "error": f"unknown_kind:{kind}"}
    return {"source_id": sid, "ok": True, "items": items, "count": len(items), "error": None}


def report_id(raw: RawReport) -> str:
    return hashlib.sha1(f"{raw.source_id}|{raw.url}".encode()).hexdigest()[:16]


def parse_eia_wpsr_archive(body, source):
    """Use explicit archive dates; never assign today's date to a landing page."""
    pattern = re.compile(r'href=["\'](/petroleum/supply/weekly/archive/(\d{4})/(\d{4})_(\d{2})_(\d{2})/wpsr_\d{4}_\d{2}_\d{2}\.php)["\']', re.I)
    out, seen = [], set()
    for path, year, y, m, d in pattern.findall(body):
        if year != y or path in seen: continue
        try: published = datetime(int(y),int(m),int(d),tzinfo=timezone.utc).isoformat()
        except ValueError: continue
        seen.add(path)
        out.append(_raw_from(source, title=f"Weekly Petroleum Status Report — {y}-{m}-{d}",
          url=urljoin(source['url'],path),summary="Official weekly U.S. crude oil and petroleum supply, production and stocks report.",published_at=published))
    return out
