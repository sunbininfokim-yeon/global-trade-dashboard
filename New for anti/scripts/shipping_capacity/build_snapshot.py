#!/usr/bin/env python3
"""Build the frontend-ready shipping_capacity_v1.json snapshot."""

from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shipping_capacity.engine import estimate_interval, simulate_route
from shipping_capacity.artifacts import build_artifact_bundle
from shipping_capacity.behavior_sensitivity import behavior_paths_for_scenario
from shipping_capacity.comtrade_routes import apply_route_flows
from shipping_capacity.container import WorldBankContainerClient
from shipping_capacity.lng_fleet import load_lng_fleet_context
from shipping_capacity.market_signals import load_market_signal_registry
from shipping_capacity.environment import (
    aggregate_environment_scenario,
    simulate_environment_route_range,
)
from shipping_capacity.portwatch import (
    PortWatchClient,
    PortWatchPortClient,
    normalize_status_contract,
)


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def rounded(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, list):
        return [rounded(item) for item in value]
    if isinstance(value, dict):
        return {key: rounded(item) for key, item in value.items()}
    return value


def aggregate_scenario(scenario: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    affected = [row for row in results if row["affected_flow_share"] > 0]
    baseline = sum(row["baseline_required_dwt"] for row in affected)
    disrupted = sum(row["disrupted_required_dwt"] for row in affected)
    absorbed = sum(row["operational_capacity_absorbed_dwt"] for row in affected)
    gap = sum(row["capacity_gap_dwt"] for row in affected)
    trapped = sum(row["trapped_loaded_dwt"] for row in affected)
    trapped_vessel_values = [
        row["trapped_vessel_equivalent"]
        for row in affected
        if row.get("trapped_vessel_equivalent") is not None
    ]
    trapped_vessel_equivalent = sum(trapped_vessel_values) if trapped_vessel_values else None
    insurance_excluded = sum(row["insurance_excluded_dwt"] for row in affected)
    unavailable = sum(row["commercially_unavailable_dwt"] for row in affected)
    available = sum(row["commercially_available_dwt"] for row in affected)
    backlog = sum(row["backlog_cargo_tonnes_horizon"] for row in affected)
    rerouted_in_transit = sum(
        row["rerouted_in_transit_cargo_tonnes_horizon"] for row in affected
    )
    served_cargo = sum(row["served_cargo_tonnes_horizon"] for row in affected)
    lost = sum(row["lost_cargo_tonnes_horizon"] for row in affected)
    if affected:
        deliverable = sum(
            row["deliverable_flow_index"] * row["baseline_required_dwt"] for row in affected
        ) / baseline
    else:
        deliverable = 1.0
    return {
        "id": scenario["id"],
        "name_ko": scenario["name_ko"],
        "chokepoint_id": scenario["chokepoint_id"],
        "event_type": scenario.get("event_type", "operational_restriction"),
        "closure_fraction": scenario["closure_fraction"],
        "effective_blockage_fraction": scenario["closure_fraction"],
        "residual_throughput_rate": scenario.get(
            "residual_throughput_rate",
            1.0 - scenario["closure_fraction"],
        ),
        "duration_days": scenario["duration_days"],
        "affected_route_count": len(affected),
        "affected_baseline_dwt": baseline,
        "disrupted_required_dwt": disrupted,
        "operational_capacity_absorbed_dwt": absorbed,
        "capacity_gap_dwt": gap,
        "commercial_capacity_gap_dwt": gap,
        "trapped_loaded_dwt": trapped,
        "trapped_vessel_equivalent": trapped_vessel_equivalent,
        "trapped_vessel_equivalent_warning": "Reference-class DWT equivalent, not an observed AIS vessel count.",
        "insurance_excluded_dwt": insurance_excluded,
        "commercially_unavailable_dwt": unavailable,
        "commercially_available_dwt": available,
        "served_cargo_tonnes_horizon": served_cargo,
        "backlog_cargo_tonnes_horizon": backlog,
        "rerouted_in_transit_cargo_tonnes_horizon": rerouted_in_transit,
        "lost_cargo_tonnes_horizon": lost,
        "weighted_deliverable_flow_index": deliverable,
        "weighted_served_flow_index": deliverable,
        "weighted_traffic_change_pct": (deliverable - 1.0) * 100.0,
        "cargo_accounting_residual_tonnes": sum(
            row["cargo_accounting_residual_tonnes"] for row in affected
        ),
    }


BEHAVIOR_SENSITIVITY_METRICS = (
    "commercial_capacity_gap_dwt",
    "commercially_available_dwt",
    "insurance_excluded_dwt",
    "trapped_loaded_dwt",
    "backlog_cargo_tonnes_horizon",
    "lost_cargo_tonnes_horizon",
    "weighted_served_flow_index",
)


def build_behavior_sensitivity(
    routes: list[dict[str, Any]],
    scenario: dict[str, Any],
    fleet_by_type: dict[str, float],
    config: dict[str, Any],
) -> dict[str, Any] | None:
    """Run named joint response paths while holding event throughput fixed."""

    variants = behavior_paths_for_scenario(scenario, config)
    if not variants:
        return None
    path_results = []
    for variant in variants:
        route_results = [
            simulate_route(route, variant, fleet_by_type[route["ship_type"]])
            for route in routes
        ]
        summary = aggregate_scenario(variant, route_results)
        path_results.append(
            {
                "path_id": variant["behavior_sensitivity_path_id"],
                "name_ko": variant["behavior_sensitivity_path_name_ko"],
                "assumptions": {
                    "response_adjustment": variant.get("response_adjustment", {}),
                    "waiting_days": variant.get("waiting_days"),
                    "trapped_days": variant.get("trapped_days"),
                    "onboard_waiting_share": variant.get("onboard_waiting_share"),
                    "insurance_unavailable_share": variant.get(
                        "insurance_unavailable_share"
                    ),
                },
                "results": {
                    metric: summary[metric] for metric in BEHAVIOR_SENSITIVITY_METRICS
                },
                "cargo_accounting_residual_tonnes": summary[
                    "cargo_accounting_residual_tonnes"
                ],
            }
        )
    ranges = {}
    for metric in BEHAVIOR_SENSITIVITY_METRICS:
        values = [float(row["results"][metric]) for row in path_results]
        ranges[metric] = {"minimum": min(values), "maximum": max(values)}
    return {
        "status": "deterministic_joint_paths_not_probability_interval",
        "event_throughput_held_fixed": True,
        "path_count": len(path_results),
        "paths": path_results,
        "ranges": ranges,
        "warning_ko": "행동변수 동시변화에 대한 민감도 범위이며 발생확률·신뢰구간·예측구간이 아닙니다.",
    }


def build_ui_scenario_grid(
    routes: list[dict[str, Any]],
    scenarios: list[dict[str, Any]],
    fleet_by_type: dict[str, float],
) -> dict[str, Any]:
    """Precompute a bounded UI grid so the browser never reimplements the model."""

    rows = []
    route_fields = (
        "route_id",
        "ship_type",
        "baseline_required_dwt",
        "continuity_required_dwt",
        "operational_capacity_absorbed_dwt",
        "commercial_capacity_gap_dwt",
        "trapped_loaded_dwt",
        "insurance_excluded_dwt",
        "commercially_available_dwt",
        "served_flow_index",
        "traffic_change_pct",
        "served_cargo_tonnes_horizon",
        "backlog_cargo_tonnes_horizon",
        "rerouted_in_transit_cargo_tonnes_horizon",
        "lost_cargo_tonnes_horizon",
    )
    for base in scenarios:
        for closure_pct in (0, 25, 50, 75, 80, 100):
            for duration_days in (7, 14, 28):
                scenario = copy.deepcopy(base)
                scenario["id"] = (
                    f"ui_{base['id']}_{closure_pct}pct_{duration_days}d"
                )
                scenario["closure_fraction"] = closure_pct / 100.0
                scenario["residual_throughput_rate"] = 1.0 - scenario["closure_fraction"]
                scenario["duration_days"] = duration_days
                scenario["horizon_days"] = 28
                results = [
                    simulate_route(route, scenario, fleet_by_type[route["ship_type"]])
                    for route in routes
                ]
                affected = [row for row in results if row["affected_flow_share"] > 0]
                rows.append(
                    {
                        "key": f"{base['id']}|{closure_pct}|{duration_days}",
                        "base_scenario_id": base["id"],
                        "closure_pct": closure_pct,
                        "duration_days": duration_days,
                        "horizon_days": 28,
                        "waiting_days": scenario.get("waiting_days", 0),
                        "summary": aggregate_scenario(scenario, results),
                        "routes": [
                            {field: result.get(field) for field in route_fields}
                            for result in affected
                        ],
                    }
                )
    return {
        "status": "precomputed_python_engine",
        "closure_pct_options": [0, 25, 50, 75, 80, 100],
        "duration_day_options": [7, 14, 28],
        "fixed_horizon_days": 28,
        "rows": rows,
    }


def build_live_display(
    chokepoints: list[dict[str, Any]],
    live_status: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build a presentation-safe live signal contract for the frontend."""

    cards: list[dict[str, Any]] = []
    for chokepoint in chokepoints:
        status = live_status.get(chokepoint["id"])
        if not status:
            continue
        metric_key = chokepoint.get("primary_live_metric", "all")
        metric = status.get("metrics", {}).get(metric_key)
        if not metric:
            continue
        shortfall = metric.get("observed_trade_volume_shortfall_fraction", 0.0)
        remaining = metric.get("remaining_trade_volume_ratio", 1.0 - shortfall)
        cards.append(
            {
                "chokepoint_id": chokepoint["id"],
                "name_ko": chokepoint["name_ko"],
                "metric_key": metric_key,
                "headline_label_ko": "추정 교역량 감소율",
                "trade_volume_shortfall_fraction": shortfall,
                "trade_volume_shortfall_pct_rounded": round(shortfall * 100),
                "basis_label_ko": chokepoint.get(
                    "primary_live_basis_ko",
                    "최근 7일 전체 추정 교역량 기준",
                ),
                "comparison_label_ko": "직전 28일 평균 대비",
                "residual_label_ko": "잔존 추정 교역량",
                "remaining_trade_volume_ratio": remaining,
                "remaining_trade_volume_pct_rounded": round(remaining * 100),
                "latest_date": status.get("latest_date"),
                "stale_days": status.get("stale_days"),
                "is_stale": status.get("is_stale", True),
                "fallback_used": status.get("fallback_used", False),
                "source_status": status.get("source_status"),
                "metric_unit": metric.get("unit", "estimated_trade_tonnes_per_day"),
                "signal_type": "observed_estimated_trade_volume_shortfall",
                "warning_ko": (
                    "DWT와 추정 적재율로 산출한 교역량 신호이며 실제 통항 DWT, "
                    "물리적 봉쇄율 또는 보험 미확보율 관측치가 아님"
                ),
            }
        )
    return cards


def build_scenario_signal_comparison(
    scenarios: list[dict[str, Any]],
    chokepoints: list[dict[str, Any]],
    live_status: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compare magnitudes without claiming a scenario was empirically calibrated."""

    chokepoint_by_id = {row["id"]: row for row in chokepoints}
    comparisons = []
    for scenario in scenarios:
        chokepoint = chokepoint_by_id.get(scenario["chokepoint_id"], {})
        metric_key = chokepoint.get("primary_live_metric", "all")
        status = live_status.get(scenario["chokepoint_id"], {})
        metric = status.get("metrics", {}).get(metric_key)
        if not metric:
            continue
        observed = metric.get("observed_trade_volume_shortfall_fraction", 0.0)
        preset = float(scenario["closure_fraction"])
        comparisons.append(
            {
                "scenario_id": scenario["id"],
                "chokepoint_id": scenario["chokepoint_id"],
                "metric_key": metric_key,
                "observation_latest_date": status.get("latest_date"),
                "observed_trade_volume_shortfall_fraction": observed,
                "preset_scenario_blockage_fraction": preset,
                "absolute_gap_percentage_points": abs(observed - preset) * 100.0,
                "scope": "magnitude comparison only; observed trade volume and scenario blockage are different concepts",
                "comparison_status": "not_empirical_calibration",
                "not_validated_fields": [
                    "physical_closure_fraction",
                    "route_flow_disruption_fraction",
                    "insurance_unavailable_share",
                    "onboard_waiting_share",
                    "trapped_days",
                ],
            }
        )
    return comparisons


def build_historical_scenario_comparisons(
    scenarios: list[dict[str, Any]],
    calibration: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compare stress-preset severity with matching historical event windows."""

    comparisons = []
    for event in calibration.get("events", []):
        primary = event.get("primary_result") or {}
        if primary.get("status") != "calibrated_observed_throughput":
            continue
        mean_shortfall = primary["observed_mean_shortfall_fraction"]
        bootstrap = primary.get("bootstrap", {})
        ci_low = bootstrap.get("shortfall_ci_95_low")
        ci_high = bootstrap.get("shortfall_ci_95_high")
        for scenario in scenarios:
            if scenario.get("chokepoint_id") != event.get("chokepoint_id"):
                continue
            severity = scenario["closure_fraction"]
            within_ci = (
                ci_low is not None
                and ci_high is not None
                and ci_low <= severity <= ci_high
            )
            comparisons.append(
                {
                    "event_id": event["event_id"],
                    "historical_event_type": event["event_type"],
                    "scenario_id": scenario["id"],
                    "scenario_event_type": scenario["event_type"],
                    "event_type_matches": scenario["event_type"] == event["event_type"],
                    "historical_window_days": event["duration_calendar_days"],
                    "scenario_duration_days": scenario["duration_days"],
                    "historical_mean_shortfall_fraction": mean_shortfall,
                    "historical_peak_7d_shortfall_fraction": primary.get(
                        "observed_peak_7d_shortfall_fraction"
                    ),
                    "historical_shortfall_ci_95": [ci_low, ci_high],
                    "scenario_closure_fraction": severity,
                    "scenario_minus_historical_mean_percentage_points": (
                        severity - mean_shortfall
                    )
                    * 100.0,
                    "scenario_within_historical_mean_ci": within_ci,
                    "comparison_status": (
                        "within_historical_mean_ci"
                        if within_ci
                        else "more_severe_than_historical_mean_ci"
                        if ci_high is not None and severity > ci_high
                        else "less_severe_than_historical_mean_ci"
                    ),
                    "warning": (
                        "Severity comparison only. Different duration/event type and unobserved "
                        "behavior shares prevent direct replay equivalence."
                    ),
                }
            )
    return comparisons


def build_snapshot(
    config_dir: Path,
    *,
    fetch_portwatch: bool = False,
    fallback_live_status: dict[str, Any] | None = None,
    fetch_portwatch_port_context: bool = False,
    fallback_portwatch_port_context: dict[str, Any] | None = None,
    fetch_container_context: bool = False,
    fallback_container_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    build_time = datetime.now(timezone.utc)
    fleet = load_json(config_dir / "fleet_2025.json")
    chokepoints = load_json(config_dir / "chokepoints.json")
    routes = load_json(config_dir / "routes.json")
    comtrade_route_path = config_dir / "comtrade_route_flows.json"
    comtrade_route_data = (
        load_json(comtrade_route_path) if comtrade_route_path.exists() else None
    )
    comtrade_history_path = config_dir / "comtrade_route_history.json"
    comtrade_history = load_json(comtrade_history_path) if comtrade_history_path.exists() else {}
    port_context_config_path = config_dir / "portwatch_port_context.json"
    port_context_config = load_json(port_context_config_path) if port_context_config_path.exists() else {}
    lng_fleet_path = config_dir / "lng_fleet_2025.json"
    lng_fleet = load_lng_fleet_context(lng_fleet_path) if lng_fleet_path.exists() else {}
    market_sources_path = config_dir / "market_signal_sources.json"
    market_signals = (
        load_market_signal_registry(market_sources_path) if market_sources_path.exists() else {}
    )
    pdf_snapshot_path = config_dir / "pdf_report_snapshots.json"
    pdf_reports = load_json(pdf_snapshot_path) if pdf_snapshot_path.exists() else {
        "status": "not_fetched",
        "sources": [],
        "errors": [],
    }
    routes = apply_route_flows(routes, comtrade_route_data)
    route_catalog_path = config_dir / "route_catalog.json"
    route_catalog = load_json(route_catalog_path) if route_catalog_path.exists() else []
    route_by_id = {row["id"]: row for row in routes}
    for catalog_row in route_catalog:
        route = route_by_id.get(catalog_row.get("route_config_id"))
        if not route:
            continue
        catalog_row["model_status"] = (
            "capacity_model_active"
            if not str(route.get("input_status", "")).startswith("scenario_seed")
            else "capacity_model_configured"
        )
    event_observations_path = config_dir / "event_observations.json"
    event_observations = (
        load_json(event_observations_path) if event_observations_path.exists() else []
    )
    model_review_path = config_dir / "model_review.json"
    model_review = load_json(model_review_path) if model_review_path.exists() else {}
    model_version = model_review.get("model_version", "1.2.0")
    environment_path = config_dir / "environment_scenarios.json"
    environment_config = load_json(environment_path) if environment_path.exists() else {}
    environment_profile_path = config_dir / "environment_route_profiles.json"
    environment_profiles = (
        load_json(environment_profile_path)
        if environment_profile_path.exists()
        else {}
    )
    container_sources_path = config_dir / "container_sources.json"
    container_sources = load_json(container_sources_path) if container_sources_path.exists() else {}
    scenarios = load_json(config_dir / "scenarios.json")
    response_profile_path = config_dir / "event_response_profiles.json"
    response_profile_config = (
        load_json(response_profile_path) if response_profile_path.exists() else {"profiles": {}}
    )
    behavior_uncertainty_path = config_dir / "behavior_uncertainty_profiles.json"
    behavior_uncertainty_config = (
        load_json(behavior_uncertainty_path)
        if behavior_uncertainty_path.exists()
        else {"status": "not_configured", "profiles": {}}
    )
    event_calibration_path = config_dir / "event_calibration.json"
    event_calibration = (
        load_json(event_calibration_path)
        if event_calibration_path.exists()
        else {"status": "calibration_not_run", "events": [], "profile_evidence": {}}
    )
    event_calibration["scenario_comparisons"] = build_historical_scenario_comparisons(
        scenarios,
        event_calibration,
    )
    response_profiles = response_profile_config.get("profiles", {})
    for scenario in scenarios:
        profile_id = scenario.get("event_type", "operational_restriction")
        scenario["response_profile_id"] = profile_id
        scenario["response_adjustment"] = response_profiles.get(profile_id, {})
    fleet_by_type = {row["ship_type"]: row["dwt"] for row in fleet["fleet_by_type"]}

    live_status: dict[str, Any] = {
        chokepoint_id: normalize_status_contract(status)
        for chokepoint_id, status in (fallback_live_status or {}).items()
    }
    live_errors: list[dict[str, str]] = []
    freshly_fetched_ids: set[str] = set()
    if fetch_portwatch:
        client = PortWatchClient()
        for chokepoint in chokepoints:
            try:
                live_status[chokepoint["id"]] = normalize_status_contract(
                    client.fetch_status(chokepoint["portwatch_id"])
                )
                freshly_fetched_ids.add(chokepoint["id"])
            except Exception as exc:  # A partial upstream outage must not erase the snapshot.
                live_errors.append({"chokepoint_id": chokepoint["id"], "error": str(exc)})

    portwatch_port_context: dict[str, Any] = fallback_portwatch_port_context or {
        "status": port_context_config.get("status", "not_configured"),
        "source": port_context_config.get("source", {}),
        "groups": [],
        "identification_boundary": port_context_config.get("identification_boundary"),
    }
    port_context_errors: list[dict[str, str]] = []
    if fetch_portwatch_port_context and port_context_config:
        client = PortWatchPortClient()
        observed_groups = []
        for group in port_context_config.get("groups", []):
            try:
                observed_groups.append({
                    **client.fetch_group_status(group),
                    "scope_warning_ko": group.get("scope_warning_ko"),
                })
            except Exception as exc:
                port_context_errors.append({"group_id": str(group.get("id")), "error": str(exc)})
        portwatch_port_context = {
            "status": "fetched" if not port_context_errors else "partial_quality_gated",
            "source": port_context_config.get("source", {}),
            "groups": observed_groups,
            "errors": port_context_errors,
            "identification_boundary": port_context_config.get("identification_boundary"),
        }

    for chokepoint_id, status in live_status.items():
        latest_date = status.get("latest_date")
        stale_days = None
        if latest_date:
            try:
                stale_days = max(
                    0,
                    (build_time.date() - datetime.fromisoformat(latest_date).date()).days,
                )
            except ValueError:
                stale_days = None
        fallback_used = chokepoint_id not in freshly_fetched_ids
        status["fetched_at"] = (
            build_time.isoformat()
            if not fallback_used
            else status.get("fetched_at")
        )
        status["stale_days"] = stale_days
        status["is_stale"] = stale_days is None or stale_days > 7
        status["fallback_used"] = fallback_used
        status["source_status"] = (
            "cached_fallback"
            if fallback_used
            else "api_observation_stale"
            if status["is_stale"]
            else "api_observation_fresh"
        )

    container_context: dict[str, Any] = fallback_container_context or {
        "status": "not_fetched",
        "groups": [],
    }
    container_fetch_errors: list[str] = []
    if fetch_container_context and container_sources:
        try:
            container_context = WorldBankContainerClient().fetch(container_sources)
        except Exception as exc:
            container_fetch_errors.append(str(exc))

    route_outputs: list[dict[str, Any]] = []
    scenario_rows: dict[str, list[dict[str, Any]]] = {scenario["id"]: [] for scenario in scenarios}
    for route in routes:
        type_fleet = fleet_by_type[route["ship_type"]]
        baseline = simulate_route(route, None, type_fleet)
        baseline_interval = estimate_interval(route, None, type_fleet)
        stress_results = []
        for scenario in scenarios:
            result = simulate_route(route, scenario, type_fleet)
            scenario_rows[scenario["id"]].append(result)
            if result["affected_flow_share"] > 0:
                result["interval"] = estimate_interval(route, scenario, type_fleet)
                stress_results.append(result)

        live_results = []
        live_persistence_results = []
        for exposure in route.get("chokepoints", []):
            status = live_status.get(exposure["id"])
            metric = status and status.get("metrics", {}).get(route["ship_type"])
            if not metric:
                continue
            observed_shortfall = metric["observed_trade_volume_shortfall_fraction"]
            observed_window_days = int(status.get("current_window_days", 7))
            live_scenario = {
                "id": f"live_{exposure['id']}",
                "chokepoint_id": exposure["id"],
                "event_type": "observed_trade_volume_signal_applied_to_route",
                "closure_fraction": observed_shortfall,
                "residual_throughput_rate": 1.0 - observed_shortfall,
                "duration_days": observed_window_days,
                "horizon_days": observed_window_days,
                "waiting_days": exposure.get("default_waiting_days", 0),
                # PortWatch observes throughput but cannot identify insurance
                # status or whether waiting cargo is already on board.
                "insurance_unavailable_share": 0.0,
                "onboard_waiting_share": 0.0,
                "response_profile_id": "observed_trade_volume_signal_applied_to_route",
                "response_adjustment": response_profiles.get(
                    "observed_trade_volume_signal_applied_to_route",
                    {},
                ),
            }
            live_result = simulate_route(route, live_scenario, type_fleet)
            live_result["applied_route_flow_disruption_fraction"] = live_result.pop(
                "effective_blockage_fraction"
            )
            live_result["applied_route_flow_remaining_ratio"] = live_result.pop(
                "residual_throughput_rate"
            )
            live_result["chokepoint_id"] = exposure["id"]
            live_result["duration_days"] = observed_window_days
            live_result["horizon_days"] = observed_window_days
            live_result["observation_latest_date"] = status.get("latest_date")
            live_result["observed_window_days"] = observed_window_days
            live_result["portwatch_estimated_trade_volume_ratio"] = metric.get(
                "estimated_trade_volume_ratio",
                1.0 - observed_shortfall,
            )
            live_result["signal_type"] = "observed_estimated_trade_volume_shortfall"
            live_result["input_mapping"] = (
                "estimated_trade_volume_shortfall_used_as_route_flow_disruption_fraction"
            )
            live_result["warning_ko"] = (
                "최근 7일 추정 교역량 감소를 항로 충격률로 적용한 결과이며 "
                "물리적 봉쇄율이나 관측 DWT가 아님"
            )
            live_results.append(live_result)

            persistence_scenario = {
                **live_scenario,
                "id": f"live_{exposure['id']}_persists_28d",
                "event_type": "hypothetical_persistence_of_observed_trade_volume_shortfall",
                "duration_days": 28,
                "horizon_days": 28,
                "response_profile_id": (
                    "hypothetical_persistence_of_observed_trade_volume_shortfall"
                ),
                "response_adjustment": response_profiles.get(
                    "hypothetical_persistence_of_observed_trade_volume_shortfall",
                    {},
                ),
            }
            persistence_result = simulate_route(route, persistence_scenario, type_fleet)
            persistence_result["applied_route_flow_disruption_fraction"] = persistence_result.pop(
                "effective_blockage_fraction"
            )
            persistence_result["applied_route_flow_remaining_ratio"] = persistence_result.pop(
                "residual_throughput_rate"
            )
            persistence_result["chokepoint_id"] = exposure["id"]
            persistence_result["duration_days"] = 28
            persistence_result["horizon_days"] = 28
            persistence_result["observation_latest_date"] = status.get("latest_date")
            persistence_result["source_observed_window_days"] = observed_window_days
            persistence_result["portwatch_estimated_trade_volume_ratio"] = metric.get(
                "estimated_trade_volume_ratio",
                1.0 - observed_shortfall,
            )
            persistence_result["signal_type"] = "hypothetical_28d_persistence_scenario"
            persistence_result["input_mapping"] = (
                "observed_7d_trade_volume_shortfall_assumed_constant_for_28d"
            )
            persistence_result["warning_ko"] = (
                "최근 7일 감소율이 28일 내내 지속된다는 가정이며 관측 결과가 아님"
            )
            live_persistence_results.append(persistence_result)

        route_outputs.append(
            {
                "id": route["id"],
                "name_ko": route["name_ko"],
                "name_en": route["name_en"],
                "ship_type": route["ship_type"],
                "cargo_segment": route.get("cargo_segment", route["ship_type"]),
                "origin": route["origin"],
                "destination": route["destination"],
                "service_type": route.get("service_type", "laden_out_ballast_return"),
                "vessel_class": route.get("vessel_class"),
                "vessel_class_ko": route.get("vessel_class_ko"),
                "reference_size": route.get("reference_size", {}),
                "benchmark_family": route.get("benchmark_family"),
                "directions": route.get("directions", []),
                "input_status": route["input_status"],
                "input_sources": route["input_sources"],
                "data_provenance": route.get("data_provenance"),
                "annual_cargo_tonnes": route["annual_cargo_tonnes"],
                "model_inputs": {
                    "distance_nm_one_way": route["distance_nm_one_way"],
                    "speed_knots": route["speed_knots"],
                    "port_days_round_trip": route["port_days_round_trip"],
                    "utilization": route["utilization"],
                    "reserve_margin": route["reserve_margin"],
                    "uncertainty": route.get("uncertainty", {}),
                },
                "chokepoints": route.get("chokepoints", []),
                "baseline": {**baseline, "interval": baseline_interval},
                "stress_tests": stress_results,
                "live_observed": live_results,
                "live_persistence_28d": live_persistence_results,
            }
        )

    scenario_summary = []
    for scenario in scenarios:
        summary = aggregate_scenario(scenario, scenario_rows[scenario["id"]])
        sensitivity = build_behavior_sensitivity(
            routes,
            scenario,
            fleet_by_type,
            behavior_uncertainty_config,
        )
        if sensitivity is not None:
            summary["behavior_sensitivity"] = sensitivity
        scenario_summary.append(summary)
    ui_scenario_grid = build_ui_scenario_grid(routes, scenarios, fleet_by_type)
    environment_results: list[dict[str, Any]] = []
    for environment_scenario in environment_config.get("scenarios", []):
        route_results = []
        for route, route_output in zip(routes, route_outputs):
            environment_route = dict(route)
            environment_route["_baseline_required_dwt"] = route_output["baseline"][
                "baseline_required_dwt"
            ]
            environment_route["_allocated_dwt_with_reserve"] = route_output["baseline"][
                "allocated_dwt_with_reserve"
            ]
            route_results.append(
                simulate_environment_route_range(
                    environment_route,
                    environment_scenario,
                    environment_profiles,
                )
            )
        environment_results.append(
            {
                **aggregate_environment_scenario(environment_scenario, route_results),
                "routes": route_results,
            }
        )
    live_display = build_live_display(chokepoints, live_status)
    scenario_signal_comparison = build_scenario_signal_comparison(
        scenarios,
        chokepoints,
        live_status,
    )
    return rounded(
        {
            "schema_version": "shipping-capacity-v1",
            "generated_at": build_time.isoformat(),
            "model": {
                "name": "Route Cycle Capacity + Chokepoint Shock",
                "version": model_version,
                "formula": "one-way: cargo * cycle / (365 * utilization); bidirectional: max(direction cargo / utilization) * cycle / 365",
                "uncertainty": "P10/P50/P90 parameter range; not an event-probability forecast",
                "shock_state_model": "throughput, cargo backlog and commercially available DWT are separate states",
                "analysis_stack": [
                    "deterministic route-cycle capacity",
                    "scenario stress testing",
                    "chronological OLS signal diagnostic",
                    "chronological multi-model regression comparison",
                    "historical event-window throughput calibration",
                    "deterministic joint behavior sensitivity paths",
                    "K-Means regime classification",
                    "Isolation Forest anomaly scoring",
                ],
            },
            "data_policy": {
                "observed": "UNCTAD fleet baseline and optional IMF PortWatch daily estimated trade volume",
                "estimated": "route DWT derived from cargo flow, distance, speed, utilization and reserve",
                "scenario": "effective blockage, residual throughput, reroute, backlog, trapped DWT, insurance and cancellation assumptions",
                "warning": "Route capacity is DWT-equivalent demand, not a vessel-by-vessel AIS inventory. Trapped and insurance-excluded DWT are scenario estimates. Behavior sensitivity ranges are deterministic joint paths, not probabilities or empirically estimated correlations.",
            },
            "sources": [
                {
                    "name": "UNCTAD Review of Maritime Transport 2025, table II.5",
                    "url": "https://unctad.org/system/files/official-document/rmt2025ch2_en.pdf",
                },
                {
                    "name": "IMF PortWatch Daily Chokepoints Data (ArcGIS REST)",
                    "url": "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services/Daily_Chokepoints_Data/FeatureServer/0/query",
                },
                {
                    "name": "UN Comtrade quantity/net-weight methodology",
                    "url": "https://comtradeapi.un.org/files/v1/app/wiki/MethodologyGuideforComtradePlus.pdf",
                },
                {
                    "name": "IMO Middle East / Strait of Hormuz official updates",
                    "url": "https://www.imo.org/en/mediacentre/hottopics/pages/middle-east-strait-of-hormuz.aspx",
                },
            ],
            "fleet": fleet,
            "lng_fleet": lng_fleet,
            "chokepoints": chokepoints,
            "chokepoints_live": live_status,
            "live_display": live_display,
            "scenario_signal_comparison": scenario_signal_comparison,
            "live_fetch_errors": live_errors,
            "live_data_quality": {
                "freshness_threshold_days": 7,
                "fresh_count": sum(
                    1 for status in live_status.values() if not status.get("is_stale")
                ),
                "stale_count": sum(
                    1 for status in live_status.values() if status.get("is_stale")
                ),
                "fallback_count": sum(
                    1 for status in live_status.values() if status.get("fallback_used")
                ),
                "status": (
                    "stale_or_fallback"
                    if any(
                        status.get("is_stale") or status.get("fallback_used")
                        for status in live_status.values()
                    )
                    else "fresh"
                ),
            },
            "event_observations": event_observations,
            "model_review": model_review,
            "environment": {
                "status": environment_profiles.get(
                    "status", environment_config.get("status", "not_configured")
                ),
                "methodology_ko": environment_profiles.get(
                    "methodology_ko", environment_config.get("methodology_ko")
                ),
                "warnings_ko": environment_config.get("warnings_ko", []),
                "sources": environment_config.get("sources", []),
                "identification_boundary": environment_profiles.get(
                    "identification_boundary", {}
                ),
                "scenarios": environment_results,
            },
            "container": {
                "status": container_sources.get("status", "not_configured"),
                "sources": container_sources.get("sources", []),
                "quality_gates": container_sources.get("quality_gates", []),
                "context": container_context,
                "fetch_errors": container_fetch_errors,
                "route_volume_status": (
                    "comtrade_directional_manufactured_goods_weight_proxy"
                    if comtrade_route_data
                    else "pending_public_bilateral_container_volume"
                ),
            },
            "comtrade_routes": {
                "status": (comtrade_route_data or {}).get("status", "not_fetched"),
                "period": (comtrade_route_data or {}).get("period"),
                "fetched_at": (comtrade_route_data or {}).get("fetched_at"),
                "method": (comtrade_route_data or {}).get("method"),
                "route_count": len((comtrade_route_data or {}).get("routes", [])),
                "history": {
                    "status": comtrade_history.get("status", "not_fetched"),
                    "periods": comtrade_history.get("periods", []),
                    "route_count": len(
                        comtrade_history.get("route_history_summary", {}).get("routes", [])
                    ),
                    "identification_boundary": comtrade_history.get("identification_boundary"),
                },
            },
            "comtrade_route_history": comtrade_history,
            "portwatch_port_context": portwatch_port_context,
            "market_signals": market_signals,
            "pdf_reports": pdf_reports,
            "event_response_profiles": response_profile_config,
            "behavior_uncertainty": behavior_uncertainty_config,
            "historical_event_calibration": event_calibration,
            "route_catalog": route_catalog,
            "routes": route_outputs,
            "scenarios": scenarios,
            "scenario_summary": scenario_summary,
            "ui_scenario_grid": ui_scenario_grid,
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "config",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "generated" / "shipping_capacity_v1.json",
    )
    parser.add_argument("--fetch-portwatch", action="store_true")
    parser.add_argument("--fetch-portwatch-port-context", action="store_true")
    parser.add_argument("--fetch-container-context", action="store_true")
    parser.add_argument("--diagnostics-output", type=Path)
    parser.add_argument("--backtests-output", type=Path)
    args = parser.parse_args()
    fallback_live_status: dict[str, Any] = {}
    fallback_portwatch_port_context: dict[str, Any] = {}
    fallback_container_context: dict[str, Any] = {}
    if args.output.exists():
        try:
            previous_snapshot = load_json(args.output)
            fallback_live_status = previous_snapshot.get("chokepoints_live", {})
            fallback_portwatch_port_context = previous_snapshot.get(
                "portwatch_port_context", {}
            )
            fallback_container_context = previous_snapshot.get("container", {}).get(
                "context",
                {},
            )
        except (OSError, ValueError, TypeError):
            # A malformed prior artifact must not prevent a clean rebuild.
            fallback_live_status = {}
            fallback_portwatch_port_context = {}
            fallback_container_context = {}
    snapshot = build_snapshot(
        args.config_dir,
        fetch_portwatch=args.fetch_portwatch,
        fallback_live_status=fallback_live_status,
        fetch_portwatch_port_context=args.fetch_portwatch_port_context,
        fallback_portwatch_port_context=fallback_portwatch_port_context,
        fetch_container_context=args.fetch_container_context,
        fallback_container_context=fallback_container_context,
    )
    bundle = build_artifact_bundle(snapshot)
    diagnostics_output = args.diagnostics_output or (
        args.output.parent / "shipping_capacity_diagnostics_v1.json"
    )
    backtests_output = args.backtests_output or (
        args.output.parent / "shipping_capacity_backtests_v1.json"
    )
    for path, payload in (
        (args.output, bundle["screen"]),
        (diagnostics_output, bundle["diagnostics"]),
        (backtests_output, bundle["backtests"]),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
