import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from refresh_us_cpi_watch import ENERGY, energy_obs, plan, rate_events, releases, save, weekly_points


class WatchRefreshTests(unittest.TestCase):
    def test_eia_series_identity_and_missing_quote(self):
        series, name = ENERGY["eia_gasoline"]
        html = (f"{series}w.xls {name} (Dollars per Gallon)"
                "<tr><td class='B6'>2026-Nov</td><td class='B5'>11/02</td><td class='B3'>4.290</td>"
                "<td class='B5'>11/09</td><td class='B3'>NA</td></tr>")
        self.assertEqual(weekly_points(html, "eia_gasoline"), {date(2026, 11, 2): 4.29})
        with self.assertRaises(ValueError):
            weekly_points(html, "eia_jet")

    def test_older_run_cannot_replace_newer(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            report = {"schema_version": "test", "briefing": {"as_of_eastern": "2026-11-26"}}
            save(report, path)
            saved = path.read_bytes()
            report["briefing"]["as_of_eastern"] = "2026-11-25"
            with self.assertRaises(ValueError):
                save(report, path)
            self.assertEqual(path.read_bytes(), saved)

    def test_calendar_weekend_and_retry(self):
        table = ("Schedule of Releases for the Consumer Price Index"
                 "<table><tr><th>November 2026</th><td>Dec. 10, 2026</td></tr></table>")
        dates = releases(table)
        for n, mode in [(4, "weekly"), (5, None), (7, "pre_release"), (9, "pre_release")]:
            self.assertEqual(plan(dates, date(2026, 12, n))[:2], (mode, "2026-11"))
        with self.assertRaises(ValueError):
            plan(dates, date(2026, 12, 10))

    def test_matched_weeks_not_following_month_or_previous_available_quote(self):
        points = {date(2026, m, d): v for m, d, v in
                  [(10, 5, 4), (10, 12, 20), (10, 19, 4), (11, 2, 4), (11, 16, 2), (12, 7, 50)]}
        obs = energy_obs(points, "2026-11", date(2026, 12, 7))
        self.assertEqual(obs["observed_on"], "2026-11-16")
        self.assertEqual(obs["prior_month_matched_weeks_pct"], -25)
        self.assertIsNone(obs["week_over_week_pct"])
        self.assertEqual(obs["status"], "stale")
        self.assertEqual(energy_obs({}, "2026-11", date(2026, 12, 7))["status"], "awaiting_target_month")

    def test_approval_is_not_application(self):
        event = dict(source_id="electricity_rate_actions", approved_on="2026-10-01", effective_on="2026-11-15",
                     jurisdiction="test", provider="test", applies_to="residential", source_url="https://example.gov/order")
        get = lambda d: rate_events([event], event["source_id"], "2026-11", date(2026, 11, d))
        self.assertEqual(get(1)["status"], "no_verified_event")
        self.assertEqual(get(16)["events"], [event])
