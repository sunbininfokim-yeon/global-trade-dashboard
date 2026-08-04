"""Stdlib RSS/Atom parser + HTTP fetch."""

from __future__ import annotations

import email.utils
import hashlib
import re
import ssl
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from typing import Any, Dict, Iterable, List, Optional
from xml.etree.ElementTree import Element


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass
class RawItem:
    source_id: str
    source_name: str
    region: str
    source_lang: str
    title: str
    summary: str
    url: str
    published_at: Optional[str]
    slant: Optional[str] = None
    commodities_focus: List[str] = field(default_factory=list)
    raw_xml_hash: str = ""


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = unescape(text)
    text = _TAG_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _child_text(el: Element, names: Iterable[str]) -> str:
    wanted = set(names)
    for child in list(el):
        if _local(child.tag) in wanted:
            if child.text and child.text.strip():
                return child.text.strip()
            # Some feeds put title text in nested tags.
            joined = "".join(child.itertext()).strip()
            if joined:
                return joined
    return ""


def _child_link(el: Element) -> str:
    for child in list(el):
        if _local(child.tag) == "link":
            href = child.attrib.get("href")
            if href:
                return href.strip()
            if child.text and child.text.strip():
                return child.text.strip()
    # RSS <guid> sometimes is the URL when isPermaLink=true
    for child in list(el):
        if _local(child.tag) == "guid":
            is_permalink = child.attrib.get("isPermaLink", "true").lower() != "false"
            if is_permalink and child.text:
                return child.text.strip()
    return ""


def _parse_date(raw: str) -> Optional[str]:
    if not raw:
        return None
    raw = raw.strip()
    # ISO-ish
    try:
        iso = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        pass
    # RFC 2822
    try:
        dt = email.utils.parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError):
        return None


def parse_feed_xml(
    body: bytes,
    *,
    source_id: str,
    source_name: str,
    region: str,
    source_lang: str,
    slant: Optional[str] = None,
    commodities_focus: Optional[List[str]] = None,
    max_items: int = 40,
) -> List[RawItem]:
    focus = commodities_focus or []
    items: List[RawItem] = []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return items

    root_local = _local(root.tag).lower()
    entries: List[Element] = []

    if root_local == "rss" or root_local == "rdf":
        channel = None
        for child in list(root):
            if _local(child.tag) == "channel":
                channel = child
                break
        parent = channel if channel is not None else root
        entries = [c for c in list(parent) if _local(c.tag) == "item"]
    elif root_local == "feed":
        entries = [c for c in list(root) if _local(c.tag) == "entry"]
    else:
        # Some "list.aspx" pages return HTML; skip.
        entries = [c for c in root.iter() if _local(c.tag) in {"item", "entry"}]

    for el in entries[:max_items]:
        title = _strip_html(_child_text(el, ("title",)))
        summary = _strip_html(
            _child_text(el, ("description", "summary", "content", "content:encoded"))
        )
        link = _child_link(el)
        pub = _parse_date(
            _child_text(el, ("pubDate", "published", "updated", "date", "dc:date"))
        )
        if not title or not link:
            continue
        digest = hashlib.sha1(f"{source_id}|{link}|{title}".encode("utf-8")).hexdigest()[:16]
        items.append(
            RawItem(
                source_id=source_id,
                source_name=source_name,
                region=region,
                source_lang=source_lang,
                title=title,
                summary=summary[:600],
                url=link,
                published_at=pub,
                slant=slant,
                commodities_focus=list(focus),
                raw_xml_hash=digest,
            )
        )
    return items


def fetch_url(url: str, *, user_agent: str, timeout: float = 18.0) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
        method="GET",
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read()


def fetch_source(source: Dict[str, Any], *, user_agent: str, timeout: float, max_items: int) -> List[RawItem]:
    body = fetch_url(source["url"], user_agent=user_agent, timeout=timeout)
    return parse_feed_xml(
        body,
        source_id=source["id"],
        source_name=source.get("name", source["id"]),
        region=source.get("region", "west"),
        source_lang=source.get("lang", "en"),
        slant=source.get("slant"),
        commodities_focus=source.get("commodities_focus"),
        max_items=max_items,
    )


def safe_fetch_source(
    source: Dict[str, Any],
    *,
    user_agent: str,
    timeout: float,
    max_items: int,
) -> Dict[str, Any]:
    started = time.time()
    try:
        items = fetch_source(
            source, user_agent=user_agent, timeout=timeout, max_items=max_items
        )
        return {
            "source_id": source["id"],
            "ok": True,
            "count": len(items),
            "items": items,
            "elapsed_ms": int((time.time() - started) * 1000),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 - feed failures must not kill the build
        return {
            "source_id": source["id"],
            "ok": False,
            "count": 0,
            "items": [],
            "elapsed_ms": int((time.time() - started) * 1000),
            "error": f"{type(exc).__name__}: {exc}",
        }
