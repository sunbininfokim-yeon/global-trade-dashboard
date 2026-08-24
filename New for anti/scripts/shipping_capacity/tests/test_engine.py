from __future__ import annotations

import json
import math
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from build_snapshot import build_snapshot
from shipping_capacity.artifacts import build_artifact_bundle, golden_contract_failures
from shipping_capacity.behavior_sensitivity import (
    apply_behavior_path,
    behavior_paths_for_scenario,
)
from shipping_capacity.comtrade_routes import (
    apply_route_flows,
    merge_route_history,
    select_net_weight_rows,
    summarize_route_history,
)
from shipping_capacity.container import summarize_world_bank_teu
from shipping_capacity.engine import InputError, estimate_interval, required_capacity_dwt, simulate_route
from shipping_capacity.environment import (
    expand_environment_scenarios,
    simulate_environment_route,
    simulate_environment_route_range,
)
from shipping_capacity.historical_calibration import calibrate_event
from shipping_capacity.ml_validation import analyze_capacity_series
from shipping_capacity.portwatch import (
    normalize_status_contract,
    summarize_port_context,
    summarize_series,
    validate_7d_28d_signal,
)
from shipping_capacity.lng_fleet import build_lng_fleet_context
from shipping_capacity.market_signals import build_market_signal_registry
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

    def test_behavior_path_changes_joint_assumptions_but_not_throughput(self) -> None:
        scenario = next(
            row for row in self.scenarios if row["id"] == "hormuz_effective_80pct_28d"
        )
        path = {
            "id": "withdrawal",
            "response_multiplier_factors": {
                "reroute_multiplier": 0.75,
                "wait_multiplier": 0.85,
                "cancel_multiplier": 1.6,
            },
            "insurance_unavailable_share_factor": 1.25,
            "onboard_waiting_share_factor": 1.15,
            "waiting_days_factor": 1.25,
            "trapped_days_factor": 1.25,
        }
        variant = apply_behavior_path(scenario, path)
        self.assertEqual(variant["closure_fraction"], scenario["closure_fraction"])
        self.assertEqual(
            variant["residual_throughput_rate"], scenario["residual_throughput_rate"]
        )
        self.assertEqual(variant["insurance_unavailable_share"], 1.0)
        self.assertGreater(variant["waiting_days"], scenario["waiting_days"])

    def test_behavior_config_uses_named_paths_without_probabilities(self) -> None:
        config = json.loads(
            (ROOT / "config" / "behavior_uncertainty_profiles.json").read_text(
                encoding="utf-8"
            )
        )
        scenario = next(
            row for row in self.scenarios if row["id"] == "hormuz_effective_80pct_28d"
        )
        variants = behavior_paths_for_scenario(scenario, config)
        self.assertEqual(len(variants), 3)
        self.assertEqual(
            {row["behavior_sensitivity_path_id"] for row in variants},
            {"insured_continuity", "central", "market_withdrawal"},
        )
        self.assertNotIn("probability", config)

    def test_comtrade_history_keeps_annual_inputs_separate(self) -> None:
        history = summarize_route_history(
            {
                "2019": {"routes": [{"route_id": "route_a", "annual_cargo_tonnes": 100.0}]},
                "2024": {"routes": [{"route_id": "route_a", "annual_cargo_tonnes": 125.0}]},
            }
        )
        route = history["routes"][0]
        self.assertEqual(route["available_period_count"], 2)
        self.assertAlmostEqual(route["first_to_last_change_fraction"], 0.25)

    def test_comtrade_history_refresh_is_resumable_by_year(self) -> None:
        previous = {
            "years": {"2019": {"routes": [{"route_id": "route_a", "annual_cargo_tonnes": 100.0}]}},
            "periods": ["2019"],
        }
        current = {
            "years": {"2020": {"routes": [{"route_id": "route_a", "annual_cargo_tonnes": 110.0}]}},
            "periods": ["2020"],
        }
        merged = merge_route_history(previous, current)
        self.assertEqual(merged["periods"], ["2019", "2020"])
        self.assertEqual(merged["route_history_summary"]["routes"][0]["available_period_count"], 2)

    def test_port_context_does_not_turn_port_calls_into_waiting_vessels(self) -> None:
        rows = []
        for index in range(35):
            rows.append(
                {
                    "date": 1_700_000_000_000 + index * 86_400_000,
                    "portcalls": 100,
                    "portcalls_container": 10,
                    "portcalls_dry_bulk": 20,
                    "portcalls_tanker": 30,
                    "import": 1_000,
                    "export": 2_000,
                    "import_container": 100,
                    "export_container": 200,
                    "import_dry_bulk": 300,
                    "export_dry_bulk": 400,
                    "import_tanker": 500,
                    "export_tanker": 600,
                }
            )
        status = summarize_port_context(rows, {"id": "test", "iso3_codes": ["OMN"]})
        self.assertEqual(
            status["waiting_anchorage_status"],
            "not_published_in_public_portwatch_daily_ports_layer",
        )
        self.assertNotIn("waiting_vessel_count", status["metrics"]["tanker"])
        self.assertEqual(status["use_in_model"], "diagnostic_context_only_not_behavior_calibration")

    def test_lng_combined_fleet_is_rejected_as_lng_only_denominator(self) -> None:
        context = build_lng_fleet_context(
            {
                "as_of": "2025-01-01",
                "liquefied_gas_carriers_dwt": 100_462_000,
                "lng_only_dwt": None,
                "source": {"url": "https://example.test"},
                "warning_ko": "combined",
            }
        )
        self.assertEqual(context["model_use"], "context_only_not_eligible_lng_only_denominator")

    def test_market_registry_never_uses_commercial_values(self) -> None:
        registry = build_market_signal_registry(
            {
                "identification_boundary": "test",
                "warning_ko": "test",
                "sources": [
                    {
                        "id": "licensed",
                        "signal_class": "charter_rate",
                        "source_name": "source",
                        "source_url": "https://example.test",
                        "access": "commercial_or_license_required",
                    }
                ],
            }
        )
        self.assertEqual(registry["signals"][0]["status"], "not_automated_without_permitted_public_series")
        self.assertEqual(registry["signals"][0]["model_use"], "not_used")

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

    def test_environment_pathways_expand_to_complete_annual_grid(self) -> None:
        config = json.loads(
            (ROOT / "config" / "environment_scenarios.json").read_text(
                encoding="utf-8"
            )
        )
        scenarios = expand_environment_scenarios(config)
        self.assertEqual(len(scenarios), 15)
        self.assertEqual(
            {row["pathway_id"] for row in scenarios},
            {"imo_adopted", "accelerated", "deferred"},
        )
        for pathway_id in {row["pathway_id"] for row in scenarios}:
            years = sorted(
                row["year"] for row in scenarios if row["pathway_id"] == pathway_id
            )
            self.assertEqual(years, [2026, 2027, 2028, 2029, 2030])
        accelerated_2030 = next(
            row for row in scenarios if row["id"] == "accelerated_2030"
        )
        self.assertEqual(
            accelerated_2030["regulatory_facts"]["cii_reduction_vs_2019_pct"],
            22.2,
        )
        self.assertEqual(
            accelerated_2030["pathway_policy_status"],
            "counterfactual_not_adopted",
        )


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
        self.assertEqual(
            len(snapshot["live_fetch_errors"]),
            len(snapshot["chokepoints"]),
        )
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
        hormuz = next(
            row
            for row in bundle["screen"]["scenario_summary"]
            if row["id"] == "hormuz_effective_80pct_28d"
        )
        sensitivity = hormuz["behavior_sensitivity"]
        self.assertEqual(sensitivity["path_count"], 3)
        self.assertEqual(
            sensitivity["status"],
            "deterministic_joint_paths_not_probability_interval",
        )
        for interval in sensitivity["ranges"].values():
            self.assertLessEqual(interval["minimum"], interval["maximum"])
        self.assertTrue(
            all(
                abs(path["cargo_accounting_residual_tonnes"]) < 1e-6
                for path in sensitivity["paths"]
            )
        )
        self.assertNotIn("historical_event_calibration", bundle["screen"])
        self.assertIn("historical_event_calibration", bundle["backtests"])

    def test_environment_ui_contract_is_complete_and_monotonic(self) -> None:
        snapshot = build_snapshot(ROOT / "config")
        bundle = build_artifact_bundle(snapshot)
        environment = bundle["screen"]["environment"]
        self.assertEqual(environment["contract_version"], "environment-pathways-v1")
        self.assertEqual(len(environment["pathways"]), 3)
        self.assertEqual(len(environment["scenarios"]), 15)
        scenarios = {
            (row["pathway_id"], row["year"]): row
            for row in environment["scenarios"]
        }
        for year in range(2026, 2031):
            adopted = scenarios[("imo_adopted", year)]
            accelerated = scenarios[("accelerated", year)]
            deferred = scenarios[("deferred", year)]
            self.assertEqual(
                accelerated["physical_allocated_dwt"],
                adopted["physical_allocated_dwt"],
            )
            self.assertEqual(
                adopted["physical_allocated_dwt"],
                deferred["physical_allocated_dwt"],
            )
            self.assertLessEqual(
                accelerated["effective_service_capacity_dwt"],
                adopted["effective_service_capacity_dwt"],
            )
            self.assertLessEqual(
                adopted["effective_service_capacity_dwt"],
                deferred["effective_service_capacity_dwt"],
            )
            self.assertEqual(
                {row["ship_type"] for row in adopted["ship_type_breakdown"]},
                {"container", "dry_bulk", "tanker"},
            )
            for scenario in (accelerated, adopted, deferred):
                self.assertAlmostEqual(
                    sum(
                        row["physical_allocated_dwt"]
                        for row in scenario["ship_type_breakdown"]
                    ),
                    scenario["physical_allocated_dwt"],
                    delta=0.01,
                )
                self.assertAlmostEqual(
                    sum(
                        row["effective_service_capacity_dwt"]
                        for row in scenario["ship_type_breakdown"]
                    ),
                    scenario["effective_service_capacity_dwt"],
                    delta=0.01,
                )
        self.assertFalse(
            golden_contract_failures(bundle["screen"], bundle["diagnostics"])
        )

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
