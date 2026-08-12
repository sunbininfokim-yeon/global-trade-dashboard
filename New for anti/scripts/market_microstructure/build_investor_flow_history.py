#!/usr/bin/env python3
"""Append or backfill KOSPI investor net-flow history from observed Naver EOD data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from fetch_kr_public_extras import fetch_naver_kospi_investor_flows  # noqa: E402
from market_microstructure.investor_flow_history import append_points  # noqa: E402


def _load(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": "kospi-investor-flow-history-v1", "points": []}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--append-only", action="store_true", help="Append rows already embedded in current micro snapshot")
    parser.add_argument("--live", action="store_true", help="Backfill observed Naver EOD rows")
    parser.add_argument("--lookback-days", type=int, default=60, help="Naver business-day query window for --live")
    parser.add_argument("--snapshot", type=Path, default=ROOT / "../../public/data/market_microstructure_v1.json")
    parser.add_argument("--out", type=Path, default=ROOT / "../../public/data/kospi_investor_flow_history_v1.json")
    args = parser.parse_args()
    if args.append_only == args.live:
        parser.error("pass exactly one of --append-only or --live")

    history = _load(args.out)
    if args.append_only:
        snap = json.loads(args.snapshot.read_text(encoding="utf-8"))
        flow_doc = ((snap.get("public_extras") or {}).get("kospi_investor_flows") or {})
    else:
        flow_doc = fetch_naver_kospi_investor_flows(lookback_days=max(1, args.lookback_days))
    history = append_points(
        history,
        list(flow_doc.get("history") or []),
        source=flow_doc.get("source"),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.out} ({history.get('n_points', 0)} points)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
