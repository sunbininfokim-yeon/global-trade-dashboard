#!/usr/bin/env python3
"""Merge build_fed_qeqt_buckets.py's output into fed_qe_qt_history_v1.json.

Kept as a separate step from build_fed_qeqt_buckets.py (which only talks to
the NY Fed) so the CUSIP fetch -- the slow, network-bound part, ~10 minutes
for a decade of months -- never has to re-run just to change how the merge
itself works.

wire_fed_qeqt.py copies fed_qe_qt_history_v1.json's `rows` into the pack
wholesale and does not know about buckets; running this first, before that,
is what gets bucket detail into the pack without touching wire_fed_qeqt.py.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "public" / "data"
HISTORY = ROOT / "fed_qe_qt_history_v1.json"
BUCKETS = ROOT / "fed_qeqt_buckets_v1.json"


def main() -> int:
    history = json.loads(HISTORY.read_text(encoding="utf-8"))
    buckets = json.loads(BUCKETS.read_text(encoding="utf-8"))

    by_month = {r["month"]: r for r in buckets["rows"]}
    matched = 0
    for row in history["rows"]:
        b = by_month.get(row["month"])
        if b:
            row["buckets"] = {"treasuries": b["treasuries"], "mbs": b["mbs"]}
            matched += 1

    history["bucket_detail"] = {
        "source": buckets["source"],
        "coverage": f"{buckets['rows'][0]['month']} ~ {buckets['rows'][-1]['month']}",
        "tsy_bucket_labels": buckets["tsy_bucket_labels"],
        "mbs_bucket_labels": buckets["mbs_bucket_labels"],
        "limitations": buckets["limitations"],
    }

    HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                       encoding="utf-8")
    print(f"merged bucket detail onto {matched}/{len(history['rows'])} rows "
          f"({buckets['rows'][0]['month']} ~ {buckets['rows'][-1]['month']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
