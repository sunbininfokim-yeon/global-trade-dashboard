from __future__ import annotations

import json
import math
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from build_snapshot import build_snapshot
from shipping_capacity.artifacts import build_artifact_bundle, golden_contract_failures
from shipping_capacity.comtrade_routes import apply_route_flows, select_net_weight_rows
from shipping_capacity.container import summarize_world_bank_teu
from shipping_capacity.engine import InputError, estimate_interval, required_capacity_dwt, simulate_route
from shipping_capacity.environment import (
    simulate_environment_route,
    simulate_environment_route_range,
)
from shipping_capacity.historical_calibration import calibrate_event
from shipping_capacity.ml_validation import analyze_capacity_series
from shipping_capacity.portwatch import (
    normalize_status_contract,
    summarize_series,
    validate_7d_28d_signal,
)
from shipping_capacity.validation import (
    run_temporary_environment_grid,
    run_temporary_scenario_grid,
)


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

    def test_rerouted_cargo_arriving_after_horizon_stays_in_transit(self) -> None:
        route = next(row for row in self.routes if row["id"] == "asia_north_europe_container")
        scenario = {
            "id": "short_horizon",
            "chokepoint_id": "suez",
            "event_type": "physical_chokepoint_closure",
            "closure_fraction": 1.0,
            "residual_throughput_rate": 0.0,
            "duration_days": 7,
            "horizon_days": 7,
            "waiting_days": 7,
        }
        result = simulate_route(route, scenario, 363_759_100)
        self.assertGreater(result["rerouted_in_transit_cargo_tonnes_horizon"], 0)
        self.assertLess(
            result["rerouted_delivered_cargo_tonnes_horizon"],
            result["rerouted_cargo_tonnes_horizon"],
        )
        total = (
            result["served_cargo_tonnes_horizon"]
            + result["backlog_cargo_tonnes_horizon"]
            + result["rerouted_in_transit_cargo_tonnes_horizon"]
            + result["lost_cargo_tonnes_horizon"]
        )
        self.assertAlmostEqual(total, result["total_annual_cargo_tonnes"] / 365 * 7)
        self.assertEqual(len(result["daily_flow_timeline"]), 7)

    def test_event_response_adjustment_changes_behavior(self) -> None:
        route = next(row for row in self.routes if row["id"] == "persian_gulf_east_asia_crude")
        base = {
            "id": "base",
            "chokepoint_id": "hormuz",
            "closure_fraction": 0.8,
            "residual_throughput_rate": 0.2,
            "duration_days": 28,
            "horizon_days": 28,
            "waiting_days": 28,
        }
        operational = simulate_route(
            route,
            {
                **base,
                "event_type": "operational_restriction",
                "response_adjustment": {
                    "reroute_multiplier": 1.0,
                    "wait_multiplier": 1.2,
                    "cancel_multiplier": 0.8,
                },
            },
            669_842_000,
        )
        military = simulate_route(
            route,
            {
                **base,
                "id": "military",
                "event_type": "military_physical_closure",
                "response_adjustment": {
                    "reroute_multiplier": 0.6,
                    "wait_multiplier": 0.8,
                    "cancel_multiplier": 2.0,
                },
            },
            669_842_000,
        )
        self.assertGreater(military["cancelled_flow_share"], operational["cancelled_flow_share"])
        self.assertLess(military["waiting_flow_share"], operational["waiting_flow_share"])

    def test_no_reroute_route_can_wait_and_cancel(self) -> None:
        route = next(row for row in self.routes if row["id"] == "black_sea_mena_grain")
        scenario = next(row for row in self.scenarios if row["id"] == "bosporus_100pct_14d")
        result = simulate_route(route, scenario, 1_036_158_000)
        self.assertEqual(result["rerouted_flow_share"], 0)
        self.assertGreater(result["waiting_flow_share"], 0)
        self.assertGreater(result["cancelled_flow_share"], 0)
        self.assertGreater(result["lost_cargo_tonnes_horizon"], 0)

    def test_full_horizon_waiting_flow_becomes_backlog(self) -> None:
        route = next(row for row in self.routes if row["id"] == "persian_gulf_east_asia_crude")
        scenario = next(row for row in self.scenarios if row["id"] == "hormuz_100pct_28d")
        result = simulate_route(route, scenario, 669_842_000)
        self.assertEqual(result["residual_throughput_rate"], 0)
        self.assertGreater(result["backlog_flow_share"], 0)
        self.assertAlmostEqual(result["cleared_waiting_flow_share"], 0)
        self.assertAlmostEqual(
            result["served_flow_index"],
            1 - result["backlog_flow_share"] - result["cancelled_flow_share"],
        )
        self.assertAlmostEqual(result["served_flow_index"], 0)

    def test_effective_blockage_keeps_residual_throughput_explicit(self) -> None:
        route = next(row for row in self.routes if row["id"] == "persian_gulf_east_asia_crude")
        scenario = next(
            row for row in self.scenarios if row["id"] == "hormuz_effective_80pct_28d"
        )
        result = simulate_route(route, scenario, 669_842_000)
        self.assertAlmostEqual(result["effective_blockage_fraction"], 0.8)
        self.assertAlmostEqual(result["residual_throughput_rate"], 0.2)
        self.assertAlmostEqual(result["served_flow_index"], 0.2)
        self.assertGreater(result["trapped_loaded_dwt"], 0)
        self.assertGreater(result["trapped_vessel_equivalent"], 0)
        self.assertAlmostEqual(
            result["trapped_vessel_equivalent"],
            result["trapped_loaded_dwt"] / result["reference_vessel_dwt_mid"],
        )
        self.assertGreater(result["insurance_excluded_dwt"], 0)
        self.assertLess(result["commercially_available_dwt"], result["allocated_dwt_with_reserve"])

    def test_waiting_can_clear_after_short_event(self) -> None:
        route = next(row for row in self.routes if row["id"] == "black_sea_mena_grain")
        scenario = next(row for row in self.scenarios if row["id"] == "bosporus_100pct_14d")
        result = simulate_route(route, scenario, 1_036_158_000)
        self.assertGreater(result["cleared_waiting_flow_share"], 0)
        self.assertAlmostEqual(result["backlog_flow_share"], 0)

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

    def test_inconsistent_blockage_and_residual_are_rejected(self) -> None:
        route = next(row for row in self.routes if row["id"] == "persian_gulf_east_asia_crude")
        scenario = dict(next(row for row in self.scenarios if row["id"] == "hormuz_effective_80pct_28d"))
        scenario["residual_throughput_rate"] = 0.30
        with self.assertRaises(InputError):
            simulate_route(route, scenario, 669_842_000)

    def test_environment_speed_reduction_lowers_service_equivalent_dwt(self) -> None:
        route = {
            "id": "environment_test",
            "ship_type": "container",
            "distance_nm_one_way": 1_200,
            "speed_knots": 10,
            "port_days_round_trip": 0,
            "_baseline_required_dwt": 100_000,
            "_allocated_dwt_with_reserve": 110_000,
        }
        scenario = {
            "id": "test",
            "year": 2030,
            "ship_type_assumptions": {
                "container": {
                    "speed_response_share": 1.0,
                    "speed_reduction_fraction": 0.1,
                    "retrofit_offhire_share": 0.0,
                }
            },
        }
        result = simulate_environment_route(route, scenario)
        self.assertAlmostEqual(result["effective_capacity_retention_rate"], 0.9)
        self.assertAlmostEqual(result["effective_service_capacity_dwt"], 99_000)
        self.assertGreater(result["same_service_required_dwt"], 100_000)
        self.assertEqual(result["physical_allocated_dwt"], 110_000)

    def test_environment_full_speed_reduction_is_rejected(self) -> None:
        route = {
            "id": "environment_invalid",
            "ship_type": "container",
            "distance_nm_one_way": 1_200,
            "speed_knots": 10,
            "port_days_round_trip": 0,
            "_baseline_required_dwt": 100_000,
            "_allocated_dwt_with_reserve": 110_000,
        }
        scenario = {
            "id": "invalid",
            "year": 2030,
            "ship_type_assumptions": {
                "container": {
                    "speed_response_share": 1.0,
                    "speed_reduction_fraction": 1.0,
                    "retrofit_offhire_share": 0.0,
                }
            },
        }
        with self.assertRaises(InputError):
            simulate_environment_route(route, scenario)

    def test_environment_segmented_range_is_ordered(self) -> None:
        route = dict(self.routes[0])
        baseline = simulate_route(route, None, 363_759_100)
        route["_baseline_required_dwt"] = baseline["baseline_required_dwt"]
        route["_allocated_dwt_with_reserve"] = baseline["allocated_dwt_with_reserve"]
        scenario = json.loads(
            (ROOT / "config" / "environment_scenarios.json").read_text(
                encoding="utf-8"
            )
        )["scenarios"][0]
        profiles = json.loads(
            (ROOT / "config" / "environment_route_profiles.json").read_text(
                encoding="utf-8"
            )
        )
        result = simulate_environment_route_range(route, scenario, profiles)
        interval = result["effective_service_capacity_dwt_range"]
        self.assertLessEqual(interval["low"], interval["central"])
        self.assertLessEqual(interval["central"], interval["high"])
        self.assertEqual(len(result["response_cases"]), 3)
        self.assertEqual(result["regulatory_dimensions"]["vessel_size_class"], "ulcv")


class PortWatchTests(unittest.TestCase):
    def test_multi_model_analysis_uses_chronological_holdout_and_baselines(self) -> None:
        values = [
            300 + 25 * math.sin(day / 11) - (80 if 150 <= day < 180 else 0)
            for day in range(260)
        ]
        result = analyze_capacity_series(values)
        self.assertGreaterEqual(result["test_count"], 20)
        self.assertIn(
            result["selected_model"],
            {"linear", "ridge", "random_forest", "gradient_boosting"},
        )
        model_names = {row["model"] for row in result["models"]}
        self.assertTrue(
            {"persistence", "linear", "ridge", "random_forest", "gradient_boosting"}
            .issubset(model_names)
        )
        self.assertIn(result["forecast_use"], {"eligible_exploratory", "descriptive_only"})
        self.assertEqual(
            result["target_scale"],
            "symmetric capacity gap in [-2, 2]; positive means shortfall",
        )
        self.assertIn("beats_best_simple_baseline_by_5pct", result)
        self.assertEqual(result["purged_count"], 7)
        self.assertEqual(result["walk_forward_backtest"]["status"], "completed")
        self.assertEqual(result["walk_forward_backtest"]["fold_count"], 4)
        self.assertEqual(result["walk_forward_backtest"]["purge_gap_samples"], 7)
        for fold in result["walk_forward_backtest"]["folds"]:
            self.assertEqual(fold["purged_count"], 7)
        self.assertGreaterEqual(result["candidate_next_7d_shortfall_fraction"], -1.0)
        self.assertLessEqual(result["candidate_next_7d_shortfall_fraction"], 1.0)
        self.assertIsNotNone(result["current_regime"])
        self.assertIsNotNone(result["current_anomaly"])

    def test_walk_forward_signal_validation_is_chronological(self) -> None:
        rows = [
            {
                "date": 1_700_000_000_000 + day * 86_400_000,
                "capacity_tanker": 250 - day + (day % 9) * 2,
            }
            for day in range(120)
        ]
        result = validate_7d_28d_signal(rows, "capacity_tanker")
        self.assertGreaterEqual(result["sample_count"], 70)
        self.assertGreater(result["train_count"], result["test_count"])
        self.assertIn(result["status"], {"exploratory_positive_skill", "exploratory_no_proven_skill"})
        self.assertIn("test_r2", result)
        self.assertIn("persistence_mae_fraction", result)
        if result["status"] == "exploratory_no_proven_skill":
            self.assertEqual(result["forecast_use"], "descriptive_only")

    @patch("build_snapshot.PortWatchClient.fetch_status", side_effect=OSError("offline"))
    def test_failed_live_fetch_preserves_previous_observation(self, _fetch_status) -> None:
        previous = {
            "suez": {
                "latest_date": "2026-08-01",
                "metrics": {
                    "all": {
                        "observed_shortfall_fraction": 0.25,
                    }
                },
            }
        }
        snapshot = build_snapshot(
            ROOT / "config",
            fetch_portwatch=True,
            fallback_live_status=previous,
        )
        self.assertEqual(snapshot["chokepoints_live"]["suez"]["latest_date"], "2026-08-01")
        self.assertEqual(len(snapshot["live_fetch_errors"]), 5)
        self.assertEqual(snapshot["model"]["version"], snapshot["model_review"]["model_version"])
        display = next(row for row in snapshot["live_display"] if row["chokepoint_id"] == "suez")
        self.assertAlmostEqual(display["trade_volume_shortfall_fraction"], 0.25)
        self.assertAlmostEqual(display["remaining_trade_volume_ratio"], 0.75)
        self.assertNotIn("effective_blockage_fraction", display)
        migrated = snapshot["chokepoints_live"]["suez"]["metrics"]["all"]
        self.assertNotIn("observed_shortfall_fraction", migrated)
        self.assertEqual(migrated["unit"], "estimated_trade_tonnes_per_day")

    def test_observed_trade_volume_shortfall_from_recent_drop(self) -> None:
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
        metric = result["metrics"]["all"]
        self.assertAlmostEqual(metric["observed_trade_volume_shortfall_fraction"], 0.5)
        self.assertAlmostEqual(metric["remaining_trade_volume_ratio"], 0.5)
        self.assertEqual(metric["unit"], "estimated_trade_tonnes_per_day")
        self.assertNotIn("current_7d_mean_dwt", metric)
        self.assertNotIn("effective_blockage_fraction", metric)
        self.assertEqual(result["current_window_days"], 7)
        self.assertEqual(result["baseline_window_days"], 28)

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
        self.assertEqual(
            result["quality"],
            "observed_estimated_trade_volume_shortfall_7d_vs_prior_28d",
        )

    def test_cached_legacy_dwt_names_are_removed(self) -> None:
        legacy = {
            "metrics": {
                "tanker": {
                    "current_7d_mean_dwt": 20,
                    "prior_28d_mean_dwt": 100,
                    "capacity_ratio": 0.2,
                    "observed_shortfall_fraction": 0.8,
                    "effective_blockage_fraction": 0.8,
                    "residual_throughput_rate": 0.2,
                }
            }
        }
        migrated = normalize_status_contract(legacy)
        metric = migrated["metrics"]["tanker"]
        self.assertEqual(metric["current_7d_mean_estimated_trade_tonnes"], 20)
        self.assertEqual(metric["prior_28d_mean_estimated_trade_tonnes"], 100)
        self.assertEqual(metric["observed_trade_volume_shortfall_fraction"], 0.8)
        self.assertEqual(metric["remaining_trade_volume_ratio"], 0.2)
        self.assertFalse(any(key.endswith("_dwt") for key in metric))
        self.assertNotIn("effective_blockage_fraction", metric)

    def test_non_fetch_build_preserves_and_migrates_cached_live_status(self) -> None:
        previous = {
            "hormuz": {
                "latest_date": "2026-08-01",
                "metrics": {
                    "tanker": {
                        "current_7d_mean_dwt": 20,
                        "prior_28d_mean_dwt": 100,
                        "capacity_ratio": 0.2,
                        "observed_shortfall_fraction": 0.8,
                        "residual_throughput_rate": 0.2,
                    }
                },
            }
        }
        snapshot = build_snapshot(ROOT / "config", fallback_live_status=previous)
        display = next(row for row in snapshot["live_display"] if row["chokepoint_id"] == "hormuz")
        self.assertEqual(display["trade_volume_shortfall_fraction"], 0.8)
        self.assertEqual(display["remaining_trade_volume_ratio"], 0.2)
        self.assertEqual(snapshot["live_fetch_errors"], [])

    @patch("build_snapshot.PortWatchClient.fetch_status")
    def test_live_observation_and_28d_persistence_are_separate(self, fetch_status) -> None:
        metric = {
            "unit": "estimated_trade_tonnes_per_day",
            "current_7d_mean_estimated_trade_tonnes": 20,
            "prior_28d_mean_estimated_trade_tonnes": 100,
            "estimated_trade_volume_ratio": 0.2,
            "observed_trade_volume_shortfall_fraction": 0.8,
            "remaining_trade_volume_ratio": 0.2,
            "change_pct": -80,
        }
        fetch_status.return_value = {
            "latest_date": "2026-08-01",
            "current_window_days": 7,
            "baseline_window_days": 28,
            "metrics": {ship_type: dict(metric) for ship_type in ["all", "container", "dry_bulk", "tanker"]},
        }
        snapshot = build_snapshot(ROOT / "config", fetch_portwatch=True)
        route = next(row for row in snapshot["routes"] if row["id"] == "asia_north_europe_container")
        observed = next(row for row in route["live_observed"] if row["chokepoint_id"] == "suez")
        persistence = next(
            row for row in route["live_persistence_28d"] if row["chokepoint_id"] == "suez"
        )
        self.assertEqual(observed["duration_days"], 7)
        self.assertEqual(observed["horizon_days"], 7)
        self.assertNotIn("effective_blockage_fraction", observed)
        self.assertEqual(observed["applied_route_flow_disruption_fraction"], 0.8)
        self.assertEqual(persistence["duration_days"], 28)
        self.assertEqual(persistence["horizon_days"], 28)
        self.assertEqual(persistence["source_observed_window_days"], 7)
        self.assertEqual(persistence["signal_type"], "hypothetical_28d_persistence_scenario")


class ScenarioGridTests(unittest.TestCase):
    def test_split_artifacts_preserve_screen_model_values(self) -> None:
        snapshot = build_snapshot(ROOT / "config")
        bundle = build_artifact_bundle(snapshot)
        self.assertEqual(bundle["screen"]["coverage_summary"]["modeled_route_count"], 21)
        self.assertEqual(
            bundle["screen"]["coverage_summary"]["public_flow_route_count"], 21
        )
        self.assertEqual(
            bundle["screen"]["bundle_id"], bundle["diagnostics"]["bundle_id"]
        )
        self.assertFalse(
            golden_contract_failures(bundle["screen"], bundle["diagnostics"])
        )
        self.assertNotIn("historical_event_calibration", bundle["screen"])
        self.assertIn("historical_event_calibration", bundle["backtests"])

    def test_temporary_grid_preserves_accounting_and_monotonicity(self) -> None:
        routes = json.loads((ROOT / "config" / "routes.json").read_text(encoding="utf-8"))
        fleet = json.loads((ROOT / "config" / "fleet_2025.json").read_text(encoding="utf-8"))
        fleet_by_type = {row["ship_type"]: row["dwt"] for row in fleet["fleet_by_type"]}
        result = run_temporary_scenario_grid(routes, fleet_by_type)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["case_count"], result["exposure_count"] * 5 * 4 * 3)
        self.assertEqual(result["accounting_failure_count"], 0)
        self.assertEqual(result["monotonic_failure_count"], 0)
        self.assertEqual(set(result["representative_cases"]), {"container", "dry_bulk", "tanker"})

    def test_temporary_environment_grid_preserves_physical_dwt(self) -> None:
        routes = json.loads((ROOT / "config" / "routes.json").read_text(encoding="utf-8"))
        fleet = json.loads((ROOT / "config" / "fleet_2025.json").read_text(encoding="utf-8"))
        fleet_by_type = {row["ship_type"]: row["dwt"] for row in fleet["fleet_by_type"]}
        result = run_temporary_environment_grid(routes, fleet_by_type)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["case_count"], len(routes) * 3 * 3 * 3)
        self.assertEqual(result["accounting_failure_count"], 0)
        self.assertEqual(result["monotonic_failure_count"], 0)
        self.assertEqual(set(result["representative_cases"]), {"container", "dry_bulk", "tanker"})


class ContainerContextTests(unittest.TestCase):
    def test_world_bank_teu_is_context_not_route_volume(self) -> None:
        payload = [
            {"lastupdated": "2026-07-13"},
            [
                {"countryiso3code": "CHN", "date": "2024", "value": 100},
                {"countryiso3code": "KOR", "date": "2024", "value": 50},
                {"countryiso3code": "CHN", "date": "2023", "value": 90},
            ],
        ]
        config = {
            "country_groups": [
                {
                    "id": "east_asia",
                    "name_ko": "동아시아",
                    "countries": ["CHN", "KOR"],
                    "minimum_coverage_ratio": 1.0,
                }
            ]
        }
        result = summarize_world_bank_teu(payload, config)
        self.assertEqual(result["status"], "observed_free_api_context_not_route_volume")
        self.assertEqual(result["groups"][0]["year"], 2024)
        self.assertEqual(result["groups"][0]["container_port_traffic_teu"], 150)
        self.assertIn("never used", result["route_usage"])


class ComtradeRouteTests(unittest.TestCase):
    def test_water_mode_is_selected_without_double_counting_total(self) -> None:
        common = {
            "reporterCode": 76,
            "partnerCode": 156,
            "flowCode": "X",
            "cmdCode": "1201",
            "period": "2024",
            "partner2Code": 0,
            "customsCode": "C00",
            "mosCode": "0",
            "isNetWgtEstimated": False,
        }
        result = select_net_weight_rows(
            [
                {**common, "motCode": 0, "netWgt": 200_000},
                {**common, "motCode": 2100, "netWgt": 150_000},
                {**common, "motCode": 1000, "netWgt": 50_000},
            ]
        )
        self.assertEqual(result["net_weight_tonnes"], 150)
        self.assertEqual(result["selected_row_count"], 1)
        self.assertEqual(result["transport_scope"], "sea_water_reported")

    def test_all_mode_is_used_only_when_water_mode_is_missing(self) -> None:
        result = select_net_weight_rows(
            [
                {
                    "reporterCode": 1,
                    "partnerCode": 2,
                    "flowCode": "X",
                    "cmdCode": "84",
                    "period": "2024",
                    "motCode": 0,
                    "netWgt": 90_000,
                    "isNetWgtEstimated": True,
                }
            ]
        )
        self.assertEqual(result["net_weight_tonnes"], 90)
        self.assertEqual(result["transport_scope"], "all_mode_proxy")
        self.assertEqual(result["estimated_net_weight_share"], 1)

    def test_route_flow_overlay_replaces_both_container_directions(self) -> None:
        routes = json.loads((ROOT / "config" / "routes.json").read_text(encoding="utf-8"))
        route_data = {
            "status": "fetched",
            "period": "2024",
            "routes": [
                {
                    "route_id": "asia_north_europe_container",
                    "annual_cargo_tonnes": 100,
                    "directions": [
                        {
                            "direction_id": "east_asia_to_north_europe",
                            "annual_cargo_tonnes": 100,
                            "input_status": "observed_bilateral_sea_weight",
                            "uncertainty_fraction": 0.12,
                        },
                        {
                            "direction_id": "north_europe_to_east_asia",
                            "annual_cargo_tonnes": 60,
                            "input_status": "observed_bilateral_sea_weight",
                            "uncertainty_fraction": 0.12,
                        },
                    ],
                }
            ],
        }
        updated = apply_route_flows(routes, route_data)
        route = next(row for row in updated if row["id"] == "asia_north_europe_container")
        self.assertEqual([row["annual_cargo_tonnes"] for row in route["directions"]], [100, 60])
        self.assertEqual(route["input_status"], "observed_bilateral_sea_weight")


class HistoricalCalibrationTests(unittest.TestCase):
    def test_event_shortfall_is_calibrated_but_behavior_partition_is_not_inferred(self) -> None:
        event_start = date(2025, 5, 1)
        event_end = event_start + timedelta(days=27)
        rows = []
        for offset in range(-400, 91):
            when = event_start + timedelta(days=offset)
            capacity = 20.0 if event_start <= when <= event_end else 100.0
            rows.append(
                {
                    "date": when.isoformat(),
                    "portid": "test",
                    "n_total": capacity / 10,
                    "capacity": capacity,
                    "capacity_container": capacity,
                    "capacity_dry_bulk": capacity,
                    "capacity_general_cargo": capacity,
                    "capacity_tanker": capacity,
                }
            )
        event = {
            "event_id": "synthetic_event",
            "event_type": "operational_restriction",
            "chokepoint_id": "test",
            "portwatch_id": "test",
            "start_date": event_start.isoformat(),
            "end_date": event_end.isoformat(),
            "window_end_is_resolution": True,
            "primary_metric": "all",
            "metrics": ["all"],
        }
        result = calibrate_event(
            rows,
            event,
            bootstrap_iterations=200,
        )
        primary = result["primary_result"]
        self.assertAlmostEqual(primary["observed_mean_shortfall_fraction"], 0.8)
        self.assertEqual(primary["evidence_grade"], "strong_event_signal")
        self.assertLessEqual(primary["placebo_test"]["one_sided_empirical_p_value"], 0.05)
        self.assertIsNotNone(primary["recovery_days_after_window_end"])
        self.assertEqual(
            result["behavior_partition_status"],
            "not_identified_by_single_chokepoint_throughput",
        )


if __name__ == "__main__":
    unittest.main()
