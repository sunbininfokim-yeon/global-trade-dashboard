#!/usr/bin/env python3
"""Hide every card that has no observed source (data_status "demo"), and unhide it again as soon as a
pipeline gives it real data. Recomputed from scratch on every run, so the flag never goes stale.

    python3 apply_hidden_flags.py

The card, its chip and its headline all get `hidden: true`; macro.js skips hidden ones and disables a
tab whose cards are all hidden. Nothing is deleted: the fixture stays in the pack, ready to come back
when a source is wired. config/hidden_cards_v1.json can force a card either way ({"show": [...],
"hide": [...]} of "ISO:id").

Cards attached through config/free_cards_v1.json are also hidden when they stopped working: the
entry was switched off after the card went live (its source is the entry's), or the daily read has
failed FREE_CARD_FAIL_HIDE times in a row (config/free_cards_status_v1.json). Either clears itself
once the entry is back on and reads again.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"
OVERRIDES = ROOT / "config" / "hidden_cards_v1.json"
FREE_REGISTRY = ROOT / "config" / "free_cards_v1.json"
FREE_STATUS = ROOT / "config" / "free_cards_status_v1.json"
HIDDEN_STATUSES = {"demo"}
FREE_CARD_FAIL_HIDE = 5          # daily runs; a monthly card's last value is still right for a few days


def broken_free_cards(registry: list[dict], status: dict, pack: dict) -> list[str]:
    """ "ISO:id" of free cards to hide: switched off after going live, or failing for days."""
    by_key = {f"{c['iso3']}/{i['id']}": i for c in pack["countries"] for i in c.get("indicators") or []}
    out = []
    for e in registry:
        key = f"{e['iso3']}/{e['id']}"
        card = by_key.get(key)
        if not card:
            continue
        if not e.get("enabled", True):
            if card.get("source") == e.get("source"):
                out.append(key.replace("/", ":"))
        elif int((status.get(key) or {}).get("consecutive_failures") or 0) >= FREE_CARD_FAIL_HIDE:
            out.append(key.replace("/", ":"))
    return out


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
    if FREE_REGISTRY.exists():
        registry = json.loads(FREE_REGISTRY.read_text(encoding="utf-8"))
        registry = registry.get("cards", registry) if isinstance(registry, dict) else registry
        status = json.loads(FREE_STATUS.read_text(encoding="utf-8")) if FREE_STATUS.exists() else {}
        broken = broken_free_cards(registry, status, pack)
        if broken:
            print(f"free cards hidden as broken: {', '.join(broken)}")
        overrides = {**overrides, "hide": [*overrides.get("hide", []), *broken]}
    counts = apply(pack, overrides)
    out = json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if out != text:
        PACK.write_text(out, encoding="utf-8")
    print(f"hidden cards: {sum(counts.values())} -- " + ", ".join(f"{k} {v}" for k, v in counts.items() if v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
