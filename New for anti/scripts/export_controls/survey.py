"""Weekly export-control survey.

Validates the catalogue, then writes one record for the ISO week under
surveys/weeks.json. It does not invent measures and it does not promote a
news clip to confidence high. A country-commodity pair with no row is an
open gap, not a clean bill of health.

Quiet weeks still get a record, so the GitHub run shows that someone looked.
The catalogue changes only when a person has read a source and edited the JSON.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

from .universe import load as load_universe
from .catalogue import load as load_catalogue
from .validate import validate_document

HERE = Path(__file__).resolve().parent
WEEKS = HERE / "surveys" / "weeks.json"
QUESTIONS = HERE / "open_questions.json"


def watch_pairs(universe):
    pairs = []
    for category, block in universe["categories"].items():
        for country in block["countries"]:
            for slug in country["commodities"]:
                pairs.append((category, country["iso"], slug))
    for pin in universe.get("pinned_outside_role") or []:
        for slug in pin["commodities"]:
            pairs.append((pin["category"], pin["iso"], slug))
    return pairs


def coverage(doc, universe):
    live = {}
    lifted = {}
    for row in doc.get("controls") or []:
        bucket = lifted if row.get("level") == "lifted" else live
        for slug in row.get("commodities") or []:
            bucket.setdefault((row.get("category"), row.get("iso"), slug), row.get("id"))
    rows = []
    unchecked = 0
    for category, iso, slug in watch_pairs(universe):
        key = (category, iso, slug)
        if key in live:
            state = "live"
        elif key in lifted:
            state = "lifted"
        else:
            state = "unchecked"
            unchecked += 1
        rows.append({
            "category": category, "iso": iso, "commodity": slug,
            "state": state, "control_id": live.get(key) or lifted.get(key),
        })
    return rows, unchecked


def digest(doc, questions):
    body = []
    for row in doc.get("controls") or []:
        body.append({
            "id": row.get("id"),
            "level": row.get("level"),
            "until": row.get("until"),
            "lifted_at": row.get("lifted_at"),
            "commodities": row.get("commodities"),
            "needs_reconfirm": row.get("needs_reconfirm", False),
        })
    payload = json.dumps({"controls": body, "questions": questions}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def iso_week(day):
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def load_questions():
    if not QUESTIONS.exists():
        return []
    return json.loads(QUESTIONS.read_text(encoding="utf-8")).get("questions") or []


def record_week(doc, universe, today=None):
    today = today or date.today()
    questions = load_questions()
    rows, unchecked = coverage(doc, universe)
    by_state = {"live": 0, "lifted": 0, "unchecked": 0}
    for row in rows:
        by_state[row["state"]] += 1
    entry = {
        "week": iso_week(today),
        "run_on": today.isoformat(),
        "catalogue_as_of": doc.get("as_of"),
        "control_count": len(doc.get("controls") or []),
        "pairs": by_state,
        "unchecked_pairs": unchecked,
        "needs_reconfirm": [
            row.get("id") for row in doc.get("controls") or [] if row.get("needs_reconfirm")
        ],
        "digest": digest(doc, questions),
        "open_questions": questions,
        "note_ko": "행이 없다고 통제가 없는 것이 아니다. unchecked 는 아직 원문을 보지 않은 쌍이다.",
    }
    WEEKS.parent.mkdir(parents=True, exist_ok=True)
    log = {"schema_version": "export-controls-survey-log-v1", "weeks": []}
    if WEEKS.exists():
        log = json.loads(WEEKS.read_text(encoding="utf-8"))
    weeks = [w for w in log.get("weeks") or [] if w.get("week") != entry["week"]]
    weeks.append(entry)
    weeks.sort(key=lambda w: w["week"])
    log["schema_version"] = "export-controls-survey-log-v1"
    log["weeks"] = weeks
    WEEKS.write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return entry


def main():
    doc = load_catalogue()
    universe = load_universe()
    errors = validate_document(doc, universe)
    if errors:
        print(f"{len(errors)} problem(s)")
        for line in errors:
            print(f"  {line}")
        return 1
    entry = record_week(doc, universe)
    print(
        f"{entry['week']} controls={entry['control_count']} "
        f"live={entry['pairs']['live']} lifted={entry['pairs']['lifted']} "
        f"unchecked={entry['pairs']['unchecked']} digest={entry['digest']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
