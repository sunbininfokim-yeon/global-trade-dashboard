"""Small parser fixtures are tests only; production never emits fixture/seed data."""

import copy
import json
import unittest
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from shipping_capacity.official_cargo import (
    EIA_URL, IMO_URL, collect_official_cargo, parse_eia, parse_imo_links,
)


NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
RETRIEVED = NOW.isoformat()


def fixture_html():
    tables = []
    for scope in ("Strait of Hormuz", "Suez Canal and SUMED pipeline"):
        tables.append(f"""<table><caption>Volume of crude oil, condensate, petroleum products, and liquefied natural gas transported through the {scope}</caption>
        <thead><tr><td colspan="3">million barrels per day</td></tr>
        <tr><th></th><th>1Q26</th><th>2Q26</th></tr></thead>
        <tbody><tr><td>Total oil flows through the {scope}</td><td>14.9</td><td>4.9</td></tr>
        <tr><td>Crude oil and condensate</td><td>10.9</td><td>3.7</td></tr>
        <tr><td>Petroleum products</td><td>4.0</td><td>1.1</td></tr>
        <tr><td>LNG flows through the {'Suez Canal' if 'Suez' in scope else scope} (billion cubic feet per day)</td><td>7.4</td><td>0.8</td></tr></tbody></table>""")
    return '<span class="releasedate">Release Date: August 12, 2026</span>' + "".join(tables)


IMO_FIXTURE = '<a href="/files/confirmed.pdf">Updated list of incidents</a><a href="https://www.ukmto.org/advisories">UKMTO - Advisories</a>'


def fixture_fetcher(url):
    return fixture_html() if url == EIA_URL else IMO_FIXTURE


class OfficialCargoTests(unittest.TestCase):
    def test_period_and_unit_conversion_are_not_daily_disaggregation(self):
        result = parse_eia(fixture_html(), RETRIEVED)
        row = next(row for row in result["records"]["hormuz"] if row["period"] == "2Q26" and row["cargo_category"] == "crude_condensate")
        self.assertEqual(row["value"], 3_700_000)
        self.assertEqual((row["period_start"], row["period_end"]), ("2026-04-01", "2026-06-30"))
        self.assertEqual(row["frequency"], "quarterly")
        self.assertEqual(row["source_published_at"], "2026-08-12")
        self.assertNotIn("date", row)

    def test_lng_keeps_native_unit_and_canal_scope(self):
        result = parse_eia(fixture_html(), RETRIEVED)
        row = next(row for row in result["records"]["suez"] if row["cargo_category"] == "lng")
        self.assertEqual(row["value"], 7.4)
        self.assertEqual(row["unit"], "billion_cubic_feet_per_day")
        self.assertEqual(row["geography_scope"], "suez_canal")
        self.assertTrue(all(row["geography_scope"] == "suez_canal_and_sumed_pipeline" for row in result["records"]["suez"] if row["cargo_category"] != "lng"))

    def test_true_zero_is_kept_but_missing_is_not_zero(self):
        parsed = parse_eia(fixture_html().replace("<td>7.4</td>", "<td>0</td>").replace("<td>0.8</td>", "<td>—</td>"), RETRIEVED)
        lng = [row for row in parsed["records"]["hormuz"] if row["cargo_category"] == "lng"]
        self.assertEqual(lng[0]["value"], 0)
        self.assertIsNone(lng[1]["value"])

    def test_changed_unit_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_eia(fixture_html().replace("million barrels per day", "tonnes"), RETRIEVED)

    def test_unrelated_numbers_and_missing_category_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_eia(fixture_html().replace("Crude oil and condensate</td>", "Unknown cargo</td>"), RETRIEVED)

    def test_future_quarter_is_not_published_as_history(self):
        with self.assertRaises(ValueError):
            parse_eia(fixture_html().replace("2Q26", "4Q26"), RETRIEVED)

    def test_duplicate_table_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_eia(fixture_html() + fixture_html(), RETRIEVED)

    def test_oil_composition_reconciliation_has_rounding_tolerance(self):
        parse_eia(fixture_html(), RETRIEVED)  # 3.7 + 1.1 versus 4.9 is permitted.
        with self.assertRaises(ValueError):
            parse_eia(fixture_html().replace("<td>4.9</td>", "<td>24.9</td>"), RETRIEVED)

    def test_failed_fetch_retains_original_retrieval_and_period(self):
        good = collect_official_cargo(fetch=True, now=NOW, fetcher=fixture_fetcher)
        before = copy.deepcopy(good)
        def fail(url):
            raise OSError("upstream unavailable")
        later = datetime(2026, 10, 2, tzinfo=timezone.utc)
        failed = collect_official_cargo(fetch=True, previous=good, now=later, fetcher=fail)
        self.assertEqual(failed["sources"]["eia"]["status"], "cached_fallback")
        self.assertEqual(failed["sources"]["eia"]["retrieved_at"], RETRIEVED)
        self.assertEqual(failed["sources"]["eia"]["last_attempt_at"], later.isoformat())
        self.assertEqual(failed["sources"]["eia"]["records"], good["sources"]["eia"]["records"])
        self.assertEqual(good, before)

    def test_no_fetch_never_uses_seed_or_calls_network(self):
        def fail(url):
            self.fail("offline build attempted a network call")
        result = collect_official_cargo(now=NOW, fetcher=fail)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["chokepoints"]["hormuz"]["reference_cards"], [])

    def test_daily_crude_and_transit_probability_remain_unknown(self):
        result = collect_official_cargo(fetch=True, now=NOW, fetcher=fixture_fetcher)
        for point in result["chokepoints"].values():
            self.assertIsNone(point["daily_crude_barrels"]["value"])
            self.assertIsNone(point["transit_assessment"]["success_probability"])
            self.assertEqual(point["daily_chart"]["classification"], "ship_type_not_commodity")
        self.assertEqual(result["api_keys_required"], [])

    def test_wrong_source_redirect_links_are_not_accepted(self):
        with self.assertRaises(ValueError):
            parse_imo_links('<a href="https://unknown.example/test">Advisories</a>')
        self.assertEqual(len(parse_imo_links(IMO_FIXTURE)), 2)

    def test_older_source_publication_cannot_replace_good_data(self):
        good = collect_official_cargo(fetch=True, now=NOW, fetcher=fixture_fetcher)
        def older(url):
            return fixture_html().replace("August 12", "July 12") if url == EIA_URL else IMO_FIXTURE
        result = collect_official_cargo(fetch=True, now=NOW, previous=good, fetcher=older)
        self.assertEqual(result["sources"]["eia"]["status"], "cached_fallback")
        self.assertEqual(result["sources"]["eia"]["source_published_at"], "2026-08-12")

    def test_monitor_schema_accepts_contract_and_rejects_fake_daily_value(self):
        from jsonschema import Draft202012Validator, FormatChecker
        schema_path = Path(__file__).resolve().parents[1] / "schemas/shipping_capacity_v1.schema.json"
        schema = json.loads(schema_path.read_text())["properties"]["official_cargo_monitor"]
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        result = collect_official_cargo(fetch=True, now=NOW, fetcher=fixture_fetcher)
        self.assertEqual(list(validator.iter_errors(result)), [])
        result["chokepoints"]["hormuz"]["daily_crude_barrels"]["value"] = 123
        self.assertTrue(list(validator.iter_errors(result)))

    def test_existing_workflow_cli_enables_official_collection(self):
        import build_snapshot
        bundle = {name: {} for name in ("screen", "scenario_grid", "diagnostics", "backtests")}
        with tempfile.TemporaryDirectory() as directory:
            with patch("sys.argv", ["build_snapshot.py", "--fetch-portwatch", "--output", str(Path(directory) / "shipping_capacity_v1.json")]), patch.object(build_snapshot, "build_snapshot", return_value={}) as build, patch.object(build_snapshot, "build_artifact_bundle", return_value=bundle):
                build_snapshot.main()
            self.assertTrue(build.call_args.kwargs["fetch_official_cargo"])

    def test_official_only_cli_preserves_matching_diagnostic_history(self):
        import build_snapshot
        bundle = {name: {} for name in ("screen", "scenario_grid", "diagnostics", "backtests")}
        for matching in (True, False):
            with self.subTest(matching=matching), tempfile.TemporaryDirectory() as directory:
                previous = Path(directory) / "previous.json"
                previous.touch()
                diagnostic = Path(directory) / "shipping_capacity_diagnostics_v1.json"
                diagnostic.touch()
                def load(path):
                    if path == previous:
                        return {"bundle_id": "same", "chokepoints_live": {"hormuz": {"history": [1]}}}
                    return {"bundle_id": "same" if matching else "different", "chokepoints_live": {"hormuz": {"history": [1, 2]}}}
                with patch("sys.argv", ["build_snapshot.py", "--fetch-official-cargo", "--previous-snapshot", str(previous), "--output", str(Path(directory) / "output.json")]), patch.object(build_snapshot, "load_json", side_effect=load), patch.object(build_snapshot, "build_snapshot", return_value={}) as build, patch.object(build_snapshot, "build_artifact_bundle", return_value=bundle):
                    build_snapshot.main()
                self.assertEqual(build.call_args.kwargs["fallback_live_status"]["hormuz"]["history"], [1, 2] if matching else [1])

    def test_monitor_survives_screen_bundle_and_golden_contract(self):
        from build_snapshot import build_snapshot
        from shipping_capacity.artifacts import build_artifact_bundle, golden_contract_failures
        root = Path(__file__).resolve().parents[1]
        monitor = collect_official_cargo(fetch=True, now=NOW, fetcher=fixture_fetcher)
        with patch("build_snapshot.collect_official_cargo", return_value=monitor):
            bundle = build_artifact_bundle(build_snapshot(root / "config"))
        self.assertEqual(bundle["screen"]["official_cargo_monitor"], monitor)
        self.assertEqual(bundle["diagnostics"]["official_cargo_monitor"], monitor)
        self.assertEqual(golden_contract_failures(bundle["screen"], bundle["diagnostics"], bundle["scenario_grid"]), [])
        bundle["screen"]["official_cargo_monitor"] = {"status": "tampered"}
        self.assertIn("official_cargo_monitor_screen_diagnostics_mismatch", golden_contract_failures(bundle["screen"], bundle["diagnostics"], bundle["scenario_grid"]))


if __name__ == "__main__":
    unittest.main()
