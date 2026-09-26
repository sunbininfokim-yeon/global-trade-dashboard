"""Assemble commodity_reports_v1.json."""

from __future__ import annotations

import json
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from .feeds import RawReport, fetch_source, parse_fas_gain_cards, parse_feed, parse_html_list
from .score import ReportScorer, ScoredReport
from .tag import CommodityTagger, CountryTagger, Tagged, tag_report

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
CACHE = ROOT / "cache"

# The bucket key for reports that name no country: world balance sheets,
# which every country view on that commodity should still be able to show.
GLOBAL_BUCKET = "_global"


def apply_series_commodity_fallback(
    tagged: Tagged, scorer: ReportScorer, title: str, summary: str
) -> None:
    """Give a bare series wrapper headline the commodities it actually covers.

    "USDA releases September WASDE" names no crop -- the report itself
    revises a dozen of them -- so the text tagger finds nothing and the
    "no commodity, no window" gate in score.py would drop it outright, right
    when it's the most authoritative report in the bucket. Only fires when
    the text-based tagger found nothing at all; a report that already names
    a crop keeps that, series list or not.
    """
    if tagged.commodities:
        return
    series = scorer.match_series(f"{title}\n{summary}".lower())
    if series and series.get("commodities"):
        tagged.commodities = list(series["commodities"])


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _collect_fixtures(sources: List[Dict[str, Any]], fixture_dir: Path, max_per: int):
    raw: List[RawReport] = []
    status: List[Dict[str, Any]] = []
    for s in sources:
        xml = fixture_dir / f"{s['id']}.xml"
        html = fixture_dir / f"{s['id']}.html"
        if xml.exists():
            items = parse_feed(xml.read_text(encoding="utf-8", errors="replace"), s, max_per)
        elif html.exists():
            body = html.read_text(encoding="utf-8", errors="replace")
            if s.get("kind") == "fas_gain_cards":
                items = parse_fas_gain_cards(body, s, max_per)
            else:
                items = parse_html_list(body, s)
        else:
            status.append({"source_id": s["id"], "ok": False, "count": 0,
                           "error": "fixture_missing", "mode": "fixture"})
            continue
        raw.extend(items)
        status.append({"source_id": s["id"], "ok": True, "count": len(items),
                       "error": None, "mode": "fixture"})
    return raw, status


def _collect_live(sources: List[Dict[str, Any]], *, ua: str, timeout: float, max_per: int):
    raw: List[RawReport] = []
    status: List[Dict[str, Any]] = []
    for s in sources:
        res = fetch_source(s, user_agent=ua, timeout=timeout, max_items=max_per)
        raw.extend(res["items"])
        status.append({"source_id": res["source_id"], "ok": res["ok"], "count": res["count"],
                       "error": res["error"], "mode": "live"})
    return raw, status


def _dedupe(scored: Iterable[ScoredReport]) -> List[ScoredReport]:
    """One row per publication.

    Agencies cross-post the same release to several feeds (USDA's newsroom
    and ERS both announce the same outlook), so the URL is the identity --
    not the title, which the two feeds word differently.
    """
    best: "OrderedDict[str, ScoredReport]" = OrderedDict()
    for item in sorted(scored, key=lambda x: -x.importance):
        parts = urlsplit(item.url)
        # EIA uses detail.php?id=...: removing every query merges different articles.
        params = [(k,v) for k,v in parse_qsl(parts.query, keep_blank_values=True)
                  if not k.lower().startswith('utm_') and k.lower() not in {'fbclid','gclid'}]
        key = urlunsplit((parts.scheme.lower(),parts.netloc.lower(),parts.path.rstrip('/'),urlencode(sorted(params)),''))
        if key not in best:
            best[key] = item
    return list(best.values())


def _recency_sort_key(report: ScoredReport) -> tuple:
    """Newest first within a bucket; dateless reports sink to the bottom.

    ISO 8601 UTC strings (what published_at always is once parsed) compare
    correctly as plain strings, so no datetime parsing is needed here.
    """
    has_date = report.published_at is not None
    return (has_date, report.published_at or "")


def build_index(
    reports: List[ScoredReport], *, per_bucket: int
) -> Dict[str, Dict[str, List[str]]]:
    """commodity -> country (or _global) -> report ids, newest first.

    A report tagged with two commodities lands on both windows; one tagged
    with two countries lands on both country cards. That duplication is the
    point -- "Argentina's drought lifts US soybean exports" is a real entry on
    both boards -- and the index holds ids, not copies, so it stays cheap.

    Which reports make a bucket's cap is still decided by importance (a named
    series and a real figure should win a slot over routine administrative
    notices) -- only the order they're then shown in is by date. Sorting by
    importance throughout looked like a bug in practice: the day's top NASS
    release could sit below a multi-year-old procedural notice just because
    the notice's series carries slightly more weight.
    """
    by_id = {r.id: r for r in reports}
    index: Dict[str, Dict[str, List[str]]] = {}
    for r in sorted(reports, key=lambda x: -x.importance):
        buckets = r.countries if r.scope == "country" else [GLOBAL_BUCKET]
        for commodity in r.commodities:
            per_commodity = index.setdefault(commodity, {})
            for bucket in buckets:
                rows = per_commodity.setdefault(bucket, [])
                if len(rows) < per_bucket and r.id not in rows:
                    rows.append(r.id)
    for buckets in index.values():
        for ids in buckets.values():
            ids.sort(key=lambda rid: _recency_sort_key(by_id[rid]), reverse=True)
    return index


def build_commodity_reports(
    *,
    fetch_live: bool = True,
    fixture_dir: Optional[Path] = None,
    per_bucket: int = 8,
    max_items: int = 500,
    translate: bool = False,
    translate_limit: int = 60,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    sources_cfg = load_json(CONFIG / "sources.json")
    commodities_cfg = load_json(CONFIG / "commodities.json")
    countries_cfg = load_json(CONFIG / "countries.json")
    series_cfg = load_json(CONFIG / "series_catalog.json")

    commodity_tagger = CommodityTagger.from_config(commodities_cfg)
    country_tagger = CountryTagger.from_config(countries_cfg)
    scorer = ReportScorer(series_cfg, label_history_path=CACHE / "label_history.jsonl")

    ua = sources_cfg.get("user_agent", "GTradeCommodityReports/1.0")
    timeout = float(sources_cfg.get("fetch_timeout_sec", 22))
    max_per = int(sources_cfg.get("max_items_per_source", 40))
    sources = [s for s in sources_cfg.get("sources", []) if s.get("enabled", True)]

    if fixture_dir:
        raw, feed_status = _collect_fixtures(sources, Path(fixture_dir), max_per)
    elif fetch_live:
        raw, feed_status = _collect_live(sources, ua=ua, timeout=timeout, max_per=max_per)
    else:
        raw, feed_status = [], [{"source_id": "_", "ok": False, "count": 0,
                                 "error": "no_fetch", "mode": "none"}]

    scored: List[ScoredReport] = []
    for r in raw:
        tagged = tag_report(
            title=r.title,
            summary=r.summary,
            commodity_tagger=commodity_tagger,
            country_tagger=country_tagger,
            commodity_hint=r.commodity_hint,
            default_country=r.default_country,
        )
        # scope_hint lets a world publisher opt out of its own default: FAO's
        # untagged releases are world balance sheets, not FAO-the-country news.
        if r.scope_hint == "global" and tagged.country_source == "source_default":
            tagged.countries, tagged.scope, tagged.country_source = [], "global", "none"
        apply_series_commodity_fallback(tagged, scorer, r.title, r.summary)
        item = scorer.score(r, tagged, now=now)
        # No commodity this dashboard tracks, or rejected outright (photo
        # galleries etc.) -- dropped, not queued anywhere. A review loop over
        # what got dropped is a real feature; it isn't built yet, so there is
        # nothing here pretending to be one.
        if item is None:
            continue
        scored.append(item)

    reports = _dedupe(scored)[:max_items]

    if translate:
        from .translate import apply_korean_titles

        apply_korean_titles(reports, limit=translate_limit)

    index = build_index(reports, per_bucket=per_bucket)

    # Only ship the reports some window actually references. Everything else
    # is weight in a file the browser downloads on the static fallback path.
    referenced = {rid for buckets in index.values() for ids in buckets.values() for rid in ids}
    items = [r.to_item() for r in reports if r.id in referenced]

    commodity_labels = {
        key: meta.get("label_ko") or key
        for key, meta in (commodities_cfg.get("commodities") or {}).items()
    }
    country_names = {
        iso: {"name": meta.get("name") or iso, "name_ko": meta.get("name_ko") or iso}
        for iso, meta in (countries_cfg.get("countries") or {}).items()
    }

    bucket_count = sum(len(b) for b in index.values())
    return {
        "schema_version": "commodity-reports-v1",
        "generated_at": now.isoformat(),
        "model": {
            "name": "commodity_reports_v1",
            "description": (
                "Official crop/energy/metal reports tagged (commodity × country) so the "
                "dashboard's stage-2 country window can show what was published about that "
                "country's commodity. The report's text picks the country, not the publisher: "
                "a USDA release on Brazilian wheat belongs on BRA·wheat."
            ),
            "buckets": "index[commodity][ISO3 | _global] -> item ids, most important first",
            "learning": {
                "label_file": "scripts/commodity_reports/cache/label_history.jsonl",
                "labels": ["promote", "keep", "drop"],
                "how": "build_reports.py label --series-id ... --label promote; next build re-weights that series.",
            },
            "per_bucket_limit": per_bucket,
        },
        "stats": {
            "sources_ok": sum(1 for s in feed_status if s.get("ok")),
            "sources_failed": sum(1 for s in feed_status if not s.get("ok")),
            "raw_items": len(raw),
            "scored": len(scored),
            "published": len(items),
            "commodities": len(index),
            "buckets": bucket_count,
        },
        "feed_status": feed_status,
        "commodity_labels": commodity_labels,
        "country_names": country_names,
        "index": index,
        "items": items,
    }


def write_json(doc: Dict[str, Any], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
