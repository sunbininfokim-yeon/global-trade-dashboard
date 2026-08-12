"""Build ticker_v1 snapshot from RSS sources."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .importance import ImportanceModel
from .rss import RawItem, parse_feed_xml, safe_fetch_source
from .score import (
    NewsScorer,
    apply_regional_and_taiwan_balance,
    dedupe,
    filter_by_importance,
)
from .translate import apply_korean_titles

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
LABEL_HISTORY = ROOT / "cache" / "importance_label_history.jsonl"


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_ticker(
    *,
    limit: int = 40,
    fetch_live: bool = True,
    translate: bool = False,
    translate_email: Optional[str] = None,
    fixture_dir: Optional[Path] = None,
    sources_path: Optional[Path] = None,
) -> Dict[str, Any]:
    sources_cfg = load_json(sources_path or (CONFIG_DIR / "sources.json"))
    commodities_cfg = load_json(CONFIG_DIR / "commodities.json")
    diplomacy_cfg = load_json(CONFIG_DIR / "diplomacy.json")
    regions_cfg = load_json(CONFIG_DIR / "regions.json")
    elections_cfg = load_json(CONFIG_DIR / "elections.json")
    politics_extra = load_json(CONFIG_DIR / "politics_extra.json")
    importance_cfg = load_json(CONFIG_DIR / "importance.json")

    importance_model = ImportanceModel(importance_cfg, label_history=LABEL_HISTORY)
    scorer = NewsScorer(
        commodities_cfg,
        diplomacy_cfg,
        regions_cfg,
        elections_cfg,
        politics_extra=politics_extra,
        importance_model=importance_model,
    )
    raw_items: List[RawItem] = []
    feed_status: List[Dict[str, Any]] = []

    sources = [s for s in sources_cfg.get("sources", []) if s.get("enabled", True)]
    ua = sources_cfg.get("user_agent", "GTradeTicker/1.0")
    timeout = float(sources_cfg.get("fetch_timeout_sec", 18))
    max_per = int(sources_cfg.get("max_items_per_source", 40))

    if fixture_dir:
        fixture_dir = Path(fixture_dir)
        for source in sources:
            fp = fixture_dir / f"{source['id']}.xml"
            if not fp.exists():
                feed_status.append(
                    {
                        "source_id": source["id"],
                        "ok": False,
                        "count": 0,
                        "error": "fixture_missing",
                    }
                )
                continue
            body = fp.read_bytes()
            items = parse_feed_xml(
                body,
                source_id=source["id"],
                source_name=source.get("name", source["id"]),
                region=source.get("region", "west"),
                source_lang=source.get("lang", "en"),
                slant=source.get("slant"),
                commodities_focus=source.get("commodities_focus"),
                max_items=max_per,
            )
            raw_items.extend(items)
            feed_status.append(
                {
                    "source_id": source["id"],
                    "ok": True,
                    "count": len(items),
                    "error": None,
                    "mode": "fixture",
                }
            )
    elif fetch_live:
        for source in sources:
            result = safe_fetch_source(
                source, user_agent=ua, timeout=timeout, max_items=max_per
            )
            raw_items.extend(result["items"])
            feed_status.append(
                {
                    "source_id": result["source_id"],
                    "ok": result["ok"],
                    "count": result["count"],
                    "elapsed_ms": result["elapsed_ms"],
                    "error": result["error"],
                    "mode": "live",
                }
            )
    else:
        feed_status.append(
            {
                "source_id": "_",
                "ok": False,
                "count": 0,
                "error": "fetch disabled and no fixtures",
            }
        )

    scored = []
    for raw in raw_items:
        item = scorer.score(raw)
        if item is not None:
            scored.append(item)

    scored = dedupe(scored)
    min_imp = float(importance_cfg.get("min_importance", 0.35))
    ticker_cap = int(importance_cfg.get("ticker_cap", limit))
    effective_limit = min(limit, ticker_cap) if ticker_cap > 0 else limit
    scored = filter_by_importance(scored, min_importance=min_imp)
    selected = apply_regional_and_taiwan_balance(
        scored, limit=effective_limit, regions_cfg=regions_cfg
    )

    cache_path = ROOT / "cache" / "translation_cache.json"
    cache: Dict[str, str] = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cache = {}

    apply_korean_titles(
        selected, enabled=translate, email=translate_email, cache=cache
    )

    if translate and cache:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    region_hist: Dict[str, int] = {}
    for it in selected:
        region_hist[it.region] = region_hist.get(it.region, 0) + 1

    generated_at = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": "ticker-v1",
        "generated_at": generated_at,
        "model": {
            "name": "commodity_diplomacy_rss_v1",
            "description": (
                "RSS multi-region ticker: regional priority (MENA/IN/TR/JP/CN/TW/RU + "
                "commodity specialists) over Western majors; politics admitted with "
                "diplomacy+trade bridge, elections, governance polls, cabinet reshuffles; "
                "horse-race national polls rejected; importance = country-tier × info-grade; "
                "main display language Korean."
            ),
            "main_display_lang": regions_cfg.get("main_display_lang", "ko"),
            "ip_lang_map": regions_cfg.get("ip_country_to_lang", {}),
            "default_lang": regions_cfg.get("default_lang", "en"),
            "importance": {
                "formula": importance_cfg.get("formula"),
                "min_importance": min_imp,
                "ticker_cap": ticker_cap,
                "label_history": str(LABEL_HISTORY.name),
            },
            "polls": {
                "reject_horserace": True,
                "admit_governance": True,
            },
            "cabinet_reshuffle": bool(
                (politics_extra.get("cabinet_reshuffle") or {}).get("admit", True)
            ),
        },
        "stats": {
            "sources_ok": sum(1 for s in feed_status if s.get("ok")),
            "sources_failed": sum(1 for s in feed_status if not s.get("ok")),
            "raw_items": len(raw_items),
            "scored_items": len(scored),
            "selected_items": len(selected),
            "region_histogram": region_hist,
            "min_importance": min_imp,
        },
        "feed_status": feed_status,
        "items": [it.to_public() for it in selected],
    }


def write_ticker(doc: Dict[str, Any], output: Path) -> None:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
