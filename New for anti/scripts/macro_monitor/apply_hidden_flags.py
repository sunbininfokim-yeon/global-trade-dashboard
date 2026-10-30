#!/usr/bin/env python3
"""Hide every card that has no observed source (data_status "demo"), and unhide it again as soon as a
pipeline gives it real data. Recomputed from scratch on every run, so the flag never goes stale.

    python3 apply_hidden_flags.py

The card, its chip and its headline all get `hidden: true`; macro.js skips hidden ones and disables a
tab whose cards are all hidden. Nothing is deleted: the fixture stays in the pack, ready to come back
when a source is wired. config/hidden_cards_v1.json can force a card either way ({"show": [...],
"hide": [...]} of "ISO:id").
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"
OVERRIDES = ROOT / "config" / "hidden_cards_v1.json"
HIDDEN_STATUSES = {"demo"}


def should_hide(iso3: str, ind: dict, overrides: dict) -> bool:
    key = f"{iso3}:{ind['id']}"
    if key in overrides.get("show", []):
        return False
    if key in overrides.get("hide", []):
        return True
    return ind.get("data_status") in HIDDEN_STATUSES


def _set(obj: dict, hide: bool) -> bool:
    if hide and not obj.get("hidden"):
        obj["hidden"] = True
        return True
    if not hide and "hidden" in obj:
        del obj["hidden"]
        return True
    return False


def apply(pack: dict, overrides: dict | None = None) -> dict[str, int]:
    overrides = overrides or {}
    counts: dict[str, int] = {}
    for country in pack["countries"]:
        iso3 = country["iso3"]
        hide = {i["id"]: should_hide(iso3, i, overrides) for i in country.get("indicators") or []}
        for ind in country.get("indicators") or []:
            _set(ind, hide[ind["id"]])
        status = {i["id"]: i.get("data_status") for i in country.get("indicators") or []}
        for chips in (country.get("categories") or {}).values():
            for chip in chips:
                _set(chip, hide.get(chip["id"], False))
                if status.get(chip["id"]) and chip.get("data_status") != status[chip["id"]]:
                    chip["data_status"] = status[chip["id"]]        # the chip's badge follows its card
        for h in country.get("headlines") or []:
            _set(h, hide.get(h.get("id"), False))
        counts[iso3] = sum(hide.values())
    return counts


def main() -> int:
    text = PACK.read_text(encoding="utf-8")
    pack = json.loads(text)
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8")) if OVERRIDES.exists() else {}
    counts = apply(pack, overrides)
    out = json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if out != text:
        PACK.write_text(out, encoding="utf-8")
    print(f"hidden cards: {sum(counts.values())} -- " + ", ".join(f"{k} {v}" for k, v in counts.items() if v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
