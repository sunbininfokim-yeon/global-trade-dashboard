#!/usr/bin/env python3
"""US Treasury coupon auction results and buybacks -> two USA liquidity cards (see macro_monitor/ust_auctions.py).

    python3 wire_ust_auctions.py

Writes public/data/ust_auctions_v1.json (the rows) and upserts `ust_auction_demand` and `ust_buybacks` into
the pack. A source that cannot be read leaves its card as it was. Keyless.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import ust_auctions as ua  # noqa: E402
from macro_monitor import us_public_series as ups  # noqa: E402

DATA = ROOT.parent.parent / "public" / "data"
PACK = DATA / "macro_monitor_v1.json"
OUT = DATA / "ust_auctions_v1.json"


def main() -> int:
    now, failures, cards = ups.now_iso(), [], []
    auctions = buybacks = None
    try:
        auctions = ua.fetch_auctions()
        cards.append(ua.auction_card(auctions, now))
    except Exception as exc:  # noqa: BLE001
        failures.append(f"auctions: {exc}")
    try:
        buybacks = ua.fetch_buybacks()
        cards.append(ua.buyback_card(buybacks, now))
    except Exception as exc:  # noqa: BLE001
        failures.append(f"buybacks: {exc}")

    if auctions or buybacks:
        prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
        doc = {"schema_version": "ust_auctions_v1",
               "source": "TreasuryDirect securities API (auctions), Fiscal Data buybacks_operations",
               "auctions": auctions if auctions is not None else prev.get("auctions", []),
               "buybacks": buybacks if buybacks is not None else prev.get("buybacks", [])}
        if doc != {k: v for k, v in prev.items() if k != "retrieved_at"}:
            OUT.write_text(json.dumps({**doc, "retrieved_at": now}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    text = PACK.read_text(encoding="utf-8")
    pack = json.loads(text)
    usa = next(c for c in pack["countries"] if c["iso3"] == "USA")
    old = {i["id"]: i for i in usa["indicators"]}
    for c in cards:
        prev = old.get(c["id"])
        if prev and {**prev, "retrieved_at": None} == {**c, "retrieved_at": None}:
            c["retrieved_at"] = prev.get("retrieved_at")       # a quiet day leaves the pack untouched
        ua.upsert(usa, c)
        print(f"{c['id']}: {c['display']}  ({c['reference_period']})")
    out = json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if out != text:
        PACK.write_text(out, encoding="utf-8")
    for f in failures:
        print(f"  FAILED {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
