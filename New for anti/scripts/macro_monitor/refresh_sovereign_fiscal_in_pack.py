#!/usr/bin/env python3
"""Graft only the official sovereign fiscal cards into the deployed pack.

This deliberately does not rerun ``build_macro_monitor.py``: the live CPI/PCE,
Fed balance-sheet and other separately wired layers in macro_monitor_v1.json
must survive a fiscal refresh unchanged.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.engine import (  # noqa: E402
    _attach_sovereign_fiscal_indicators,
    _sort_chips,
)

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"
SPEC = ROOT / "config" / "series.spec.json"
TARGET_IDS = ("sovereign_debt", "sovereign_interest")


def _axis_from_country(indicators: list[dict]) -> list[str] | None:
    # Take the longest available window (typically 10y/120mo), not just the
    # first one >=24 months -- grabbing e.g. a 5y/60mo window here would
    # silently cap every fiscal history at 5 years, with the "10년" UI
    # toggle showing the same truncated range as "5년".
    best: list[str] | None = None
    for ind in indicators:
        for hist in (ind.get("history") or {}).values():
            dates = hist.get("dates") or []
            if len(dates) >= 24 and (best is None or len(dates) > len(best)):
                best = list(dates)
    return best


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    specs_doc = json.loads(SPEC.read_text(encoding="utf-8"))
    specs_by_id = {spec["id"]: spec for spec in specs_doc["series"]}
    refreshed: list[str] = []

    for country in pack.get("countries") or []:
        # Explicit product scope: the user wants UK only, not a Euro-area card.
        if country.get("iso3") == "EMU":
            continue
        indicators = country.get("indicators") or []
        dates = _axis_from_country(indicators)
        if not dates:
            continue
        by_id = {ind["id"]: ind for ind in indicators}
        old_positions = {sid: indicators.index(by_id[sid]) for sid in TARGET_IDS if sid in by_id}
        old_indicators = {sid: by_id[sid] for sid in TARGET_IDS if sid in by_id}
        # Keep the old cards if an upstream download was incomplete for this
        # country; never replace real data with an empty placeholder.
        for sid in TARGET_IDS:
            if sid in by_id:
                indicators.remove(by_id[sid])
                del by_id[sid]

        _attach_sovereign_fiscal_indicators(
            iso3=country["iso3"], specs_by_id=specs_by_id, cfg_map={}, dates=dates,
            by_id=by_id, indicators=indicators,
        )
        rebuilt = [sid for sid in TARGET_IDS if sid in by_id]
        if not rebuilt:
            # Restore older indicators if this source did not cover country.
            for sid, pos in sorted(old_positions.items(), key=lambda item: item[1]):
                indicators.insert(pos, old_indicators[sid])
            continue
        for sid in rebuilt:
            indicators.remove(by_id[sid])
        insert_at = min(old_positions.values()) if old_positions else len(indicators)
        for offset, sid in enumerate(TARGET_IDS):
            if sid in by_id:
                indicators.insert(insert_at + offset, by_id[sid])

        rates = (country.get("categories") or {}).get("rates") or []
        rates[:] = [chip for chip in rates if chip.get("id") not in TARGET_IDS]
        for sid in rebuilt:
            ind = by_id[sid]
            rates.append({
                "id": sid, "category": "rates", "label_ko": ind["label_ko"],
                "display": ind.get("display_chip") or ind.get("display"),
            })
        country["categories"]["rates"] = _sort_chips("rates", rates)
        refreshed.append(country["iso3"])

    PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"refreshed sovereign fiscal cards for {len(refreshed)} countries: {', '.join(refreshed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
