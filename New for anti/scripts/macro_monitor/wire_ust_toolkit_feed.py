#!/usr/bin/env python3
"""Accumulate Treasury's debt-management releases (see macro_monitor/ust_toolkit_feed.py) in
config/ust_toolkit_feed_v1.json. Runs before wire_ust_auctions.py and wire_ust_maturity.py, which show it.

    python3 wire_ust_toolkit_feed.py

A source that cannot be read is skipped (exit 1); what was stored stays. Keyless.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import ust_toolkit_feed as tf  # noqa: E402
from macro_monitor import us_public_series as ups  # noqa: E402

STORE = ROOT / "config" / "ust_toolkit_feed_v1.json"
KEEP = 200


def main() -> int:
    doc = json.loads(STORE.read_text(encoding="utf-8")) if STORE.exists() else {"schema": "ust_toolkit_feed_v1", "items": []}
    fresh, errors = tf.fetch_fresh()
    items = tf.update(doc["items"], fresh, tf.page_text, ups.now_iso()[:10])[:KEEP]
    new = len(items) - len(doc["items"])
    if items != doc["items"]:
        doc["items"] = items
        STORE.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"toolkit feed: {len(fresh)} read, {max(new, 0)} new, {len(items)} kept")
    for it in items[:max(new, 0)]:
        print(f"  + {it['date']} [{it['kind']}] {it['title'][:90]}")
    for e in errors:
        print(f"  FAILED {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
