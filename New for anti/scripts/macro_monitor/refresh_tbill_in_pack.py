#!/usr/bin/env python3
"""Add real T-bill auction sizes to the QRA 만기별 tab (and the TGA mirror).

Reads the current TBAC quarter from qra_engine_v1.json, pulls that quarter's
bill auctions (+ bills outstanding) from Fiscal Data, writes
public/data/tbill_issuance_v1.json, and grafts the result onto the deployed
macro pack. Does not rebuild the pack. Weekly workflow: tbill_issuance_refresh.yml.

    python3 refresh_tbill_in_pack.py

refresh_qra_quarters_in_pack.py re-applies the stored file after it resets the
components to coupons, so a QRA refresh does not drop the bill rows.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.qra import tbill  # noqa: E402

DATA = ROOT.parent.parent / "public" / "data"
ENGINE = DATA / "qra_engine_v1.json"
PACK = DATA / "macro_monitor_v1.json"
OUT = DATA / "tbill_issuance_v1.json"


def current_quarter_label(engine: dict) -> str | None:
    latest_id = (engine.get("latest") or {}).get("id")
    event = next((e for e in engine.get("events") or [] if e.get("id") == latest_id), {})
    tbac = event.get("tbac_financing") or {}
    return tbac.get("quarter_label") if tbac.get("parse_ok") else None


def graft_from_file(pack: dict, block: dict) -> bool:
    usa = next(c for c in pack["countries"] if c.get("iso3") == "USA")
    return tbill.graft({i["id"]: i for i in usa["indicators"]}, block)


def main() -> int:
    engine = json.loads(ENGINE.read_text(encoding="utf-8"))
    label = current_quarter_label(engine)
    window = tbill.quarter_window(label or "")
    if not window:
        print(f"no readable TBAC quarter in the engine file (label={label!r}); nothing written", file=sys.stderr)
        return 1

    rows = tbill.fetch_bill_auctions(window["start"], window["end"])
    outstanding = None
    try:
        outstanding = tbill.fetch_bills_outstanding(3)
    except Exception as exc:  # the outstanding line is context, not the row itself
        print(f"bills outstanding unavailable: {exc}", file=sys.stderr)
    block = tbill.summarize(rows, quarter_label=label, window=window, outstanding=outstanding)
    if not block["n_auctions"]:
        print(block["reason_missing"], file=sys.stderr)
        return 1

    OUT.write_text(json.dumps(block, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    if not graft_from_file(pack, block):
        print("pack has no USA qra_issuance indicator", file=sys.stderr)
        return 1
    PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(tbill.note_ko(block))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
