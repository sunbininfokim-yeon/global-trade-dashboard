"""Target selection for the pre-open direction run (tools/ops/preopen_target.py)."""
import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from preopen_target import resolve  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
# 2026-11: weekdays are sessions; Wed 11/11 stands in for a KR holiday.
HOLIDAY = {"2026-11-11"}


def is_session(day):
    d = datetime.strptime(day, "%Y-%m-%d")
    return d.weekday() < 5 and day not in HOLIDAY


def at(day, hhmm):
    h, m = map(int, hhmm.split(":"))
    y, mo, d = map(int, day.split("-"))
    return datetime(y, mo, d, h, m, tzinfo=KST)


FORECAST = {"status": "research_preopen_forecast"}


class ResolveTarget(unittest.TestCase):
    def test_weekday_morning_targets_today(self):
        self.assertEqual(resolve(at("2026-11-10", "06:25"), "", None, is_session),
                         ("2026-11-10", True, True, ""))

    def test_weekday_after_cutoff_skips(self):
        target, run, valid, why = resolve(at("2026-11-10", "09:40"), "", None, is_session)
        self.assertEqual((target, run, valid), ("2026-11-10", False, False))
        self.assertIn("cutoff", why)

    def test_saturday_targets_monday(self):
        self.assertEqual(resolve(at("2026-11-07", "06:25"), "", None, is_session)[:3],
                         ("2026-11-09", True, True))

    def test_saturday_afternoon_still_runs(self):
        # The 08:30 cutoff is for the target day, not for Saturday.
        self.assertEqual(resolve(at("2026-11-07", "15:00"), "", None, is_session)[:2], ("2026-11-09", True))

    def test_sunday_skips_when_monday_forecast_exists(self):
        doc = dict(FORECAST, target_date="2026-11-09")
        target, run, _, why = resolve(at("2026-11-08", "06:25"), "", doc, is_session)
        self.assertEqual((target, run), ("2026-11-09", False))
        self.assertIn("already", why)

    def test_unavailable_is_retried(self):
        doc = {"status": "unavailable", "target_date": "2026-11-09"}
        self.assertTrue(resolve(at("2026-11-08", "06:25"), "", doc, is_session)[1])

    def test_holiday_targets_next_session(self):
        self.assertEqual(resolve(at("2026-11-11", "06:25"), "", None, is_session)[0], "2026-11-12")

    def test_old_forecast_does_not_block_new_target(self):
        doc = dict(FORECAST, target_date="2026-11-06")
        self.assertTrue(resolve(at("2026-11-07", "06:25"), "", doc, is_session)[1])

    def test_requested_target_bypasses_cutoff_rule(self):
        self.assertEqual(resolve(at("2026-11-10", "10:00"), "2026-11-10", None, is_session)[:2],
                         ("2026-11-10", True))

    def test_requested_non_session_is_invalid(self):
        self.assertEqual(resolve(at("2026-11-07", "10:00"), "2026-11-08", None, is_session)[:3],
                         ("2026-11-08", False, False))


if __name__ == "__main__":
    unittest.main()
