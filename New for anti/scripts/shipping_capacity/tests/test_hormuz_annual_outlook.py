"""Calendar math, release isolation, and fail-closed scenario tests."""

import json
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker

from build_snapshot import build_snapshot
from shipping_capacity.artifacts import build_artifact_bundle, golden_contract_failures
from shipping_capacity.hormuz_annual_outlook import UNITS, build_hormuz_annual_outlook
from shipping_capacity.official_cargo import quarter_dates


ROOT = Path(__file__).resolve().parents[1]
AS_OF = date(2026, 11, 25)


def release_fixture(crude, lng, *, year=2026, publication="2026-11-16"):
    rows = []
    for category, rates in (("crude_condensate", crude), ("lng", lng)):
        for quarter, value in enumerate(rates, 1):
            period = f"{quarter}Q{year}"
            start, end = quarter_dates(period)
            rows.append({
                "publisher": "EIA", "frequency": "quarterly", "statistic": "period_daily_mean",
                "evidence_class": "institution_estimate", "direction": "source_aggregate_not_direction_resolved",
                "chokepoint_id": "hormuz", "geography_scope": "strait_of_hormuz",
                "source_published_at": publication, "cargo_category": category, "unit": UNITS[category][0],
                "period": period, "period_start": start, "period_end": end,
                "value": value, "status": "not_reported" if value is None else "reported",
            })
    return {"sources": {"eia": {"status": "fetched", "source_published_at": publication, "records": {"hormuz": rows}}}}


class HormuzAnnualOutlookTests(unittest.TestCase):
    def test_quarter_length_and_each_unreported_case_stay_separate(self):
        result = build_hormuz_annual_outlook(release_fixture([100, 80, 120], [5, 2, 3]), AS_OF)
        crude, lng = result["cards"]
        self.assertEqual(crude["status"], "conditional_outlook")
        self.assertEqual(crude["reported_cumulative"], 27_320)
        self.assertEqual(crude["published_period_end"], "2026-09-30")
        self.assertEqual(crude["unreported_period_start"], "2026-10-01")
        self.assertEqual(crude["unreported_days"], 92)
        self.assertEqual(crude["unreported_elapsed_days"], 56)
        cases = {row["id"]: row for row in crude["scenarios"]}
        self.assertEqual(cases["latest_quarter_pace"]["annual_total"], 38_360)
        self.assertEqual(cases["previous_quarter_pace"]["annual_total"], 34_680)
        self.assertEqual(cases["previous_quarter_pace"]["reference_period_end"], "2026-06-30")
        self.assertEqual(lng["unit"], "billion_cubic_feet")
        self.assertEqual(lng["scenarios"][0]["annual_total"], 1184)

    def test_one_reported_quarter_is_not_annualized(self):
        crude = build_hormuz_annual_outlook(release_fixture([100], [5]), AS_OF)["cards"][0]
        self.assertEqual(crude["status"], "awaiting_second_quarter")
        self.assertEqual(crude["reported_cumulative"], 9000)
        self.assertEqual(crude["scenarios"], [])

    def test_midyear_and_latest_dashes_do_not_become_zero(self):
        crude, lng = build_hormuz_annual_outlook(release_fixture([100, None, 120], [5, 2, None]), AS_OF)["cards"]
        for card, missing in ((crude, "2026-04-01"), (lng, "2026-07-01")):
            self.assertEqual(card["status"], "insufficient_reported_quarters")
            self.assertEqual(card["missing_quarter_starts"], [missing])
            self.assertEqual(card["published_period_end"], "2026-09-30")
            self.assertIsNone(card["reported_cumulative"])
            self.assertEqual(card["scenarios"], [])

    def test_invalid_scope_edition_and_duplicates_never_patch_missing_quarter(self):
        for overrides in (
            {"source_published_at": "2026-08-12"}, {"geography_scope": "oman_gulf_bypass"},
            {"publisher": "IEA"}, {"frequency": "monthly"}, {"unit": "tonnes_per_day"},
            {"direction": "outbound"}, {"period_end": "2026-06-01"},
        ):
            with self.subTest(overrides=overrides):
                fixture = release_fixture([100, 80, 120], [5, 2, 3])
                fixture["sources"]["eia"]["records"]["hormuz"][1].update(overrides)
                crude = build_hormuz_annual_outlook(fixture, AS_OF)["cards"][0]
                self.assertEqual(crude["missing_quarter_starts"], ["2026-04-01"])
                self.assertEqual(crude["scenarios"], [])
        fixture = release_fixture([100, 80, 120], [5, 2, 3])
        rows = fixture["sources"]["eia"]["records"]["hormuz"]
        rows.append({**rows[1], "period": "2Q26"})
        self.assertEqual(build_hormuz_annual_outlook(fixture, AS_OF)["cards"][0]["missing_quarter_starts"], ["2026-04-01"])

    def test_past_year_is_not_projected_but_a_completed_leap_year_is_summed(self):
        as_of = date(2025, 2, 1)
        source = release_fixture([100, 100, 100], [2, 2, 2], year=2024, publication="2025-01-20")
        crude = build_hormuz_annual_outlook(source, as_of)["cards"][0]
        self.assertEqual(crude["status"], "past_year_awaiting_final_quarter")
        self.assertEqual(crude["scenarios"], [])
        source = release_fixture([100] * 4, [2] * 4, year=2024, publication="2025-01-20")
        crude = build_hormuz_annual_outlook(source, as_of)["cards"][0]
        self.assertEqual(crude["status"], "full_year_institution_estimate")
        self.assertEqual(crude["full_year_institution_total"], 36600)
        self.assertEqual(crude["unreported_days"], 0)
        self.assertIsNone(crude["unreported_period_start"])
        self.assertEqual(crude["scenarios"], [])

    def test_legitimate_zero_and_identical_rates_are_not_misrepresented(self):
        source = release_fixture([100, 0, 0], [2, 1, 1])
        source["sources"]["eia"]["status"] = "cached_fallback"
        result = build_hormuz_annual_outlook(source, AS_OF)
        self.assertEqual(result["source_status"], "cached_fallback")
        self.assertEqual(result["source_published_at"], "2026-11-16")
        case, = result["cards"][0]["scenarios"]
        self.assertEqual(case["unreported_period_estimate"], 0)
        self.assertEqual(case["annual_total"], 9000)

    def test_no_hindsight_when_publication_is_future_or_coverage_is_too_old(self):
        result = build_hormuz_annual_outlook(release_fixture([100, 80], [2, 1]), date(2026, 11, 15))
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["cards"], [])
        old = release_fixture([100] * 4, [2] * 4, year=2024, publication="2025-01-20")
        self.assertEqual(build_hormuz_annual_outlook(old, AS_OF)["cards"], [])

    def test_future_period_in_release_is_not_an_observation(self):
        result = build_hormuz_annual_outlook(release_fixture([100] * 4, [2] * 4), AS_OF)
        self.assertEqual(result["cards"][0]["published_period_end"], "2026-09-30")
        self.assertIsNone(result["cards"][0]["full_year_institution_total"])

    def test_build_and_schema_keep_forecast_separate_from_institutional_total(self):
        fixture = release_fixture([100, 80, 120], [5, 2, 3])
        with patch("build_snapshot.collect_official_cargo", return_value=fixture), patch("build_snapshot.datetime") as clock:
            clock.now.return_value = datetime(2026, 11, 25, tzinfo=timezone.utc)
            bundle = build_artifact_bundle(build_snapshot(ROOT / "config"))
        screen = bundle["screen"]
        panel = screen["hormuz_annual_outlook"]
        self.assertEqual(panel["cards"][0]["status"], "conditional_outlook")
        schema = json.loads((ROOT / "schemas/shipping_capacity_v1.schema.json").read_text())
        validator = Draft202012Validator(schema["properties"]["hormuz_annual_outlook"], format_checker=FormatChecker())
        self.assertEqual(list(validator.iter_errors(panel)), [])
        self.assertEqual(panel, bundle["diagnostics"]["hormuz_annual_outlook"])
        self.assertEqual(golden_contract_failures(screen, bundle["diagnostics"], bundle["scenario_grid"]), [])
        panel_copy = build_hormuz_annual_outlook(fixture, AS_OF)
        panel_copy["cards"][0]["full_year_institution_total"] = 12
        self.assertTrue(list(validator.iter_errors(panel_copy)))
        screen["hormuz_annual_outlook"] = {"status": "changed"}
        self.assertIn("hormuz_annual_outlook_screen_diagnostics_mismatch",
                      golden_contract_failures(screen, bundle["diagnostics"], bundle["scenario_grid"]))


if __name__ == "__main__":
    unittest.main()
