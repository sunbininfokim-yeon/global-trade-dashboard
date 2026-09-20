#!/usr/bin/env python3
"""Refresh board-derived sections of elections_calendar_master_v1.json.

board_tracked_all_events and party_leadership_and_conventions come from
config/calendars for countries in country_seed.json.

world_by_month is derived from those board events. A row enters the timeline
when its date is YYYY-MM-DD or YYYY-MM. Sentinel dates 없음/불명 are omitted
and printed so a missing cell is visible every run.

Curated world_by_month rows that are not yet on the board are carried forward
(A-1 must not drop them; lifting them onto the board is A-3).
World-national highlights remain curated separately.
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

SENTINEL_DATES = {"없음", "불명"}
TIMELINE_FIELDS = ("date", "iso3", "type", "label_en", "label_ko")
TYPE_LABEL_EN = {
    "presidential": "Presidential",
    "general": "General",
    "local": "Local",
    "by_election": "By-election",
    "party_leadership": "Party leadership",
    "party_convention": "Party convention",
    "leadership_review": "Leadership review",
    "speaker_election": "Speaker election",
    "referendum": "Referendum",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def event_sort_key(event: dict[str, Any]) -> tuple[int, str, str]:
    date = str(event.get("date") or "")
    return (0 if len(date) >= 10 and date[:4].isdigit() else 1, date, str(event.get("label_ko") or ""))


def date_kind(date: str) -> str:
    """Classify a date string: day, month, 없음, 불명, or other."""
    value = str(date or "").strip()
    if value in SENTINEL_DATES:
        return value
    if len(value) >= 10 and value[4] == "-" and value[7] == "-" and value[:4].isdigit():
        return "day"
    if len(value) == 7 and value[4] == "-" and value[:4].isdigit() and value[5:7].isdigit():
        return "month"
    if not value:
        return "empty"
    return "other"


def month_key(date: str) -> str | None:
    kind = date_kind(date)
    if kind in {"day", "month"}:
        return date[:7]
    return None


def curated_label_en(
    previous: dict[tuple[str, str], list[dict[str, Any]]],
    iso3: str,
    date: str,
    type_: str,
    label_ko: str,
) -> str | None:
    for row in previous.get((iso3, date), []):
        if row.get("type") == type_ and row.get("label_en"):
            return str(row["label_en"])
    for row in previous.get((iso3, date), []):
        if row.get("label_ko") == label_ko and row.get("label_en"):
            return str(row["label_en"])
    for row in previous.get((iso3, date), []):
        if row.get("label_en"):
            return str(row["label_en"])
    return None


def ensure_timeline_fields(
    event: dict[str, Any],
    *,
    previous: dict[tuple[str, str], list[dict[str, Any]]],
) -> dict[str, Any]:
    row = dict(event)
    iso3 = str(row.get("iso3") or "")
    date = str(row.get("date") or "")
    type_ = str(row.get("type") or "")
    label_ko = str(row.get("label_ko") or row.get("label_en") or "불명")
    label_en = (
        str(row["label_en"]).strip()
        if isinstance(row.get("label_en"), str) and row.get("label_en").strip()
        else None
    )
    if not label_en:
        label_en = curated_label_en(previous, iso3, date, type_, label_ko)
    if not label_en:
        label_en = TYPE_LABEL_EN.get(type_, "Election")
    row["date"] = date
    row["iso3"] = iso3
    row["type"] = type_ or "불명"
    row["label_ko"] = label_ko
    row["label_en"] = label_en
    for field in TIMELINE_FIELDS:
        if not row.get(field):
            raise ValueError(f"timeline row missing {field}: {row.get('id') or row}")
    return row


def month_sort_key(event: dict[str, Any]) -> tuple[int, str, str]:
    date = str(event.get("date") or "")
    kind = date_kind(date)
    # YYYY-MM rows go at the end of that month; day-precision rows stay chronological.
    bucket = 0 if kind == "day" else 1
    return (bucket, date, str(event.get("label_ko") or ""))


def index_world_by_month(
    world_by_month: dict[str, list[dict[str, Any]]] | None,
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    index: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for rows in (world_by_month or {}).values():
        for row in rows:
            key = (str(row.get("iso3") or ""), str(row.get("date") or ""))
            index.setdefault(key, []).append(row)
    return index


def derive_world_by_month(
    events: list[dict[str, Any]],
    previous_world: dict[str, list[dict[str, Any]]] | None,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, str]], int]:
    previous = index_world_by_month(previous_world)
    by_month: dict[str, list[dict[str, Any]]] = {}
    excluded: list[dict[str, str]] = []
    placed_keys: set[tuple[str, str]] = set()

    for event in events:
        date = str(event.get("date") or "")
        kind = date_kind(date)
        iso3 = str(event.get("iso3") or "")
        label_ko = str(event.get("label_ko") or "")
        if kind in {"day", "month"}:
            row = ensure_timeline_fields(event, previous=previous)
            if kind == "month":
                row.setdefault(
                    "date_note",
                    event.get("date_note") or event.get("notes") or "일자 공고 전, 월까지만 확정",
                )
            by_month.setdefault(row["date"][:7], []).append(row)
            placed_keys.add((iso3, date))
            continue
        reason = kind if kind in SENTINEL_DATES else f"날짜 형식 아님:{date or '(empty)'}"
        excluded.append(
            {
                "iso3": iso3,
                "date": date or "(empty)",
                "type": str(event.get("type") or ""),
                "label_ko": label_ko,
                "reason": reason,
            }
        )

    carried = 0
    for key, rows in previous.items():
        if key in placed_keys:
            continue
        for event in rows:
            date = str(event.get("date") or "")
            kind = date_kind(date)
            if kind not in {"day", "month"}:
                continue
            row = ensure_timeline_fields(event, previous=previous)
            if kind == "month":
                row.setdefault("date_note", event.get("date_note") or "일자 공고 전, 월까지만 확정")
            by_month.setdefault(row["date"][:7], []).append(row)
            carried += 1

    ordered = {
        month: sorted(rows, key=month_sort_key)
        for month, rows in sorted(by_month.items())
    }
    return ordered, excluded, carried


def print_exclusion_report(excluded: list[dict[str, str]], carried: int, timeline_n: int) -> None:
    print(f"world_by_month: {timeline_n} rows")
    print(f"excluded from timeline: {len(excluded)}")
    by_reason: dict[str, list[dict[str, str]]] = {}
    for row in excluded:
        by_reason.setdefault(row["reason"], []).append(row)
    for reason in sorted(by_reason):
        group = by_reason[reason]
        print(f"  {reason} ({len(group)})")
        for row in group:
            print(f"    {row['iso3']} {row['type']} {row['label_ko']}")
    print(f"carried world_by_month rows not yet on board: {carried}")


def main() -> int:
    seed = load_json(CONFIG / "country_seed.json")
    year = int(seed.get("year", 2026))
    base = load_json(EXTRACTED_PATH if EXTRACTED_PATH.exists() else PUBLIC_PATH)
    previous_world = base.get("world_by_month") if isinstance(base.get("world_by_month"), dict) else {}
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
            # date_end is optional; do not invent null (null_policy forbids it).
            events.append(row)

    events.sort(key=event_sort_key)
    world_by_month, excluded, carried = derive_world_by_month(events, previous_world)
    timeline_n = sum(len(rows) for rows in world_by_month.values())

    base["as_of"] = max(as_of_values) if as_of_values else base.get("as_of")
    base["generated_at"] = datetime.now(timezone.utc).isoformat()
    base["summary"] = {
        **(base.get("summary") or {}),
        "board_tracked_event_rows": len(events),
        "board_party_leadership_rows": sum(1 for event in events if event.get("type") == "party_leadership"),
        "board_countries": sorted(board_countries),
        "world_by_month_rows": timeline_n,
        "world_by_month_excluded_rows": len(excluded),
        "world_by_month_excluded_없음": sum(1 for row in excluded if row["reason"] == "없음"),
        "world_by_month_excluded_불명": sum(1 for row in excluded if row["reason"] == "불명"),
        "world_by_month_carried_untracked_rows": carried,
    }
    base["board_tracked_all_events"] = events
    base["party_leadership_and_conventions"] = [
        event for event in events if event.get("type") == "party_leadership"
    ]
    base["world_by_month"] = world_by_month

    rendered = json.dumps(base, ensure_ascii=False, indent=2) + "\n"
    for path in (EXTRACTED_PATH, PUBLIC_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        print("wrote", path)
    print_exclusion_report(excluded, carried, timeline_n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
