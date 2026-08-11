#!/usr/bin/env python3
"""Label importance keys for cold priority tuning.

Examples:
  python3 label_importance.py promote --key tier:A --note "major country prior"
  python3 label_importance.py demote --key grade:3
  python3 label_importance.py drop --key UNK:election
  python3 label_importance.py promote --key USA:cabinet_reshuffle
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from commodity_news.importance import append_importance_label

DEFAULT_PATH = ROOT / "cache" / "importance_label_history.jsonl"
VALID = {"promote", "keep", "demote", "drop"}


def main() -> int:
    p = argparse.ArgumentParser(description="Append importance label (promote|keep|demote|drop)")
    p.add_argument("label", choices=sorted(VALID))
    p.add_argument("--key", required=True, help="e.g. tier:A, grade:3, USA:election")
    p.add_argument("--note", default="")
    p.add_argument("--path", type=Path, default=DEFAULT_PATH)
    args = p.parse_args()

    append_importance_label(args.path, key=args.key, label=args.label, note=args.note)
    print(f"appended {args.label} key={args.key} -> {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
