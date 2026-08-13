#!/usr/bin/env python3
"""Enrich a KFA UI snapshot from its embedded normalised filing facts.

This command is deliberately offline.  It is useful for fixtures and for
snapshots that already contain the accounting inputs.  A plain Basic-only UI
sample cannot become a live SEC/OpenDART calculation: unavailable source facts
remain null with reasons.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dart_kfa.derived_cards import enrich_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich a KFA JSON snapshot with expert cards/models")
    parser.add_argument("input", type=Path, help="existing kfa_<code>_v1.json")
    parser.add_argument("--output", type=Path, help="output path; defaults to input only with --write")
    parser.add_argument("--write", action="store_true", help="overwrite input after enrichment")
    args = parser.parse_args()
    if args.write and args.output:
        parser.error("use either --write or --output, not both")
    if not args.write and not args.output:
        parser.error("refusing to overwrite: pass --output or --write")

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    output = enrich_snapshot(payload)
    destination = args.input if args.write else args.output
    assert destination is not None
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
