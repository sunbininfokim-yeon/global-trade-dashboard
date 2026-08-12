#!/usr/bin/env python3
"""Build one U.S. CPI structure snapshot from a single BLS release vintage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from macro_monitor.cpi import build_cpi_structure, fetch_release_tables  # noqa: E402
from macro_monitor.cpi.bls import load_mapping  # noqa: E402


DEFAULT_MAPPING = ROOT / "config" / "cpi_structure.map.json"
DEFAULT_OUT = ROOT.parent.parent / "public" / "data" / "us_cpi_structure_v1.json"


def _read(path: Path | None) -> str | None:
    return path.read_text(encoding="utf-8") if path else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Build U.S. CPI contribution/structure snapshot")
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--table2-html", type=Path, help="Saved BLS Table 2 HTML for this release")
    parser.add_argument("--table6-html", type=Path, help="Saved BLS Table 6 HTML for this release")
    parser.add_argument("--table7-html", type=Path, help="Saved BLS Table 7 HTML for this release")
    parser.add_argument("--no-table2", action="store_true")
    parser.add_argument("--print-stats", action="store_true")
    args = parser.parse_args()

    supplied = [args.table6_html, args.table7_html]
    if args.table2_html and not all(supplied):
        parser.error("--table2-html requires --table6-html and --table7-html from the same release")
    if any(supplied) and not all(supplied):
        parser.error("--table6-html and --table7-html must be supplied together")
    if all(supplied):
        tables = {
            "one_month": _read(args.table6_html),
            "twelve_month": _read(args.table7_html),
            "detail": None if args.no_table2 else _read(args.table2_html),
        }
    else:
        tables = fetch_release_tables()
        if args.no_table2:
            tables["detail"] = None

    doc = build_cpi_structure(
        one_month_html=tables["one_month"] or "",
        twelve_month_html=tables["twelve_month"] or "",
        detail_html=tables.get("detail"),
        mapping=load_mapping(args.mapping),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if args.print_stats:
        print(f"wrote {args.out}")
        print(f"release={doc['release_month']} mapped={doc['coverage']['mapped_components']}")
        for row in doc["drivers"]["one_month"]["top_positive"]:
            print(f"  up: {row['label_ko']} {row['effect']:+.3f}pp")
        for row in doc["drivers"]["one_month"]["top_negative"]:
            print(f"  down: {row['label_ko']} {row['effect']:+.3f}pp")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
