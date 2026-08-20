#!/usr/bin/env python3
"""Link headline and core into one switch inside the inflation drawer.

Headline and core CPI are the same measurement with one exclusion between
them, and reading one almost always means checking the other -- but they are
separate chips, so comparing meant closing the drawer, finding the neighbouring
chip, and losing the YoY/MoM and 5y/10y choices on the way. This adds a peer
list so the drawer can swap the series in place and keep those choices.

The pairs stay separate indicators. CPI and PCE come from different agencies
on different release calendars, so they are two groups, not four options in
one: swapping headline CPI for core PCE in a single click would invite reading
the step between them as a move.
"""

from __future__ import annotations

import json
from pathlib import Path

PACK = Path(__file__).resolve().parents[2] / "public" / "data" / "macro_monitor_v1.json"

GROUPS = [
    {"group": "us_cpi", "label_ko": "지수",
     "options": [("cpi_yoy", "헤드라인 CPI"), ("core_cpi_yoy", "근원 CPI")]},
    {"group": "us_pce", "label_ko": "지수",
     "options": [("pce_yoy", "헤드라인 PCE"), ("core_pce_yoy", "근원 PCE")]},
]


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    usa = next(c for c in pack["countries"] if c["iso3"] == "USA")
    by_id = {i["id"]: i for i in usa["indicators"]}

    wired = []
    for spec in GROUPS:
        present = [(iid, lbl) for iid, lbl in spec["options"] if iid in by_id]
        # A one-sided switch is worse than none: it implies a second option the
        # drawer cannot actually reach.
        if len(present) < 2:
            print(f"  skip {spec['group']}: only {[i for i, _ in present]} present")
            continue
        peers = {
            "group": spec["group"],
            "label_ko": spec["label_ko"],
            "options": [{"id": iid, "label_ko": lbl} for iid, lbl in present],
        }
        for iid, _ in present:
            by_id[iid]["peers"] = peers
        wired.append((spec["group"], [i for i, _ in present]))

    # Chips carry the same link so the drawer has it before any peer swap.
    for chips in (usa.get("categories") or {}).values():
        for ch in chips:
            src = by_id.get(ch.get("id"))
            if src and src.get("peers"):
                ch["peers"] = src["peers"]

    PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")
    for g, ids in wired:
        print(f"wired {g}: {' <-> '.join(ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
