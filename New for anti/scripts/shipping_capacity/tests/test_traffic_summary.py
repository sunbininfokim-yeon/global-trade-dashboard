"""Synthetic series here are test fixtures only, never production data."""
import copy
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import refresh_traffic_summary
from shipping_capacity.artifacts import _screen_chokepoints_live
from shipping_capacity.traffic_summary import build_traffic_summary


END = date(2026, 3, 31)


def status():
    rows = [{"date": (END - timedelta(days=offset)).isoformat(), "value": 100.0} for offset in reversed(range(730))]
    return {"latest_date": END.isoformat(), "metric_histories": {key: {"history": copy.deepcopy(rows)} for key in ("all", "container", "dry_bulk", "tanker", "general_cargo")}}


class TrafficSummaryTests(unittest.TestCase):
    def test_calendar_windows_and_month_end_clamp(self):
        result = build_traffic_summary(status())
        self.assertEqual(result["current"]["start_date"], "2026-03-25")
        self.assertEqual(result["comparisons"]["week"]["baseline"]["end_date"], "2026-03-24")
        self.assertEqual(result["comparisons"]["month"]["baseline"]["start_date"], "2026-02-22")
        self.assertEqual(result["comparisons"]["month"]["baseline"]["end_date"], "2026-02-28")
        self.assertEqual(result["comparisons"]["year"]["baseline"]["end_date"], (END - timedelta(days=364)).isoformat())
        self.assertEqual(result["comparisons"]["month"]["change_pct"], 0)

    def test_percentage_uses_preceding_week_not_prior_28_days(self):
        data = status()
        for row in data["metric_histories"]["all"]["history"][-7:]:
            row["value"] = 150
        result = build_traffic_summary(data)
        self.assertEqual(result["current"]["value"], 150)
        self.assertEqual(result["comparisons"]["week"]["change_pct"], 50)

    def test_missing_day_blocks_only_affected_comparison(self):
        data = status()
        rows = data["metric_histories"]["all"]["history"]
        rows[:] = [row for row in rows if row["date"] != "2026-02-25"]
        result = build_traffic_summary(data)
        self.assertIsNone(result["comparisons"]["month"]["change_pct"])
        self.assertEqual(result["comparisons"]["week"]["change_pct"], 0)

    def test_missing_recent_day_never_uses_seven_older_observations(self):
        data = status()
        data["metric_histories"]["all"]["history"].pop()
        result = build_traffic_summary(data)
        self.assertIsNone(result["current"]["value"])
        self.assertEqual(result["current"]["observed_days"], 6)
        self.assertIsNone(result["comparisons"]["week"]["change_pct"])

    def test_zero_baseline_not_infinite_and_zero_current_is_valid(self):
        data = status()
        for row in data["metric_histories"]["all"]["history"][-14:-7]:
            row["value"] = 0
        result = build_traffic_summary(data)
        self.assertEqual(result["comparisons"]["week"]["status"], "zero_baseline")
        self.assertIsNone(result["comparisons"]["week"]["change_pct"])
        for row in data["metric_histories"]["all"]["history"][-7:]:
            row["value"] = 0
        self.assertEqual(build_traffic_summary(data)["comparisons"]["month"]["change_pct"], -100)

    def test_duplicates_invalid_values_and_unsorted_history(self):
        data = status()
        rows = data["metric_histories"]["all"]["history"]
        rows.append({"date": END.isoformat(), "value": 999})
        rows.reverse()
        self.assertIsNone(build_traffic_summary(data)["current"]["value"])
        for value in (float("nan"), float("inf"), True, -1):
            data = status()
            data["metric_histories"]["all"]["history"][-1]["value"] = value
            self.assertIsNone(build_traffic_summary(data)["current"]["value"])

    def test_sorted_ship_type_weights_use_all_ship_denominator(self):
        data = status()
        for key, value in (("all", 1000), ("tanker", 400), ("dry_bulk", 300), ("container", 250), ("general_cargo", 40)):
            for row in data["metric_histories"][key]["history"]:
                row["value"] = value
        before = copy.deepcopy(data)
        result = build_traffic_summary(data)
        self.assertEqual([row["metric_key"] for row in result["ship_types"][:3]], ["tanker", "dry_bulk", "container"])
        self.assertEqual([row["share_pct"] for row in result["ship_types"][:3]], [40, 30, 25])
        self.assertEqual(result["remaining_types_share_pct"], 5)
        self.assertEqual(data, before)

    def test_non_additive_or_missing_ship_types_do_not_renormalize(self):
        result = build_traffic_summary(status())
        self.assertEqual(result["composition_status"], "non_additive_source_totals")
        self.assertTrue(all(row["share_pct"] is None for row in result["ship_types"]))
        data = status()
        data["metric_histories"].pop("container")
        self.assertEqual(build_traffic_summary(data)["composition_status"], "incomplete_ship_types")

    def test_legacy_tanker_history_is_not_all_ship_history(self):
        data = status()
        data["history"] = data["metric_histories"]["tanker"]["history"]
        data["history_metric_key"] = "tanker"
        data["metric_histories"] = {}
        self.assertIsNone(build_traffic_summary(data)["current"]["value"])

    def test_summary_survives_screen_trim_with_two_year_chart_history(self):
        data = status()
        data["traffic_summary"] = build_traffic_summary(data)
        screen = _screen_chokepoints_live({"suez": data})["suez"]
        self.assertEqual(screen["traffic_summary"], data["traffic_summary"])
        self.assertEqual(len(screen["history"]), 0)
        self.assertEqual(len(screen["metric_histories"]["all"]["history"]), 730)
        self.assertEqual(screen["traffic_summary"]["comparisons"]["year"]["change_pct"], 0)

    def test_cached_refresh_preserves_backtest_records_and_rejects_mixed_bundle(self):
        names = {"screen": "shipping_capacity_v1.json", "diagnostics": "shipping_capacity_diagnostics_v1.json", "scenario_grid": "shipping_capacity_scenario_grid_v1.json", "backtests": "shipping_capacity_backtests_v1.json"}
        existing = {key: {"bundle_id": "old", "generated_at": "2026-03-31"} for key in names}
        existing["backtests"].update({"event_observations": [{"value": 123}], "historical_event_calibration": {"observed": 456}})
        rebuilt = {key: {"bundle_id": "new", "generated_at": "2026-03-31"} for key in names}
        with tempfile.TemporaryDirectory() as directory:
            for key, name in names.items():
                (Path(directory) / name).write_text(json.dumps(existing[key]))
            with patch("sys.argv", ["refresh_traffic_summary", "--data-dir", directory]), patch.object(refresh_traffic_summary, "build_artifact_bundle", return_value=rebuilt), patch.object(refresh_traffic_summary, "golden_contract_failures", return_value=[]):
                refresh_traffic_summary.main()
            backtests = json.loads((Path(directory) / names["backtests"]).read_text())
            self.assertEqual(backtests, {**existing["backtests"], "bundle_id": "new"})
            (Path(directory) / names["diagnostics"]).write_text(json.dumps(existing["diagnostics"]))
            before = {name: (Path(directory) / name).read_text() for name in names.values()}
            with patch("sys.argv", ["refresh_traffic_summary", "--data-dir", directory]), patch.object(refresh_traffic_summary, "build_artifact_bundle") as build:
                with self.assertRaisesRegex(SystemExit, "bundle mismatch"):
                    refresh_traffic_summary.main()
                build.assert_not_called()
            self.assertEqual(before, {name: (Path(directory) / name).read_text() for name in names.values()})


if __name__ == "__main__":
    unittest.main()
