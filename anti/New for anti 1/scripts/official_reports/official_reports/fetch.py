"""Fetch RSS and simple HTML list pages into RawReport items."""

from __future__ import annotations

import email.utils
import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from typing import Any, Dict, List, Optional

from .httputil import absolutize, fetch_text, html_to_text


@dataclass
class RawReport:
    source_id: str
    country: str
    agency: str
    title: str
    url: str
    summary: str
    published_at: Optional[str]
    domains_hint: List[str] = field(default_factory=list)
    weight: float = 1.0
    lang: str = "en"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _parse_date(raw: str) -> Optional[str]:
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


def parse_rss(body: str, source: Dict[str, Any], max_items: int = 30) -> List[RawReport]:
    items: List[RawReport] = []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return items
    root_l = _local(root.tag).lower()
    entries = []
    if root_l in {"rss", "rdf"}:
        channel = next((c for c in list(root) if _local(c.tag) == "channel"), root)
        entries = [c for c in list(channel) if _local(c.tag) == "item"]
    elif root_l == "feed":
        entries = [c for c in list(root) if _local(c.tag) == "entry"]
    for el in entries[:max_items]:
        title = summary = link = pub = ""
        for child in list(el):
            n = _local(child.tag)
            text = "".join(child.itertext()).strip()
            if n == "title":
                title = text
            elif n in {"description", "summary", "content"}:
                summary = text
            elif n == "link":
                link = child.attrib.get("href") or text
            elif n in {"pubDate", "published", "updated", "date"}:
                pub = text
        title = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", title))).strip()
        summary = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", summary))).strip()[:500]
        if not title or not link:
            continue
        items.append(
            RawReport(
                source_id=source["id"],
                country=source.get("country", "UNK"),
                agency=source.get("agency", source["id"]),
                title=title,
                url=link.strip(),
                summary=summary,
                published_at=_parse_date(pub),
                domains_hint=list(source.get("domains") or []),
                weight=float(source.get("weight", 1.0)),
                lang=source.get("lang", "en"),
            )
        )
    return items


def parse_html_list(body: str, source: Dict[str, Any]) -> List[RawReport]:
    cfg = source.get("html") or {}
    base = cfg.get("base") or source.get("url") or ""
    href_re = cfg.get("item_href_re") or r'href="([^"]+)"'
    max_items = int(cfg.get("max_items") or 20)
    prefer = [p.lower() for p in (cfg.get("prefer_keywords") or [])]
    # Find all href matches
    if not href_re.startswith("(") and "href" not in href_re:
        pattern = rf'href="({href_re})"'
    else:
        pattern = href_re if "href" in href_re else rf'href="({href_re})"'
    found = re.findall(pattern, body, flags=re.I)
    # normalize to list of strings
    hrefs: List[str] = []
    for f in found:
        if isinstance(f, tuple):
            hrefs.append(f[0])
        else:
            hrefs.append(f)

    items: List[RawReport] = []
    seen = set()
    for href in hrefs:
        full = absolutize(base, href)
        if full in seen:
            continue
        # window around href for title text
        idx = body.find(href)
        window = body[max(0, idx - 120) : idx + 280]
        title_m = re.search(r">([^<]{12,180})<", window)
        title = ""
        if title_m:
            title = re.sub(r"\s+", " ", unescape(title_m.group(1))).strip()
        if not title or title.lower() in {"read more", "details", "more"}:
            title = full.rsplit("/", 1)[-1].replace("-", " ")[:120]
        blob = (title + " " + window).lower()
        if prefer and not any(p in blob for p in prefer):
            # still keep treasury press paths which are high value
            if source.get("id") != "us_treasury_press_list":
                continue
        seen.add(full)
        items.append(
            RawReport(
                source_id=source["id"],
                country=source.get("country", "UNK"),
                agency=source.get("agency", source["id"]),
                title=title,
                url=full,
                summary="",
                published_at=None,
                domains_hint=list(source.get("domains") or []),
                weight=float(source.get("weight", 1.0)),
                lang=source.get("lang", "en"),
            )
        )
        if len(items) >= max_items:
            break
    return items


def fetch_source(source: Dict[str, Any], *, user_agent: str, timeout: float, max_items: int) -> Dict[str, Any]:
    try:
        body = fetch_text(source["url"], user_agent=user_agent, timeout=timeout)
        kind = source.get("kind", "rss")
        if kind == "rss":
            # sometimes HTML error pages
            if "<rss" not in body.lower() and "<feed" not in body.lower():
                return {
                    "source_id": source["id"],
                    "ok": False,
                    "items": [],
                    "error": "not_rss_payload",
                }
            items = parse_rss(body, source, max_items=max_items)
        elif kind == "html_list":
            items = parse_html_list(body, source)
        else:
            return {
                "source_id": source["id"],
                "ok": False,
                "items": [],
                "error": f"unknown_kind:{kind}",
            }
        return {"source_id": source["id"], "ok": True, "items": items, "error": None, "count": len(items)}
    except Exception as exc:  # noqa: BLE001
        return {
            "source_id": source["id"],
            "ok": False,
            "items": [],
            "error": f"{type(exc).__name__}: {exc}",
            "count": 0,
        }


def report_id(raw: RawReport) -> str:
    return hashlib.sha1(f"{raw.source_id}|{raw.url}|{raw.title}".encode()).hexdigest()[:16]
