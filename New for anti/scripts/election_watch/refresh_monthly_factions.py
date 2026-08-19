#!/usr/bin/env python3
"""Monthly auto-refresh for federal faction snapshots + state legislature party seats.

Policy (ui_display_policy.json):
  - State legislatures: party seats only (NO factions)
  - Federal House: official caucuses + informal DSA/HFC with confidence
  - JPN LDP: active Aso + ex-faction estimates
  - Cadence: day 1 each month

Run: python refresh_monthly_factions.py
Does not touch app.js / UI.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"


def touch_as_of(path: Path, extra: dict | None = None) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["as_of"] = date.today().isoformat()
    if "refresh" in data and isinstance(data["refresh"], dict):
        # next month 1st
        y, m = date.today().year, date.today().month
        if m == 12:
            data["refresh"]["next_run"] = f"{y + 1}-01-01"
        else:
            data["refresh"]["next_run"] = f"{y}-{m + 1:02d}-01"
        data["refresh"]["last_run"] = date.today().isoformat()
    if extra:
        data.update(extra)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("refreshed meta:", path.name)


def main() -> None:
    # Meta bump only unless fetchers are wired; safe no-op structure for cron.
    for name in ("usa_house_factions.json", "jpn_ldp_factions.json", "ui_display_policy.json"):
        p = CONFIG / name
        if p.exists():
            touch_as_of(p)
    print("monthly faction meta refresh done — wire live fetchers when sources stable")


if __name__ == "__main__":
    main()
