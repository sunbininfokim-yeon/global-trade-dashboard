"""Build elections_board_v1.json from country seed + news tags + betting markets."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from election_watch.betting import fetch_us_election_markets  # noqa: E402


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_board(
    *,
    seed_path: Optional[Path] = None,
    ticker_path: Optional[Path] = None,
    betting_cfg_path: Optional[Path] = None,
    year: Optional[int] = None,
    fetch_betting: bool = True,
) -> Dict[str, Any]:
    seed = load_json(seed_path or (ROOT / "config" / "country_seed.json"))
    year = year or int(seed.get("year") or datetime.now(timezone.utc).year)

    live_news: List[Dict[str, Any]] = []
    if ticker_path and Path(ticker_path).exists():
        ticker = load_json(Path(ticker_path))
        for it in ticker.get("items", []):
            cat = it.get("category")
            if cat in {"election", "cabinet_reshuffle"} or it.get("election_type"):
                live_news.append(
                    {
                        "title": (it.get("title") or {}).get("ko")
                        or (it.get("title") or {}).get("original"),
                        "url": it.get("url"),
                        "election_type": it.get("election_type"),
                        "category": cat,
                        "country_tier": it.get("country_tier"),
                        "info_grade": it.get("info_grade"),
                        "importance": (it.get("scores") or {}).get("importance"),
                        "source_region": (it.get("source") or {}).get("region"),
                        "published_at": it.get("published_at"),
                    }
                )

    countries_out = []
    for c in seed.get("countries", []):
        system = c.get("system", "presidential")
        parties = list(c.get("parties_tracked") or [])
        if system == "presidential":
            parties = parties[:2]
        else:
            parties = parties[:4]
        events = [
            e
            for e in (c.get("events_2026") or [])
            if str(e.get("date", "")).startswith(str(year)) or not e.get("date")
        ]
        countries_out.append(
            {
                "iso3": c.get("iso3"),
                "name_ko": c.get("name_ko"),
                "system": system,
                "ruling_party": c.get("ruling_party"),
                "parties_tracked": parties,
                "events": events,
                "events_this_year": len(events),
            }
        )

    countries_out.sort(
        key=lambda x: (-x["events_this_year"], x.get("name_ko") or x.get("iso3") or "")
    )

    betting_block: Dict[str, Any] = {
        "enabled": False,
        "markets": [],
        "note": "skipped",
    }
    if fetch_betting:
        bcfg = load_json(betting_cfg_path or (ROOT / "config" / "betting.json"))
        poly = bcfg.get("polymarket") or {}
        betting_block = fetch_us_election_markets(
            queries=list(poly.get("queries") or []),
            max_markets=int(poly.get("max_markets", 12)),
            timeout=float(poly.get("timeout_sec", 18)),
            enabled=bool(bcfg.get("enabled", True)),
        )
        # Optional optional ticker lines for high-volume markets (UI later)
        betting_block["ticker_hints"] = [
            {
                "event_type": "election_betting",
                "question": m.get("question"),
                "url": m.get("url"),
                "top_outcome": (m.get("outcomes") or [{}])[0] if m.get("outcomes") else None,
            }
            for m in (betting_block.get("markets") or [])[:5]
        ]

    return {
        "schema_version": "elections-board-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "year": year,
        "model": {
            "name": "election_watch_seed_v1",
            "description": (
                "World election board: system type, tracked parties "
                "(presidential: ruling+main opposition; parliamentary: up to 4 majors), "
                "calendar + live headlines. Governance approval polls admitted; horse-race "
                "national polls dropped at ticker. US prediction-market snapshot (Polymarket) "
                "during election cycles. Major cabinet reshuffles tracked as grade-1 news."
            ),
            "leadership_policy": seed.get("leadership_policy"),
            "polls": {
                "reject_horserace": True,
                "admit_governance": True,
            },
            "betting_source": "polymarket",
        },
        "summary": {
            "countries": len(countries_out),
            "countries_with_events": sum(1 for c in countries_out if c["events_this_year"] > 0),
            "live_election_headlines": len(live_news),
            "betting_markets": len(betting_block.get("markets") or []),
        },
        "countries": countries_out,
        "live_election_news": live_news[:40],
        "betting_markets": betting_block,
    }


def main() -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument(
        "--output",
        type=Path,
        default=ROOT.parents[1] / "public" / "data" / "elections_board_v1.json",
    )
    p.add_argument(
        "--ticker",
        type=Path,
        default=ROOT.parents[1] / "public" / "data" / "ticker_v1.json",
        help="Optional ticker JSON to attach election headlines",
    )
    p.add_argument("--year", type=int, default=None)
    p.add_argument("--no-betting", action="store_true", help="Skip Polymarket fetch")
    p.add_argument("--print-stats", action="store_true")
    args = p.parse_args()

    doc = build_board(ticker_path=args.ticker, year=args.year, fetch_betting=not args.no_betting)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.print_stats:
        print(doc["summary"])
        print("wrote", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
