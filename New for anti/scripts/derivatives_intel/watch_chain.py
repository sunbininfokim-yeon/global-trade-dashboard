#!/usr/bin/env python3
"""CLI: intraday polling watcher for unusual options activity.

Free, so the constraint is politeness rather than cost. The CBOE chain is a
~15-minute-delayed snapshot, so polling faster than a few minutes tells you
nothing new — the default 5-minute interval is already ahead of the data.

Only *newly* flagged contracts alert; a strike that stays unusual all afternoon
notifies once, not sixty times.

    python watch_chain.py --tickers TSLA NVDA
    python watch_chain.py --interval 600 --send
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from derivatives_intel import cboe  # noqa: E402
from derivatives_intel.alerts import dispatch, format_unusual, resolve_sinks  # noqa: E402
from derivatives_intel.analyze import ChainRules, find_unusual  # noqa: E402
from derivatives_intel.httputil import make_session  # noqa: E402

log = logging.getLogger("watch_chain")

_stopping = False


def _handle_sigint(signum, frame) -> None:  # noqa: ARG001
    global _stopping
    _stopping = True
    log.info("stop requested — finishing current cycle")


def main() -> int:
    p = argparse.ArgumentParser(description="Poll CBOE chains for unusual options activity")
    p.add_argument("--config", type=Path, default=ROOT / "config" / "watchlist.json")
    p.add_argument("--tickers", nargs="*", default=None)
    p.add_argument("--interval", type=float, default=300.0, help="seconds between polls")
    p.add_argument("--min-notional", type=float, default=None)
    p.add_argument("--send", action="store_true", help="transmit alerts (default: print only)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.interval < 60:
        log.warning("interval %.0fs is below the data's own refresh rate; clamping to 60s",
                    args.interval)
        args.interval = 60.0

    cfg = json.loads(args.config.read_text(encoding="utf-8")) if args.config.exists() else {}
    tickers = args.tickers or cfg.get("tickers") or ["TSLA", "NVDA"]
    rules = ChainRules.from_dict(cfg.get("chain_rules", {}))
    if args.min_notional is not None:
        rules.min_notional = args.min_notional

    sinks = resolve_sinks(dry_run=not args.send)
    session = make_session()
    signal.signal(signal.SIGINT, _handle_sigint)

    seen: set[str] = set()
    asof = date.today()
    cycles = 0

    log.info("polling %s every %.0fs | min notional $%s",
             ", ".join(tickers), args.interval, f"{rules.min_notional:,.0f}")

    while not _stopping:
        cycles += 1
        for ticker in tickers:
            if _stopping:
                break
            chain = cboe.fetch_chain(session, ticker)
            if chain is None:
                continue
            for item in find_unusual(chain, rules, asof):
                # Re-alert if a contract's volume grows materially, not on every
                # poll: the key carries a coarse volume bucket.
                key = f"{item.contract.osi}:{item.volume // max(rules.min_volume, 1)}"
                if key in seen:
                    continue
                seen.add(key)
                dispatch(sinks, format_unusual(item))

        if _stopping:
            break
        time.sleep(args.interval)

    log.info("stopped after %d cycles, %d alerts", cycles, len(seen))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
