from datetime import date
from unittest import TestCase

from wire_us_dkw import FACTORS, FITTED, OBSERVED, build_panel


REFERENCE = """Fed nominal yield estimates
Date,SVENY10
2026-08-31,4.60
2026-09-30,4.80
2026-10-15,4.71
2026-10-30,4.50
2026-11-02,4.45
"""
TODAY = date(2026, 11, 25)


def dkw_csv(*rows):
    header = ",".join(("date", *FACTORS, OBSERVED, FITTED))
    return "\n".join((header, *rows))


AUGUST = "2026-08-31,1.20,2.60,0.70,0.10,4.60,4.60"
SEPTEMBER = "2026-09-30,1.30,2.60,0.80,0.10,4.80,4.80"
OCTOBER_MID = "2026-10-15,1.20,2.60,0.80,0.10,4.71,4.70"
OCTOBER_END = "2026-10-30,1.20,2.50,0.70,0.10,4.50,4.50"


class TestDkwMonthEnd(TestCase):
    def test_partial_latest_month_retains_previous_month(self):
        panel = build_panel(dkw_csv(AUGUST, SEPTEMBER, OCTOBER_MID), REFERENCE, TODAY)
        self.assertEqual(panel["asof"], "2026-09-30")
        self.assertEqual(panel["latest"]["observed_change_bp"], 20)
        self.assertNotIn("2026-10", panel["dates"])

    def test_observed_month_end_can_precede_calendar_month_end(self):
        panel = build_panel(dkw_csv(AUGUST, SEPTEMBER, OCTOBER_END), REFERENCE, TODAY)
        self.assertEqual(panel["asof"], "2026-10-30")
        self.assertEqual(panel["latest"]["observed_change_bp"], -30)

    def test_reference_tail_month_is_not_confirmed(self):
        reference = REFERENCE.split("2026-11-02")[0]
        panel = build_panel(dkw_csv(AUGUST, SEPTEMBER, OCTOBER_END), reference, TODAY)
        self.assertEqual(panel["asof"], "2026-09-30")

    def test_no_month_over_month_comparison_across_an_interior_gap(self):
        with self.assertRaisesRegex(ValueError, "Nonconsecutive"):
            build_panel(dkw_csv(AUGUST, OCTOBER_END), REFERENCE, TODAY)
