"""QRA trend tab: the real quarterly series replaces the seeded monthly walk."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macro_monitor.qra.compare import _period_end_date, apply_real_history  # noqa: E402

ROWS = [
    {"event_id": "2023-Q1", "period": "January–March 2023", "net_borrowing_bn": 932.0},
    {"event_id": "2022-Q4", "period": "October–December 2022", "net_borrowing_bn": 550.0},
    {"event_id": "2023-Q3", "period": "July–September 2023", "net_borrowing_bn": 1006.9999999999999},
]


def _synthetic():
    return {"history": {"5y": {"dates": [f"m{i}" for i in range(60)], "values": [1410.0] * 60}}}


class PeriodEnd(unittest.TestCase):
    def test_quarter_end_dates(self):
        self.assertEqual(_period_end_date("October–December 2022"), "2022-12-31")
        self.assertEqual(_period_end_date("January–March 2023"), "2023-03-31")
        self.assertEqual(_period_end_date("April–June 2024"), "2024-06-30")
        self.assertEqual(_period_end_date("Nov 2022–Jan 2023"), "2023-01-31")

    def test_unreadable_period_is_none(self):
        self.assertIsNone(_period_end_date("Q3 2023"))
        self.assertIsNone(_period_end_date(None))
        self.assertIsNone(_period_end_date(""))


class ApplyRealHistory(unittest.TestCase):
    def test_replaces_synthetic_walk_with_sorted_quarters(self):
        ind = _synthetic()
        self.assertTrue(apply_real_history(ind, ROWS))
        s = ind["history"]["5y"]
        self.assertEqual(s["dates"], ["2022-12-31", "2023-03-31", "2023-09-30"])
        self.assertEqual(s["values"], [550.0, 932.0, 1007.0])  # float noise rounded
        self.assertIs(ind["history"]["10y"], s)
        self.assertNotIn(1410.0, s["values"])

    def test_note_says_announced_estimates_not_outturns(self):
        ind = _synthetic()
        apply_real_history(ind, ROWS)
        self.assertIn("예상치", ind["history_note_ko"])
        self.assertIn("실제 집행액이 아닙니다", ind["history_note_ko"])
        self.assertIn("3개 분기", ind["history_note_ko"])

    def test_bad_rows_are_skipped_not_filled(self):
        ind = _synthetic()
        rows = ROWS + [
            {"period": "Q4 2026", "net_borrowing_bn": 100.0},
            {"period": "April–June 2024", "net_borrowing_bn": None},
        ]
        apply_real_history(ind, rows)
        self.assertEqual(len(ind["history"]["5y"]["values"]), 3)

    def test_no_usable_rows_empties_the_trend_instead_of_keeping_synthetic(self):
        for rows in (None, [], [{"period": "junk", "net_borrowing_bn": 1.0}]):
            ind = _synthetic()
            ind["history_note_ko"] = "stale"
            self.assertFalse(apply_real_history(ind, rows))
            self.assertEqual(ind["history"], {})
            self.assertNotIn("history_note_ko", ind)


if __name__ == "__main__":
    unittest.main()
