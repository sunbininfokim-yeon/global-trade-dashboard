"""Unit tests for build_us_macro_quality_from_collect's pure helpers."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build_us_macro_quality_from_collect import _current_vote_roster, _next_meeting_schedule  # noqa: E402

_ROSTER = [
    {"name": "Kevin Warsh", "role": "Board of Governors, Chairman"},
    {"name": "John C. Williams", "role": "New York, Vice Chair"},
    {"name": "Michael S. Barr", "role": "Board of Governors"},
    {"name": "Beth M. Hammack", "role": "Cleveland"},
    {"name": "Neel Kashkari", "role": "Minneapolis"},
    {"name": "Lorie K. Logan", "role": "Dallas"},
]

_CALENDAR = {
    "meetings": [
        {"decision_date": "2026-06-17", "has_sep": True},
        {"decision_date": "2026-07-29", "has_sep": False},
        {"decision_date": "2026-09-16", "has_sep": True},
        {"decision_date": "2026-10-28", "has_sep": False},
    ]
}


class TestNextMeetingSchedule(unittest.TestCase):
    def test_picks_first_meeting_after_today(self):
        result = _next_meeting_schedule(_CALENDAR, today=date(2026, 8, 31))
        self.assertEqual(result["next_meeting_date"], "2026-09-16")

    def test_beige_book_estimate_is_fourteen_days_before(self):
        result = _next_meeting_schedule(_CALENDAR, today=date(2026, 8, 31))
        self.assertEqual(result["next_beige_book_estimate"], "2026-09-02")

    def test_meeting_on_today_is_not_next(self):
        result = _next_meeting_schedule(_CALENDAR, today=date(2026, 9, 16))
        self.assertEqual(result["next_meeting_date"], "2026-10-28")

    def test_no_upcoming_meetings_returns_none(self):
        result = _next_meeting_schedule(_CALENDAR, today=date(2027, 1, 1))
        self.assertIsNone(result)


class TestCurrentVoteRoster(unittest.TestCase):
    def test_derives_for_side_from_roster_when_statement_names_only_dissenters(self):
        row = {
            "vote_for": 3, "vote_against": 3,
            "voters_for": [],
            "dissenters": [
                {"name": "Beth M. Hammack", "dissent_direction": "tighter"},
                {"name": "Neel Kashkari", "dissent_direction": "tighter"},
                {"name": "Lorie K. Logan", "dissent_direction": "tighter"},
            ],
        }
        entries = _current_vote_roster(row, _ROSTER)
        for_names = {e["name"] for e in entries if e["vote"] == "for"}
        self.assertEqual(for_names, {"Kevin Warsh", "John C. Williams", "Michael S. Barr"})
        self.assertTrue(all(e["inferred"] for e in entries if e["vote"] == "for"))
        against_names = {e["name"] for e in entries if e["vote"] == "against"}
        self.assertEqual(against_names, {"Beth M. Hammack", "Neel Kashkari", "Lorie K. Logan"})

    def test_does_not_derive_when_counts_mismatch(self):
        row = {
            "vote_for": 9,  # roster only has 3 non-dissenters -- can't match 9
            "vote_against": 3,
            "voters_for": [],
            "dissenters": [
                {"name": "Beth M. Hammack", "dissent_direction": "tighter"},
                {"name": "Neel Kashkari", "dissent_direction": "tighter"},
                {"name": "Lorie K. Logan", "dissent_direction": "tighter"},
            ],
        }
        entries = _current_vote_roster(row, _ROSTER)
        self.assertEqual([e for e in entries if e["vote"] == "for"], [])

    def test_uses_named_for_side_directly_when_statement_provides_it(self):
        row = {
            "vote_for": 2, "vote_against": 0,
            "voters_for": ["Kevin Warsh, Chair", "John C. Williams, Vice Chair"],
            "dissenters": [],
        }
        entries = _current_vote_roster(row, _ROSTER)
        self.assertTrue(all(not e["inferred"] for e in entries))
        self.assertEqual({e["name"] for e in entries}, {"Kevin Warsh, Chair", "John C. Williams, Vice Chair"})


if __name__ == "__main__":
    unittest.main()
