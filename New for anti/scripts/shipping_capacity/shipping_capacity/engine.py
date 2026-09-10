"""Deterministic route-capacity model with transparent uncertainty bands.

The engine deliberately avoids pretending that public data can identify every
ship assigned to a commercial service.  It estimates the DWT-equivalent fleet
that must be continuously tied to a route to move a stated annual cargo flow.
Every output retains the provenance class of its inputs: observed, estimated,
or scenario.
"""

from __future__ import annotations

import copy
import hashlib
import math
import random
from collections import defaultdict
from typing import Any, Iterable


class InputError(ValueError):
    """Raised when a route or scenario violates the model contract."""


def _number(value: Any, name: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise InputError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise InputError(f"{name} must be >= {minimum}")
    return result


def _share(value: Any, name: str) -> float:
    result = _number(value, name, minimum=0.0)
    if result > 1.0:
        raise InputError(f"{name} must be <= 1.0")
    return result


def required_capacity_dwt(
    annual_cargo_tonnes: float,
    cycle_days: float,
    utilization: float,
) -> float:
    """Return DWT-equivalent capacity continuously required by a route.

    Formula: annual cargo tonnes * round-trip cycle days /
    (365 * effective cargo utilization).
    """

    cargo = _number(annual_cargo_tonnes, "annual_cargo_tonnes", minimum=0.0)
    cycle = _number(cycle_days, "cycle_days", minimum=0.0)
    util = _share(utilization, "utilization")
    if util == 0:
        raise InputError("utilization must be greater than zero")
    return cargo * cycle / (365.0 * util)


def route_cycle_days(route: dict[str, Any]) -> float:
    distance = _number(route["distance_nm_one_way"], "distance_nm_one_way", minimum=0.0)
    speed = _number(route["speed_knots"], "speed_knots", minimum=0.01)
    port_days = _number(route.get("port_days_round_trip", 0), "port_days_round_trip", minimum=0.0)
    return (2.0 * distance / speed / 24.0) + port_days


def route_operational_profile(route: dict[str, Any]) -> dict[str, Any]:
    """Expose normal and chokepoint-detour transit assumptions transparently.

    The route configuration already contains a normal one-way distance and a
    chokepoint-specific extra distance.  The simulator uses those inputs to
    calculate extra cycle capacity; this profile publishes the same arithmetic
    for the UI without claiming a port-by-port schedule or observed voyage time.
    """

    distance = _number(
        route["distance_nm_one_way"],
        "distance_nm_one_way",
        minimum=0.0,
    )
    speed = _number(route["speed_knots"], "speed_knots", minimum=0.01)
    port_days = _number(
        route.get("port_days_round_trip", 0),
        "port_days_round_trip",
        minimum=0.0,
    )
    baseline_sea_days_one_way = distance / speed / 24.0
    baseline_cycle = route_cycle_days(route)
    alternatives = []
    for exposure in route.get("chokepoints", []):
        reroute_available = bool(exposure.get("reroute_available", True))
        extra_nm = _number(
            exposure.get("reroute_extra_nm_one_way", 0),
            "reroute_extra_nm_one_way",
            minimum=0.0,
        )
        if not reroute_available:
            extra_nm = 0.0
        extra_days_one_way = extra_nm / speed / 24.0
        extra_cycle_days = 2.0 * extra_days_one_way
        distance_evidence = exposure.get("distance_evidence")
        alternatives.append(
            {
                "chokepoint_id": exposure["id"],
                "reroute_receiver_id": exposure.get("reroute_receiver_id"),
                "reroute_available": reroute_available,
                "baseline_distance_nm_one_way": distance,
                "reroute_extra_nm_one_way": extra_nm if reroute_available else None,
                "rerouted_distance_nm_one_way": (
                    distance + extra_nm if reroute_available else None
                ),
                "baseline_sea_days_one_way": baseline_sea_days_one_way,
                "reroute_extra_days_one_way": (
                    extra_days_one_way if reroute_available else None
                ),
                "rerouted_sea_days_one_way": (
                    baseline_sea_days_one_way + extra_days_one_way
                    if reroute_available
                    else None
                ),
                "baseline_cycle_days": baseline_cycle,
                "reroute_extra_cycle_days": (
                    extra_cycle_days if reroute_available else None
                ),
                "rerouted_cycle_days": (
                    baseline_cycle + extra_cycle_days
                    if reroute_available
                    else None
                ),
                "cycle_increase_pct": (
                    extra_cycle_days / baseline_cycle * 100.0
                    if reroute_available and baseline_cycle > 0
                    else None
                ),
                "exposure_share": _share(
                    exposure.get("exposure_share", 1.0),
                    "exposure_share",
                ),
                "input_status": (
                    distance_evidence.get("status")
                    if isinstance(distance_evidence, dict)
                    else "route_config_distance_assumption"
                ),
                "distance_evidence": distance_evidence,
                "warning": (
                    "Distance/speed model assumption; not an observed schedule, "
                    "port-call itinerary or carrier quotation."
                ),
            }
        )
    return {
        "normal": {
            "distance_nm_one_way": distance,
            "speed_knots": speed,
            "sea_days_one_way": baseline_sea_days_one_way,
            "port_days_round_trip": port_days,
            "cycle_days_round_trip": baseline_cycle,
        },
        "chokepoint_alternatives": alternatives,
        "method": "configured nautical miles divided by service speed",
        "input_status": "route_config_distance_assumption",
        "warning": (
            "Transit times are route-level assumptions and exclude named intermediate "
            "port-call schedules unless explicitly represented in port_days_round_trip."
        ),
    }


def _route_flow_profile(route: dict[str, Any]) -> dict[str, Any]:
    """Return the capacity-driving flow without double-counting a two-way service.

    Container ships carry both headhaul and backhaul cargo during one round trip.
    The same vessel capacity therefore serves both directions; required capacity
    is driven by the larger cargo-to-utilization ratio, not the sum of two
    independently calculated fleets.  Dry-bulk and tanker routes without a
    ``directions`` list retain the original one-way-cargo/ballast-return model.
    """

    directional_rows = []
    for direction in route.get("directions", []):
        raw_cargo = direction.get("annual_cargo_tonnes")
        if raw_cargo is None:
            continue
        cargo = _number(raw_cargo, "directions.annual_cargo_tonnes", minimum=0.0)
        utilization = _share(
            direction.get("utilization", route["utilization"]),
            "directions.utilization",
        )
        if utilization == 0:
            raise InputError("direction utilization must be greater than zero")
        directional_rows.append(
            {
                "id": direction.get("id"),
                "annual_cargo_tonnes": cargo,
                "utilization": utilization,
                "capacity_equivalent_tonnes": cargo / utilization,
            }
        )

    if not directional_rows:
        cargo = _number(route["annual_cargo_tonnes"], "annual_cargo_tonnes", minimum=0.0)
        utilization = _share(route["utilization"], "utilization")
        if utilization == 0:
            raise InputError("utilization must be greater than zero")
        directional_rows.append(
            {
                "id": None,
                "annual_cargo_tonnes": cargo,
                "utilization": utilization,
                "capacity_equivalent_tonnes": cargo / utilization,
            }
        )

    driver = max(directional_rows, key=lambda row: row["capacity_equivalent_tonnes"])
    return {
        "known_direction_count": len(directional_rows),
        "total_annual_cargo_tonnes": sum(row["annual_cargo_tonnes"] for row in directional_rows),
        "capacity_driver_direction_id": driver["id"],
        "capacity_driver_annual_tonnes": driver["annual_cargo_tonnes"],
        "capacity_driver_utilization": driver["utilization"],
        "capacity_equivalent_tonnes": driver["capacity_equivalent_tonnes"],
    }


def _find_exposure(route: dict[str, Any], chokepoint_id: str) -> dict[str, Any] | None:
    for exposure in route.get("chokepoints", []):
        if exposure.get("id") == chokepoint_id:
            return exposure
    return None


def _response_shares(
    exposure: dict[str, Any],
    scenario: dict[str, Any],
) -> tuple[float, float, float]:
    response = scenario.get("response_override") or exposure.get("response", {})
    reroute = _share(response.get("reroute", 0), "response.reroute")
    wait = _share(response.get("wait", 0), "response.wait")
    cancel = _share(response.get("cancel", 0), "response.cancel")
    adjustment = scenario.get("response_adjustment", {})
    reroute *= _number(
        adjustment.get("reroute_multiplier", 1.0),
        "response_adjustment.reroute_multiplier",
        minimum=0.0,
    )
    wait *= _number(
        adjustment.get("wait_multiplier", 1.0),
        "response_adjustment.wait_multiplier",
        minimum=0.0,
    )
    cancel *= _number(
        adjustment.get("cancel_multiplier", 1.0),
        "response_adjustment.cancel_multiplier",
        minimum=0.0,
    )
    if not exposure.get("reroute_available", True):
        reroute = 0.0
    total = reroute + wait + cancel
    if total <= 0:
        raise InputError("adjusted reroute + wait + cancel response shares must be positive")
    return reroute / total, wait / total, cancel / total


def _scenario_throughput(scenario: dict[str, Any]) -> tuple[float, float]:
    """Return (effective blockage, residual throughput) for a scenario.

    ``closure_fraction`` remains supported for the existing UI contract, while
    ``residual_throughput_rate`` makes the operational meaning explicit.  They
    are complements: an 80% scenario blockage means 20% of baseline route flow
    remains, not that the waterway is necessarily physically sealed.
    """

    closure = _share(scenario["closure_fraction"], "closure_fraction")
    residual_raw = scenario.get("residual_throughput_rate")
    residual = 1.0 - closure if residual_raw is None else _share(
        residual_raw,
        "residual_throughput_rate",
    )
    if not math.isclose(closure + residual, 1.0, abs_tol=1e-9):
        raise InputError("closure_fraction + residual_throughput_rate must equal 1.0")
    return closure, residual


def _simulate_daily_cargo_flow(
    *,
    annual_cargo_tonnes: float,
    exposure_share: float,
    closure_fraction: float,
    duration_days: float,
    horizon_days: float,
    reroute_response: float,
    wait_response: float,
    cancel_response: float,
    reroute_extra_arrival_days: float,
    waiting_days: float,
) -> dict[str, Any]:
    """Track scheduled cargo through direct, rerouted, waiting and cancelled states."""

    daily_cargo = annual_cargo_tonnes / 365.0
    total_scheduled = daily_cargo * horizon_days
    expected_waiting = (
        daily_cargo
        * min(duration_days, horizon_days)
        * exposure_share
        * closure_fraction
        * wait_response
    )
    if waiting_days == 0:
        daily_clearance_capacity = expected_waiting
    else:
        daily_clearance_capacity = expected_waiting / waiting_days

    waiting_queue = 0.0
    rerouted_in_transit = 0.0
    rerouted_departed = 0.0
    rerouted_arrived = 0.0
    waiting_added_total = 0.0
    waiting_cleared_total = 0.0
    cancelled_total = 0.0
    served_total = 0.0
    peak_backlog = 0.0
    peak_backlog_day = None
    arrival_schedule: dict[int, float] = defaultdict(float)
    timeline = []

    for day in range(1, math.ceil(horizon_days) + 1):
        day_fraction = max(0.0, min(1.0, horizon_days - (day - 1)))
        active_fraction = max(0.0, min(day_fraction, duration_days - (day - 1)))
        scheduled_today = daily_cargo * day_fraction
        rerouted_arrival_today = arrival_schedule.pop(day, 0.0)
        rerouted_in_transit = max(0.0, rerouted_in_transit - rerouted_arrival_today)

        affected_today = daily_cargo * active_fraction * exposure_share * closure_fraction
        rerouted_today = affected_today * reroute_response
        waiting_today = affected_today * wait_response
        cancelled_today = affected_today * cancel_response
        direct_served_today = scheduled_today - affected_today

        rerouted_departed += rerouted_today
        waiting_added_total += waiting_today
        cancelled_total += cancelled_today
        waiting_queue += waiting_today

        if rerouted_today > 0:
            delay_days = max(0, math.ceil(reroute_extra_arrival_days))
            if delay_days == 0:
                rerouted_arrival_today += rerouted_today
            else:
                arrival_schedule[day + delay_days] += rerouted_today
                rerouted_in_transit += rerouted_today

        non_event_fraction = max(0.0, day_fraction - active_fraction)
        waiting_cleared_today = min(
            waiting_queue,
            daily_clearance_capacity * non_event_fraction,
        )
        waiting_queue -= waiting_cleared_today
        waiting_cleared_total += waiting_cleared_today
        rerouted_arrived += rerouted_arrival_today
        served_today = direct_served_today + rerouted_arrival_today + waiting_cleared_today
        served_total += served_today

        if waiting_queue > peak_backlog:
            peak_backlog = waiting_queue
            peak_backlog_day = day
        timeline.append(
            {
                "day": day,
                "event_active_fraction": active_fraction,
                "scheduled_cargo_tonnes": scheduled_today,
                "direct_served_tonnes": direct_served_today,
                "rerouted_departed_tonnes": rerouted_today,
                "rerouted_arrived_tonnes": rerouted_arrival_today,
                "waiting_added_tonnes": waiting_today,
                "waiting_cleared_tonnes": waiting_cleared_today,
                "cancelled_tonnes": cancelled_today,
                "end_waiting_backlog_tonnes": waiting_queue,
                "end_rerouted_in_transit_tonnes": rerouted_in_transit,
                "served_tonnes": served_today,
            }
        )

    conservation = served_total + waiting_queue + rerouted_in_transit + cancelled_total
    return {
        "timeline": timeline,
        "scheduled_cargo_tonnes": total_scheduled,
        "served_cargo_tonnes": served_total,
        "waiting_added_tonnes": waiting_added_total,
        "waiting_cleared_tonnes": waiting_cleared_total,
        "waiting_backlog_tonnes": waiting_queue,
        "peak_waiting_backlog_tonnes": peak_backlog,
        "peak_waiting_backlog_day": peak_backlog_day,
        "rerouted_departed_tonnes": rerouted_departed,
        "rerouted_arrived_tonnes": rerouted_arrived,
        "rerouted_in_transit_tonnes": rerouted_in_transit,
        "cancelled_tonnes": cancelled_total,
        "daily_clearance_capacity_tonnes": daily_clearance_capacity,
        "accounting_residual_tonnes": total_scheduled - conservation,
    }


def simulate_route(
    route: dict[str, Any],
    scenario: dict[str, Any] | None,
    fleet_dwt: float,
) -> dict[str, Any]:
    """Simulate one route under one chokepoint scenario.

    ``duration_days / horizon_days`` limits the share of sailings exposed to a
    finite event.  Flow, cargo backlog and commercially available DWT are kept
    separate: waiting cargo is not counted as delivered inside the horizon, and
    trapped or uninsured tonnage remains in the physical fleet while being
    unavailable to the commercial market.
    """

    flow_profile = _route_flow_profile(route)
    reserve_margin = _share(route.get("reserve_margin", 0.0), "reserve_margin")
    global_fleet = _number(fleet_dwt, "fleet_dwt", minimum=0.01)
    base_cycle = route_cycle_days(route)
    baseline_required = flow_profile["capacity_equivalent_tonnes"] * base_cycle / 365.0
    allocated_capacity = baseline_required * (1.0 + reserve_margin)
    reference_size = route.get("reference_size", {})
    reference_vessel_dwt = None
    if reference_size.get("dwt_min") is not None and reference_size.get("dwt_max") is not None:
        reference_vessel_dwt = (
            _number(reference_size["dwt_min"], "reference_size.dwt_min", minimum=0.01)
            + _number(reference_size["dwt_max"], "reference_size.dwt_max", minimum=0.01)
        ) / 2.0

    result: dict[str, Any] = {
        "route_id": route["id"],
        "scenario_id": scenario["id"] if scenario else "normal",
        "ship_type": route["ship_type"],
        "known_direction_count": flow_profile["known_direction_count"],
        "total_annual_cargo_tonnes": flow_profile["total_annual_cargo_tonnes"],
        "capacity_driver_direction_id": flow_profile["capacity_driver_direction_id"],
        "capacity_driver_annual_tonnes": flow_profile["capacity_driver_annual_tonnes"],
        "capacity_driver_utilization": flow_profile["capacity_driver_utilization"],
        "baseline_cycle_days": base_cycle,
        "baseline_required_dwt": baseline_required,
        "allocated_dwt_with_reserve": allocated_capacity,
        "global_type_fleet_dwt": global_fleet,
        "route_share_of_type_fleet_pct": baseline_required / global_fleet * 100.0,
        "event_type": "normal",
        "effective_blockage_fraction": 0.0,
        "residual_throughput_rate": 1.0,
        "affected_flow_share": 0.0,
        "rerouted_flow_share": 0.0,
        "rerouted_in_transit_flow_share": 0.0,
        "waiting_flow_share": 0.0,
        "cleared_waiting_flow_share": 0.0,
        "backlog_flow_share": 0.0,
        "cancelled_flow_share": 0.0,
        "reroute_extra_cycle_days": 0.0,
        "reroute_extra_arrival_days": 0.0,
        "trapped_loaded_dwt": 0.0,
        "reference_vessel_dwt_mid": reference_vessel_dwt,
        "trapped_vessel_equivalent": 0.0 if reference_vessel_dwt else None,
        "insurance_excluded_dwt": 0.0,
        "commercially_unavailable_dwt": 0.0,
        "commercially_available_dwt": allocated_capacity,
        "continuity_required_dwt": baseline_required,
        "commercial_capacity_gap_dwt": 0.0,
        "disrupted_required_dwt": baseline_required,
        "operational_capacity_absorbed_dwt": 0.0,
        "operational_capacity_absorbed_pct_of_route_allocated": 0.0,
        "commercially_unavailable_pct_of_route_allocated": 0.0,
        "net_required_capacity_change_dwt": 0.0,
        "capacity_gap_dwt": 0.0,
        "global_type_fleet_absorption_pct": 0.0,
        "deliverable_flow_index": 1.0,
        "served_flow_index": 1.0,
        "traffic_change_pct": 0.0,
        "served_cargo_tonnes_horizon": 0.0,
        "backlog_cargo_tonnes_horizon": 0.0,
        "lost_cargo_tonnes_horizon": 0.0,
        "rerouted_cargo_tonnes_horizon": 0.0,
        "rerouted_delivered_cargo_tonnes_horizon": 0.0,
        "rerouted_in_transit_cargo_tonnes_horizon": 0.0,
        "waiting_cargo_tonnes_horizon": 0.0,
        "cleared_waiting_cargo_tonnes_horizon": 0.0,
        "peak_backlog_cargo_tonnes": 0.0,
        "peak_backlog_day": None,
        "daily_flow_timeline": [],
        "cargo_accounting_residual_tonnes": 0.0,
        "response_profile_id": None,
        "method": "daily-stock-flow-cycle-capacity-v3",
    }
    if scenario is None:
        return result

    chokepoint_id = str(scenario["chokepoint_id"])
    exposure = _find_exposure(route, chokepoint_id)
    if exposure is None:
        return result

    closure, residual_throughput = _scenario_throughput(scenario)
    duration = _number(scenario["duration_days"], "duration_days", minimum=0.0)
    horizon = _number(scenario.get("horizon_days", 28), "horizon_days", minimum=0.01)
    duration_factor = min(duration / horizon, 1.0)
    exposure_share = _share(exposure.get("exposure_share", 1.0), "exposure_share")
    reroute_response, wait_response, cancel_response = _response_shares(exposure, scenario)

    extra_nm = _number(exposure.get("reroute_extra_nm_one_way", 0), "reroute_extra_nm_one_way", minimum=0.0)
    speed = _number(route["speed_knots"], "speed_knots", minimum=0.01)
    extra_cycle_days = 2.0 * extra_nm / speed / 24.0
    extra_arrival_days = extra_nm / speed / 24.0
    waiting_days = _number(
        scenario.get("waiting_days", exposure.get("default_waiting_days", 0)),
        "waiting_days",
        minimum=0.0,
    )
    event_type = str(scenario.get("event_type", "operational_restriction"))
    daily_flow = _simulate_daily_cargo_flow(
        annual_cargo_tonnes=flow_profile["total_annual_cargo_tonnes"],
        exposure_share=exposure_share,
        closure_fraction=closure,
        duration_days=duration,
        horizon_days=horizon,
        reroute_response=reroute_response,
        wait_response=wait_response,
        cancel_response=cancel_response,
        reroute_extra_arrival_days=extra_arrival_days,
        waiting_days=waiting_days,
    )
    horizon_cargo = daily_flow["scheduled_cargo_tonnes"]
    denominator = horizon_cargo if horizon_cargo else 1.0
    rerouted = daily_flow["rerouted_departed_tonnes"] / denominator
    waiting = daily_flow["waiting_added_tonnes"] / denominator
    cleared_waiting = daily_flow["waiting_cleared_tonnes"] / denominator
    backlog = daily_flow["waiting_backlog_tonnes"] / denominator
    cancelled = daily_flow["cancelled_tonnes"] / denominator
    rerouted_in_transit = daily_flow["rerouted_in_transit_tonnes"] / denominator
    affected = rerouted + waiting + cancelled
    served_flow_index = (
        daily_flow["served_cargo_tonnes"] / denominator if horizon_cargo else 1.0
    )
    served_tonnes = daily_flow["served_cargo_tonnes"]
    backlog_tonnes = daily_flow["waiting_backlog_tonnes"]
    lost_tonnes = daily_flow["cancelled_tonnes"]

    reroute_capacity = flow_profile["capacity_equivalent_tonnes"] / 365.0 * (
        rerouted * extra_cycle_days
    )
    onboard_waiting_share = _share(
        scenario.get("onboard_waiting_share", exposure.get("onboard_waiting_share", 1.0)),
        "onboard_waiting_share",
    )
    trapped_days = _number(
        scenario.get("trapped_days", min(waiting_days, horizon)),
        "trapped_days",
        minimum=0.0,
    )
    trapped_days = min(trapped_days, horizon)
    trapped_loaded_dwt = flow_profile["capacity_equivalent_tonnes"] / 365.0 * (
        waiting * onboard_waiting_share * trapped_days
    )
    trapped_vessel_equivalent = (
        trapped_loaded_dwt / reference_vessel_dwt if reference_vessel_dwt else None
    )

    insurance_unavailable_share = _share(
        scenario.get("insurance_unavailable_share", 0.0),
        "insurance_unavailable_share",
    )
    insurance_eligible_pool = max(0.0, allocated_capacity - trapped_loaded_dwt)
    insurance_excluded_dwt = (
        insurance_eligible_pool
        * exposure_share
        * duration_factor
        * insurance_unavailable_share
    )
    commercially_unavailable = min(
        allocated_capacity,
        trapped_loaded_dwt + insurance_excluded_dwt,
    )
    commercially_available = max(0.0, allocated_capacity - commercially_unavailable)

    # Capacity needed to preserve baseline service.  Trapped and uninsured DWT
    # are already removed from commercially_available and must not be counted
    # twice on the required side of the comparison.
    continuity_required = baseline_required + reroute_capacity
    commercial_capacity_gap = max(0.0, continuity_required - commercially_available)
    operational_absorbed = reroute_capacity + commercially_unavailable

    result.update(
        {
            "event_type": event_type,
            "effective_blockage_fraction": closure,
            "residual_throughput_rate": residual_throughput,
            "affected_flow_share": affected,
            "rerouted_flow_share": rerouted,
            "rerouted_in_transit_flow_share": rerouted_in_transit,
            "waiting_flow_share": waiting,
            "cleared_waiting_flow_share": cleared_waiting,
            "backlog_flow_share": backlog,
            "cancelled_flow_share": cancelled,
            "reroute_extra_cycle_days": extra_cycle_days,
            "reroute_extra_arrival_days": extra_arrival_days,
            "trapped_loaded_dwt": trapped_loaded_dwt,
            "trapped_vessel_equivalent": trapped_vessel_equivalent,
            "insurance_excluded_dwt": insurance_excluded_dwt,
            "commercially_unavailable_dwt": commercially_unavailable,
            "commercially_available_dwt": commercially_available,
            "continuity_required_dwt": continuity_required,
            "commercial_capacity_gap_dwt": commercial_capacity_gap,
            # Backward-compatible aliases consumed by the current UI.
            "disrupted_required_dwt": continuity_required,
            "operational_capacity_absorbed_dwt": operational_absorbed,
            "operational_capacity_absorbed_pct_of_route_allocated": (
                operational_absorbed / allocated_capacity * 100.0
                if allocated_capacity > 0
                else 0.0
            ),
            "commercially_unavailable_pct_of_route_allocated": (
                commercially_unavailable / allocated_capacity * 100.0
                if allocated_capacity > 0
                else 0.0
            ),
            "net_required_capacity_change_dwt": continuity_required - baseline_required,
            "capacity_gap_dwt": commercial_capacity_gap,
            "global_type_fleet_absorption_pct": operational_absorbed / global_fleet * 100.0,
            "deliverable_flow_index": served_flow_index,
            "served_flow_index": served_flow_index,
            "traffic_change_pct": (served_flow_index - 1.0) * 100.0,
            "served_cargo_tonnes_horizon": served_tonnes,
            "backlog_cargo_tonnes_horizon": backlog_tonnes,
            "lost_cargo_tonnes_horizon": lost_tonnes,
            "rerouted_cargo_tonnes_horizon": daily_flow["rerouted_departed_tonnes"],
            "rerouted_delivered_cargo_tonnes_horizon": daily_flow[
                "rerouted_arrived_tonnes"
            ],
            "rerouted_in_transit_cargo_tonnes_horizon": daily_flow[
                "rerouted_in_transit_tonnes"
            ],
            "waiting_cargo_tonnes_horizon": daily_flow["waiting_added_tonnes"],
            "cleared_waiting_cargo_tonnes_horizon": daily_flow[
                "waiting_cleared_tonnes"
            ],
            "peak_backlog_cargo_tonnes": daily_flow["peak_waiting_backlog_tonnes"],
            "peak_backlog_day": daily_flow["peak_waiting_backlog_day"],
            "daily_flow_timeline": daily_flow["timeline"],
            "cargo_accounting_residual_tonnes": daily_flow[
                "accounting_residual_tonnes"
            ],
            "response_profile_id": scenario.get("response_profile_id"),
        }
    )
    return result


def _percentile(values: Iterable[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise InputError("cannot compute percentile of an empty series")
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def estimate_interval(
    route: dict[str, Any],
    scenario: dict[str, Any] | None,
    fleet_dwt: float,
    *,
    samples: int = 400,
) -> dict[str, dict[str, float]]:
    """Monte Carlo P10/P50/P90 range using explicit input bounds.

    This is parameter uncertainty, not a probabilistic forecast of geopolitical
    events.  The seed is stable for identical route/scenario identifiers.
    """

    if samples < 20:
        raise InputError("samples must be at least 20")
    uncertainty = route.get("uncertainty", {})
    cargo_mode = _number(route["annual_cargo_tonnes"], "annual_cargo_tonnes", minimum=0.0)
    cargo_low = _number(uncertainty.get("annual_cargo_tonnes_low", cargo_mode), "cargo_low", minimum=0.0)
    cargo_high = _number(uncertainty.get("annual_cargo_tonnes_high", cargo_mode), "cargo_high", minimum=0.0)
    util_mode = _share(route["utilization"], "utilization")
    util_low = _share(uncertainty.get("utilization_low", util_mode), "utilization_low")
    util_high = _share(uncertainty.get("utilization_high", util_mode), "utilization_high")
    speed_mode = _number(route["speed_knots"], "speed_knots", minimum=0.01)
    speed_low = _number(uncertainty.get("speed_knots_low", speed_mode), "speed_knots_low", minimum=0.01)
    speed_high = _number(uncertainty.get("speed_knots_high", speed_mode), "speed_knots_high", minimum=0.01)
    if not (cargo_low <= cargo_mode <= cargo_high):
        raise InputError("cargo uncertainty must satisfy low <= mode <= high")
    if not (0 < util_low <= util_mode <= util_high <= 1):
        raise InputError("utilization uncertainty must satisfy 0 < low <= mode <= high <= 1")
    if not (0 < speed_low <= speed_mode <= speed_high):
        raise InputError("speed uncertainty must satisfy 0 < low <= mode <= high")

    seed_text = f"{route.get('id')}|{scenario.get('id') if scenario else 'normal'}|v1"
    seed = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:16], 16)
    rng = random.Random(seed)
    metrics = {
        "baseline_required_dwt": [],
        "disrupted_required_dwt": [],
        "operational_capacity_absorbed_dwt": [],
        "capacity_gap_dwt": [],
        "deliverable_flow_index": [],
        "backlog_cargo_tonnes_horizon": [],
        "trapped_loaded_dwt": [],
        "commercially_available_dwt": [],
    }
    for _ in range(samples):
        sampled = copy.deepcopy(route)
        sampled_cargo = rng.triangular(cargo_low, cargo_high, cargo_mode)
        sampled_utilization = rng.triangular(util_low, util_high, util_mode)
        sampled["annual_cargo_tonnes"] = sampled_cargo
        sampled["utilization"] = sampled_utilization
        if sampled.get("directions"):
            cargo_scale = sampled_cargo / cargo_mode if cargo_mode else 1.0
            utilization_scale = sampled_utilization / util_mode
            for direction in sampled["directions"]:
                if direction.get("annual_cargo_tonnes") is not None:
                    direction["annual_cargo_tonnes"] *= cargo_scale
                if direction.get("utilization") is not None:
                    direction["utilization"] = min(
                        1.0,
                        max(0.01, direction["utilization"] * utilization_scale),
                    )
        sampled["speed_knots"] = rng.triangular(speed_low, speed_high, speed_mode)
        trial = simulate_route(sampled, scenario, fleet_dwt)
        for metric in metrics:
            metrics[metric].append(float(trial[metric]))
    intervals: dict[str, dict[str, float]] = {}
    for metric, values in metrics.items():
        p10 = _percentile(values, 0.10)
        p50 = max(p10, _percentile(values, 0.50))
        p90 = max(p50, _percentile(values, 0.90))
        intervals[metric] = {"p10": p10, "p50": p50, "p90": p90}
    return intervals
