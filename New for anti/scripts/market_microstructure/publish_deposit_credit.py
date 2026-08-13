#!/usr/bin/env python3
"""Refresh public/data/deposit_credit_v1.json from FreeSIS (no API key needed).

The file had been assembled by hand, which is why it carried history_n=65 but
no history array: the UI could show today's deposit/credit levels but had
nothing to draw the credit overlay line against. fetch_freesis_funding_credit
already returns the daily series, so publishing is just writing what it gives
back, with schema/ui_ko carried over from the existing file.
"""

from __future__ import annotations

import json
from pathlib import Path

from fetch_freesis_credit import fetch_freesis_funding_credit

OUTPUT = Path(__file__).resolve().parents[2] / "public" / "data" / "deposit_credit_v1.json"


def main() -> int:
    payload = fetch_freesis_funding_credit()
    if payload.get("quality") != "observed":
        print(f"refusing to publish: {payload.get('note_ko')}")
        return 1

    existing = {}
    if OUTPUT.exists():
        existing = json.loads(OUTPUT.read_text(encoding="utf-8"))

    doc = {
        "schema": existing.get("schema", "deposit_credit_v1"),
        "as_of": payload["as_of"],
        "deposit_credit": payload,
        "ui_ko": existing.get("ui_ko", ""),
    }
    OUTPUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT} (as_of {payload['as_of']}, {payload['history_n']} days)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
