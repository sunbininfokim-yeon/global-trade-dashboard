#!/usr/bin/env python3
"""Refresh board-derived sections of elections_calendar_master_v1.json.

World-national highlights remain curated separately. This command updates only the
sections derived from config/calendars for countries active in country_seed.json.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"
PUBLIC_PATH = ROOT.parents[1] / "public" / "data" / "elections_calendar_master_v1.json"
EXTRACTED_PATH = CONFIG / "extracted" / "elections_calendar_master_v1.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def event_sort_key(event: dict[str, Any]) -> tuple[int, str, str]:
    date = str(event.get("date") or "")
    return (0 if len(date) >= 10 and date[:4].isdigit() else 1, date, str(event.get("label_ko") or ""))


def main() -> int:
    seed = load_json(CONFIG / "country_seed.json")
    year = int(seed.get("year", 2026))
    base = load_json(EXTRACTED_PATH if EXTRACTED_PATH.exists() else PUBLIC_PATH)
    events: list[dict[str, Any]] = []
    as_of_values: list[str] = []
    board_countries: list[str] = []

    for country in seed.get("countries", []):
        iso3 = country.get("iso3")
        if not iso3:
            continue
        board_countries.append(iso3)
        calendar_path = CONFIG / "calendars" / f"{iso3.lower()}_{year}.json"
        if not calendar_path.exists():
            continue
        calendar = load_json(calendar_path)
        if isinstance(calendar.get("as_of"), str):
            as_of_values.append(calendar["as_of"])
        for event in calendar.get("events", []):
            row = dict(event)
            row["iso3"] = iso3
            row.setdefault("date_end", None)
            events.append(row)

    events.sort(key=event_sort_key)
    base["as_of"] = max(as_of_values) if as_of_values else base.get("as_of")
    base["generated_at"] = datetime.now(timezone.utc).isoformat()
    base["summary"] = {
        **(base.get("summary") or {}),
        "board_tracked_event_rows": len(events),
        "board_party_leadership_rows": sum(1 for event in events if event.get("type") == "party_leadership"),
        "board_countries": sorted(board_countries),
    }
    base["board_tracked_all_events"] = events
    base["party_leadership_and_conventions"] = [
        event for event in events if event.get("type") == "party_leadership"
    ]

    rendered = json.dumps(base, ensure_ascii=False, indent=2) + "\n"
    for path in (EXTRACTED_PATH, PUBLIC_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
