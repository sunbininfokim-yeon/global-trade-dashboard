#!/usr/bin/env python3
"""Official releases and press articles beside the US macro cards (see macro_monitor/card_news.py).

    python3 wire_card_news.py

Runs last among the card builders (after wire_ust_toolkit_feed.py, whose Treasury feed it reuses, and after every
wire that rebuilds a US card -- wire_us_monetary.py, wire_ust_auctions.py, ... -- which would drop the news otherwise). A feed or query that fails keeps the card's
previous list; exit status 1 names what failed. Keyless.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import card_news as cn  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    usa = next(c for c in pack["countries"] if c["iso3"] == "USA")
    present = {i["id"] for i in usa.get("indicators") or []}
    feeds, errors = cn.fetch_feeds()
    treasury = cn.treasury_items()
    google = cn.google_reader()
    official, press = {}, {}
    for card in cn.CARDS:
        if card not in present:
            continue
        srcs = cn.CARDS[card][0]
        if all(s.split(":")[0] in ("bls", "treasury", "link") or s.split(":")[0] in feeds for s in srcs):
            official[card] = cn.official_for(card, feeds, treasury)
        try:
            press[card] = cn.press_for(card, google, date.today())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"press {card}: {exc}")
    changed = cn.apply(usa, official, press)
    if changed:
        PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"card news: {len(official)} official, {len(press)} press lists; changed {len(changed)}")
    for card in official:
        print(f"  {card:20s} official {len(official[card]):2d}  press {len(press.get(card, [])):2d}")
    for e in errors:
        print(f"  FAILED {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
