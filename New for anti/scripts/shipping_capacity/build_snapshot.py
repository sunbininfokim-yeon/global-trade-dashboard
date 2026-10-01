#!/usr/bin/env python3
"""Build the frontend-ready shipping_capacity_v1.json snapshot."""

from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shipping_capacity.engine import estimate_interval, route_operational_profile, simulate_route
from shipping_capacity.artifacts import build_artifact_bundle
from shipping_capacity.behavior_sensitivity import behavior_paths_for_scenario
from shipping_capacity.comtrade_routes import apply_route_flows
from shipping_capacity.container import WorldBankContainerClient
from shipping_capacity.lng_fleet import load_lng_fleet_context
from shipping_capacity.market_signals import load_market_signal_registry
from shipping_capacity.environment import (
    aggregate_environment_scenario,
    expand_environment_scenarios,
    simulate_environment_route_range,
)
from shipping_capacity.portwatch import (
    PortWatchClient,
    PortWatchPortClient,
    normalize_status_contract,
)
from shipping_capacity.route_distances import attach_distance_evidence
from shipping_capacity.official_cargo import collect_official_cargo
from shipping_capacity.hormuz_reconstruction import collect_hormuz_reconstruction


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


def aggregate_reroute_receivers(
    scenario: dict[str, Any],
    results: list[dict[str, Any]],
    routes: list[dict[str, Any]],
    receiver_config: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate modeled detours at an alternative corridor without inventing AIS flow."""

    receivers = {row["id"]: row for row in receiver_config}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for route, result in zip(routes, results):
        if result["affected_flow_share"] <= 0 or result["rerouted_cargo_tonnes_horizon"] <= 0:
            continue
        exposure = next(
            (
                row
                for row in route.get("chokepoints", [])
                if row.get("id") == scenario["chokepoint_id"]
            ),
            None,
        )
        receiver_id = exposure and exposure.get("reroute_receiver_id")
        if not receiver_id:
            continue
        receiver = receivers.get(receiver_id)
        if receiver is None:
            raise ValueError(f"unknown reroute receiver: {receiver_id}")
        if scenario["chokepoint_id"] not in receiver.get("source_chokepoint_ids", []):
            raise ValueError(
                f"reroute receiver {receiver_id} does not allow source "
                f"{scenario['chokepoint_id']}"
            )
        grouped.setdefault(receiver_id, []).append(
            {**result, "cargo_segment": route.get("cargo_segment", route["ship_type"])}
        )

    output = []
    for receiver_id, rows in grouped.items():
        receiver = receivers[receiver_id]
        ship_type_breakdown = []
        for ship_type in ("container", "dry_bulk", "tanker"):
            typed = [row for row in rows if row["ship_type"] == ship_type]
            if not typed:
                continue
            baseline_service_capacity_dwt = sum(
                row["baseline_required_dwt"] for row in typed
            )
            additional_service_capacity_dwt = sum(
                row["net_required_capacity_change_dwt"] for row in typed
            )
            weighted_served_flow_index = (
                sum(
                    row["served_flow_index"] * row["baseline_required_dwt"]
                    for row in typed
                )
                / baseline_service_capacity_dwt
                if baseline_service_capacity_dwt > 0
                else 1.0
            )
            ship_type_breakdown.append(
                {
                    "ship_type": ship_type,
                    "affected_route_count": len(typed),
                    "baseline_service_capacity_dwt": baseline_service_capacity_dwt,
                    "rerouted_cargo_tonnes_horizon": sum(
                        row["rerouted_cargo_tonnes_horizon"] for row in typed
                    ),
                    "rerouted_in_transit_cargo_tonnes_horizon": sum(
                        row["rerouted_in_transit_cargo_tonnes_horizon"] for row in typed
                    ),
                    "additional_service_capacity_dwt": additional_service_capacity_dwt,
                    "additional_service_capacity_pct_of_baseline": (
                        additional_service_capacity_dwt
                        / baseline_service_capacity_dwt
                        * 100.0
                        if baseline_service_capacity_dwt > 0
                        else None
                    ),
                    "weighted_traffic_change_pct": (
                        weighted_served_flow_index - 1.0
                    ) * 100.0,
                    "scope": (
                        "Representative affected route-service capacity, not a "
                        "live liner-network vessel inventory."
                    ),
                }
            )
        cargo_segment_breakdown = []
        for cargo_segment in sorted({row["cargo_segment"] for row in rows}):
            segmented = [row for row in rows if row["cargo_segment"] == cargo_segment]
            cargo_segment_breakdown.append(
                {
                    "cargo_segment": cargo_segment,
                    "affected_route_count": len(segmented),
                    "rerouted_cargo_tonnes_horizon": sum(
                        row["rerouted_cargo_tonnes_horizon"] for row in segmented
                    ),
                    "rerouted_in_transit_cargo_tonnes_horizon": sum(
                        row["rerouted_in_transit_cargo_tonnes_horizon"] for row in segmented
                    ),
                    "additional_service_capacity_dwt": sum(
                        row["net_required_capacity_change_dwt"] for row in segmented
                    ),
                    "global_fleet_denominator_status": (
                        "lng_only_global_dwt_not_available_free"
                        if cargo_segment == "lng"
                        else "not_applicable_to_cargo_segment"
                    ),
                }
            )
        output.append(
            {
                "id": receiver_id,
                "name_ko": receiver["name_ko"],
                "name_en": receiver["name_en"],
                "receiver_role": receiver["receiver_role"],
                "source_chokepoint_id": scenario["chokepoint_id"],
                "affected_route_count": len(rows),
                "rerouted_cargo_tonnes_horizon": sum(
                    row["rerouted_cargo_tonnes_horizon"] for row in rows
                ),
                "rerouted_in_transit_cargo_tonnes_horizon": sum(
                    row["rerouted_in_transit_cargo_tonnes_horizon"] for row in rows
                ),
                "additional_service_capacity_dwt": sum(
                    row["net_required_capacity_change_dwt"] for row in rows
                ),
                "ship_type_breakdown": ship_type_breakdown,
                "cargo_segment_breakdown": cargo_segment_breakdown,
                "methodology_ko": receiver["methodology_ko"],
                "warning_ko": receiver["warning_ko"],
                "status": "modelled_reroute_receiver_not_observed_traffic",
            }
        )
    return output


def aggregate_cargo_segments(
    results: list[dict[str, Any]], routes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Keep LNG visible without treating the tanker denominator as LNG fleet DWT."""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for route, result in zip(routes, results):
        if result["affected_flow_share"] <= 0:
            continue
        cargo_segment = route.get("cargo_segment", route["ship_type"])
        grouped.setdefault(cargo_segment, []).append(result)

    output = []
    for cargo_segment, rows in sorted(grouped.items()):
        baseline = sum(row["baseline_required_dwt"] for row in rows)
        deliverable = (
            sum(row["deliverable_flow_index"] * row["baseline_required_dwt"] for row in rows)
            / baseline
            if baseline > 0
            else 1.0
        )
        output.append(
            {
                "cargo_segment": cargo_segment,
                "affected_route_count": len(rows),
                "affected_baseline_dwt": baseline,
                "affected_allocated_dwt_with_reserve": sum(
                    row["allocated_dwt_with_reserve"] for row in rows
                ),
                "operational_capacity_absorbed_dwt": sum(
                    row["operational_capacity_absorbed_dwt"] for row in rows
                ),
                "commercial_capacity_gap_dwt": sum(
                    row["capacity_gap_dwt"] for row in rows
                ),
                "commercially_unavailable_dwt": sum(
                    row["commercially_unavailable_dwt"] for row in rows
                ),
                "backlog_cargo_tonnes_horizon": sum(
                    row["backlog_cargo_tonnes_horizon"] for row in rows
                ),
                "rerouted_in_transit_cargo_tonnes_horizon": sum(
                    row["rerouted_in_transit_cargo_tonnes_horizon"] for row in rows
                ),
                "weighted_traffic_change_pct": (deliverable - 1.0) * 100.0,
                "global_fleet_denominator_status": (
                    "lng_only_global_dwt_not_available_free"
                    if cargo_segment == "lng"
                    else "not_applicable_to_cargo_segment"
                ),
                "scope": (
                    "Representative route-model allocations for this cargo segment; "
                    "not an AIS-observed unique-vessel inventory."
                ),
            }
        )
    return output


def aggregate_scenario(
    scenario: dict[str, Any],
    results: list[dict[str, Any]],
    routes: list[dict[str, Any]],
    receiver_config: list[dict[str, Any]],
) -> dict[str, Any]:
    affected = [row for row in results if row["affected_flow_share"] > 0]
    baseline = sum(row["baseline_required_dwt"] for row in affected)
    allocated = sum(row["allocated_dwt_with_reserve"] for row in affected)
    global_type_fleet_by_ship_type = {
        row["ship_type"]: row["global_type_fleet_dwt"] for row in affected
    }
    relevant_global_type_fleet = sum(global_type_fleet_by_ship_type.values())
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

    ship_type_breakdown = []
    for ship_type in ("container", "dry_bulk", "tanker"):
        rows = [row for row in affected if row["ship_type"] == ship_type]
        if not rows:
            continue
        type_baseline = sum(row["baseline_required_dwt"] for row in rows)
        type_allocated = sum(row["allocated_dwt_with_reserve"] for row in rows)
        type_disrupted = sum(row["disrupted_required_dwt"] for row in rows)
        type_absorbed = sum(row["operational_capacity_absorbed_dwt"] for row in rows)
        type_gap = sum(row["capacity_gap_dwt"] for row in rows)
        type_unavailable = sum(row["commercially_unavailable_dwt"] for row in rows)
        type_available = sum(row["commercially_available_dwt"] for row in rows)
        type_backlog = sum(row["backlog_cargo_tonnes_horizon"] for row in rows)
        type_rerouted = sum(
            row["rerouted_in_transit_cargo_tonnes_horizon"] for row in rows
        )
        type_served = sum(row["served_cargo_tonnes_horizon"] for row in rows)
        type_lost = sum(row["lost_cargo_tonnes_horizon"] for row in rows)
        type_global_fleet = rows[0]["global_type_fleet_dwt"]
        type_deliverable = (
            sum(row["deliverable_flow_index"] * row["baseline_required_dwt"] for row in rows)
            / type_baseline
            if type_baseline > 0
            else 1.0
        )
        ship_type_breakdown.append(
            {
                "ship_type": ship_type,
                "affected_route_count": len(rows),
                "affected_baseline_dwt": type_baseline,
                "affected_allocated_dwt_with_reserve": type_allocated,
                "relevant_global_type_fleet_dwt": type_global_fleet,
                "disrupted_required_dwt": type_disrupted,
                "operational_capacity_absorbed_dwt": type_absorbed,
                "operational_capacity_absorbed_pct_of_affected_allocated": (
                    type_absorbed / type_allocated * 100.0
                    if type_allocated > 0
                    else None
                ),
                "operational_capacity_absorbed_pct_of_relevant_global_type_fleet": (
                    type_absorbed / type_global_fleet * 100.0
                    if type_global_fleet > 0
                    else None
                ),
                "commercial_capacity_gap_dwt": type_gap,
                "commercially_unavailable_dwt": type_unavailable,
                "commercially_available_dwt": type_available,
                "commercially_unavailable_pct_of_affected_allocated": (
                    type_unavailable / type_allocated * 100.0
                    if type_allocated > 0
                    else None
                ),
                "commercially_available_pct_of_affected_allocated": (
                    type_available / type_allocated * 100.0
                    if type_allocated > 0
                    else None
                ),
                "served_cargo_tonnes_horizon": type_served,
                "backlog_cargo_tonnes_horizon": type_backlog,
                "rerouted_in_transit_cargo_tonnes_horizon": type_rerouted,
                "lost_cargo_tonnes_horizon": type_lost,
                "weighted_served_flow_index": type_deliverable,
                "weighted_traffic_change_pct": (type_deliverable - 1.0) * 100.0,
                "scope": (
                    "Representative route-model allocations for this ship type; "
                    "not an AIS-observed unique-vessel inventory."
                ),
            }
        )
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
        "affected_allocated_dwt_with_reserve": allocated,
        "relevant_global_type_fleet_dwt": relevant_global_type_fleet,
        "disrupted_required_dwt": disrupted,
        "operational_capacity_absorbed_dwt": absorbed,
        "operational_capacity_absorbed_pct_of_affected_allocated": (
            absorbed / allocated * 100.0 if allocated > 0 else None
        ),
        "operational_capacity_absorbed_pct_of_relevant_global_type_fleet": (
            absorbed / relevant_global_type_fleet * 100.0
            if relevant_global_type_fleet > 0
            else None
        ),
        "capacity_gap_dwt": gap,
        "commercial_capacity_gap_dwt": gap,
        "trapped_loaded_dwt": trapped,
        "trapped_vessel_equivalent": trapped_vessel_equivalent,
        "trapped_vessel_equivalent_warning": "Reference-class DWT equivalent, not an observed AIS vessel count.",
        "insurance_excluded_dwt": insurance_excluded,
        "commercially_unavailable_dwt": unavailable,
        "commercially_unavailable_pct_of_affected_allocated": (
            unavailable / allocated * 100.0 if allocated > 0 else None
        ),
        "commercially_available_dwt": available,
        "commercially_available_pct_of_affected_allocated": (
            available / allocated * 100.0 if allocated > 0 else None
        ),
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
        "ship_type_breakdown": ship_type_breakdown,
        "cargo_segment_breakdown": aggregate_cargo_segments(results, routes),
        "reroute_receivers": aggregate_reroute_receivers(
            scenario, results, routes, receiver_config
        ),
        "capacity_denominator_warning": (
            "Affected allocated DWT is the sum of representative route-model "
            "allocations, not an AIS-observed unique-vessel inventory. Relevant "
            "global type fleet counts each affected ship type once."
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
    receiver_config: list[dict[str, Any]],
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
        summary = aggregate_scenario(variant, route_results, routes, receiver_config)
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


DEFAULT_UI_GRID_CONFIG = {
    "closure_pct_options": list(range(0, 101, 10)),
    "duration_day_options": [1, 3, 7, 14, 21, 28],
    "fixed_horizon_days": 28,
}


def build_ui_scenario_grid(
    routes: list[dict[str, Any]],
    scenarios: list[dict[str, Any]],
    fleet_by_type: dict[str, float],
    receiver_config: list[dict[str, Any]],
    grid_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Precompute a bounded UI grid so the browser never reimplements the model."""

    config = {**DEFAULT_UI_GRID_CONFIG, **(grid_config or {})}
    closure_options = sorted({int(value) for value in config["closure_pct_options"]})
    duration_options = sorted({int(value) for value in config["duration_day_options"]})
    horizon_days = int(config["fixed_horizon_days"])
    if (
        not closure_options
        or closure_options[0] != 0
        or closure_options[-1] != 100
        or any(value < 0 or value > 100 for value in closure_options)
    ):
        raise ValueError("ui scenario closure_pct_options must cover 0 through 100")
    if not duration_options or any(value <= 0 or value > horizon_days for value in duration_options):
        raise ValueError("ui scenario duration_day_options must be positive and within horizon")

    rows = []
    route_fields = (
        "route_id",
        "ship_type",
        "cargo_segment",
        "baseline_required_dwt",
        "allocated_dwt_with_reserve",
        "continuity_required_dwt",
        "operational_capacity_absorbed_dwt",
        "operational_capacity_absorbed_pct_of_route_allocated",
        "commercial_capacity_gap_dwt",
        "trapped_loaded_dwt",
        "insurance_excluded_dwt",
        "commercially_available_dwt",
        "commercially_unavailable_dwt",
        "commercially_unavailable_pct_of_route_allocated",
        "served_flow_index",
        "traffic_change_pct",
        "served_cargo_tonnes_horizon",
        "backlog_cargo_tonnes_horizon",
        "rerouted_in_transit_cargo_tonnes_horizon",
        "lost_cargo_tonnes_horizon",
    )
    for base in scenarios:
        for closure_pct in closure_options:
            for duration_days in duration_options:
                scenario = copy.deepcopy(base)
                scenario["id"] = (
                    f"ui_{base['id']}_{closure_pct}pct_{duration_days}d"
                )
                scenario["closure_fraction"] = closure_pct / 100.0
                scenario["residual_throughput_rate"] = 1.0 - scenario["closure_fraction"]
                scenario["duration_days"] = duration_days
                scenario["horizon_days"] = horizon_days
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
                        "horizon_days": horizon_days,
                        "waiting_days": scenario.get("waiting_days", 0),
                        "summary": aggregate_scenario(
                            scenario, results, routes, receiver_config
                        ),
                        "routes": [
                            {field: result.get(field) for field in route_fields}
                            for result in affected
                        ],
                    }
                )
    return {
        "status": "precomputed_python_engine",
        "closure_pct_options": closure_options,
        "duration_day_options": duration_options,
        "fixed_horizon_days": horizon_days,
        "input_policy": {
            "closure_pct_step": min(
                b - a for a, b in zip(closure_options, closure_options[1:])
            ),
            "duration_values_precomputed": True,
            "browser_recalculation": False,
            "warning_ko": (
                config.get(
                    "methodology_ko",
                    "선택값은 Python 엔진이 사전 계산한 범위입니다. 임의 수치의 "
                    "브라우저 보간·재계산은 하지 않습니다.",
                )
            ),
        },
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


def build_ui_delivery_contract() -> dict[str, Any]:
    """Publish the no-browser-calculation boundary for the shipping UI.

    Paths are relative to the screen snapshot root.  They are intentionally
    presentation instructions, not an alternate calculation layer.
    """

    return {
        "contract_version": "shipping-ui-delivery-v2",
        "calculation_owner": "python_shipping_capacity_engine",
        "unavailable_value_rule": (
            "Render unavailable or the supplied warning when a value is null or a "
            "status says unavailable; never substitute zero or derive a replacement."
        ),
        "views": {
            "global_fleet": {
                "title_ko": "글로벌 선대",
                "data_paths": ["fleet.fleet_by_type", "lng_fleet"],
                "render_only_rule": "Use the published DWT or TEU context fields without reclassification.",
            },
            "route_service": {
                "title_ko": "항로 운항 선복량",
                "subtitle_ko": "선종별 운항 서비스",
                "tabs": ["all", "container", "dry_bulk", "tanker"],
                "data_paths": [
                    "routes[]",
                    "routes[].baseline",
                "routes[].operational_profile.normal",
                "routes[].operational_profile.chokepoint_alternatives[]",
                "routes[].operational_profile.chokepoint_alternatives[].distance_evidence",
                ],
                "primary_metrics": [
                    "baseline.baseline_required_dwt",
                    "baseline.allocated_dwt_with_reserve",
                    "operational_profile.normal.cycle_days_round_trip",
                ],
                "render_only_rule": (
                    "This is service capacity continuously required by the modeled flow, "
                    "not an AIS vessel-position inventory."
                ),
                "container_teu_rule": (
                    "Use fleet DWT for cross-ship-type global comparison. For container "
                    "service size, show routes[].reference_size.teu_min/teu_max; do not "
                    "invent a global container-TEU fleet total when it is not published."
                ),
            },
            "chokepoint_detail": {
                "title_ko": "초크포인트 상세 및 봉쇄 시뮬레이터",
                "scenario_grid_source": "shipping_capacity_scenario_grid_v1.json",
                "data_paths": [
                    "chokepoints[]",
                    "live_display[]",
                    "chokepoints_live.<id>.history[]",
                    "chokepoints_live.<id>.daily_averages",
                    "chokepoints_live.<id>.metrics.<ship_type>",
                    "chokepoints_live.<id>.metric_histories.<ship_type>.history[]",
                    "official_cargo_monitor.chokepoints.<id>.reference_cards[]",
                    "official_cargo_monitor.chokepoints.<id>.supplementary_reference_cards[]",
                    "official_cargo_monitor.chokepoints.<id>.reported_series[]",
                    "official_cargo_monitor.chokepoints.<id>.transit_assessment",
                    "hormuz_reconstruction.headline",
                    "hormuz_reconstruction.mass_balance.terms[]",
                    "hormuz_reconstruction.producer_exports",
                    "hormuz_reconstruction.importer_receipts",
                    "hormuz_reconstruction.sar_coverage",
                    "scenarios[]",
                    "ui_scenario_grid.rows[]",
                    "ui_scenario_grid.input_policy",
                ],
                "input_fields": [
                    "base_scenario_id",
                    "closure_pct",
                    "duration_days",
                ],
                "result_fields": [
                    "summary.affected_baseline_dwt",
                    "summary.operational_capacity_absorbed_dwt",
                    "summary.operational_capacity_absorbed_pct_of_affected_allocated",
                    "summary.commercially_unavailable_dwt",
                    "summary.backlog_cargo_tonnes_horizon",
                    "summary.ship_type_breakdown[]",
                    "summary.cargo_segment_breakdown[]",
                    "summary.reroute_receivers[]",
                    "summary.reroute_receivers[].ship_type_breakdown[]",
                ],
                "labels_ko": {
                    "closure_pct": "실효 통행제약률",
                    "duration_days": "제약 지속일",
                    "backlog_cargo_tonnes_horizon": "28일 분석기간 말 미운송 화물",
                    "commercially_unavailable_dwt": "상업적으로 사용 불가한 모델상 DWT",
                    "cargo_segment_breakdown": "화물 세그먼트별 모델 결과; LNG 전용 세계 선대 DWT 분모는 무료 공개 검증 전까지 사용하지 않음",
                    "daily_averages": "일별 추정 교역량 및 관측일 기준 이동평균",
                    "official_cargo_monitor": "기관 발표 기간별 일평균; 일별 실제 원유량·통항 성공확률 아님",
                    "hormuz_reconstruction": "호르무즈 미포착 흐름 역산 원장; 입력이 식별될 때만 월간 미설명 물량 범위, 그 전에는 null",
                },
                "render_only_rule": (
                    "Match a precomputed row by all three input fields. Do not calculate "
                    "closure, traffic, backlog, insurance exclusion or ship-type totals in JavaScript."
                ),
            },
            "environment": {
                "title_ko": "환경 규제 시나리오",
                "data_paths": [
                    "environment.pathways[]",
                    "environment.scenarios[]",
                    "environment.scenarios[].ship_type_breakdown[]",
                ],
                "render_only_rule": (
                    "Filter by pathway_id and order by year only. Regulation targets, "
                    "operator-response assumptions and effective DWT are already separated."
                ),
            },
        },
    }


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
    fetch_official_cargo: bool = False,
    fallback_official_cargo: dict[str, Any] | None = None,
    fetch_reconstruction: bool = False,
    fallback_reconstruction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    build_time = datetime.now(timezone.utc)
    official_cargo = collect_official_cargo(
        fetch=fetch_official_cargo, previous=fallback_official_cargo, now=build_time,
    )
    fleet = load_json(config_dir / "fleet_2025.json")
    chokepoints = load_json(config_dir / "chokepoints.json")
    routes = load_json(config_dir / "routes.json")
    reroute_receivers_path = config_dir / "reroute_receivers.json"
    reroute_receivers = (
        load_json(reroute_receivers_path) if reroute_receivers_path.exists() else []
    )
    distance_evidence_path = config_dir / "route_distance_observations.json"
    distance_evidence = (
        load_json(distance_evidence_path)
        if distance_evidence_path.exists()
        else {"status": "not_generated", "routes": []}
    )
    attach_distance_evidence(routes, distance_evidence)
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
    ui_grid_path = config_dir / "ui_scenario_grid.json"
    ui_grid_config = load_json(ui_grid_path) if ui_grid_path.exists() else {}
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
                "operational_profile": route_operational_profile(route),
                "chokepoints": route.get("chokepoints", []),
                "baseline": {**baseline, "interval": baseline_interval},
                "stress_tests": stress_results,
                "live_observed": live_results,
                "live_persistence_28d": live_persistence_results,
            }
        )

    scenario_summary = []
    for scenario in scenarios:
        summary = aggregate_scenario(
            scenario,
            scenario_rows[scenario["id"]],
            routes,
            reroute_receivers,
        )
        sensitivity = build_behavior_sensitivity(
            routes,
            scenario,
            fleet_by_type,
            behavior_uncertainty_config,
            reroute_receivers,
        )
        if sensitivity is not None:
            summary["behavior_sensitivity"] = sensitivity
        scenario_summary.append(summary)
    ui_scenario_grid = build_ui_scenario_grid(
        routes, scenarios, fleet_by_type, reroute_receivers, ui_grid_config
    )
    environment_results: list[dict[str, Any]] = []
    environment_scenarios = expand_environment_scenarios(environment_config)
    for environment_scenario in environment_scenarios:
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
                    "name": "Open-source maritime-network route-distance evidence",
                    "url": "https://github.com/genthalili/searoute-py",
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
            "official_cargo_monitor": official_cargo,
            "hormuz_reconstruction": collect_hormuz_reconstruction(
                fetch=fetch_reconstruction, previous=fallback_reconstruction, now=build_time,
                official_cargo=official_cargo, live_status=live_status,
            ),
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
            "ui_delivery_contract": build_ui_delivery_contract(),
            "environment": {
                "contract_version": environment_config.get(
                    "contract_version", "environment-legacy"
                ),
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
                "pathways": [
                    {
                        key: pathway.get(key)
                        for key in (
                            "id",
                            "name_ko",
                            "policy_status",
                            "description_ko",
                        )
                    }
                    for pathway in environment_config.get("pathways", [])
                ],
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
    parser.add_argument("--fetch-official-cargo", action="store_true")
    parser.add_argument("--fetch-reconstruction", action="store_true")
    parser.add_argument("--previous-snapshot", type=Path)
    parser.add_argument("--fetch-portwatch-port-context", action="store_true")
    parser.add_argument("--fetch-container-context", action="store_true")
    parser.add_argument("--scenario-grid-output", type=Path)
    parser.add_argument("--diagnostics-output", type=Path)
    parser.add_argument("--backtests-output", type=Path)
    args = parser.parse_args()
    fallback_live_status: dict[str, Any] = {}
    fallback_portwatch_port_context: dict[str, Any] = {}
    fallback_container_context: dict[str, Any] = {}
    fallback_official_cargo: dict[str, Any] = {}
    fallback_reconstruction: dict[str, Any] = {}
    previous_path = args.previous_snapshot or args.output
    if previous_path.exists():
        try:
            previous_snapshot = load_json(previous_path)
            fallback_official_cargo = previous_snapshot.get("official_cargo_monitor", {})
            fallback_reconstruction = previous_snapshot.get("hormuz_reconstruction", {})
            fallback_live_status = previous_snapshot.get("chokepoints_live", {})
            # A screen cache has only 180 days. An official-only refresh must
            # not erase the matching diagnostic cache's 730-day AIS history.
            previous_diagnostics_path = previous_path.parent / "shipping_capacity_diagnostics_v1.json"
            if previous_diagnostics_path.exists():
                try:
                    previous_diagnostics = load_json(previous_diagnostics_path)
                    if previous_diagnostics.get("bundle_id") == previous_snapshot.get("bundle_id") and previous_snapshot.get("bundle_id"):
                        fallback_live_status = previous_diagnostics.get("chokepoints_live", fallback_live_status)
                except (OSError, ValueError, TypeError):
                    pass
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
        # Existing daily shipping workflow already invokes --fetch-portwatch.
        # This is deliberately keyless and needs no workflow/secret change.
        fetch_official_cargo=args.fetch_official_cargo or args.fetch_portwatch,
        fallback_official_cargo=fallback_official_cargo,
        # Same keyless rule: the daily --fetch-portwatch run refreshes it.
        fetch_reconstruction=args.fetch_reconstruction or args.fetch_portwatch,
        fallback_reconstruction=fallback_reconstruction,
    )
    bundle = build_artifact_bundle(snapshot)
    scenario_grid_output = args.scenario_grid_output or (
        args.output.parent / "shipping_capacity_scenario_grid_v1.json"
    )
    diagnostics_output = args.diagnostics_output or (
        args.output.parent / "shipping_capacity_diagnostics_v1.json"
    )
    backtests_output = args.backtests_output or (
        args.output.parent / "shipping_capacity_backtests_v1.json"
    )
    for path, payload in (
        (args.output, bundle["screen"]),
        (scenario_grid_output, bundle["scenario_grid"]),
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
