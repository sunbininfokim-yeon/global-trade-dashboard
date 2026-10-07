#!/usr/bin/env python3
"""Apply the P0 JSON audit contract to checked-in KFA static samples.

This does not fetch OpenDART, use an API key, or invent historical data.
"""

from __future__ import annotations

import json
from pathlib import Path

from dart_kfa.snapshot_adapter import enrich_legacy_snapshot


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "public" / "data"


def main() -> int:
    for path in sorted(DATA.glob("kfa_*_v1.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        enriched = enrich_legacy_snapshot(raw)
        path.write_text(json.dumps(enriched, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
