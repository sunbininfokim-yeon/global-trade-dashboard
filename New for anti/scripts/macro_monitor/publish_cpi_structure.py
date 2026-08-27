#!/usr/bin/env python3
"""Publish the CPI relationship map to public/data/, where the browser can reach it.

config/cpi_structure.map.json is the source of truth (hand-curated, edited
directly), but scripts/ is entirely excluded from the deployed asset bundle
(.assetsignore: "Everything here would otherwise be downloadable straight
from the site" -- true of the Python pipeline, not of this reference data).
mmEnsureCpiStructure() in macro.js already tries
/public/data/us_cpi_structure_v1.json first, ahead of a
/scripts/macro_monitor/... fallback that works against a local dev server
but returns the SPA's index.html (200, not JSON) in production -- this
script is what makes the preferred path actually exist.

Run this after editing the map by hand; there is no build step in between,
just a copy, so nothing here needs re-deriving.
"""

from __future__ import annotations

import json
from pathlib import Path

SRC = Path(__file__).resolve().parent / "config" / "cpi_structure.map.json"
OUT = Path(__file__).resolve().parents[2] / "public" / "data" / "us_cpi_structure_v1.json"


def main() -> int:
    doc = json.loads(SRC.read_text(encoding="utf-8"))
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"published {SRC} -> {OUT}")
    print(f"  {len(doc.get('relationships', []))} relationships, {len(doc.get('items', []))} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
