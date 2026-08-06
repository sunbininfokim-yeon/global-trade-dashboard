from __future__ import annotations

import json
import unittest
from pathlib import Path

from shipping_capacity.engine import InputError, estimate_interval, required_capacity_dwt, simulate_route
from shipping_capacity.portwatch import summarize_series


ROOT = Path(__file__).resolve().parents[1]


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.routes = json.loads((ROOT / "config" / "routes.json").read_text(encoding="utf-8"))
        cls.scenarios = json.loads((ROOT / "config" / "scenarios.json").read_text(encoding="utf-8"))

    def test_capacity_formula(self) -> None:
        self.assertAlmostEqual(required_capacity_dwt(365_000, 10, 1.0), 10_000)

    def test_bidirectional_service_counts_shared_fleet_once(self) -> None:
        route = {
            "id": "two_way_container",
            "ship_type": "container",
            "annual_cargo_tonnes": 365_000,
            "distance_nm_one_way": 1_200,
            "speed_knots": 10,
            "port_days_round_trip": 0,
            "utilization": 1.0,
            "reserve_margin": 0,
            "directions": [
                {"id": "eastbound", "annual_cargo_tonnes": 365_000, "utilization": 1.0},
                {"id": "westbound", "annual_cargo_tonnes": 182_500, "utilization": 1.0},
            ],
        }
        result = simulate_route(route, None, 1_000_000)
        self.assertAlmostEqual(result["baseline_required_dwt"], 10_000)
        self.assertEqual(result["known_direction_count"], 2)
        self.assertEqual(result["capacity_driver_direction_id"], "eastbound")
        self.assertEqual(result["total_annual_cargo_tonnes"], 547_500)

    def test_larger_reverse_flow_becomes_capacity_driver(self) -> None:
        route = {
            "id": "reverse_driven_container",
            "ship_type": "container",
            "annual_cargo_tonnes": 365_000,
            "distance_nm_one_way": 1_200,
            "speed_knots": 10,
            "port_days_round_trip": 0,
            "utilization": 1.0,
            "reserve_margin": 0,
            "directions": [
                {"id": "eastbound", "annual_cargo_tonnes": 365_000, "utilization": 1.0},
                {"id": "westbound", "annual_cargo_tonnes": 730_000, "utilization": 1.0},
            ],
        }
        result = simulate_route(route, None, 1_000_000)
        self.assertAlmostEqual(result["baseline_required_dwt"], 20_000)
        self.assertEqual(result["capacity_driver_direction_id"], "westbound")

    def test_unaffected_route_is_unchanged(self) -> None:
        route = next(row for row in self.routes if row["id"] == "brazil_china_soy")
        scenario = next(row for row in self.scenarios if row["id"] == "suez_100pct_28d")
        result = simulate_route(route, scenario, 1_036_158_000)
        self.assertEqual(result["affected_flow_share"], 0)
        self.assertAlmostEqual(result["traffic_change_pct"], 0)

    def test_suez_reroute_absorbs_capacity(self) -> None:
        route = next(row for row in self.routes if row["id"] == "asia_north_europe_container")
        scenario = next(row for row in self.scenarios if row["id"] == "suez_100pct_28d")
        result = simulate_route(route, scenario, 363_759_100)
        self.assertGreater(result["operational_capacity_absorbed_dwt"], 0)
        self.assertGreater(result["reroute_extra_cycle_days"], 0)
        self.assertLess(result["deliverable_flow_index"], 1)

    def test_no_reroute_route_can_wait_and_cancel(self) -> None:
        route = next(row for row in self.routes if row["id"] == "black_sea_mena_grain")
        scenario = next(row for row in self.scenarios if row["id"] == "bosporus_100pct_14d")
        result = simulate_route(route, scenario, 1_036_158_000)
        self.assertEqual(result["rerouted_flow_share"], 0)
        self.assertGreater(result["waiting_flow_share"], 0)
        self.assertGreater(result["cancelled_flow_share"], 0)
        self.assertGreater(result["lost_cargo_tonnes_horizon"], 0)

    def test_interval_is_ordered_and_reproducible(self) -> None:
        route = self.routes[0]
        scenario = self.scenarios[0]
        first = estimate_interval(route, scenario, 363_759_100, samples=60)
        second = estimate_interval(route, scenario, 363_759_100, samples=60)
        self.assertEqual(first, second)
        for metric in first.values():
            self.assertLessEqual(metric["p10"], metric["p50"])
            self.assertLessEqual(metric["p50"], metric["p90"])

    def test_zero_utilization_is_rejected(self) -> None:
        with self.assertRaises(InputError):
            required_capacity_dwt(100, 10, 0)


class PortWatchTests(unittest.TestCase):
    def test_observed_closure_from_recent_drop(self) -> None:
        rows = []
        for day in range(35):
            capacity = 50 if day >= 28 else 100
            rows.append(
                {
                    "date": 1_700_000_000_000 + day * 86_400_000,
                    "portname": "Test Canal",
                    "capacity": capacity,
                    "capacity_container": capacity,
                    "capacity_dry_bulk": capacity,
                    "capacity_general_cargo": capacity,
                    "capacity_tanker": capacity,
                }
            )
        result = summarize_series(rows, "test")
        self.assertAlmostEqual(result["metrics"]["all"]["observed_shortfall_fraction"], 0.5)

    def test_arcgis_date_only_strings_are_supported(self) -> None:
        rows = []
        for day in range(35):
            rows.append(
                {
                    "date": f"2026-07-{day + 1:02d}" if day < 31 else f"2026-08-{day - 30:02d}",
                    "portname": "Test Canal",
                    "capacity": 100,
                    "capacity_container": 100,
                    "capacity_dry_bulk": 100,
                    "capacity_general_cargo": 100,
                    "capacity_tanker": 100,
                }
            )
        result = summarize_series(rows, "test")
        self.assertEqual(result["latest_date"], "2026-08-04")
        self.assertEqual(result["quality"], "observed_capacity_shortfall_7d_vs_prior_28d")


if __name__ == "__main__":
    unittest.main()
