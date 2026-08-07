#!/usr/bin/env python3
"""CLI: build derivatives_intel_v1 snapshot.

Every source is free and needs no API key.

    python build_derivatives.py                      # full run
    python build_derivatives.py --no-chain           # short-selling only
    python build_derivatives.py --no-fetch           # cache only, no network
    python build_derivatives.py --send               # actually notify
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from derivatives_intel.alerts import compose_digest, dispatch, resolve_sinks  # noqa: E402
from derivatives_intel.analyze import ChainRules  # noqa: E402
from derivatives_intel.build import build_derivatives_intel, write_json  # noqa: E402
from derivatives_intel.rehydrate import snapshots_from_doc  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Build options positioning + short-selling intel JSON")
    p.add_argument(
        "--output",
        type=Path,
        default=ROOT.parents[1] / "public" / "data" / "derivatives_intel_v1.json",
    )
    p.add_argument("--config", type=Path, default=ROOT / "config" / "watchlist.json")
    p.add_argument("--db", type=Path, default=ROOT / "cache" / "derivatives.sqlite")
    p.add_argument("--tickers", nargs="*", default=None, help="override the configured watchlist")
    p.add_argument("--no-fetch", action="store_true", help="use cached DB only; hit no network")
    p.add_argument("--no-chain", action="store_true", help="skip CBOE chains (short-selling only)")
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
    rules = ChainRules.from_dict(cfg.get("chain_rules", {}))

    doc = build_derivatives_intel(
        tickers=tickers,
        rules=rules,
        db_path=args.db,
        fetch_live=not args.no_fetch,
        with_chain=not args.no_chain,
        baseline_days=int(cfg.get("baseline_days", 20)),
        short_lookback_days=int(cfg.get("short_lookback_days", 40)),
    )

    write_json(doc, args.output)

    # Render the digest from the document we just wrote, so what gets sent is
    # exactly what the dashboard will render.
    digest = compose_digest(
        snapshots_from_doc(doc),
        doc.get("generated_at", "")[:16].replace("T", " ") + " UTC",
    )
    dispatch(resolve_sinks(dry_run=not args.send), digest)

    if args.print_stats:
        print(json.dumps(doc["stats"], ensure_ascii=False, indent=2))
        print(json.dumps(doc["feed_status"], ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
