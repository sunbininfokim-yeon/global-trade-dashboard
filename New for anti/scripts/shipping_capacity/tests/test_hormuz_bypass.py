"""Fixtures are tests only; production never emits fixture or seed values."""

import json
import unittest
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from shipping_capacity.hormuz_bypass import (
    collect_hormuz_bypass, parse_yanbu_rows, summarize_yanbu, threat_status, yanbu_query_url,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def epoch_ms(day):
    return int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp() * 1000)


def payload(days, export=100.0):
    start = date(2026, 9, 25) - timedelta(days=days - 1)
    return {"features": [{"attributes": {
        "date": epoch_ms(start + timedelta(days=offset)), "portcalls_tanker": 1,
        "export_tanker": export if offset < days - 7 else 0.0, "import_tanker": 0.0,
    }} for offset in range(days)]}


def official_fixture():
    def rows(point, scope, values):
        return [{"publisher": "EIA", "frequency": "quarterly", "cargo_category": "crude_condensate", "unit": "barrels_per_day",
                 "geography_scope": scope, "period": period, "period_start": start, "value": value}
                for (period, start), value in zip((("1Q26", "2026-01-01"), ("2Q26", "2026-04-01")), values)]
    return {"chokepoints": {
        "hormuz": {"reported_series": rows("hormuz", "strait_of_hormuz", (10_900_000, 3_700_000))},
        "bab_el_mandeb": {"reported_series": rows("bab_el_mandeb", "strait_of_bab_el_mandeb", (3_400_000, 6_100_000))
                          + [{"publisher": "EIA", "frequency": "quarterly", "cargo_category": "total_oil", "unit": "barrels_per_day",
                              "geography_scope": "strait_of_bab_el_mandeb", "period": "2Q26", "period_start": "2026-04-01", "value": 8_100_000}]},
    }}


class BypassTests(unittest.TestCase):
    def test_query_only_accepts_checked_port_ids(self):
        url = yanbu_query_url(["port570", "port1408"], date(2026, 1, 1))
        where = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["where"][0]
        self.assertEqual(where, "portid IN ('port570','port1408') AND date >= DATE '2026-01-01'")
        with self.assertRaises(ValueError):
            yanbu_query_url(["port570' OR 1=1 --"], date(2026, 1, 1))

    def test_negative_or_error_payload_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_yanbu_rows({"error": {"code": 400}})
        bad = payload(3)
        bad["features"][0]["attributes"]["export_tanker"] = -1
        with self.assertRaises(ValueError):
            parse_yanbu_rows(bad)

    def test_monthly_means_and_recent_change(self):
        rows = parse_yanbu_rows(payload(35))
        summary = summarize_yanbu(rows, NOW.date())
        self.assertEqual(summary["latest_date"], "2026-09-25")
        self.assertEqual(summary["recent_7d_mean_tonnes_per_day"], 0.0)
        self.assertEqual(summary["prior_28d_mean_tonnes_per_day"], 100.0)
        self.assertEqual(summary["change_pct"], -100.0)
        september = next(row for row in summary["monthly"] if row["month"] == "2026-09")
        self.assertTrue(september["partial_month"])  # 25 of 30 days observed

    def test_short_history_has_no_change_figure(self):
        summary = summarize_yanbu(parse_yanbu_rows(payload(10)), NOW.date())
        self.assertIsNone(summary["prior_28d_mean_tonnes_per_day"])
        self.assertIsNone(summary["change_pct"])

    def test_threat_status_expires_with_review_age(self):
        config = json.loads((ROOT / "config" / "hormuz_bypass.json").read_text(encoding="utf-8"))
        self.assertEqual(threat_status(config, date(2026, 10, 1))["status"], "recent_events_reported")
        self.assertEqual(threat_status(config, date(2027, 1, 1))["status"], "log_review_stale")
        quiet = {**config, "reviewed_at": "2026-12-20"}
        self.assertEqual(threat_status(quiet, date(2026, 12, 21))["status"], "no_recent_events_in_log")

    def test_every_logged_event_cites_a_source(self):
        config = json.loads((ROOT / "config" / "hormuz_bypass.json").read_text(encoding="utf-8"))
        for event in config["threat_events"]:
            self.assertIn(event["evidence_class"], ("press_report", "official_statement"))
            self.assertTrue(event["sources"])
            self.assertTrue(all(source["url"].startswith("https://") for source in event["sources"]))

    def test_comparison_keeps_crude_only_and_never_computes_diversion(self):
        out = collect_hormuz_bypass(ROOT / "config", now=NOW, official_cargo=official_fixture())
        comparison = out["official_crude_comparison"]
        self.assertIsNone(comparison["diverted_volume"])
        bab = next(series for series in comparison["series"] if series["chokepoint_id"] == "bab_el_mandeb")
        self.assertEqual([point["value"] for point in bab["points"]], [3_400_000, 6_100_000])  # total_oil row excluded
        suez = next(series for series in comparison["series"] if series["chokepoint_id"] == "suez")
        self.assertEqual(suez["points"], [])

    def test_fetch_failure_keeps_last_good_summary(self):
        good = collect_hormuz_bypass(ROOT / "config", fetch=True, now=NOW, fetcher=lambda url: json.dumps(payload(35)).encode())
        self.assertEqual(good["sources"]["portwatch_ports"]["status"], "fetched")
        self.assertNotIn("rows", good["sources"]["portwatch_ports"])  # raw rows are not republished

        def fail(url):
            raise OSError("down")
        later = collect_hormuz_bypass(ROOT / "config", fetch=True, now=NOW, previous=good, fetcher=fail)
        self.assertEqual(later["sources"]["portwatch_ports"]["status"], "cached_fallback")
        self.assertEqual(later["yanbu_port_activity"]["monthly"], good["yanbu_port_activity"]["monthly"])
        empty = collect_hormuz_bypass(ROOT / "config", fetch=True, now=NOW, fetcher=fail)
        self.assertEqual(empty["status"], "unavailable")
        self.assertEqual(empty["yanbu_port_activity"]["status"], "unavailable")

    def test_schema_accepts_monitor(self):
        from jsonschema import Draft202012Validator, FormatChecker
        schema = json.loads((ROOT / "schemas" / "shipping_capacity_v1.schema.json").read_text())["properties"]["hormuz_bypass_monitor"]
        out = collect_hormuz_bypass(ROOT / "config", now=NOW, official_cargo=official_fixture())
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        self.assertEqual(list(validator.iter_errors(out)), [])
        out["official_crude_comparison"]["diverted_volume"] = 1_000_000
        self.assertTrue(list(validator.iter_errors(out)))


if __name__ == "__main__":
    unittest.main()
