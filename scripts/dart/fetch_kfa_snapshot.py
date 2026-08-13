#!/usr/bin/env python3
"""Fetch one company's live OpenDART data and write a kfa_<code>_v1.json snapshot.

Requires DART_API_KEY in the environment -- see dart_kfa/dart_facts.py. Without
it, fetch_xbrl_facts returns {} (no network call) and the resulting snapshot
has every card null + reason="missing:not_in_opendart"; this script still
writes it and warns, rather than silently producing a plausible-looking file.

corp_code is OpenDART's internal 8-digit id, not the 6-digit KRX stock code --
look it up via OpenDART's corpCode.xml, or reuse an already-verified value
(Samsung Electronics=00126380, SK Hynix=00164779).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dart_kfa.snapshot_builder import build_kfa_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("corp_code", help="OpenDART 8-digit corp_code")
    parser.add_argument("stock_code", help="KRX 6-digit stock code")
    parser.add_argument("name_ko", help="entity name, Korean")
    parser.add_argument("name_eng", help="entity name, English")
    parser.add_argument("--year", type=int, required=True, help="fiscal year (bsns_year), e.g. 2025")
    parser.add_argument("--fs-div", default="CFS", choices=["CFS", "OFS"], help="consolidated (default) or separate")
    parser.add_argument(
        "--output", type=Path,
        help="defaults to New for anti/public/data/kfa_<stock_code>_v1.json",
    )
    args = parser.parse_args()

    snapshot = build_kfa_snapshot(
        args.corp_code, args.stock_code, args.name_ko, args.name_eng, args.year, args.fs_div,
    )

    dq = snapshot["data_quality"]
    if not dq["live_key_present"]:
        print("WARNING: DART_API_KEY not set -- every card will be null + reason. Export it and rerun.")
    elif dq["facts_fetched"] == 0:
        print("WARNING: 0 facts fetched -- check corp_code/year/fs_div are correct for this filer.")

    output = args.output or (
        Path(__file__).resolve().parent.parent.parent
        / "New for anti" / "public" / "data" / f"kfa_{args.stock_code}_v1.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output} ({dq['facts_fetched']} facts fetched)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
