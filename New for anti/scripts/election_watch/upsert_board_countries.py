#!/usr/bin/env python3
"""Add or refresh selected countries in elections_board_v1.json without a full rebuild.

A full ``build_board.py`` run also re-derives USA ui_ready and several calendars
from inputs that other jobs refresh on their own schedule. To add a country
without touching those, this script builds the board in memory (no betting
fetch) and copies only the named countries' rows into the published board:

* a new country is appended;
* an existing country is replaced.

Everything else stays byte-for-byte the same, apart from the country count in
``summary``.

    python3 upsert_board_countries.py ARM AZE ...
    python3 upsert_board_countries.py --check ARM AZE ...  # fail if rows differ
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from build_board import build_board  # noqa: E402

BOARD = ROOT.parents[1] / "public" / "data" / "elections_board_v1.json"


def upsert(board: dict, rows: dict) -> dict:
    out = dict(board)
    countries = list(board["countries"])
    index = {row["iso3"]: i for i, row in enumerate(countries)}
    for iso3, row in rows.items():
        if iso3 in index:
            countries[index[iso3]] = row
        else:
            countries.append(row)
    out["countries"] = countries
    summary = dict(board.get("summary") or {})
    summary["countries"] = len(countries)
    summary["countries_with_head"] = sum(1 for c in countries if c.get("head"))
    out["summary"] = summary
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("iso3", nargs="+")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    wanted = [code.upper() for code in args.iso3]
    built = build_board(fetch_betting=False)
    rows = {row["iso3"]: row for row in built["countries"] if row["iso3"] in wanted}
    missing = sorted(set(wanted) - set(rows))
    if missing:
        print(f"not in country_seed.json: {', '.join(missing)}", file=sys.stderr)
        return 1
    board = json.loads(BOARD.read_text(encoding="utf-8"))
    current = {row["iso3"]: row for row in board["countries"]}
    if args.check:
        stale = [iso3 for iso3, row in rows.items() if current.get(iso3) != row]
        if stale:
            print(f"board rows differ for {', '.join(stale)}; run upsert_board_countries.py", file=sys.stderr)
            return 1
        print(f"ok ({len(rows)} countries)")
        return 0
    BOARD.write_text(json.dumps(upsert(board, rows), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"upserted {', '.join(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
