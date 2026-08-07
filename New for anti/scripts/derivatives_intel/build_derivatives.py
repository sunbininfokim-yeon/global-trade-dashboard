#!/usr/bin/env python3
"""CLI: build derivatives_intel_v1 snapshot (end-of-day batch).

    # free sources only — no API key, no cost
    python build_derivatives.py --no-flow

    # with options flow, cost-capped, printing the digest instead of sending
    DATABENTO_API_KEY=db-... python build_derivatives.py --max-cost 0.50

    # actually notify (requires TELEGRAM_* or DISCORD_WEBHOOK_URL)
    python build_derivatives.py --send
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from derivatives_intel.alerts import compose_digest, dispatch, resolve_sinks  # noqa: E402
from derivatives_intel.analyze import FlowRules  # noqa: E402
from derivatives_intel.build import build_derivatives_intel, write_json  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Build options-flow + short-selling intel JSON")
    p.add_argument(
        "--output",
        type=Path,
        default=ROOT.parents[1] / "public" / "data" / "derivatives_intel_v1.json",
    )
    p.add_argument("--config", type=Path, default=ROOT / "config" / "watchlist.json")
    p.add_argument("--db", type=Path, default=ROOT / "cache" / "derivatives.sqlite")
    p.add_argument("--tickers", nargs="*", default=None, help="override the configured watchlist")
    p.add_argument("--session", type=date.fromisoformat, default=None, help="flow session date (YYYY-MM-DD)")
    p.add_argument("--no-fetch", action="store_true", help="use cached DB only; hit no network")
    p.add_argument("--no-flow", action="store_true", help="skip Databento entirely (free run)")
    p.add_argument("--max-cost", type=float, default=None, help="hard cap on the Databento quote, USD")
    p.add_argument("--send", action="store_true", help="transmit the digest (default: print only)")
    p.add_argument("--print-stats", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    cfg = json.loads(args.config.read_text(encoding="utf-8")) if args.config.exists() else {}
    tickers = args.tickers or cfg.get("tickers") or ["TSLA", "NVDA"]
    rules = FlowRules.from_dict(cfg.get("flow_rules", {}))
    max_cost = args.max_cost if args.max_cost is not None else float(cfg.get("max_cost_usd", 1.0))

    key = None if args.no_flow else os.getenv("DATABENTO_API_KEY")
    if not args.no_flow and not key:
        logging.warning("DATABENTO_API_KEY not set — running free sources only")

    doc = build_derivatives_intel(
        tickers=tickers,
        rules=rules,
        db_path=args.db,
        fetch_live=not args.no_fetch,
        flow_session=args.session,
        databento_key=key,
        max_cost_usd=max_cost,
        baseline_days=int(cfg.get("baseline_days", 20)),
        short_lookback_days=int(cfg.get("short_lookback_days", 40)),
    )

    write_json(doc, args.output)

    # Rebuild snapshots for the digest straight from the document we just wrote,
    # so what gets sent is exactly what the dashboard will render.
    digest = _digest_from_doc(doc)
    sinks = resolve_sinks(dry_run=not args.send)
    dispatch(sinks, digest)

    if args.print_stats:
        print(json.dumps(doc["stats"], ensure_ascii=False, indent=2))
        print(json.dumps(doc["feed_status"], ensure_ascii=False, indent=2))

    return 0


def _digest_from_doc(doc: dict) -> str:
    """Render the digest from the emitted JSON (no re-collection)."""
    from datetime import datetime

    from derivatives_intel.models import (
        FlowAlert,
        OptionContract,
        ShortInterestRow,
        ShortVolumeRow,
        TickerSnapshot,
    )

    snaps: list[TickerSnapshot] = []
    for entry in doc.get("tickers", []):
        sv = entry.get("short_volume")
        si = entry.get("short_interest")
        snap = TickerSnapshot(
            symbol=entry["symbol"],
            short_volume=None
            if not sv
            else ShortVolumeRow(
                date=date.fromisoformat(sv["date"]),
                symbol=entry["symbol"],
                short_volume=sv["short_volume"],
                short_exempt_volume=sv["short_exempt_volume"],
                total_volume=sv["total_volume"],
                markets=sv.get("markets", ""),
            ),
            short_ratio_mean_20d=entry.get("short_ratio_mean_20d"),
            short_ratio_z=entry.get("short_ratio_z"),
            short_interest=None
            if not si
            else ShortInterestRow(
                settlement_date=date.fromisoformat(si["settlement_date"]),
                symbol=entry["symbol"],
                current_short=si["current_short"],
                previous_short=si["previous_short"],
                avg_daily_volume=si["avg_daily_volume"],
                days_to_cover=si.get("days_to_cover"),
                change_pct=si.get("change_pct"),
            ),
            call_premium=entry.get("call_premium", 0.0),
            put_premium=entry.get("put_premium", 0.0),
        )
        for a in entry.get("flow_alerts", []):
            snap.flow_alerts.append(
                FlowAlert(
                    contract=OptionContract(
                        osi=a["osi"],
                        underlying=a["underlying"],
                        expiry=date.fromisoformat(a["expiry"]),
                        right=a["right"],
                        strike=a["strike"],
                    ),
                    ts=datetime.fromisoformat(a["ts"]),
                    kind=a["kind"],
                    aggressor=a["aggressor"],
                    sentiment=a["sentiment"],
                    size=a["size"],
                    notional=a["notional"],
                    vwap=a["vwap"],
                    venues=a["venues"],
                    prints=a["prints"],
                    dte=a["dte"],
                )
            )
        snaps.append(snap)

    return compose_digest(snaps, doc.get("generated_at", "")[:16].replace("T", " ") + " UTC")


if __name__ == "__main__":
    raise SystemExit(main())
