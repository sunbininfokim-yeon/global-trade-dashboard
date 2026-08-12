"""Build liquidity_intel_v1.json from Treasury / Fed / priority reporters."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .fed import fed_to_ticker, parse_fed_press_rss, scan_beige_hub, score_beige_tone
from .httputil import extract_title, fetch_text, html_to_text
from .liquidity import compute_liquidity_bias
from .qra import is_qra_document, parse_qra_html, qra_to_ticker_item
from .reporters import (
    analyze_reporter_liquidity,
    enrich_article_body,
    indicator_summary_to_optional_ticker,
    scrape_economy21_priority,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_treasury_qra_urls(list_html: str, base: str, patterns: Dict[str, Any]) -> List[str]:
    # press release cards: /news/press-releases/xxNNNN
    hrefs = re.findall(r'href="(/news/press-releases/[a-z0-9]+)"', list_html, re.I)
    urls = []
    seen = set()
    title_hints = [t.lower() for t in patterns.get("qra", {}).get("title_any", [])]
    # Also search nearby text in list page
    for h in hrefs:
        full = base.rstrip("/") + h if h.startswith("/") else h
        if full in seen:
            continue
        # keep all recent; filter by title on detail page if needed
        # Prefer links whose surrounding 200 chars mention Marketable/Borrowing
        idx = list_html.find(h)
        window = list_html[max(0, idx - 180) : idx + 220].lower()
        if any(t in window for t in title_hints) or "marketable borrowing" in window or "borrowing estimates" in window:
            urls.append(full)
            seen.add(full)
    return urls[:5]


def build_liquidity_intel(
    *,
    fetch_live: bool = True,
    fixture_dir: Optional[Path] = None,
    explicit_qra_url: Optional[str] = None,
    enrich_reporter_bodies: bool = False,
) -> Dict[str, Any]:
    sources = load_json(CONFIG_DIR / "sources.json")
    rules = load_json(CONFIG_DIR / "liquidity_rules.json")
    reporter_liq_cfg = load_json(CONFIG_DIR / "reporter_liquidity.json")
    ua = sources.get("user_agent", "GTrade-MacroIntel/1.0")
    timeout = float(sources.get("fetch_timeout_sec", 25))
    src = sources["sources"]
    patterns = sources.get("event_patterns", {})
    soft = rules.get("beige_soft_terms", [])
    firm = rules.get("beige_firm_terms", [])

    feed_status: List[Dict[str, Any]] = []
    ticker_items: List[Dict[str, Any]] = []
    qra_block: Optional[Dict[str, Any]] = None
    qra_signals: List[str] = []
    beige_tone: Optional[str] = None
    fed_block: Dict[str, Any] = {"beige_book": None, "items": []}
    reporter_analyses: List[Dict[str, Any]] = []
    reporter_panel: Dict[str, Any] = {}
    reporter_signals: List[str] = []

    def _read(name: str, url: str) -> str:
        if fixture_dir:
            fp = Path(fixture_dir) / name
            if fp.exists():
                feed_status.append({"source": name, "ok": True, "mode": "fixture"})
                return fp.read_text(encoding="utf-8", errors="replace")
            feed_status.append({"source": name, "ok": False, "error": "fixture_missing"})
            return ""
        if not fetch_live:
            feed_status.append({"source": name, "ok": False, "error": "fetch_disabled"})
            return ""
        try:
            text = fetch_text(url, user_agent=ua, timeout=timeout)
            feed_status.append({"source": name, "ok": True, "mode": "live", "url": url})
            return text
        except Exception as exc:  # noqa: BLE001
            feed_status.append(
                {"source": name, "ok": False, "error": f"{type(exc).__name__}: {exc}", "url": url}
            )
            return ""

    # --- Treasury QRA ---
    qra_urls: List[str] = []
    if explicit_qra_url:
        qra_urls = [explicit_qra_url]
    else:
        list_html = _read("treasury_press_list.html", src["treasury_press_list"])
        if list_html:
            qra_urls = _find_treasury_qra_urls(
                list_html, src.get("treasury_press_item_prefix", "https://home.treasury.gov"), patterns
            )
        if fixture_dir and (Path(fixture_dir) / "treasury_qra.html").exists():
            qra_urls = qra_urls or ["fixture://treasury_qra"]

    for i, qurl in enumerate(qra_urls[:3]):
        if qurl.startswith("fixture://"):
            html = _read("treasury_qra.html", qurl)
            qurl = "https://home.treasury.gov/news/press-releases/sb0584"
        else:
            html = _read(f"treasury_qra_{i}.html", qurl)
            if not html and fixture_dir:
                html = _read("treasury_qra.html", qurl)
        if not html:
            continue
        title = extract_title(html) or ""
        plain = html_to_text(html)
        if not is_qra_document(title, plain, patterns.get("qra", {})) and "Marketable Borrowing" not in title:
            if "privately-held net marketable" not in plain.lower():
                continue
        parsed = parse_qra_html(html, url=qurl, title=title)
        if not parsed.quarters and not parsed.signals:
            continue
        qra_block = parsed.to_dict()
        qra_signals = list(parsed.signals)
        ticker_items.append(qra_to_ticker_item(parsed))
        break

    # --- Fed ---
    rss = _read("fed_press.xml", src["fed_press_rss"])
    if rss:
        for it in parse_fed_press_rss(rss, patterns):
            if it.event_type == "beige_book" and it.summary:
                it.tone = score_beige_tone(it.summary + " " + it.title, soft, firm)
                beige_tone = it.tone
            fed_block["items"].append(
                {
                    "title": it.title,
                    "url": it.url,
                    "published": it.published,
                    "event_type": it.event_type,
                    "tone": it.tone,
                }
            )
            ticker_items.append(fed_to_ticker(it))

    hub = _read("beige_hub.html", src["fed_beige_book_hub"])
    if hub:
        bb = scan_beige_hub(hub, soft, firm)
        if bb:
            if not beige_tone:
                beige_tone = bb.tone
            fed_block["beige_book"] = {
                "title": bb.title,
                "url": bb.url,
                "tone": bb.tone,
            }
            if not any(t.get("event_type") == "beige_book" for t in ticker_items):
                ticker_items.append(fed_to_ticker(bb))

    # --- Priority reporters: extract liquidity INDICATORS (not celebrity-style news ticker) ---
    eco = _read("economy21_list.html", src["economy21_section"])
    if eco:
        for author in sources.get("priority_authors", []):
            arts = scrape_economy21_priority(
                eco,
                origin=src.get("economy21_origin", "http://www.economy21.co.kr"),
                author_needles=author.get("match", []),
                max_items=int(author.get("max_articles", 8)),
            )
            if enrich_reporter_bodies and fetch_live and not fixture_dir:
                for a in arts[:5]:
                    enrich_article_body(a, user_agent=ua, timeout=timeout)
            analysis = analyze_reporter_liquidity(
                arts,
                reporter_liq_cfg,
                author=author.get("name_ko") or author.get("id") or "reporter",
            )
            reporter_analyses.append(analysis)
            reporter_signals.extend(analysis.get("reporter_signals") or [])
            for k, v in (analysis.get("finance_panel_fields") or {}).items():
                if v is not None:
                    reporter_panel[k] = v
            # At most one analytics headline for ticker (metrics), never per-article dump
            line = indicator_summary_to_optional_ticker(analysis)
            if line:
                ticker_items.append(line)

    bias = compute_liquidity_bias(
        qra_signals=qra_signals,
        beige_tone=beige_tone,
        reporter_signals=reporter_signals,
        rules=rules,
    )

    priority = {
        "qra": 0,
        "beige_book": 1,
        "fomc": 2,
        "press": 3,
        "liquidity_indicator": 4,
    }
    ticker_items.sort(
        key=lambda x: (priority.get(x.get("event_type"), 9), -float(x.get("scores", {}).get("final", 0)))
    )

    finance_fields = {
        "qra_next_net_borrowing_bn": (
            qra_block["quarters"][0]["net_borrowing_bn"]
            if qra_block and qra_block.get("quarters")
            else None
        ),
        "qra_end_cash_bn": (
            qra_block["quarters"][0].get("end_cash_balance_bn")
            if qra_block and qra_block.get("quarters")
            else None
        ),
        "qra_vs_prior_bn": (
            qra_block["quarters"][0].get("vs_prior_bn")
            if qra_block and qra_block.get("quarters")
            else None
        ),
        "liquidity_bias": bias["bias"],
        "liquidity_headline_ko": bias["headline_ko"],
        "beige_tone": beige_tone,
        **reporter_panel,
    }

    return {
        "schema_version": "liquidity-intel-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": {
            "name": "macro_liquidity_official_v1",
            "description": (
                "QRA / Fed official liquidity + priority-reporter ARTICLES mined for "
                "liquidity indicators (FIMA, TGA, RRP, FX intervention…) — not reporter news fluff."
            ),
            "learning_strategy": {
                "phase": "extract_and_store",
                "not_doing": "Dumping every 양영빈 article to the ticker as celebrity news",
                "doing": [
                    "Structured QRA parse",
                    "Fed beige/FOMC",
                    "Map designated reporters' prose → liquidity indicator themes",
                    "finance_panel_fields for dashboard tiles",
                ],
                "future": "Label which extracted indicators were decision-useful; calibrate weights.",
            },
        },
        "liquidity": {
            **bias,
            "qra": qra_block,
            "fed": fed_block,
            "reporter_liquidity": reporter_analyses,
            "finance_panel_fields": finance_fields,
        },
        "ticker_items": ticker_items,
        "feed_status": feed_status,
        "stats": {
            "ticker_items": len(ticker_items),
            "qra_parsed": bool(qra_block),
            "reporter_analyses": len(reporter_analyses),
            "reporter_indicator_hits": sum(
                len(a.get("top_indicators") or []) for a in reporter_analyses
            ),
            "sources_ok": sum(1 for s in feed_status if s.get("ok")),
            "sources_failed": sum(1 for s in feed_status if not s.get("ok")),
        },
    }


def write_json(doc: Dict[str, Any], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
