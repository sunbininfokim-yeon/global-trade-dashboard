"""Split the internal shipping model into screen, diagnostics and backtest artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import Any


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
        )
    } | {
        "baseline": {
            field: route.get("baseline", {}).get(field) for field in baseline_fields
        }
    }


def _screen_grid(grid: dict[str, Any]) -> dict[str, Any]:
    summary_fields = (
        "operational_capacity_absorbed_dwt",
        "commercial_capacity_gap_dwt",
        "backlog_cargo_tonnes_horizon",
        "rerouted_in_transit_cargo_tonnes_horizon",
        "trapped_loaded_dwt",
        "insurance_excluded_dwt",
        "lost_cargo_tonnes_horizon",
        "weighted_traffic_change_pct",
    )
    route_fields = (
        "route_id",
        "baseline_required_dwt",
        "continuity_required_dwt",
        "operational_capacity_absorbed_dwt",
        "traffic_change_pct",
    )
    return {
        key: grid[key]
        for key in (
            "status",
            "closure_pct_options",
            "duration_day_options",
            "fixed_horizon_days",
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
        "cii_reduction_vs_2019_pct",
        "representative_route_count",
        "physical_allocated_dwt",
        "effective_service_capacity_dwt",
        "effective_dwt_loss",
        "effective_capacity_retention_rate",
        "effective_capacity_retention_rate_range",
        "same_service_required_dwt",
        "same_service_required_dwt_range",
        "scope",
    )
    return {
        "status": environment.get("status"),
        "methodology_ko": environment.get("methodology_ko"),
        "warnings_ko": environment.get("warnings_ko", []),
        "sources": environment.get("sources", []),
        "identification_boundary": environment.get("identification_boundary", {}),
        "scenarios": [
            {field: row.get(field) for field in aggregate_fields}
            for row in environment.get("scenarios", [])
        ],
    }


def build_artifact_bundle(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return three artifacts sharing a deterministic contract bundle id."""

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
                "data_policy",
                "sources",
                "fleet",
                "lng_fleet",
                "chokepoints",
                "chokepoints_live",
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
        "routes": [_screen_route(route) for route in routes],
        "ui_scenario_grid": _screen_grid(snapshot["ui_scenario_grid"]),
        "environment": _screen_environment(snapshot.get("environment", {})),
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
                "ui_scenario_grid",
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
    return {"screen": screen, "diagnostics": diagnostics, "backtests": backtests}


def golden_contract_failures(
    screen: dict[str, Any], diagnostics: dict[str, Any]
) -> list[str]:
    """Compare every UI-visible route and simulator value with model diagnostics."""

    failures: list[str] = []
    if screen.get("bundle_id") != diagnostics.get("bundle_id"):
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
    return failures
