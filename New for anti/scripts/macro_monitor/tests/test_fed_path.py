"""fed_path: the meeting-by-meeting arithmetic of fed funds futures."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_monitor import fed_path as fp  # noqa: E402


class Path_(unittest.TestCase):
    def test_symbols_and_months(self):
        self.assertEqual(fp.symbol("2026-12"), "ZQZ26.CBT")
        self.assertEqual(fp.symbol("2027-01"), "ZQF27.CBT")
        self.assertEqual(fp.add_months("2026-11", 2), "2027-01")

    def test_a_meeting_month_is_solved_from_its_own_average(self):
        # Dec 9 decision, January also has a meeting: post from December's average.
        rates = {"2026-11": 3.88, "2026-12": 3.88 * 9 / 31 + 4.13 * 22 / 31, "2027-01": 4.13}
        rows = fp.path(rates, ["2026-12-09", "2027-01-27"], "2026-11-06", 3.88)
        self.assertAlmostEqual(rows[0]["pre"], 3.88)
        self.assertAlmostEqual(rows[0]["post"], 4.13, places=3)
        self.assertAlmostEqual(rows[0]["change_bp"], 25.0, places=1)

    def test_a_late_meeting_takes_post_from_the_quiet_month_after(self):
        rates = {"2027-01": 4.0, "2027-02": 4.1}
        rows = fp.path(rates, ["2027-01-27"], "2026-12-15", 4.0)
        self.assertEqual(rows[0]["post"], 4.1)

    def test_odds_split_between_the_two_steps(self):
        self.assertEqual(fp.split(0.15), {0.0: 0.4, 0.25: 0.6})
        self.assertEqual(fp.split(-0.05), {-0.25: 0.2, 0.0: 0.8})
        self.assertEqual(fp.split(0.0), {0.0: 1.0})

    def test_headline_names_the_likeliest_move(self):
        rows = fp.enrich([{"date": "2026-12-09", "pre": 3.88, "post": 4.0675, "change_bp": 18.75}], 3.88, 3.75)
        chip, full = fp.headline(rows)
        self.assertEqual(chip, "인상 75%")
        self.assertIn("12/9 FOMC 인상 75% · 동결 25%", full)
        self.assertEqual(rows[0]["range_odds"][0]["range"], "4.00–4.25%")

    def test_parse_chart(self):
        doc = {"chart": {"result": [{"timestamp": [1793923200, 1794009600],
                                     "indicators": {"quote": [{"close": [96.0, None]}]}}]}}
        self.assertEqual(fp.parse_chart(doc), [("2026-11-06", 96.0)])


class Weekly(unittest.TestCase):
    def test_weekly_max_keeps_spikes(self):
        from macro_monitor import free_cards as fc
        pts = [("2026-09-28", 0.0), ("2026-09-30", 6.0), ("2026-10-02", 1.0), ("2026-10-05", 0.0)]
        self.assertEqual(fc.weekly(pts, max), [("2026-10-02", 6.0), ("2026-10-05", 0.0)])


if __name__ == "__main__":
    unittest.main()
