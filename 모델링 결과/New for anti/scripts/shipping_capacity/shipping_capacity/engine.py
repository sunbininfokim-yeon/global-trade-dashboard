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


def _response_shares(exposure: dict[str, Any]) -> tuple[float, float, float]:
    response = exposure.get("response", {})
    reroute = _share(response.get("reroute", 0), "response.reroute")
    wait = _share(response.get("wait", 0), "response.wait")
    cancel = _share(response.get("cancel", 0), "response.cancel")
    total = reroute + wait + cancel
    if not math.isclose(total, 1.0, abs_tol=1e-9):
        raise InputError("reroute + wait + cancel response shares must equal 1.0")
    if not exposure.get("reroute_available", True) and reroute > 0:
        raise InputError("reroute share must be zero when no reroute is available")
    return reroute, wait, cancel


def simulate_route(
    route: dict[str, Any],
    scenario: dict[str, Any] | None,
    fleet_dwt: float,
) -> dict[str, Any]:
    """Simulate one route under one chokepoint scenario.

    ``duration_days / horizon_days`` limits the share of sailings exposed to a
    finite event.  A 28-day closure on a 28-day horizon is a steady-state shock;
    a seven-day closure exposes one quarter as much of the horizon's traffic.
    """

    flow_profile = _route_flow_profile(route)
    reserve_margin = _share(route.get("reserve_margin", 0.0), "reserve_margin")
    global_fleet = _number(fleet_dwt, "fleet_dwt", minimum=0.01)
    base_cycle = route_cycle_days(route)
    baseline_required = flow_profile["capacity_equivalent_tonnes"] * base_cycle / 365.0
    allocated_capacity = baseline_required * (1.0 + reserve_margin)

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
        "route_share_of_type_fleet_pct": baseline_required / global_fleet * 100.0,
        "affected_flow_share": 0.0,
        "rerouted_flow_share": 0.0,
        "waiting_flow_share": 0.0,
        "cancelled_flow_share": 0.0,
        "reroute_extra_cycle_days": 0.0,
        "disrupted_required_dwt": baseline_required,
        "operational_capacity_absorbed_dwt": 0.0,
        "net_required_capacity_change_dwt": 0.0,
        "capacity_gap_dwt": 0.0,
        "global_type_fleet_absorption_pct": 0.0,
        "deliverable_flow_index": 1.0,
        "traffic_change_pct": 0.0,
        "lost_cargo_tonnes_horizon": 0.0,
        "method": "annual-flow-cycle-capacity-v1",
    }
    if scenario is None:
        return result

    chokepoint_id = str(scenario["chokepoint_id"])
    exposure = _find_exposure(route, chokepoint_id)
    if exposure is None:
        return result

    closure = _share(scenario["closure_fraction"], "closure_fraction")
    duration = _number(scenario["duration_days"], "duration_days", minimum=0.0)
    horizon = _number(scenario.get("horizon_days", 28), "horizon_days", minimum=0.01)
    duration_factor = min(duration / horizon, 1.0)
    exposure_share = _share(exposure.get("exposure_share", 1.0), "exposure_share")
    affected = exposure_share * closure * duration_factor
    reroute_response, wait_response, cancel_response = _response_shares(exposure)
    rerouted = affected * reroute_response
    waiting = affected * wait_response
    cancelled = affected * cancel_response

    extra_nm = _number(exposure.get("reroute_extra_nm_one_way", 0), "reroute_extra_nm_one_way", minimum=0.0)
    speed = _number(route["speed_knots"], "speed_knots", minimum=0.01)
    extra_cycle_days = 2.0 * extra_nm / speed / 24.0
    waiting_days = _number(
        scenario.get("waiting_days", exposure.get("default_waiting_days", 0)),
        "waiting_days",
        minimum=0.0,
    )

    # Capacity tied up by cargo that still sails, plus weighted rerouting/wait.
    retained_base_capacity = baseline_required * (1.0 - cancelled)
    delay_capacity = flow_profile["capacity_equivalent_tonnes"] / 365.0 * (
        rerouted * extra_cycle_days + waiting * waiting_days
    )
    disrupted_required = retained_base_capacity + delay_capacity
    capacity_gap = max(0.0, disrupted_required - allocated_capacity)
    operational_absorbed = max(0.0, delay_capacity)
    capacity_coverage = min(1.0, allocated_capacity / disrupted_required) if disrupted_required else 1.0
    deliverable_index = (1.0 - cancelled) * capacity_coverage
    lost_tonnes = flow_profile["total_annual_cargo_tonnes"] / 365.0 * horizon * cancelled

    result.update(
        {
            "affected_flow_share": affected,
            "rerouted_flow_share": rerouted,
            "waiting_flow_share": waiting,
            "cancelled_flow_share": cancelled,
            "reroute_extra_cycle_days": extra_cycle_days,
            "disrupted_required_dwt": disrupted_required,
            "operational_capacity_absorbed_dwt": operational_absorbed,
            "net_required_capacity_change_dwt": disrupted_required - baseline_required,
            "capacity_gap_dwt": capacity_gap,
            "global_type_fleet_absorption_pct": operational_absorbed / global_fleet * 100.0,
            "deliverable_flow_index": deliverable_index,
            "traffic_change_pct": (deliverable_index - 1.0) * 100.0,
            "lost_cargo_tonnes_horizon": lost_tonnes,
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
    return {
        metric: {
            "p10": _percentile(values, 0.10),
            "p50": _percentile(values, 0.50),
            "p90": _percentile(values, 0.90),
        }
        for metric, values in metrics.items()
    }
