"""build_fomc_preview: Fed calendar SEP marks, the blackout rule, BEA schedule rows (no network)."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build_fomc_preview as bp  # noqa: E402

FED = ("<h4>2026 FOMC Meetings</h4> January 27-28 Statement ... September 15-16* Projection Materials "
       "October 27-28 ... April 30-May 1 ... <h4>2025 FOMC Meetings</h4> December 9-10*")
BEA = """<th>Year 2026</th>
<tr class="x"><td><div class="release-date">October 29</div><small class="text-muted">8:30 AM</small></td>
<td>icon</td><td class="release-title views-field">GDP (Advance Estimate), 3rd Quarter 2026  </td></tr>
<tr class="x"><td><div class="release-date">January 7</div><small class="text-muted">10:00 AM</small></td>
<td>icon</td><td class="release-title views-field">Something</td></tr>"""


class Calendar(unittest.TestCase):
    def test_sep_mark_and_cross_month(self):
        ms = bp.parse_fed_calendar(FED, 2026)
        self.assertIn({"start": "2026-09-15", "end": "2026-09-16", "sep": True}, ms)
        self.assertIn({"start": "2026-10-27", "end": "2026-10-28", "sep": False}, ms)
        self.assertIn({"start": "2026-04-30", "end": "2026-05-01", "sep": False}, ms)
        self.assertFalse(any(m["start"].startswith("2025") for m in ms))      # the 2025 block is cut off

    def test_blackout_second_saturday_before_through_day_after(self):
        self.assertEqual(bp.blackout(date(2026, 10, 27), date(2026, 10, 28)), ("2026-10-17", "2026-10-29"))
        self.assertEqual(bp.blackout(date(2026, 12, 8), date(2026, 12, 9)), ("2026-11-28", "2026-12-10"))


class Bea(unittest.TestCase):
    def test_rows_and_year_rollover(self):
        rows = bp.parse_bea_schedule(BEA)
        self.assertEqual(rows[0], {"date": "2026-10-29", "time": "8:30 AM", "title": "GDP (Advance Estimate), 3rd Quarter 2026", "source": "BEA"})
        self.assertEqual(rows[1]["date"], "2027-01-07")

    def test_build_flags_releases_relative_to_the_decision(self):
        doc = bp.build(FED, BEA, date(2026, 10, 8))
        self.assertEqual(doc["next_meeting"]["end"], "2026-10-28")
        self.assertFalse(doc["next_meeting"]["sep"])
        self.assertEqual([r["relative"] for r in doc["releases"]], ["after"])           # Jan 7 is beyond a week after


if __name__ == "__main__":
    unittest.main()
