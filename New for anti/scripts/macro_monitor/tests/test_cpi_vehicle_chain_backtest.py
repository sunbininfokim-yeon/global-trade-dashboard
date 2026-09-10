from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np

from macro_monitor.cpi.vehicle_chain_backtest import _design, run_relationship


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config" / "cpi_vehicle_chain_backtest_v1.json").read_text(encoding="utf-8"))


def months() -> list[str]:
    return [f"{year:04d}-{month:02d}" for year in range(2010, 2027) for month in range(1, 13)]


class TestVehicleChainBacktest(unittest.TestCase):
    def test_no_contemporaneous_lag_is_allowed(self):
        for row in CONFIG["relationships"]:
            self.assertGreaterEqual(min(row["lag_grid_months"]), 1)

    def test_existing_parts_to_repair_candidate_is_kept_separate(self):
        relation = next(row for row in CONFIG["relationships"] if row["id"] == "vehicle_parts_to_maintenance")
        self.assertEqual(relation["relationship_map_id"], "vehicle_parts_to_repair")
        self.assertEqual(relation["source"], "motor_vehicle_parts")
        self.assertEqual(relation["target"], "motor_vehicle_maintenance")

    def test_design_uses_only_prior_source_values(self):
        target = {"2024-01": 1.0, "2024-02": 2.0, "2024-03": 3.0}
        source = {"2024-01": 10.0, "2024-02": 20.0, "2024-03": 30.0}
        dates, x, y, labels = _design(target, source, {}, [1])
        self.assertEqual(dates, ["2024-02", "2024-03"])
        self.assertEqual(labels, ["target_lag_1", "source_lag_1"])
        np.testing.assert_array_equal(x[0], [1.0, 10.0])
        np.testing.assert_array_equal(y, [2.0, 3.0])

    def test_each_path_is_evaluated_independently_and_never_activates(self):
        rng = np.random.default_rng(22)
        history = {month: float(rng.normal()) for month in months()}
        series = {
            "new_vehicles": history,
            "used_cars_and_trucks": {month: 0.2 * history[month] + float(rng.normal(scale=0.2)) for month in history},
            "motor_vehicle_parts": {month: float(rng.normal()) for month in history},
            "motor_vehicle_maintenance": {month: float(rng.normal()) for month in history},
            "motor_vehicle_insurance": {month: float(rng.normal()) for month in history},
            "core_goods": {month: float(rng.normal()) for month in history},
            "motor_fuel": {month: float(rng.normal()) for month in history},
        }
        result = run_relationship(CONFIG["relationships"][0], series=series, minimum_train_months=72)
        self.assertEqual(result["activation"]["status"], "not_activated")
        self.assertIn("diebold_mariano", result["out_of_sample"])


if __name__ == "__main__":
    unittest.main()
