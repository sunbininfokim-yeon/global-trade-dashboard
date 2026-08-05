"""Priority reporters → liquidity indicator extraction (not ticker celebrity news)."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from html import unescape
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urljoin

from .httputil import fetch_text, html_to_text


@dataclass
class ReporterArticle:
    title: str
    url: str
    author: str
    published: str | None
    snippet: str
    source_id: str
    body: str = ""


_DATE = re.compile(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})")


def scrape_economy21_priority(
    html: str,
    *,
    origin: str,
    author_needles: List[str],
    max_items: int = 12,
) -> List[ReporterArticle]:
    """Collect list-page cards that mention a priority author."""
    out: List[ReporterArticle] = []
    seen = set()

    chunks = re.split(r'(?=<div class="list-titles")', html)
    if len(chunks) < 2:
        chunks = re.split(r'(?=<a[^>]+href="/news/articleView\.html\?idxno=)', html)

    for chunk in chunks:
        if "articleView.html?idxno=" not in chunk:
            continue
        if not any(n in chunk for n in author_needles):
            continue
        hm = re.search(r'href="(/news/articleView\.html\?idxno=\d+)"', chunk)
        if not hm:
            continue
        path = hm.group(1)
        if path in seen:
            continue
        seen.add(path)

        title = ""
        tm = re.search(
            r'class="list-titles"[^>]*>\s*<a[^>]*>\s*<strong>([^<]+)</strong>',
            chunk,
            re.I,
        )
        if not tm:
            tm = re.search(
                r'class="list-titles"[^>]*>\s*<a[^>]*>([^<]{6,200})</a>',
                chunk,
                re.I,
            )
        if not tm:
            tm = re.search(
                r'<span class="show-for-sr">([^<]{6,200})</span>',
                chunk,
                re.I,
            )
        if tm:
            title = unescape(re.sub(r"\s+", " ", tm.group(1))).strip()
        if not title:
            title = path

        dm = _DATE.search(chunk)
        published = dm.group(1) if dm else None
        snip = ""
        sm = re.search(r'class="list-summary"[^>]*>.*?<a[^>]*>(.*?)</a>', chunk, re.I | re.S)
        if sm:
            snip = unescape(re.sub(r"<[^>]+>", " ", sm.group(1)))
            snip = re.sub(r"\s+", " ", snip).strip()[:500]
        if not snip:
            for n in author_needles:
                sm2 = re.search(re.escape(n) + r"[^\n<]{0,200}", chunk)
                if sm2:
                    snip = unescape(re.sub(r"\s+", " ", sm2.group(0)))[:300]
                    break
        matched_author = next((n for n in author_needles if n in chunk), author_needles[0])
        out.append(
            ReporterArticle(
                title=title,
                url=urljoin(origin, path),
                author=matched_author,
                published=published,
                snippet=snip,
                source_id="economy21",
            )
        )
        if len(out) >= max_items:
            break
    return out


def enrich_article_body(
    article: ReporterArticle,
    *,
    user_agent: str,
    timeout: float = 18.0,
) -> None:
    """Optional full-page text (title+body) for better indicator coverage."""
    try:
        html = fetch_text(article.url, user_agent=user_agent, timeout=timeout)
    except Exception:
        return
    text = html_to_text(html)
    # keep a bounded window to avoid noise
    article.body = text[:8000]


def _compile_terms(terms: Sequence[str]) -> List[re.Pattern[str]]:
    pats = []
    for t in terms:
        t = t.strip()
        if not t:
            continue
        if re.fullmatch(r"[A-Za-z0-9+.\- /]+", t):
            pats.append(re.compile(rf"(?i)(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])"))
        else:
            pats.append(re.compile(re.escape(t), re.IGNORECASE))
    return pats


@dataclass
class IndicatorHit:
    indicator_id: str
    label_ko: str
    weight: float
    liquidity_hint: str
    mentions: int
    evidence: List[str] = field(default_factory=list)


def extract_liquidity_indicators(
    text: str,
    indicators_cfg: Dict[str, Any],
) -> List[IndicatorHit]:
    hits: List[IndicatorHit] = []
    if not text:
        return hits
    for ind in indicators_cfg.get("indicators", []):
        pats = _compile_terms(ind.get("terms") or [])
        found = []
        for p in pats:
            for m in p.finditer(text):
                start = max(0, m.start() - 40)
                end = min(len(text), m.end() + 60)
                found.append(re.sub(r"\s+", " ", text[start:end]).strip())
        if not found:
            continue
        hits.append(
            IndicatorHit(
                indicator_id=ind["id"],
                label_ko=ind.get("label_ko", ind["id"]),
                weight=float(ind.get("weight", 1.0)),
                liquidity_hint=ind.get("liquidity_hint", "mixed"),
                mentions=len(found),
                evidence=found[:3],
            )
        )
    hits.sort(key=lambda h: (-h.mentions * h.weight, h.indicator_id))
    return hits


def analyze_reporter_liquidity(
    articles: List[ReporterArticle],
    indicators_cfg: Dict[str, Any],
    *,
    author: str,
) -> Dict[str, Any]:
    """Aggregate liquidity themes across a priority reporter's recent articles."""
    per_article: List[Dict[str, Any]] = []
    counter: Counter = Counter()
    hint_weights: Dict[str, float] = defaultdict(float)
    evidence_by_id: Dict[str, List[str]] = defaultdict(list)

    for a in articles:
        blob = "\n".join([a.title, a.snippet, a.body]).strip()
        hits = extract_liquidity_indicators(blob, indicators_cfg)
        if not hits:
            continue
        for h in hits:
            counter[h.indicator_id] += h.mentions * h.weight
            hint_weights[h.liquidity_hint] += h.mentions * h.weight
            evidence_by_id[h.indicator_id].extend(h.evidence[:1])
        per_article.append(
            {
                "title": a.title,
                "url": a.url,
                "published": a.published,
                "author": a.author,
                "indicators": [
                    {
                        "id": h.indicator_id,
                        "label_ko": h.label_ko,
                        "mentions": h.mentions,
                        "hint": h.liquidity_hint,
                        "evidence": h.evidence,
                    }
                    for h in hits
                ],
            }
        )

    ranked = [
        {
            "id": iid,
            "score": round(score, 3),
            "label_ko": next(
                (
                    i.get("label_ko", iid)
                    for i in indicators_cfg.get("indicators", [])
                    if i["id"] == iid
                ),
                iid,
            ),
            "evidence": evidence_by_id.get(iid, [])[:2],
        }
        for iid, score in counter.most_common(12)
    ]

    # Panel: top themes as readable Korean lines
    themes_ko = [f"{r['label_ko']} (점수 {r['score']})" for r in ranked[:6]]

    # Map hints → soft bias contribution for liquidity engine
    reporter_signals: List[str] = []
    if hint_weights.get("tightening", 0) > hint_weights.get("easing", 0) + 1:
        reporter_signals.append("reporter_tightening_theme")
    if hint_weights.get("easing", 0) > hint_weights.get("tightening", 0) + 1:
        reporter_signals.append("reporter_easing_theme")
    if hint_weights.get("tga", 0) >= 1:
        reporter_signals.append("reporter_tga_focus")
    if hint_weights.get("rrp", 0) >= 1:
        reporter_signals.append("reporter_rrp_focus")
    if hint_weights.get("fx_intervention", 0) >= 1:
        reporter_signals.append("reporter_fx_intervention")
    if hint_weights.get("fima", 0) >= 1 or counter.get("fima", 0) >= 1:
        reporter_signals.append("reporter_fima_focus")

    primary = ranked[0] if ranked else None
    headline = None
    if primary:
        headline = f"[유동성 분석·{author}] 최근 기사 핵심 지표: {primary['label_ko']}"
        if len(ranked) > 1:
            headline += f" · 외 {len(ranked)-1}개 테마"

    return {
        "author": author,
        "articles_scanned": len(articles),
        "articles_with_hits": len(per_article),
        "top_indicators": ranked,
        "themes_ko": themes_ko,
        "hint_weights": {k: round(v, 3) for k, v in sorted(hint_weights.items(), key=lambda x: -x[1])},
        "reporter_signals": reporter_signals,
        "headline_ko": headline,
        "per_article": per_article[:10],
        "finance_panel_fields": {
            "reporter_liquidity_primary": primary["id"] if primary else None,
            "reporter_liquidity_primary_ko": primary["label_ko"] if primary else None,
            "reporter_liquidity_themes": themes_ko,
            "reporter_liquidity_signals": reporter_signals,
            "reporter_liquidity_headline_ko": headline,
        },
    }


def indicator_summary_to_optional_ticker(analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    One analytics line for ticker (metric-focused), only if we extracted indicators.
    Not a journalist-name news dump.
    """
    if not analysis.get("top_indicators"):
        return None
    primary = analysis["top_indicators"][0]
    author = analysis.get("author") or "지정기자"
    themes = " · ".join(r["label_ko"] for r in analysis["top_indicators"][:3])
    ko = f"[유동성지표·{author}] {themes}"
    return {
        "id": f"liq-ind-{abs(hash(ko)) % (10**12)}",
        "published_at": None,
        "source": {
            "id": "reporter_liquidity",
            "name": f"지정기자 유동성 분석 · {author}",
            "region": "korea",
            "slant": None,
        },
        "url": (analysis.get("per_article") or [{}])[0].get("url") or "",
        "category": "liquidity_indicator",
        "commodities": [],
        "title": {
            "original": themes,
            "original_lang": "ko",
            "ko": ko,
        },
        "summary": analysis.get("headline_ko") or themes,
        "scores": {
            "commodity": 0,
            "diplomacy": 0,
            "region_weight": 1.0,
            "freshness": 1.0,
            "final": 7.5,
        },
        "rank_reasons": [f"indicator:{primary['id']}"] + list(analysis.get("reporter_signals") or [])[:4],
        "translation_status": "ok",
        "event_type": "liquidity_indicator",
        "indicators": analysis["top_indicators"][:5],
    }
