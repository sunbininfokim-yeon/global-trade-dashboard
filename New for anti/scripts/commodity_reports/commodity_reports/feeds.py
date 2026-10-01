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
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urljoin

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
    # "month" when only the year and month are known (a GAIN page with no
    # dated element falls back to the /YYYY/MM/ in its URL). The card then
    # shows 2026.09, not a day nobody published.
    date_precision: str = "day"
    # Source-level relevance switches (config/sources.json): market_only drops
    # an item whose text has no market term at all (publisher PR boards);
    # commodity_from "title" tags commodities from the headline only (broad
    # policy feeds whose bodies mention crops in passing).
    market_only: bool = False
    commodity_from: str = "text"
    # commodity_scope: the only commodities this source may be filed under. A
    # grain exchange's macro column that says "petróleo" once is not an oil
    # report (BCR, 2026-09-27). Empty means no restriction.
    commodity_scope: List[str] = field(default_factory=list)
    weight: float = 1.0
    # Priors from the source catalog, used only where the text itself is silent.
    default_country: Optional[str] = None
    commodity_hint: List[str] = field(default_factory=list)
    scope_hint: str = "country"


def strip_html(doc: str) -> str:
    doc = _SCRIPT_RE.sub(" ", doc)
    doc = _TAG_RE.sub(" ", doc)
    return _WS_RE.sub(" ", unescape(doc)).strip()


# Some ministries drop or reset a connection that does not look like a
# browser's (MOFCOM's English site resets ours and serves Chrome's). A source
# opts in with "headers": "browser"; everyone else keeps the honest UA.
# The Sec-Fetch-* and Upgrade-Insecure-Requests lines are what MOFCOM checks:
# with the User-Agent and Accept lines alone it reset all 14 builds, and the
# same urllib request with these added got 200 (feed probe, 2026-10-01).
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


def fetch_text(url: str, *, user_agent: str, timeout: float = 22.0, browser: bool = False) -> str:
    headers = dict(BROWSER_HEADERS) if browser else {
        "User-Agent": user_agent,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, "
        "text/xml, text/html, */*",
        "Accept-Language": "en,pt;q=0.8,es;q=0.8,fr;q=0.6",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
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
        market_only=bool(source.get("market_only")),
        commodity_from=source.get("commodity_from", "text"),
        commodity_scope=list(source.get("commodity_scope") or []),
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
    pattern = re.compile(rf"href=[\"']({href_re})[\"'][^>]*>", re.I | re.S)

    def anchors():
        # The anchor's text is whatever sits before its </a>. Card layouts
        # (WGC, ILZSG) wrap a whole teaser in the link, so the closing tag can
        # be kilobytes away; a text that long is not a headline and the slug
        # stands in for it.
        for m in pattern.finditer(body):
            end = body.find("</a>", m.end(), m.end() + 4000)
            inner = body[m.end():end] if end != -1 else ""
            yield m.group(1), inner

    items: List[RawReport] = []
    seen = set()
    for href, inner in anchors():
        full = urljoin(base, href)
        key = full.split("?", 1)[0].rstrip("/").lower()
        if key in seen:
            continue
        title = strip_html(inner)
        if len(title) > 200:
            title = ""
        if len(title) < 12:
            # Icon-only or "read more" links: fall back to the slug, which for
            # these publishers is a readable title -- once its %-escapes are
            # decoded (ANRPC's "report%2C june 2026") and its first letter
            # capitalized.
            slug = unquote(full.rstrip("/").rsplit("/", 1)[-1])
            slug = re.sub(r"\.(?:html?|php|aspx?|pdf)$|\.\d+\.html?$", "", slug, flags=re.I)
            title = re.sub(r"\s+", " ", re.sub(r"[-_]+", " ", slug)).strip(" .")
            title = title[:1].upper() + title[1:]
        if len(title) < 12:
            continue
        seen.add(key)
        items.append(
            _raw_from(source, title=title, url=full, summary="", published_at=None)
        )
        if len(items) >= max_items:
            break
    return items


def fetch_bytes(url: str, *, user_agent: str, timeout: float = 30.0, limit: int = 12_000_000) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "application/pdf,*/*"})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
        return resp.read(limit)


def pdf_text(data: bytes, max_pages: int = 2) -> str:
    """Text of a PDF's first pages, or "" when pypdf is missing or the file
    will not parse. The pipeline must build without it; the workflow installs it."""
    try:
        import io

        from pypdf import PdfReader  # type: ignore
    except Exception:  # noqa: BLE001 -- ImportError, or a broken crypto backend
        return ""
    try:
        reader = PdfReader(io.BytesIO(data))
        return " ".join((page.extract_text() or "") for page in reader.pages[:max_pages])
    except Exception:  # noqa: BLE001
        return ""


def add_pdf_summaries(
    items: List[RawReport], *, fetch_pdf, extract=pdf_text, max_pdfs: int = 3, skip_urls=()
) -> int:
    """Quote the opening of each newest PDF item as its summary.

    Study-group press releases (ILZSG) are PDFs with the month's balance in
    the first paragraph; the list page only gives a file name. Only the
    newest few are fetched per run, and reports already summarized in the
    previous build (skip_urls) are not fetched again.
    """
    done = 0
    for item in items:
        if done >= max_pdfs:
            break
        if item.summary or not item.url.lower().split("?", 1)[0].endswith(".pdf") or item.url in skip_urls:
            continue
        try:
            text = extract(fetch_pdf(item.url))
        except Exception:  # noqa: BLE001
            continue
        done += 1
        text = _WS_RE.sub(" ", text).strip()
        if text:
            item.summary = clip(text)
    return done


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


_GAIN_PAGE_LINK_RE = re.compile(
    r"href=[\"'](?:https?://(?:www\.)?fas\.usda\.gov)?(/data/gain/(\d{4})/(\d{2})/[a-z0-9-]+)[\"'?#]", re.I
)
_META_RE = re.compile(r"<meta\s+[^>]*>", re.I)
_META_KEY_RE = re.compile(r"(?:property|name|itemprop)=[\"']([^\"']+)[\"']", re.I)
# Quote-paired: a summary like content="Brazil's crop..." must not stop at
# the apostrophe.
_META_CONTENT_RE = re.compile(r"content=(?:\"([^\"]*)\"|'([^']*)')", re.I)
_TIME_RE = re.compile(r"<time[^>]+datetime=[\"']([^\"']+)[\"']", re.I)
_LD_DATE_RE = re.compile(r"\"datePublished\"\s*:\s*\"([^\"]+)\"")
_PDF_RE = re.compile(r"href=[\"']([^\"']*/data/gain-report/[^\"']+\.pdf)[\"']", re.I)


def _metas(body: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for tag in _META_RE.findall(body):
        k = _META_KEY_RE.search(tag)
        v = _META_CONTENT_RE.search(tag)
        if k and v and k.group(1).lower() not in out:
            out[k.group(1).lower()] = unescape(v.group(1) if v.group(1) is not None else v.group(2)).strip()
    return out


def gain_links(list_html: str) -> List[tuple]:
    """(path, year, month) for every GAIN report a FAS list page links to."""
    seen, out = set(), []
    for path, year, month in _GAIN_PAGE_LINK_RE.findall(list_html):
        if path not in seen:
            seen.add(path)
            out.append((path, int(year), int(month)))
    return out


def parse_fas_gain_page(body: str, url: str, year: int, month: int, source: Dict[str, Any]) -> Optional[RawReport]:
    """One GAIN report page (fas.usda.gov/data/gain/YYYY/MM/slug).

    The page is server-rendered with Open Graph tags: og:title is the report
    title as FAS lists it ("Malaysia: Oilseeds and Products Update") and the
    description is the report's own summary paragraph. The date comes from the
    page when it carries one inside the URL's month; otherwise from the URL.
    """
    meta = _metas(body)
    title = meta.get("og:title") or meta.get("twitter:title") or ""
    if not title:
        m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
        title = strip_html(m.group(1)).split(" | ")[0] if m else ""
    title = strip_html(title)
    if not title:
        return None
    summary = meta.get("og:description") or meta.get("description") or ""
    published, precision = None, "month"
    for raw in [meta.get("article:published_time", "")] + _TIME_RE.findall(body) + _LD_DATE_RE.findall(body):
        iso = parse_date(raw)
        if iso and iso[:7] == f"{year:04d}-{month:02d}":
            published, precision = iso, "day"
            break
    if published is None:
        published = datetime(year, month, 1, tzinfo=timezone.utc).isoformat()
    item = _raw_from(source, title=title, url=url, summary=clip(strip_html(summary)), published_at=published)
    item.date_precision = precision
    return item


def fetch_fas_gain_pages(
    source: Dict[str, Any], *, fetch, max_items: int, now: Optional[datetime] = None,
    known: Optional[List[RawReport]] = None, pause=None,
) -> Dict[str, Any]:
    """GAIN reports gathered from FAS's commodity and country pages.

    fas.usda.gov/data/search -- the only page that lists every GAIN report --
    answers "Access Denied" to Actions runners (urllib, browser headers, a
    Chrome TLS fingerprint and a real headless Chrome alike; checked
    2026-09-26 with tools/ops/feed_probe.py). The commodity pages
    (/data/commodities/<x>) and country pages (/regions/<x>) are not blocked
    and each links its latest few GAIN reports, and the report pages
    themselves are readable, so the list is assembled from those.

    `fetch(url) -> str` is injected so fixture builds and tests run offline.
    `known` are the reports the last build already read; their pages are not
    fetched again. `pause()` runs between requests (a delay, live only). Five
    list pages failing in a row stops the run: that is a block, and asking
    forty more times only makes it last longer.
    """
    pause = pause or (lambda: None)
    known_by_url = {r.url: r for r in (known or [])}
    cfg = source.get("html") or {}
    base = cfg.get("base") or "https://www.fas.usda.gov"
    now = now or datetime.now(timezone.utc)
    max_age_days = int(cfg.get("max_age_days") or 150)
    max_pages = int(cfg.get("max_pages") or max_items)
    exclude = re.compile(cfg["exclude_slug_re"]) if cfg.get("exclude_slug_re") else None
    slug_hints: Dict[str, List[str]] = cfg.get("slug_commodities") or {}

    lists_ok, errors, failed_in_row = 0, [], 0
    found: Dict[str, tuple] = {}
    for n, path in enumerate(cfg.get("list_urls") or []):
        if n:
            pause()
        try:
            html = fetch(urljoin(base, path))
        except Exception as exc:  # noqa: BLE001 -- one dead list page must not sink the rest
            errors.append(f"{path}: {type(exc).__name__}")
            failed_in_row += 1
            if failed_in_row >= 5 and not lists_ok:
                break
            continue
        failed_in_row = 0
        lists_ok += 1
        for link, year, month in gain_links(html):
            slug = link.rsplit("/", 1)[-1]
            if exclude and exclude.search(slug):
                continue
            age = (now - datetime(year, month, 1, tzinfo=timezone.utc)).days
            if age > max_age_days or age < -31:
                continue
            found.setdefault(link, (year, month))
    if not lists_ok:
        return {"ok": False, "items": [], "error": "no list page answered: " + "; ".join(errors[:3])}

    newest_first = sorted(found.items(), key=lambda kv: kv[1], reverse=True)[:max_pages]
    items: List[RawReport] = []
    reused = 0
    for link, (year, month) in newest_first:
        url = urljoin(base, link)
        if url in known_by_url:
            items.append(known_by_url[url])
            reused += 1
            continue
        pause()
        try:
            body = fetch(url)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{link}: {type(exc).__name__}")
            continue
        item = parse_fas_gain_page(body, url, year, month, source)
        if item is None:
            continue
        slug = link.rsplit("/", 1)[-1]
        hints = [c for key, cs in slug_hints.items() if key in slug for c in cs]
        if hints:
            item.commodity_hint = list(dict.fromkeys(hints))
        items.append(item)
    return {"ok": True, "items": items, "error": None,
            "note": f"{lists_ok} list pages, {len(found)} reports linked, {len(items) - reused} read, {reused} already known"
            + (f"; {len(errors)} failed" if errors else "")}


def fetch_source(
    source: Dict[str, Any], *, user_agent: str, timeout: float, max_items: int,
    known: Optional[List[RawReport]] = None,
) -> Dict[str, Any]:
    sid = source["id"]
    if source.get("kind") == "fas_gain_pages":
        delay = float((source.get("html") or {}).get("delay_sec", 1.0))
        res = fetch_fas_gain_pages(
            source,
            fetch=lambda u: fetch_text(u, user_agent=user_agent, timeout=timeout),
            max_items=max_items,
            known=known,
            pause=lambda: time.sleep(delay),
        )
        return {"source_id": sid, "ok": res["ok"], "items": res["items"],
                "count": len(res["items"]), "error": res["error"], "note": res.get("note")}
    try:
        body = fetch_text(source["url"], user_agent=user_agent, timeout=timeout,
                          browser=source.get("headers") == "browser")
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
    elif kind == "html_list":
        items = parse_html_list(body, source)
        if (source.get("html") or {}).get("pdf_summary"):
            known_by_url = {r.url: r for r in (known or []) if r.summary}
            for it in items:
                if it.url in known_by_url:
                    it.summary = known_by_url[it.url].summary
            add_pdf_summaries(
                items,
                fetch_pdf=lambda u: fetch_bytes(u, user_agent=user_agent, timeout=timeout + 10),
                skip_urls=set(known_by_url),
            )
    elif kind == "fas_gain_cards":
        items = parse_fas_gain_cards(body, source, max_items=max_items)

    else:
        return {"source_id": sid, "ok": False, "items": [], "count": 0,
                "error": f"unknown_kind:{kind}"}
    return {"source_id": sid, "ok": True, "items": items, "count": len(items), "error": None}


def report_id(raw: RawReport) -> str:
    return hashlib.sha1(f"{raw.source_id}|{raw.url}".encode()).hexdigest()[:16]
