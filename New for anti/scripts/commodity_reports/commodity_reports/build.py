"""Assemble commodity_reports_v1.json."""

from __future__ import annotations

import json
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any, Dict, Iterable, List, Optional

from .feeds import RawReport, report_id, fetch_fas_gain_pages, fetch_source, parse_fas_gain_cards, parse_feed, parse_html_list
from .gemini import GeminiAnnotator
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

    Series marked "covers_all": true (WASDE, EIA's STEO and AEO) are
    multi-commodity reports by construction: they go on every window they
    cover even when the headline happens to name only one ("STEO: oil
    demand to fall" still revises natural gas).
    """
    series = scorer.match_series(f"{title}\n{summary}".lower())
    if not series or not series.get("commodities"):
        return
    if not tagged.commodities:
        tagged.commodities = list(series["commodities"])
    elif series.get("covers_all") and scorer.match_series(title.lower()) is series:
        # Only when the headline is the release itself. A crude oil story
        # that cites "our STEO" in its body stays a crude oil story.
        tagged.commodities = list(dict.fromkeys(tagged.commodities + list(series["commodities"])))


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _collect_fixtures(
    sources: List[Dict[str, Any]], fixture_dir: Path, max_per: int, now: Optional[datetime] = None
):
    raw: List[RawReport] = []
    status: List[Dict[str, Any]] = []
    for s in sources:
        xml = fixture_dir / f"{s['id']}.xml"
        html = fixture_dir / f"{s['id']}.html"
        pages = fixture_dir / f"{s['id']}.pages.json"
        if s.get("kind") == "fas_gain_pages" and pages.exists():
            # {"<url>": "<html>"} for every list page and report page it reads.
            store = json.loads(pages.read_text(encoding="utf-8"))

            def fetch(url: str, store=store) -> str:
                if url not in store:
                    raise FileNotFoundError(url)
                return store[url]

            res = fetch_fas_gain_pages(s, fetch=fetch, max_items=max_per, now=now)
            raw.extend(res["items"])
            status.append({"source_id": s["id"], "ok": res["ok"], "count": len(res["items"]),
                           "error": res["error"], "mode": "fixture"})
            continue
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


# How far back the board keeps reports: every build re-adds the previous
# build's reports, so a report that has scrolled off its publisher's feed
# stays browsable (the panel pages through them) until it is this old. A
# source that lists older reports on purpose (GAIN: max_age_days 150) keeps
# them as long as it would list them. Dateless reports age from first_seen_at.
ARCHIVE_DAYS = 84
CARRY_OVER_DAYS = ARCHIVE_DAYS  # kept for callers that tune it (tests)


def source_home(src: Dict[str, Any]) -> Optional[str]:
    if src.get("home"):
        return src["home"]
    parts = urlsplit(src.get("url") or "")
    return f"{parts.scheme}://{parts.netloc}/" if parts.scheme in ("http", "https") and parts.netloc else None


def horizon_days(src: Optional[Dict[str, Any]]) -> int:
    return max(CARRY_OVER_DAYS, int(((src or {}).get("html") or {}).get("max_age_days") or 0))


def news_time(published: Optional[str], precision: Optional[str], first_seen: Optional[str],
              now: datetime) -> datetime:
    """When a report became news: its date, the end of its month for a
    month-only date, else when the pipeline first saw it, else now."""
    for raw in (published, first_seen):
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if raw is published and precision == "month":
            dt = dt + timedelta(days=30)
        return dt
    return now


def previous_raws(
    previous: Optional[Dict[str, Any]], sources: List[Dict[str, Any]], now: datetime
) -> Dict[str, List[RawReport]]:
    """The last build's published reports, back as RawReports per source.

    Rebuilt from the published items (headline, summary, link, date) plus the
    source's own config, then tagged and scored again like a fresh fetch --
    so a config or alias fix applies to carried reports too.
    """
    out: Dict[str, List[RawReport]] = {}
    if not previous:
        return out
    by_id = {s["id"]: s for s in sources}
    for item in previous.get("items") or []:
        src = by_id.get(item.get("source_id"))
        if not src:
            continue
        published = item.get("published_at")
        seen = news_time(published, item.get("published_precision"), item.get("first_seen_at"), now)
        if (now - seen).days > horizon_days(src):
            continue
        r = RawReport(
            source_id=src["id"],
            agency=src.get("agency", src["id"]),
            agency_ko=src.get("agency_ko", src.get("agency", src["id"])),
            url=item.get("url") or "",
            title=(item.get("title") or {}).get("original") or "",
            summary=item.get("summary") or "",
            published_at=published,
            lang=src.get("lang", "en"),
            weight=float(src.get("weight", 1.0)),
            default_country=src.get("default_country") or None,
            commodity_hint=list(src.get("commodity_hint") or []),
            scope_hint=src.get("scope_hint", "country"),
            date_precision=item.get("published_precision") or "day",
            market_only=bool(src.get("market_only")),
            commodity_from=src.get("commodity_from", "text"),
            commodity_scope=list(src.get("commodity_scope") or []),
            board=src.get("board") or None,
        )
        if r.url and r.title:
            out.setdefault(src["id"], []).append(r)
    return out


def _collect_live(
    sources: List[Dict[str, Any]], *, ua: str, timeout: float, max_per: int,
    carried: Optional[Dict[str, List[RawReport]]] = None,
):
    raw: List[RawReport] = []
    status: List[Dict[str, Any]] = []
    carried = carried or {}
    for s in sources:
        res = fetch_source(s, user_agent=ua, timeout=timeout, max_items=max_per,
                           known=carried.get(s["id"]))
        raw.extend(res["items"])
        row = {"source_id": res["source_id"], "ok": res["ok"], "count": res["count"],
               "error": res["error"], "mode": "live"}
        if res.get("note"):
            row["note"] = res["note"]
        previous = carried.get(s["id"]) or []
        if not res["ok"] and previous:
            # A publisher that blocked this one run (fas.usda.gov answers 403
            # to some runners and not others) keeps what it last published.
            raw.extend(previous)
            row["carried_over"] = len(previous)
        elif previous:
            # Reports that have scrolled off the publisher's feed since the
            # last build stay on the board, for paging back through, until
            # they pass the archive horizon (previous_raws drops those).
            fresh = {r.url for r in res["items"]}
            older = [r for r in previous if r.url not in fresh]
            raw.extend(older)
            if older:
                row["archived"] = len(older)
        status.append(row)
    return raw, status


def _dedupe(scored: Iterable[ScoredReport]) -> List[ScoredReport]:
    """One row per publication.

    Agencies cross-post the same release to several feeds (USDA's newsroom
    and ERS both announce the same outlook), so the URL is the identity --
    not the title, which the two feeds word differently.
    """
    best: "OrderedDict[str, ScoredReport]" = OrderedDict()
    titles = set()
    for item in sorted(scored, key=lambda x: -x.importance):
        key = item.url.split("?", 1)[0].rstrip("/").lower()
        # One publisher sometimes links the same post under two addresses
        # (ITA's feed: a permalink and a ?p= link); same source, same
        # headline is one report.
        title_key = (item.source_id, " ".join(item.title.lower().split()))
        if key not in best and title_key not in titles:
            best[key] = item
            titles.add(title_key)
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


BOARD_LIMIT = 200


def annotate_raws(raw: List[RawReport], sources: Dict[str, Dict[str, Any]],
                  previous: Optional[Dict[str, Any]], annotator: GeminiAnnotator) -> Dict[str, Dict[str, Any]]:
    """report id -> {"en", "ko", "control"?, "fresh"} for opted-in reports.

    Reused from the previous build when the same URL still carries the same
    headline; only new or re-titled headlines are sent.
    """
    prev: Dict[str, Dict[str, Any]] = {}
    for it in (previous or {}).get("items") or []:
        title = it.get("title") or {}
        if title.get("en"):
            prev[it.get("url") or ""] = {
                "original": title.get("original"), "en": title["en"], "ko": title.get("ko"),
                "control": {k: v for k, v in (it.get("control") or {}).items()
                            if k in ("measure", "items", "targets")} or None,
            }
    notes: Dict[str, Dict[str, Any]] = {}
    ask: List[Dict[str, Any]] = []
    for r in raw:
        src = sources.get(r.source_id) or {}
        if not (src.get("translate") or r.board):
            continue
        rid = report_id(r)
        if rid in notes:
            continue
        hit = prev.get(r.url)
        if hit and hit["original"] == r.title and (hit["control"] or not r.board):
            notes[rid] = {"en": hit["en"], "ko": hit["ko"], "fresh": False,
                          **({"control": hit["control"]} if hit["control"] else {})}
            continue
        ask.append({"key": rid, "title": r.title, "lang": r.lang, "control": bool(r.board)})
    for rid, res in annotator.annotate(ask).items():
        notes[rid] = {**res, "fresh": True}
    return notes


def control_record(src: Dict[str, Any], note: Dict[str, Any]) -> Dict[str, Any]:
    """The export-controls window's fields for one board item.

    issuer / issuer_body come from the source catalog (who published it);
    measure / items / targets are Gemini's reading of the headline, null
    until one has been made.
    """
    reading = note.get("control") or {}
    return {
        "issuer": src.get("issuer") or src.get("default_country"),
        "issuer_body": src.get("issuer_body") or src.get("agency"),
        "issuer_body_ko": src.get("agency_ko") or src.get("agency"),
        "measure": reading.get("measure"),
        "items": reading.get("items") or [],
        "targets": reading.get("targets") or [],
        "extracted_by": "gemini" if reading else None,
    }


def build_boards(reports: List[ScoredReport], *, limit: int = BOARD_LIMIT) -> Dict[str, List[str]]:
    """board -> report ids, newest first (dateless ones after, by importance)."""
    out: Dict[str, List[ScoredReport]] = {}
    for r in reports:
        if r.board:
            out.setdefault(r.board, []).append(r)
    return {
        name: [r.id for r in sorted(rows, key=lambda r: (_recency_sort_key(r), r.importance), reverse=True)[:limit]]
        for name, rows in out.items()
    }


def build_commodity_reports(
    *,
    fetch_live: bool = True,
    fixture_dir: Optional[Path] = None,
    per_bucket: int = 500,
    max_items: int = 5000,
    translate: bool = False,
    translate_limit: int = 60,
    annotator: Optional[GeminiAnnotator] = None,
    now: Optional[datetime] = None,
    previous_path: Optional[Path] = None,
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

    previous = None
    if fixture_dir:
        raw, feed_status = _collect_fixtures(sources, Path(fixture_dir), max_per, now)
    elif fetch_live:
        if previous_path and Path(previous_path).exists():
            try:
                previous = load_json(Path(previous_path))
            except (OSError, ValueError):
                previous = None
        raw, feed_status = _collect_live(
            sources, ua=ua, timeout=timeout, max_per=max_per,
            carried=previous_raws(previous, sources, now),
        )
    else:
        raw, feed_status = [], [{"source_id": "_", "ok": False, "count": 0,
                                 "error": "no_fetch", "mode": "none"}]

    # English (and Korean) headlines for sources that opt in, and a control
    # reading for export-control boards -- before tagging, so the English is
    # what the taggers see. Off without GEMINI_API_KEY.
    annotator = annotator or GeminiAnnotator()
    by_src = {s["id"]: s for s in sources}
    notes = annotate_raws(raw, by_src, previous, annotator)
    gemini_status = {
        "enabled": annotator.enabled, "model": annotator.model_used, "calls": annotator.calls,
        "annotated": sum(1 for n in notes.values() if n.get("fresh")),
        "reused": sum(1 for n in notes.values() if not n.get("fresh")),
        "error": annotator.error,
    }

    scored: List[ScoredReport] = []
    for r in raw:
        note = notes.get(report_id(r)) or {}
        tagged = tag_report(
            title=f"{r.title}\n{note['en']}" if note.get("en") else r.title,
            summary=r.summary,
            commodity_tagger=commodity_tagger,
            country_tagger=country_tagger,
            commodity_hint=r.commodity_hint,
            default_country=r.default_country,
            commodity_text=r.commodity_from,
        )
        # scope_hint lets a world publisher opt out of its own default: FAO's
        # untagged releases are world balance sheets, not FAO-the-country news.
        if r.scope_hint == "global" and tagged.country_source == "source_default":
            tagged.countries, tagged.scope, tagged.country_source = [], "global", "none"
        apply_series_commodity_fallback(tagged, scorer, r.title, r.summary)
        # A narrow publisher's off-topic piece loses its tags here and is then
        # dropped like any untagged item.
        if r.commodity_scope:
            tagged.commodities = [c for c in tagged.commodities if c in r.commodity_scope]
        item = scorer.score(r, tagged, now=now)
        # No commodity this dashboard tracks, or rejected outright (photo
        # galleries etc.) -- dropped, not queued anywhere. A review loop over
        # what got dropped is a real feature; it isn't built yet, so there is
        # nothing here pretending to be one.
        if item is None:
            continue
        if note.get("en"):
            item.title_en = note["en"]
            item.title_ko = item.title_ko or note.get("ko")
        if r.board:
            item.control = control_record(by_src.get(r.source_id) or {}, note)
        scored.append(item)

    # The board is the last ARCHIVE_DAYS (or a source's own longer window).
    # Some feeds carry a rolling archive years deep (NASS's ASB and news
    # feeds reach back to 2023); those stay out now that the panel pages
    # through history instead of showing the top eight.
    prev_first_seen = {
        it.get("id"): it.get("first_seen_at")
        for it in (previous or {}).get("items") or []
        if it.get("first_seen_at")
    }
    by_source = {s["id"]: s for s in sources}
    scored = [
        r for r in scored
        if (now - news_time(r.published_at, r.date_precision, prev_first_seen.get(r.id), now)).days
        <= horizon_days(by_source.get(r.source_id))
    ]

    reports = _dedupe(scored)[:max_items]

    if translate:
        from .translate import apply_korean_titles

        apply_korean_titles(reports, limit=translate_limit)

    index = build_index(reports, per_bucket=per_bucket)

    # Only ship the reports some window actually references. Everything else
    # is weight in a file the browser downloads on the static fallback path.
    boards = build_boards(reports)
    referenced = {rid for buckets in index.values() for ids in buckets.values() for rid in ids}
    referenced |= {rid for ids in boards.values() for rid in ids}
    items = [r.to_item() for r in reports if r.id in referenced]
    # The publisher's own site, so the card's agency name links there (the
    # title already links the report itself). A source's "home" wins; else
    # the scheme and host of the URL it is collected from.
    homes = {s["id"]: source_home(s) for s in sources}
    for it in items:
        if homes.get(it["source_id"]):
            it["agency_url"] = homes[it["source_id"]]
    # When this build first saw each report. List-page sources publish no
    # date, and the weekly favorites digest mails what is new in the last
    # week -- without this those reports (ANRPC, VRA, CONAB, USGS...) could
    # never be mailed. Carried from the previous build by id; never shown as
    # a publication date.
    first_seen = {
        it.get("id"): it.get("first_seen_at")
        for it in (previous or {}).get("items") or []
        if it.get("first_seen_at")
    }
    for it in items:
        it["first_seen_at"] = first_seen.get(it["id"]) or now.isoformat()

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
        "translation": gemini_status,
        # Named lists fed by a source regardless of commodity: board -> ids,
        # newest first. "cn_export_controls": MOFCOM's export-control bureau.
        "boards": boards,
        "commodity_labels": commodity_labels,
        "country_names": country_names,
        "index": index,
        "items": items,
    }


def write_json(doc: Dict[str, Any], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
