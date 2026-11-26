import unittest
from datetime import date

from build_us_cpi_food_watch import build_watch, latest_egg_cpi, parse_usda, read_usda


TABLE = """Daily National Shell Egg Index Report (5-day rolling average)
Report for: 11/25/2026
NATIONAL SHELL EGGS¹ - Caged
30-Dozen Cases / Cents Per Dozen / FOB
Type Color Class Volume Price Range Wtd Avg Change Last Reported (11/24/2026) Year Ago (11/26/2025)
Graded Loose  White Extra Large  16,620   95.00 - 158.00  118.63  -0.64  119.27  191.92
              White Large        59,172   95.00 - 168.00  142.26   4.56  137.70  226.23
              Brown Large                                      90.00  162.00
Gradeable Nest Run  White 1  6,240 45.00 - 125.00 65.13 7.13 58.00 189.65
NATIONAL SHELL EGGS¹ - Cage-Free
30-Dozen Cases / Cents Per Dozen / FOB
Type Color Class Volume Price Range Wtd Avg Change Last Reported (11/24/2026) Year Ago (11/26/2025)
Graded Loose  White Large  6,840 109.00 - 127.00 118.07 1.03 117.04 216.20
"""


class CpiFoodWatchTests(unittest.TestCase):
    def test_extracts_only_the_comparable_national_quote(self):
        quote = parse_usda(TABLE)
        self.assertEqual(quote["cents_per_dozen"], 142.26)
        self.assertEqual(quote["prior_reference_date"], "2026-11-24")
        self.assertAlmostEqual(quote["change_pct"], 3.3115)
        for invalid in (
            TABLE.replace("142.26", "242.26"),
            TABLE.replace("142.26", "141.26"),
            TABLE.replace("142.26   4.56", "             "),
            TABLE.replace("¹ - Caged", "¹ - Cage-Free"),
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    parse_usda(invalid)

    def test_alert_deduplication_staleness_and_cpi_month_guard(self):
        q = parse_usda(TABLE)
        target = {"item_id": "eggs", "reference_period": "2026-10"}
        report = build_watch(q, target, as_of=date(2026, 11, 26))
        self.assertEqual(report, build_watch(q, target, as_of=date(2026, 11, 27)))
        alert = report["alerts"][0]
        self.assertEqual(alert["target_item_id"], "eggs")
        self.assertEqual(alert["target_cpi_reference_period"], "2026-11")
        self.assertEqual(alert["expires_on_us_eastern"], "2026-12-01")
        self.assertFalse(report["policy"]["forecast_active"])
        self.assertEqual(build_watch(q, {**target, "reference_period": "2026-11"},
                                     as_of=date(2026, 11, 26))["alerts"], [])
        self.assertEqual(build_watch({**q, "change_pct": 2}, target, as_of=date(2026, 11, 26))["alerts"], [])
        for invalid_day in (date(2026, 12, 2), date(2026, 11, 24)):
            with self.assertRaises(ValueError):
                build_watch(q, target, as_of=invalid_day)

    def test_cpi_target_requires_exact_code_and_does_not_fill_missing_yoy(self):
        contrib = {"latest_month": "2026-10", "nodes": [
            {"code": "SAF11"}, {"code": "SEFH"},
        ], "baskets": {"headline": {"2026-10": {"mom": {"rows": {"1": [0.583, 0.001, 0.116]}}}}}}
        target = latest_egg_cpi(contrib)
        self.assertEqual((target["item_id"], target["mom_pct"]), ("eggs", 0.583))
        self.assertTrue(target["headline_only"])
        self.assertIsNone(target["yoy_pct"])
        contrib["nodes"].pop()
        with self.assertRaises(ValueError):
            latest_egg_cpi(contrib)

    def test_rejects_non_pdf(self):
        with self.assertRaises(ValueError):
            read_usda(b"<html>timeout</html>")


if __name__ == "__main__":
    unittest.main()
