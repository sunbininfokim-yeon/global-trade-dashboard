#!/usr/bin/env python3
"""Collect the weekly FIMA repo facility level (H.4.1) -> config/fima_repo_v1.json.

First run backfills --years years (default 5, about 260 page fetches, a few at a time);
every later run only fetches the Thursdays it does not have yet.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import h41_fima  # noqa: E402

OUT = ROOT / "config" / "fima_repo_v1.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", type=int, default=5, help="the H.4.1 page layout before 2021-08 is preformatted text this parser does not read")
    args = ap.parse_args()

    existing = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    rows = {r["wednesday"]: r for r in existing.get("weeks", [])}
    have_releases = {r["release"] for r in rows.values()}

    today = date.today()
    start = date(today.year - args.years, today.month, min(today.day, 28))
    wanted = [d for d in h41_fima.thursdays(start, today) if d not in have_releases]
    # a release moved off Thursday is stored under its real date, so skip a Thursday whose week is already held
    wanted = [d for d in wanted if not any(abs((date.fromisoformat(w) - date.fromisoformat(d)).days) <= 2 for w in rows)]
    print(f"{len(rows)} weeks held, {len(wanted)} to fetch", flush=True)

    def save(new_rows: list[dict]) -> None:
        merged = dict(rows)
        for r in new_rows:
            merged[r["wednesday"]] = r
        if not merged:
            return
        doc = {
            "schema_version": "fima-repo-v1",
            "source": "Federal Reserve H.4.1, Table 1: Repurchase agreements -> Foreign official (Wednesday level, $ millions)",
            "source_url": h41_fima.BASE + "/",
            "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "weeks": [merged[k] for k in sorted(merged)],
        }
        OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")
        print(f"  saved {len(doc['weeks'])} weeks", flush=True)

    new, problems = h41_fima.collect(wanted, on_chunk=save)
    if not OUT.exists():
        print("nothing collected; nothing written", file=sys.stderr)
        return 1
    doc = json.loads(OUT.read_text(encoding="utf-8"))
    print(f"FIMA repo: {len(doc['weeks'])} weeks, latest {doc['weeks'][-1]['wednesday']} = {doc['weeks'][-1]['foreign_official_mn']:.0f} $M -> {OUT}")
    for m in problems:
        print(f"  problem: {m}", file=sys.stderr)
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
