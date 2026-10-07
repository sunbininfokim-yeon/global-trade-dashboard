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
        self.assertEqual(
            result["daily_averages"]["latest_daily_observation"]["value"],
            1039.0,
        )
        self.assertEqual(
            result["daily_averages"]["trailing_7d_average"]["observation_count"],
            7,
        )
        self.assertEqual(
            result["daily_averages"]["prior_28d_average"]["observation_count"],
            28,
        )
        self.assertAlmostEqual(
            result["daily_averages"]["trailing_7d_average"]["value"],
            1036.0,
        )
        for metric_key, expected in {
            "all": 1039.0,
            "container": 839.0,
            "dry_bulk": 639.0,
            "general_cargo": 239.0,
            "tanker": 439.0,
        }.items():
            history = result["metric_histories"][metric_key]
            self.assertEqual(history["history_point_count"], 40)
            self.assertEqual(history["history"][-1]["value"], expected)

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
        self.assertEqual(
            result["metric_histories"]["container"]["history"][-1]["value"],
            234.0,
        )

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
        self.assertIsNone(migrated["daily_averages"]["latest_daily_observation"])
        self.assertIsNone(migrated["daily_averages"]["trailing_7d_average"]["value"])

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

    def test_screen_metric_histories_are_bounded_without_cross_type_copying(self) -> None:
        full_history = [
            {"date": f"2026-01-{(day % 28) + 1:02d}", "value": float(day)}
            for day in range(800)
        ]
        screen = _screen_chokepoints_live(
            {
                "test": {
                    "history": [],
                    "metric_histories": {
                        "container": {
                            "metric_key": "container",
                            "history": full_history,
                        }
                    },
                }
            }
        )["test"]
        container = screen["metric_histories"]["container"]
        self.assertEqual(container["history_source_point_count"], 800)
        self.assertEqual(container["history"], full_history[-730:])
        self.assertEqual(container["history_screen_point_limit"], 730)


    def test_screen_year_ago_is_aligned_52_weeks_back_without_filling_gaps(self) -> None:
        from datetime import date, timedelta
        start = date(2025, 1, 1)
        full_history = [
            {"date": (start + timedelta(days=day)).isoformat(), "value": float(day)}
            for day in range(600)
            if day != 250  # a missing prior-year day must stay null
        ]
        screen = _screen_chokepoints_live(
            {"test": {"history": [], "metric_histories": {
                "tanker": {"metric_key": "tanker", "history": full_history},
                "general_cargo": {"metric_key": "general_cargo", "history": full_history},
            }}}
        )["test"]
        tanker = screen["metric_histories"]["tanker"]
        values = tanker["year_ago"]["values"]
        self.assertEqual(len(values), len(tanker["history"]))
        for row, prior in zip(tanker["history"], values):
            offset = (date.fromisoformat(row["date"]) - start).days - 364
            expected = None if offset < 0 or offset == 250 else float(offset)
            self.assertEqual(prior, expected)
        self.assertIsNone(screen["metric_histories"]["general_cargo"]["year_ago"])
        self.assertEqual(len(screen["metric_histories"]["general_cargo"]["history"]), 180)
        # last 7 screen days are 593..599; 52 weeks earlier is 229..235
        self.assertEqual(tanker["year_ago"]["recent_7d_mean"], 596.0)
        self.assertEqual(tanker["year_ago"]["year_ago_7d_mean"], 232.0)
        self.assertEqual(tanker["year_ago"]["change_pct"], round((596 / 232 - 1) * 100, 1))


class RouteOperationalContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.snapshot = build_snapshot(ROOT / "config")
        bundle = build_artifact_bundle(cls.snapshot)
        cls.screen = bundle["screen"]
        cls.grid = bundle["scenario_grid"]["ui_scenario_grid"]

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
            for item in self.grid["rows"]
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
            for item in self.grid["rows"]
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

    def test_grid_ship_type_breakdown_is_precomputed_and_reconciles(self) -> None:
        hormuz = next(
            item
            for item in self.grid["rows"]
            if item["base_scenario_id"] == "hormuz_effective_80pct_28d"
            and item["closure_pct"] == 80
            and item["duration_days"] == 28
        )
        self.assertEqual(
            {item["ship_type"] for item in hormuz["summary"]["ship_type_breakdown"]},
            {"tanker"},
        )
        for row in self.grid["rows"]:
            summary = row["summary"]
            breakdown = summary["ship_type_breakdown"]
            if summary["affected_baseline_dwt"] == 0:
                self.assertEqual(breakdown, [])
                continue
            self.assertTrue(breakdown)
            self.assertAlmostEqual(
                sum(item["affected_baseline_dwt"] for item in breakdown),
                summary["affected_baseline_dwt"],
                delta=0.01,
            )
            self.assertAlmostEqual(
                sum(item["operational_capacity_absorbed_dwt"] for item in breakdown),
                summary["operational_capacity_absorbed_dwt"],
                delta=0.01,
            )
            self.assertAlmostEqual(
                sum(item["backlog_cargo_tonnes_horizon"] for item in breakdown),
                summary["backlog_cargo_tonnes_horizon"],
                delta=0.01,
            )


if __name__ == "__main__":
    unittest.main()
