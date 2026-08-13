"""Fed Beige Book / press RSS scanners."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .httputil import html_to_text


@dataclass
class FedItem:
    title: str
    url: str
    published: Optional[str]
    event_type: str  # beige_book | fomc | press
    summary: str = ""
    tone: Optional[str] = None  # soft | firm | mixed | unknown


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def parse_fed_press_rss(body: str, patterns: Dict[str, Any]) -> List[FedItem]:
    items: List[FedItem] = []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return items

    channel = None
    for c in list(root):
        if _local(c.tag) == "channel":
            channel = c
            break
    parent = channel if channel is not None else root
    beige_pats = [t.lower() for t in patterns.get("beige_book", {}).get("title_any", [])]
    fomc_pats = [t.lower() for t in patterns.get("fomc", {}).get("title_any", [])]

    for el in list(parent):
        if _local(el.tag) != "item":
            continue
        title = ""
        link = ""
        pub = None
        desc = ""
        for child in list(el):
            name = _local(child.tag)
            text = (child.text or "").strip()
            if name == "title":
                title = text
            elif name == "link":
                link = text
            elif name == "pubDate":
                pub = text
            elif name == "description":
                desc = text
        if not title or not link:
            continue
        low = title.lower()
        if any(p in low for p in beige_pats):
            et = "beige_book"
        elif any(p in low for p in fomc_pats):
            et = "fomc"
        else:
            # keep only high-signal liquidity-related Fed notices
            if not any(
                k in low
                for k in (
                    "reserve requirements",
                    "discount rate",
                    "balance sheet",
                    "repo",
                    "interest on reserve",
                    "standing repo",
                )
            ):
                continue
            et = "press"
        items.append(FedItem(title=title, url=link, published=pub, event_type=et, summary=desc[:400]))
    return items


def score_beige_tone(text: str, soft_terms: List[str], firm_terms: List[str]) -> str:
    low = text.lower()
    soft = sum(1 for t in soft_terms if t in low)
    firm = sum(1 for t in firm_terms if t in low)
    if soft >= firm + 2:
        return "soft"
    if firm >= soft + 2:
        return "firm"
    if soft or firm:
        return "mixed"
    return "unknown"


def scan_beige_hub(html: str, soft_terms: List[str], firm_terms: List[str]) -> Optional[FedItem]:
    """Pick the latest Beige Book link from the hub page."""
    # common pattern: /monetarypolicy/beigebookYYYYMM.htm
    m = re.search(
        r'href="(/monetarypolicy/beigebook\d{6}\.htm[^"]*)"',
        html,
        re.I,
    )
    if not m:
        m = re.search(r'href="(https://www\.federalreserve\.gov/monetarypolicy/beigebook\d{6}\.htm[^"]*)"', html, re.I)
    if not m:
        return None
    href = m.group(1)
    if href.startswith("/"):
        href = "https://www.federalreserve.gov" + href
    title_m = re.search(r"Beige Book[^<]{0,80}", html, re.I)
    title = title_m.group(0).strip() if title_m else "Beige Book"
    tone = score_beige_tone(html_to_text(html)[:5000], soft_terms, firm_terms)
    return FedItem(
        title=title,
        url=href,
        published=None,
        event_type="beige_book",
        summary="Latest Beige Book hub entry",
        tone=tone,
    )


def fed_to_ticker(item: FedItem) -> Dict[str, Any]:
    label = {
        "beige_book": "베이지북",
        "fomc": "FOMC",
        "press": "연준",
    }.get(item.event_type, "연준")
    tone_ko = {
        "soft": "경기 연화 톤",
        "firm": "경기·물가 견조 톤",
        "mixed": "혼조",
        "unknown": "",
    }.get(item.tone or "unknown", "")
    ko = f"[{label}] {item.title}"
    if tone_ko:
        ko += f" · {tone_ko}"
    return {
        "id": f"fed-{abs(hash(item.url)) % (10**12)}",
        "published_at": item.published,
        "source": {
            "id": "federal_reserve",
            "name": "Federal Reserve",
            "region": "west",
            "slant": None,
        },
        "url": item.url,
        "category": "liquidity_official",
        "commodities": [],
        "title": {
            "original": item.title,
            "original_lang": "en",
            "ko": ko,
        },
        "summary": item.summary[:280],
        "scores": {
            "commodity": 0,
            "diplomacy": 0,
            "region_weight": 1.0,
            "freshness": 1.0,
            "final": 9.0 if item.event_type == "beige_book" else 8.5,
        },
        "rank_reasons": [f"event:{item.event_type}"]
        + ([f"tone:{item.tone}"] if item.tone else []),
        "translation_status": "ok",
        "event_type": item.event_type,
    }
