#!/usr/bin/env python3
"""CLI: live OPRA options-flow watcher.

Streams prints for the watchlist and fires an alert the moment a block or sweep
clears the thresholds. This is the billable path — it holds an open OPRA
subscription for as long as it runs, so treat it as something you switch on for
a session, not a daemon you forget about.

    DATABENTO_API_KEY=db-... python watch_flow.py --tickers TSLA NVDA
    DATABENTO_API_KEY=db-... python watch_flow.py --send --min-notional 2000000
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
from collections import deque
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from derivatives_intel.alerts import dispatch, format_alert, resolve_sinks  # noqa: E402
from derivatives_intel.analyze import FlowRules, detect_flow  # noqa: E402

log = logging.getLogger("watch_flow")

_stopping = False


def _handle_sigint(signum, frame) -> None:  # noqa: ARG001
    global _stopping
    _stopping = True
    log.info("stop requested — closing subscription")


def main() -> int:
    p = argparse.ArgumentParser(description="Live OPRA options flow watcher")
    p.add_argument("--config", type=Path, default=ROOT / "config" / "watchlist.json")
    p.add_argument("--tickers", nargs="*", default=None)
    p.add_argument("--min-notional", type=float, default=None)
    p.add_argument("--flush-seconds", type=float, default=2.0,
                   help="how long to buffer prints before running sweep detection")
    p.add_argument("--send", action="store_true", help="transmit alerts (default: print only)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    key = os.getenv("DATABENTO_API_KEY")
    if not key:
        log.error("DATABENTO_API_KEY is not set — the live feed needs it")
        return 2

    cfg = json.loads(args.config.read_text(encoding="utf-8")) if args.config.exists() else {}
    tickers = args.tickers or cfg.get("tickers") or ["TSLA", "NVDA"]
    rules = FlowRules.from_dict(cfg.get("flow_rules", {}))
    if args.min_notional is not None:
        rules.min_notional = args.min_notional

    sinks = resolve_sinks(dry_run=not args.send)
    signal.signal(signal.SIGINT, _handle_sigint)

    from derivatives_intel.flow_source import LiveFlowStream

    asof = date.today()
    buffer: deque = deque()
    seen: set[tuple] = set()
    flush_after = timedelta(seconds=args.flush_seconds)
    last_flush = datetime.now(timezone.utc)
    total = 0

    log.info("watching %s | min notional $%s", ", ".join(tickers), f"{rules.min_notional:,.0f}")

    with LiveFlowStream(key, tickers) as stream:
        for trade in stream.trades():
            if _stopping:
                break
            buffer.append(trade)
            total += 1

            now = datetime.now(timezone.utc)
            if now - last_flush < flush_after:
                continue

            alerts = detect_flow(list(buffer), rules, asof)
            for alert in alerts:
                fingerprint = (alert.contract.osi, alert.ts.isoformat(), alert.aggressor, alert.size)
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                dispatch(sinks, format_alert(alert))

            # Keep a tail one sweep-window long so a burst straddling the flush
            # boundary is still seen as a single sweep on the next pass.
            tail_cutoff = now - timedelta(milliseconds=rules.sweep_window_ms)
            tail = [t for t in buffer if t.ts >= tail_cutoff]
            buffer.clear()
            buffer.extend(tail)

            last_flush = now
            if len(seen) > 20_000:
                seen.clear()

    log.info("closed after %d prints, %d alerts", total, len(seen))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
