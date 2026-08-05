"""Build official_reports_v1.json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .extract import extract_for_series
from .fetch import RawReport, fetch_source, parse_html_list, parse_rss
from .score import OfficialScorer

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
CACHE = ROOT / "cache"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_official_reports(
    *,
    limit: int = 40,
    fetch_live: bool = True,
    fixture_dir: Optional[Path] = None,
    fetch_qra_detail: bool = True,
) -> Dict[str, Any]:
    sources_cfg = load_json(CONFIG / "sources.json")
    domains_cfg = load_json(CONFIG / "domains.json")
    series_cfg = load_json(CONFIG / "series_catalog.json")
    scorer = OfficialScorer(
        domains_cfg, series_cfg, label_history_path=CACHE / "label_history.jsonl"
    )

    ua = sources_cfg.get("user_agent", "GTradeOfficial/1.0")
    timeout = float(sources_cfg.get("fetch_timeout_sec", 22))
    max_per = int(sources_cfg.get("max_items_per_source", 30))
    sources = [s for s in sources_cfg.get("sources", []) if s.get("enabled", True)]

    raw: List[RawReport] = []
    feed_status: List[Dict[str, Any]] = []

    if fixture_dir:
        fixture_dir = Path(fixture_dir)
        for s in sources:
            fp = fixture_dir / f"{s['id']}.xml"
            hp = fixture_dir / f"{s['id']}.html"
            if fp.exists():
                items = parse_rss(fp.read_text(encoding="utf-8", errors="replace"), s, max_per)
                raw.extend(items)
                feed_status.append({"source_id": s["id"], "ok": True, "count": len(items), "mode": "fixture"})
            elif hp.exists():
                items = parse_html_list(hp.read_text(encoding="utf-8", errors="replace"), s)
                raw.extend(items)
                feed_status.append({"source_id": s["id"], "ok": True, "count": len(items), "mode": "fixture"})
            else:
                feed_status.append({"source_id": s["id"], "ok": False, "error": "fixture_missing"})
    elif fetch_live:
        for s in sources:
            res = fetch_source(s, user_agent=ua, timeout=timeout, max_items=max_per)
            raw.extend(res.get("items") or [])
            feed_status.append(
                {
                    "source_id": res["source_id"],
                    "ok": res["ok"],
                    "count": res.get("count", len(res.get("items") or [])),
                    "error": res.get("error"),
                    "mode": "live",
                }
            )
    else:
        feed_status.append({"source_id": "_", "ok": False, "error": "no_fetch"})

    scored = []
    for r in raw:
        item = scorer.score(r)
        if item:
            scored.append(item)

    # dedupe by url
    seen = set()
    deduped = []
    for it in sorted(scored, key=lambda x: x.significance, reverse=True):
        u = it.url.split("?", 1)[0].rstrip("/").lower()
        if u in seen:
            continue
        seen.add(u)
        deduped.append(it)

    selected = deduped[:limit]

    # extract indicators for top catalog hits
    indicators: List[Dict[str, Any]] = []
    for it in selected:
        if not it.series_id:
            continue
        try:
            ext = extract_for_series(
                it.series_id,
                url=it.url,
                title=it.title,
                summary=it.summary,
                user_agent=ua,
                fetch_detail=fetch_qra_detail and it.series_id == "US_QRA_MARKETABLE_BORROWING",
            )
        except Exception:
            ext = None
        it.extract = ext
        row = it.to_indicator_row()
        if row:
            indicators.append(row)

    # pending review: mid-significance without series (teach loop)
    pending = [
        {
            "title": x.title,
            "url": x.url,
            "country": x.country,
            "domains": x.domains,
            "significance": round(x.significance, 3),
            "suggest": "label promote|keep|drop + series_id later",
        }
        for x in deduped[limit : limit + 15]
        if not x.series_id
    ]

    # dashboard flat map from latest extracts
    dashboard: Dict[str, Any] = {}
    for ind in indicators:
        vals = ind.get("values") or {}
        for k in (
            "qra_next_net_borrowing_bn",
            "qra_end_cash_bn",
            "qra_vs_prior_bn",
            "beige_tone",
        ):
            if k in vals and vals[k] is not None:
                dashboard[k] = vals[k]

    ticker_items = [it.to_ticker_item() for it in selected]

    return {
        "schema_version": "official-reports-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": {
            "name": "official_reports_learnable_v1",
            "description": (
                "Official sources only (US/JP/CN/EU/UK public RSS·HTML). "
                "Domains: economy/finance/diplomacy/security/agriculture. "
                "Series catalog + label_history for collaborative learning. No Dropbox."
            ),
            "learning": {
                "label_file": "scripts/official_reports/cache/label_history.jsonl",
                "labels": ["promote", "keep", "drop"],
                "how": (
                    "Append JSONL rows when you decide a report is 의미 있음/없음; "
                    "next build adjusts series multipliers. New series go into series_catalog.json."
                ),
            },
        },
        "stats": {
            "sources_ok": sum(1 for s in feed_status if s.get("ok")),
            "sources_failed": sum(1 for s in feed_status if not s.get("ok")),
            "raw_items": len(raw),
            "scored": len(scored),
            "selected": len(selected),
            "indicators": len(indicators),
        },
        "feed_status": feed_status,
        "dashboard_fields": dashboard,
        "indicators": indicators,
        "ticker_items": ticker_items,
        "pending_review": pending,
        "items": ticker_items,
    }


def write_json(doc: Dict[str, Any], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
