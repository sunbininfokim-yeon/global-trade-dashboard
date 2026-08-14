"""Contracts for published PortWatch history and route-capacity denominators."""

from __future__ import annotations

import unittest
from pathlib import Path

from build_snapshot import build_snapshot
from shipping_capacity.artifacts import _screen_chokepoints_live, build_artifact_bundle
from shipping_capacity.engine import route_operational_profile
from shipping_capacity.portwatch import normalize_status_contract, summarize_series


ROOT = Path(__file__).resolve().parents[1]


class PortWatchHistoryContractTests(unittest.TestCase):
    def test_daily_history_preserves_observed_values_without_interpolation(self) -> None:
        rows = [
            {
                "date": 1_700_000_000_000 + day * 86_400_000,
                "portname": "Test Canal",
                "capacity": 1_000 + day,
                "capacity_container": 800 + day,
                "capacity_dry_bulk": 600 + day,
                "capacity_general_cargo": 200 + day,
                "capacity_tanker": 400 + day,
            }
            for day in range(40)
        ]
        result = summarize_series(rows, "test")
        self.assertEqual(result["history_metric_key"], "all")
        self.assertEqual(result["history_field"], "capacity")
        self.assertEqual(result["history_point_count"], 40)
        self.assertEqual(
            [point["value"] for point in result["history"]],
            [float(1_000 + day) for day in range(40)],
        )
        self.assertEqual(
            result["history_status"],
            "observed_daily_estimated_trade_volume",
        )

    def test_hormuz_history_uses_tanker_metric(self) -> None:
        rows = [
            {
                "date": 1_700_000_000_000 + day * 86_400_000,
                "portname": "Hormuz",
                "capacity": 2_000 + day,
                "capacity_container": 200 + day,
                "capacity_dry_bulk": 300 + day,
                "capacity_general_cargo": 100 + day,
                "capacity_tanker": 900 + day,
            }
            for day in range(35)
        ]
        result = summarize_series(rows, "chokepoint6")
        self.assertEqual(result["history_metric_key"], "tanker")
        self.assertEqual(result["history_field"], "capacity_tanker")
        self.assertEqual(result["history"][-1]["value"], 934.0)

    def test_legacy_summary_does_not_invent_daily_history(self) -> None:
        migrated = normalize_status_contract(
            {
                "metrics": {
                    "all": {
                        "current_7d_mean_estimated_trade_tonnes": 10,
                        "prior_28d_mean_estimated_trade_tonnes": 20,
                    }
                }
            }
        )
        self.assertEqual(migrated["history"], [])
        self.assertEqual(migrated["history_point_count"], 0)
        self.assertEqual(
            migrated["history_status"],
            "unavailable_cached_summary_only",
        )

    def test_screen_history_is_bounded_without_changing_values(self) -> None:
        full_history = [
            {"date": f"2026-01-{(day % 28) + 1:02d}", "value": float(day)}
            for day in range(200)
        ]
        screen = _screen_chokepoints_live(
            {"test": {"history": full_history, "history_point_count": 200}}
        )["test"]
        self.assertEqual(screen["history_point_count"], 180)
        self.assertEqual(screen["history_source_point_count"], 200)
        self.assertEqual(screen["history"], full_history[-180:])


class RouteOperationalContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = build_snapshot(ROOT / "config")
        cls.screen = build_artifact_bundle(cls.snapshot)["screen"]

    def test_route_profile_uses_same_distance_speed_arithmetic_as_engine(self) -> None:
        profile = route_operational_profile(
            {
                "id": "test_route",
                "distance_nm_one_way": 1_200,
                "speed_knots": 10,
                "port_days_round_trip": 2,
                "chokepoints": [
                    {
                        "id": "test_passage",
                        "exposure_share": 1.0,
                        "reroute_available": True,
                        "reroute_extra_nm_one_way": 240,
                    },
                    {
                        "id": "closed_exit",
                        "exposure_share": 1.0,
                        "reroute_available": False,
                        "reroute_extra_nm_one_way": 0,
                    },
                ],
            }
        )
        self.assertAlmostEqual(profile["normal"]["sea_days_one_way"], 5.0)
        self.assertAlmostEqual(profile["normal"]["cycle_days_round_trip"], 12.0)
        detour = profile["chokepoint_alternatives"][0]
        self.assertAlmostEqual(detour["reroute_extra_days_one_way"], 1.0)
        self.assertAlmostEqual(detour["reroute_extra_cycle_days"], 2.0)
        self.assertAlmostEqual(detour["rerouted_cycle_days"], 14.0)
        unavailable = profile["chokepoint_alternatives"][1]
        self.assertIsNone(unavailable["rerouted_cycle_days"])
        self.assertIsNone(unavailable["reroute_extra_nm_one_way"])

    def test_screen_routes_publish_detour_profiles(self) -> None:
        route = next(
            row
            for row in self.screen["routes"]
            if row["id"] == "asia_north_europe_container"
        )
        suez = next(
            row
            for row in route["operational_profile"]["chokepoint_alternatives"]
            if row["chokepoint_id"] == "suez"
        )
        self.assertTrue(suez["reroute_available"])
        self.assertGreater(suez["reroute_extra_days_one_way"], 0)
        self.assertGreater(suez["rerouted_cycle_days"], suez["baseline_cycle_days"])

    def test_scenario_grid_publishes_both_capacity_denominators(self) -> None:
        row = next(
            item
            for item in self.screen["ui_scenario_grid"]["rows"]
            if item["base_scenario_id"] == "hormuz_effective_80pct_28d"
            and item["closure_pct"] == 80
            and item["duration_days"] == 28
        )
        summary = row["summary"]
        absorbed = summary["operational_capacity_absorbed_dwt"]
        self.assertGreater(summary["affected_allocated_dwt_with_reserve"], 0)
        self.assertGreater(summary["relevant_global_type_fleet_dwt"], 0)
        self.assertAlmostEqual(
            summary["operational_capacity_absorbed_pct_of_affected_allocated"],
            absorbed / summary["affected_allocated_dwt_with_reserve"] * 100,
            places=5,
        )
        self.assertAlmostEqual(
            summary["operational_capacity_absorbed_pct_of_relevant_global_type_fleet"],
            absorbed / summary["relevant_global_type_fleet_dwt"] * 100,
            places=5,
        )
        self.assertIn("not an AIS-observed", summary["capacity_denominator_warning"])
        self.assertTrue(row["routes"])
        for route in row["routes"]:
            self.assertGreater(route["allocated_dwt_with_reserve"], 0)
            self.assertGreaterEqual(
                route["operational_capacity_absorbed_pct_of_route_allocated"],
                0,
            )

    def test_zero_impact_grid_does_not_publish_a_fabricated_percentage(self) -> None:
        row = next(
            item
            for item in self.screen["ui_scenario_grid"]["rows"]
            if item["base_scenario_id"] == "hormuz_effective_80pct_28d"
            and item["closure_pct"] == 0
            and item["duration_days"] == 28
        )
        summary = row["summary"]
        self.assertEqual(summary["affected_allocated_dwt_with_reserve"], 0)
        self.assertIsNone(
            summary["operational_capacity_absorbed_pct_of_affected_allocated"]
        )
        self.assertIsNone(summary["commercially_available_pct_of_affected_allocated"])


if __name__ == "__main__":
    unittest.main()
