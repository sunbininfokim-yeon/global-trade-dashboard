"""Unit contracts for secret-safe external CPI pathway validation."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np

from macro_monitor.cpi.external_backtest import (
    MonthlyPoint,
    _benjamini_hochberg,
    _design,
    mom_pct,
    run_relationship,
    fetch_fred_monthly_series,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config" / "cpi_external_backtest_v1.json").read_text(encoding="utf-8"))


def month_range(start_year: int = 2010, end_year: int = 2026) -> list[str]:
    return [f"{year:04d}-{month:02d}" for year in range(start_year, end_year + 1) for month in range(1, 13)]


class TestCpiExternalBacktest(unittest.TestCase):
    def test_fred_public_csv_fallback_needs_no_key(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self): return b"DATE,TEST\n2024-01-01,10\n2024-02-01,11\n"

        points = fetch_fred_monthly_series("TEST", api_key="", start="2024-01", opener=lambda *_args, **_kwargs: Response())
        self.assertEqual([(point.month, point.value) for point in points], [("2024-01", 10.0), ("2024-02", 11.0)])

    def test_mom_uses_monthly_levels(self):
        points = [MonthlyPoint("2024-01", 100.0), MonthlyPoint("2024-02", 103.0)]
        self.assertEqual(mom_pct(points), {"2024-02": 3.0})

    def test_design_respects_lag_zero_and_one(self):
        target = {"2024-01": 1.0, "2024-02": 2.0, "2024-03": 3.0}
        source = {"2024-01": 10.0, "2024-02": 20.0, "2024-03": 30.0}
        months, x, y, labels = _design(sorted(target), target, {"x": source}, {}, [0, 1])
        self.assertEqual(months, ["2024-02", "2024-03"])
        self.assertEqual(labels[:3], ["target_lag_1", "x_lag_0", "x_lag_1"])
        np.testing.assert_array_equal(x[0][:3], [1.0, 20.0, 10.0])
        np.testing.assert_array_equal(y, [2.0, 3.0])

    def test_config_is_limited_to_the_two_mapped_external_paths(self):
        self.assertEqual({row["relationship_map_id"] for row in CONFIG["relationships"]}, {"energy_to_airfares", "energy_cost_to_food_prices"})
        self.assertTrue(all(row["lag_grid_months"][0] == 0 for row in CONFIG["relationships"]))

    def test_results_cannot_activate_on_current_vintage_data(self):
        months = month_range()
        rng = np.random.default_rng(7)
        source = {month: float(rng.normal()) for month in months}
        target = {month: 0.2 * source[month] + float(rng.normal(scale=0.1)) for month in months}
        control = {month: float(rng.normal()) for month in months}
        spec = CONFIG["relationships"][0]
        result = run_relationship(spec, series={
            "cpi_airline_fares_sa": target,
            "jet_fuel_us_gulf_coast_spot": source,
            "industrial_production_sa": control,
        }, minimum_train_months=72)
        self.assertEqual(result["activation"]["status"], "not_activated")
        self.assertGreater(result["coverage"]["oos_months"], 12)
        self.assertIn("diebold_mariano", result["out_of_sample"])
        self.assertIn("lag_months", result["best_lag_out_of_sample_exploratory"])

    def test_fdr_marks_all_rows_without_claiming_causality(self):
        rows = [
            {"conditional_predictive_test": {"pvalue": 0.01}},
            {"conditional_predictive_test": {"pvalue": 0.04}},
        ]
        _benjamini_hochberg(rows)
        self.assertLessEqual(rows[0]["conditional_predictive_test"]["fdr_qvalue"], 0.04)
        self.assertLessEqual(rows[1]["conditional_predictive_test"]["fdr_qvalue"], 0.04)


if __name__ == "__main__":
    unittest.main()
