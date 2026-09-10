"""Split the internal shipping model into screen, diagnostics and backtest artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import Any


SCREEN_HISTORY_POINT_LIMIT = 180


def _bundle_id(snapshot: dict[str, Any]) -> str:
    identity = {
        "generated_at": snapshot["generated_at"],
        "model_version": snapshot.get("model", {}).get("version"),
        "route_ids": [row["id"] for row in snapshot.get("routes", [])],
        "scenario_ids": [row["id"] for row in snapshot.get("scenarios", [])],
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:20]


def _screen_route(route: dict[str, Any]) -> dict[str, Any]:
    baseline_fields = (
        "baseline_required_dwt",
        "allocated_dwt_with_reserve",
        "route_share_of_type_fleet_pct",
        "baseline_cycle_days",
        "capacity_driver_direction_id",
        "interval",
    )
    return {
        key: route.get(key)
        for key in (
            "id",
            "name_ko",
            "name_en",
            "ship_type",
            "cargo_segment",
            "origin",
            "destination",
            "service_type",
            "vessel_class",
            "vessel_class_ko",
            "reference_size",
            "benchmark_family",
            "directions",
            "input_status",
            "annual_cargo_tonnes",
            "model_inputs",
            "operational_profile",
        )
    } | {
        "baseline": {
            field: route.get("baseline", {}).get(field) for field in baseline_fields
        }
    }


def _screen_chokepoints_live(
    live_status: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Keep the public screen artifact compact while diagnostics retain 730 days."""

    screen_status: dict[str, dict[str, Any]] = {}
    for chokepoint_id, status in live_status.items():
        full_history = status.get("history", [])
        history = (
            full_history[-SCREEN_HISTORY_POINT_LIMIT:]
            if isinstance(full_history, list)
            else []
        )
        screen_metric_histories = {}
        for metric_key, metric_status in status.get("metric_histories", {}).items():
            if not isinstance(metric_status, dict):
                continue
            full_metric_history = metric_status.get("history", [])
            metric_history = (
                full_metric_history[-SCREEN_HISTORY_POINT_LIMIT:]
                if isinstance(full_metric_history, list)
                else []
            )
            screen_metric_histories[metric_key] = {
                **metric_status,
                "history": metric_history,
                "history_point_count": len(metric_history),
                "history_source_point_count": (
                    len(full_metric_history)
                    if isinstance(full_metric_history, list)
                    else 0
                ),
                "history_screen_point_limit": SCREEN_HISTORY_POINT_LIMIT,
            }
        screen_status[chokepoint_id] = {
            **status,
            "history": history,
            "history_point_count": len(history),
            "history_source_point_count": (
                len(full_history) if isinstance(full_history, list) else 0
            ),
            "history_screen_point_limit": SCREEN_HISTORY_POINT_LIMIT,
            "metric_histories": screen_metric_histories,
        }
    return screen_status


def _screen_grid(grid: dict[str, Any]) -> dict[str, Any]:
    summary_fields = (
        "affected_route_count",
        "affected_baseline_dwt",
        "operational_capacity_absorbed_dwt",
        "affected_allocated_dwt_with_reserve",
        "relevant_global_type_fleet_dwt",
        "operational_capacity_absorbed_pct_of_affected_allocated",
        "operational_capacity_absorbed_pct_of_relevant_global_type_fleet",
        "commercial_capacity_gap_dwt",
        "commercially_unavailable_dwt",
        "commercially_unavailable_pct_of_affected_allocated",
        "commercially_available_dwt",
        "commercially_available_pct_of_affected_allocated",
        "backlog_cargo_tonnes_horizon",
        "rerouted_in_transit_cargo_tonnes_horizon",
        "trapped_loaded_dwt",
        "insurance_excluded_dwt",
        "lost_cargo_tonnes_horizon",
        "weighted_traffic_change_pct",
        "ship_type_breakdown",
        "cargo_segment_breakdown",
        # This is already computed by the Python engine for every grid row.
        # Keep it in the screen artifact so the simulator never has to fall
        # back to a base scenario or reconstruct reroute arithmetic in JS.
        "reroute_receivers",
        "capacity_denominator_warning",
    )
    route_fields = (
        "route_id",
        "ship_type",
        "cargo_segment",
        "baseline_required_dwt",
        "allocated_dwt_with_reserve",
        "continuity_required_dwt",
        "operational_capacity_absorbed_dwt",
        "operational_capacity_absorbed_pct_of_route_allocated",
        "commercially_unavailable_dwt",
        "commercially_unavailable_pct_of_route_allocated",
        "traffic_change_pct",
    )
    return {
        key: grid[key]
        for key in (
            "status",
            "closure_pct_options",
            "duration_day_options",
            "fixed_horizon_days",
            "input_policy",
        )
    } | {
        "rows": [
            {
                "key": row["key"],
                "base_scenario_id": row["base_scenario_id"],
                "closure_pct": row["closure_pct"],
                "duration_days": row["duration_days"],
                "horizon_days": row["horizon_days"],
                "summary": {
                    field: row["summary"].get(field) for field in summary_fields
                },
                "routes": [
                    {field: route.get(field) for field in route_fields}
                    for route in row.get("routes", [])
                ],
            }
            for row in grid.get("rows", [])
        ]
    }


def _screen_environment(environment: dict[str, Any]) -> dict[str, Any]:
    aggregate_fields = (
        "id",
        "name_ko",
        "year",
        "status",
        "pathway_id",
        "pathway_name_ko",
        "pathway_policy_status",
        "pathway_description_ko",
        "behavior_assumption_status",
        "regulatory_inputs",
        "cii_reduction_vs_2019_pct",
        "representative_route_count",
        "physical_allocated_dwt",
        "effective_service_capacity_dwt",
        "effective_dwt_loss",
        "effective_capacity_retention_rate",
        "effective_capacity_retention_rate_range",
        "baseline_required_dwt",
        "same_service_required_dwt",
        "same_service_required_dwt_range",
        "additional_required_vs_baseline_dwt",
        "capacity_gap_vs_allocated_dwt",
        "ship_type_breakdown",
        "scope",
    )
    return {
        "contract_version": environment.get("contract_version"),
        "status": environment.get("status"),
        "methodology_ko": environment.get("methodology_ko"),
        "warnings_ko": environment.get("warnings_ko", []),
        "sources": environment.get("sources", []),
        "identification_boundary": environment.get("identification_boundary", {}),
        "pathways": environment.get("pathways", []),
        "scenarios": [
            {field: row.get(field) for field in aggregate_fields}
            for row in environment.get("scenarios", [])
        ],
    }


def build_artifact_bundle(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return four artifacts sharing a deterministic contract bundle id.

    The scenario grid is split out of the screen artifact: it is ~90% of the
    screen payload by size but only needed once a user opens a simulator, so
    the fleet/routes/chokepoint list screens should not have to download it.
    """

    bundle_id = _bundle_id(snapshot)
    routes = snapshot.get("routes", [])
    public_count = sum(
        not str(route.get("input_status", "")).startswith("scenario_seed")
        for route in routes
    )
    screen = {
        "schema_version": "shipping-capacity-v1",
        "artifact_type": "screen_snapshot",
        "bundle_id": bundle_id,
        "generated_at": snapshot["generated_at"],
        "artifact_manifest": {
            "screen": "shipping_capacity_v1.json",
            "scenario_grid": "shipping_capacity_scenario_grid_v1.json",
            "diagnostics": "shipping_capacity_diagnostics_v1.json",
            "backtests": "shipping_capacity_backtests_v1.json",
        },
        "coverage_summary": {
            "modeled_route_count": len(routes),
            "public_flow_route_count": public_count,
            "bidirectional_service_count": sum(
                bool(route.get("directions")) for route in routes
            ),
            "cargo_segments": sorted(
                {
                    route.get("cargo_segment", route.get("ship_type", "unknown"))
                    for route in routes
                }
            ),
        },
        **{
            key: snapshot[key]
            for key in (
                "model",
                "ui_delivery_contract",
                "data_policy",
                "sources",
                "fleet",
                "lng_fleet",
                "chokepoints",
                "live_display",
                "live_fetch_errors",
                "live_data_quality",
                "route_catalog",
                "scenarios",
                "scenario_summary",
                "comtrade_routes",
                "portwatch_port_context",
                "market_signals",
                "pdf_reports",
            )
        },
        "chokepoints_live": _screen_chokepoints_live(
            snapshot.get("chokepoints_live", {})
        ),
        "routes": [_screen_route(route) for route in routes],
        "environment": _screen_environment(snapshot.get("environment", {})),
    }
    scenario_grid = {
        "schema_version": "shipping-capacity-scenario-grid-v1",
        "artifact_type": "scenario_grid",
        "bundle_id": bundle_id,
        "generated_at": snapshot["generated_at"],
        "ui_scenario_grid": _screen_grid(snapshot["ui_scenario_grid"]),
    }
    diagnostics = {
        "schema_version": "shipping-capacity-diagnostics-v1",
        "artifact_type": "model_diagnostics",
        "bundle_id": bundle_id,
        "generated_at": snapshot["generated_at"],
        **{
            key: value
            for key, value in snapshot.items()
            if key
            not in {
                "schema_version",
                "generated_at",
                "event_observations",
                "historical_event_calibration",
            }
        },
    }
    backtests = {
        "schema_version": "shipping-capacity-backtests-v1",
        "artifact_type": "historical_backtests",
        "bundle_id": bundle_id,
        "generated_at": snapshot["generated_at"],
        "event_observations": snapshot.get("event_observations", []),
        "scenario_signal_comparison": snapshot.get(
            "scenario_signal_comparison", []
        ),
        "historical_event_calibration": snapshot.get(
            "historical_event_calibration", {}
        ),
    }
    return {
        "screen": screen,
        "scenario_grid": scenario_grid,
        "diagnostics": diagnostics,
        "backtests": backtests,
    }


def golden_contract_failures(
    screen: dict[str, Any],
    diagnostics: dict[str, Any],
    scenario_grid: dict[str, Any],
) -> list[str]:
    """Compare every UI-visible route and simulator value with model diagnostics."""

    failures: list[str] = []
    bundle_id_values = {screen.get("bundle_id"), diagnostics.get("bundle_id"), scenario_grid.get("bundle_id")}
    if None in bundle_id_values or len(bundle_id_values) != 1:
        failures.append("bundle_id_mismatch")
    diagnostic_routes = {row["id"]: row for row in diagnostics.get("routes", [])}
    for route in screen.get("routes", []):
        source = diagnostic_routes.get(route["id"])
        if source is None:
            failures.append(f"missing_diagnostic_route:{route['id']}")
            continue
        for field, value in route.get("baseline", {}).items():
            if value != source.get("baseline", {}).get(field):
                failures.append(f"route_baseline_mismatch:{route['id']}:{field}")
    diagnostic_environment = {
        row["id"]: row
        for row in diagnostics.get("environment", {}).get("scenarios", [])
    }
    for scenario in screen.get("environment", {}).get("scenarios", []):
        source = diagnostic_environment.get(scenario["id"])
        if source is None:
            failures.append(f"missing_diagnostic_environment:{scenario['id']}")
            continue
        for field, value in scenario.items():
            if value != source.get(field):
                failures.append(
                    f"environment_scenario_mismatch:{scenario['id']}:{field}"
                )
    diagnostic_grid = {
        row["key"]: row for row in diagnostics.get("ui_scenario_grid", {}).get("rows", [])
    }
    for row in scenario_grid.get("ui_scenario_grid", {}).get("rows", []):
        source = diagnostic_grid.get(row["key"])
        if source is None:
            failures.append(f"missing_diagnostic_grid:{row['key']}")
            continue
        for field, value in row.get("summary", {}).items():
            if value != source.get("summary", {}).get(field):
                failures.append(f"grid_summary_mismatch:{row['key']}:{field}")
        diagnostic_grid_routes = {
            route["route_id"]: route for route in source.get("routes", [])
        }
        for route in row.get("routes", []):
            diagnostic_route = diagnostic_grid_routes.get(route["route_id"])
            if diagnostic_route is None:
                failures.append(
                    f"missing_diagnostic_grid_route:{row['key']}:{route['route_id']}"
                )
                continue
            for field, value in route.items():
                if value != diagnostic_route.get(field):
                    failures.append(
                        f"grid_route_mismatch:{row['key']}:{route['route_id']}:{field}"
                    )
    return failures
