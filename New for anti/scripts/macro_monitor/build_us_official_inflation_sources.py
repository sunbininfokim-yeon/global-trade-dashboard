#!/usr/bin/env python3
"""Collect display-safe published inflation indicators from official Fed pages."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from macro_monitor.cpi.official_sources import (  # noqa: E402
    CLEVELAND_MEDIAN_URL,
    CLEVELAND_NOWCAST_URL,
    build_official_inflation_sources,
    fetch_text,
    parse_cleveland_median,
    parse_cleveland_nowcast,
)


DEFAULT_OUT = ROOT.parent.parent / "public" / "data" / "us_official_inflation_sources_v1.json"


def _read_or_fetch(path: Path | None, url: str) -> str:
    return path.read_text(encoding="utf-8") if path else fetch_text(url)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect official external U.S. inflation indicators")
    parser.add_argument("--nowcast-html", type=Path, help="Cached Cleveland Fed nowcast page")
    parser.add_argument("--median-html", type=Path, help="Cached Cleveland Fed Median CPI page")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--print-stats", action="store_true")
    args = parser.parse_args()

    nowcast = parse_cleveland_nowcast(_read_or_fetch(args.nowcast_html, CLEVELAND_NOWCAST_URL))
    median = parse_cleveland_median(_read_or_fetch(args.median_html, CLEVELAND_MEDIAN_URL))
    doc = build_official_inflation_sources(nowcast, median)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if args.print_stats:
        headline = doc["published_indicators"][0]
        underlying = doc["published_indicators"][1]
        print(f"wrote {args.out}")
        print(f"Cleveland nowcast {headline['monthly_pct']['reference_period']}: CPI {headline['monthly_pct']['cpi_pct']:+.2f}% / core {headline['monthly_pct']['core_cpi_pct']:+.2f}%")
        print(f"Cleveland underlying {underlying['year_over_year_pct']['reference_period']}: median {underlying['year_over_year_pct']['median_cpi_pct']:+.2f}% / trimmed {underlying['year_over_year_pct']['trimmed_mean_cpi_pct']:+.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
