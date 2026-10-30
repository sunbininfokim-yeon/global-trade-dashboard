"""Fixtures are tests only; production never emits fixture or seed values."""

import unittest
from datetime import date, timedelta

from shipping_capacity.chokepoint_trend import build_chokepoint_trend, official_vs_ais, rolling_yoy


START = date(2025, 1, 1)


def history(days, value_for):
    return [{"date": (START + timedelta(days=offset)).isoformat(), "value": value_for(offset)} for offset in range(days)]


def eia_point(values):
    return {"reported_series": [
        {"publisher": "EIA", "frequency": "quarterly", "cargo_category": "total_oil", "period": period, "period_start": start, "value": value}
        for (period, start), value in zip((("2Q25", "2025-04-01"), ("2Q26", "2026-04-01")), values)
    ], "reference_cards": [{"cargo_category": "total_oil", "value": values[1], "period": "2Q26", "period_end": "2026-06-30", "publisher": "EIA"}],
        "supplementary_reference_cards": [{"cargo_category": "total_oil", "value": 7_600_000, "period": "2026-08", "period_end": "2026-08-31", "publisher": "IEA"}]}


class TrendTests(unittest.TestCase):
    def test_rise_is_kept_positive(self):
        rows = history(600, lambda day: 200.0 if day >= 364 else 100.0)
        series = rolling_yoy(rows, window_days=10)
        self.assertEqual(series["yoy_pct"][-1], 100.0)

    def test_gap_on_either_side_is_not_filled(self):
        rows = [row for row in history(600, lambda day: 100.0) if row["date"] != (START + timedelta(days=599 - 364)).isoformat()]
        self.assertIsNone(rolling_yoy(rows, window_days=1)["yoy_pct"][-1])

    def test_zero_base_has_no_percentage(self):
        rows = history(600, lambda day: 0.0 if day < 364 else 5.0)
        self.assertIsNone(rolling_yoy(rows, window_days=1)["yoy_pct"][-1])

    def test_undercount_flag_compares_shares_not_units(self):
        # official keeps 25% of last year; AIS keeps 5% -> ratio 0.2
        rows = history(600, lambda day: 5.0 if day >= 364 else 100.0)
        result = official_vs_ais(eia_point((20_000_000, 5_000_000)), rows)
        self.assertEqual(result["official_yoy_pct"], -75.0)
        self.assertEqual(result["ais_yoy_pct"], -95.0)
        self.assertEqual(result["ais_to_official_share_ratio"], 0.2)
        self.assertEqual(result["status"], "ais_undercount_likely")

    def test_matching_shares_are_consistent(self):
        rows = history(600, lambda day: 25.0 if day >= 364 else 100.0)
        self.assertEqual(official_vs_ais(eia_point((20_000_000, 5_000_000)), rows)["status"], "consistent")

    def test_thin_ais_coverage_is_not_judged(self):
        rows = [row for index, row in enumerate(history(600, lambda day: 10.0)) if index % 2]
        result = official_vs_ais(eia_point((20_000_000, 5_000_000)), rows)
        self.assertEqual(result["status"], "ais_coverage_insufficient")
        self.assertIsNone(result["ais_to_official_share_ratio"])

    def test_build_reports_newest_official_and_display_metric(self):
        rows = history(600, lambda day: 5.0 if day >= 364 else 100.0)
        out = build_chokepoint_trend(
            [{"id": "hormuz"}, {"id": "panama"}],
            {"hormuz": {"metric_histories": {"tanker": {"history": rows}}}, "panama": {"metric_histories": {"all": {"history": rows}}}},
            [{"chokepoint_id": "hormuz", "metric_key": "tanker"}],
            {"chokepoints": {"hormuz": eia_point((20_000_000, 5_000_000))}},
        )
        hormuz, panama = out["points"]
        self.assertEqual(hormuz["metric_key"], "tanker")
        self.assertEqual(hormuz["latest_yoy_pct"], -95.0)
        self.assertEqual(hormuz["official_latest"]["publisher"], "IEA")
        self.assertEqual(panama["metric_key"], "all")
        self.assertIsNone(panama["official_vs_ais"])


if __name__ == "__main__":
    unittest.main()
