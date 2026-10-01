"""Parser fixtures are synthetic tests, never production observations."""

import copy
import unittest

from shipping_capacity.iea_reports import (
    IEA_DISCOVERY_URL, collect_iea_reports, discover_iea_reports, parse_iea_report,
)


URL = "https://www.iea.org/commentaries/middle-east-test-report"
NOW = "2026-10-01T00:00:00+00:00"
DISCOVERY = f'<a href="{URL}">Report</a>'


def report(text="Flows through the Strait of Hormuz averaged only 7.6 mb/d in August, compared with earlier months.", published="2026-09-18", license="CC BY 4.0"):
    return f'<link rel="canonical" href="{URL}"><time datetime="{published}T10:00:00+00:00"></time><p>{text}</p><p>Licence: {license}</p>'


def fetcher(url):
    return DISCOVERY if url == IEA_DISCOVERY_URL else report()


class IEATests(unittest.TestCase):
    def test_completed_month_mean_keeps_units_commodity_and_attribution(self):
        row = parse_iea_report(report(), URL, NOW)[0]
        self.assertEqual(row["value"], 7_600_000)
        self.assertEqual((row["period_start"], row["period_end"]), ("2026-08-01", "2026-08-31"))
        self.assertEqual(row["cargo_category"], "total_oil")
        self.assertEqual(row["frequency"], "monthly")
        self.assertEqual(row["source_published_at"], "2026-09-18")
        self.assertEqual(row["reuse_status"], "publisher_cc_by_4_0")
        self.assertNotIn("date", row)

    def test_discovery_is_bounded_deduplicated_and_publisher_only(self):
        links = DISCOVERY * 2 + '<a href="https://unknown.example/commentaries/hormuz">Bad</a>'
        links += '<a href="https://www.iea.org:443/commentaries/hormuz">Port</a>'
        links += '<a href="https://www.iea.org/commentaries/hormuz?token=private">Query</a>'
        links += '<script><a href="/commentaries/hormuz-hidden">Hidden</a></script>'
        self.assertEqual(discover_iea_reports(links), [URL])
        many = ''.join(f'<a href="/commentaries/hormuz-{n}">Report</a>' for n in range(10))
        self.assertEqual(len(discover_iea_reports(many)), 4)

    def test_explicit_license_required(self):
        with self.assertRaises(ValueError):
            parse_iea_report(report(license="All rights reserved"), URL, NOW)

    def test_canonical_identity_and_unambiguous_date_required(self):
        for html in (report().replace(URL, "https://www.iea.org/commentaries/other"), report().replace('<time', '<not-time'), report() + '<time datetime="2026-09-17"></time>'):
            with self.subTest(html=html), self.assertRaises(ValueError):
                parse_iea_report(html, URL, NOW)

    def test_future_publication_and_incomplete_month_rejected(self):
        for html in (report(published="2026-10-02"), report().replace("in August,", "in September,")):
            with self.subTest(html=html), self.assertRaises(ValueError):
                parse_iea_report(html, URL, NOW)

    def test_forecast_and_other_geography_not_inferred(self):
        for text in ("Flows through the Strait of Hormuz are forecast at 8 mb/d in August.", "Flows through Oman averaged only 7.6 mb/d in August."):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_iea_report(report(text), URL, NOW)

    def test_true_zero_not_missing(self):
        self.assertEqual(parse_iea_report(report().replace("7.6 mb/d", "0 mb/d"), URL, NOW)[0]["value"], 0)
        with self.assertRaises(ValueError):
            parse_iea_report(report().replace("7.6 mb/d", "unknown mb/d"), URL, NOW)

    def test_conflicting_period_values_are_not_published(self):
        with self.assertRaises(ValueError):
            parse_iea_report(report() + '<p>Flows through the Strait of Hormuz averaged 8 mb/d in August.</p>', URL, NOW)

    def test_previous_year_inferred_only_for_completed_month(self):
        row = parse_iea_report(report().replace("in August,", "in December,"), URL, NOW)[0]
        self.assertEqual(row["period"], "2025-12")
        row = parse_iea_report(report().replace("in August,", "in August 2025,"), URL, NOW)[0]
        self.assertEqual(row["period"], "2025-08")

    def test_failure_keeps_last_good_values_and_original_retrieval(self):
        good = collect_iea_reports(fetch=True, previous=None, timestamp=NOW, fetcher=fetcher)
        before = copy.deepcopy(good)
        def fail(url):
            raise OSError("upstream unavailable")
        failed = collect_iea_reports(fetch=True, previous=good, timestamp="2026-10-02T00:00:00+00:00", fetcher=fail)
        self.assertEqual(failed["status"], "cached_fallback")
        self.assertEqual(failed["retrieved_at"], NOW)
        self.assertEqual(failed["records"], good["records"])
        self.assertEqual(good, before)

    def test_older_revision_cannot_replace_cache(self):
        good = collect_iea_reports(fetch=True, previous=None, timestamp=NOW, fetcher=fetcher)
        def older(url):
            return DISCOVERY if url == IEA_DISCOVERY_URL else report(published="2026-09-17")
        result = collect_iea_reports(fetch=True, previous=good, timestamp=NOW, fetcher=older)
        self.assertEqual(result["status"], "cached_fallback")
        self.assertEqual(result["records"], good["records"])
        self.assertEqual(result["candidate_errors"][0]["status"], "review_required_not_published")

    def test_offline_never_calls_network_and_empty_has_no_seed(self):
        def fail(url):
            self.fail("offline attempted network")
        result = collect_iea_reports(fetch=False, previous=None, timestamp=NOW, fetcher=fail)
        self.assertEqual(result["status"], "not_fetched")
        self.assertEqual(result["records"], {"hormuz": [], "suez": []})

    def test_eia_components_not_replaced_by_newer_iea_total(self):
        from test_official_cargo import fixture_html, IMO_FIXTURE
        from shipping_capacity.official_cargo import collect_official_cargo, EIA_URL, IMO_URL
        from datetime import datetime
        def combined(url):
            return fixture_html() if url == EIA_URL else IMO_FIXTURE if url == IMO_URL else fetcher(url)
        monitor = collect_official_cargo(fetch=True, now=datetime.fromisoformat(NOW), fetcher=combined)
        point = monitor["chokepoints"]["hormuz"]
        self.assertTrue(all(row["publisher"] == "EIA" and row["period"] == "2Q26" for row in point["reference_cards"]))
        self.assertEqual(point["supplementary_reference_cards"][0]["value"], 7_600_000)
        self.assertEqual(len(point["reported_series"]), 9)
        self.assertIsNone(point["daily_crude_barrels"]["value"])
        from jsonschema import Draft202012Validator, FormatChecker
        import json
        from pathlib import Path
        schema = json.loads((Path(__file__).resolve().parents[1] / "schemas/shipping_capacity_v1.schema.json").read_text())["properties"]["official_cargo_monitor"]
        self.assertEqual(list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(monitor)), [])


if __name__ == "__main__":
    unittest.main()
