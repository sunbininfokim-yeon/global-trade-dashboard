#!/usr/bin/env python3
"""CLI for the commodity report snapshot and its label-learning loop."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from commodity_reports.build import build_commodity_reports, write_json  # noqa: E402
from commodity_reports.score import append_label  # noqa: E402

DEFAULT_OUTPUT = ROOT.parents[1] / "public" / "data" / "commodity_reports_v1.json"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in {"build", "label"}:
        argv = ["build"] + argv

    parser = argparse.ArgumentParser(description="Official commodity report intel")
    sub = parser.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Build the snapshot")
    b.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    b.add_argument("--per-bucket", type=int, default=500,
                   help="Reports kept per commodity × country window. A backstop, "
                        "not a page size: the archive horizon is what ages items "
                        "out, and the panel pages through whatever is kept")
    b.add_argument("--max-items", type=int, default=5000)
    b.add_argument("--fixtures", type=Path, default=None)
    b.add_argument("--no-fetch", action="store_true")
    b.add_argument("--translate", action="store_true",
                   help="Korean headlines via MyMemory (slow, free-tier quota)")
    b.add_argument("--translate-limit", type=int, default=60)
    b.add_argument("--print-stats", action="store_true")

    lab = sub.add_parser("label", help="Record a promote/keep/drop label for a series")
    lab.add_argument("--series-id", required=True)
    lab.add_argument("--url", default="")
    lab.add_argument("--title", default="")
    lab.add_argument("--label", required=True, choices=["promote", "keep", "drop"])
    lab.add_argument("--note", default="")

    args = parser.parse_args(argv)

    if args.cmd == "label":
        append_label(
            ROOT / "cache" / "label_history.jsonl",
            series_id=args.series_id,
            url=args.url,
            title=args.title,
            label=args.label,
            note=args.note,
        )
        print(f"appended {args.label} for {args.series_id}")
        return 0

    doc = build_commodity_reports(
        fetch_live=not args.no_fetch and args.fixtures is None,
        fixture_dir=args.fixtures,
        per_bucket=args.per_bucket,
        max_items=args.max_items,
        translate=args.translate,
        translate_limit=args.translate_limit,
        # A live build carries a failed source's last good reports forward
        # from the file it is about to overwrite.
        previous_path=args.output if args.fixtures is None else None,
    )
    write_json(doc, args.output)

    if args.print_stats:
        print(doc["stats"])
        # Counts and the model name only -- no headline text, no key.
        print("translation:", doc.get("translation"))
        for name, ids in sorted((doc.get("boards") or {}).items()):
            print(f"board {name}: {len(ids)}")
        failed = [s for s in doc["feed_status"] if not s.get("ok")]
        if failed:
            print("failed feeds:")
            for s in failed:
                print(f"  - {s['source_id']}: {s.get('error')}")
        print("windows:")
        for commodity, buckets in sorted(doc["index"].items()):
            shown = ", ".join(f"{k}({len(v)})" for k, v in list(buckets.items())[:8])
            print(f"  {commodity}: {shown}")
        print("wrote", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
