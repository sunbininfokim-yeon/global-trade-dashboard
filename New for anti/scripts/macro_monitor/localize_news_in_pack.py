#!/usr/bin/env python3
"""Make the deployed pack's news queries/tags country-aware, in place.

series.spec.json keeps one news_query per indicator, written for the U.S. card
("US CPI inflation consumer prices BLS"). The engine localizes it per country at
build time (macro_monitor.series.localize_news_fields); this grafts the same
result onto an already-built macro_monitor_v1.json without a rebuild:
the country's name for "US", its own statistics agency (countries.json
"stats_agency") for BLS/BEA, and Fed/FOMC dropped -- in the query and the tags.

Only cards that carry the spec's U.S. default (raw, or the earlier agency-less
localization) are touched. Re-running is a no-op.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.series import localize_news_fields  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"
SPEC = ROOT / "config" / "series.spec.json"
COUNTRIES = ROOT / "config" / "countries.json"


def localize_pack(pack: dict, spec: dict, countries: dict) -> list[str]:
    spec_query = {s["id"]: s.get("news_query") for s in spec["series"]}
    by_iso = {c["iso3"]: c for c in countries["countries"]}
    changed: list[str] = []
    for country in pack["countries"]:
        iso3 = country["iso3"]
        cfg = by_iso.get(iso3) or {}
        name_en = country.get("name_en") or cfg.get("name_en")
        for ind in country.get("indicators") or []:
            if localize_news_fields(ind, iso3, name_en, cfg.get("stats_agency"), spec_query.get(ind.get("id"))):
                changed.append(f"{iso3}:{ind['id']}")
    return changed


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    countries = json.loads(COUNTRIES.read_text(encoding="utf-8"))
    changed = localize_pack(pack, spec, countries)
    if changed:
        PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"localized {len(changed)} card(s)" + (": " + ", ".join(changed) if changed else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
