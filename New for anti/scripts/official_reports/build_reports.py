#!/usr/bin/env python3
"""CLI for official reports snapshot + label learning."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from official_reports.build import build_official_reports, write_json  # noqa: E402
from official_reports.score import append_label  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # default subcommand = build
    if not argv or argv[0] not in {"build", "label"}:
        argv = ["build"] + argv

    p = argparse.ArgumentParser(description="Official multi-country report intel")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Build snapshot")
    b.add_argument(
        "--output",
        type=Path,
        default=ROOT.parents[1] / "public" / "data" / "official_reports_v1.json",
    )
    b.add_argument("--limit", type=int, default=40)
    b.add_argument("--fixtures", type=Path, default=None)
    b.add_argument("--no-fetch", action="store_true")
    b.add_argument("--no-qra-detail", action="store_true")
    b.add_argument("--print-stats", action="store_true")

    lab = sub.add_parser("label", help="Record human label for learning")
    lab.add_argument("--series-id", required=True)
    lab.add_argument("--url", required=True)
    lab.add_argument("--title", default="")
    lab.add_argument("--label", required=True, choices=["promote", "keep", "drop"])
    lab.add_argument("--note", default="")

    args = p.parse_args(argv)

    if args.cmd == "label":
        append_label(
            ROOT / "cache" / "label_history.jsonl",
            series_id=args.series_id,
            url=args.url,
            title=args.title,
            label=args.label,
            note=args.note,
        )
        print("appended label", args.label, args.series_id)
        return 0

    doc = build_official_reports(
        limit=args.limit,
        fetch_live=not args.no_fetch and args.fixtures is None,
        fixture_dir=args.fixtures,
        fetch_qra_detail=not args.no_qra_detail,
    )
    write_json(doc, args.output)
    if args.print_stats:
        print(doc["stats"])
        print("dashboard", doc.get("dashboard_fields"))
        print("top:")
        for it in doc.get("ticker_items", [])[:8]:
            print(" -", it.get("series_id"), "|", (it["title"].get("ko") or it["title"]["original"])[:90])
        print("wrote", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
