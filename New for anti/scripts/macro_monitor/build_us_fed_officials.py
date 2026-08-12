#!/usr/bin/env python3
"""Collect official Fed FOMC/Beige Book facts and rebuild the quality snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from build_us_macro_quality import DEFAULT_OUT, DEFAULT_SPEC, build_snapshot  # noqa: E402
from macro_monitor.us_quality.fed import build_fed_official_input  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect official Fed FOMC and Beige Book facts")
    parser.add_argument("--years", type=int, default=2, help="Current calendar year plus this many prior years")
    parser.add_argument("--input-out", type=Path, default=ROOT / "cache" / "us_macro_quality" / "fed_official_input.json")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--print-stats", action="store_true")
    args = parser.parse_args()

    current_year = date.today().year
    years = range(current_year - max(args.years - 1, 0), current_year + 1)
    inputs = build_fed_official_input(years=years)
    args.input_out.parent.mkdir(parents=True, exist_ok=True)
    args.input_out.write_text(json.dumps(inputs, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    snapshot = build_snapshot(inputs, spec, generated_at=generated_at)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if args.print_stats:
        print(f"wrote {args.input_out}")
        print(f"wrote {args.out}")
        print(f"meetings={len(inputs['fomc_meetings'])} documents={len(inputs['official_documents'])} errors={len(inputs['collector']['errors'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
