"""Temporary-value validation grid for the deterministic shipping simulator."""

from __future__ import annotations

import math
from typing import Any, Iterable

from shipping_capacity.engine import simulate_route
from shipping_capacity.environment import simulate_environment_route


TEMPORARY_CLOSURE_FRACTIONS = (0.0, 0.25, 0.50, 0.80, 1.0)
TEMPORARY_DURATIONS = (0, 7, 14, 28)
TEMPORARY_INSURANCE_SHARES = (0.0, 0.50, 1.0)
TEMPORARY_SPEED_RESPONSE_SHARES = (0.0, 0.50, 1.0)
TEMPORARY_SPEED_REDUCTIONS = (0.0, 0.10, 0.20)
TEMPORARY_RETROFIT_OFFHIRE_SHARES = (0.0, 0.05, 0.10)


def _nondecreasing(values: Iterable[float], *, tolerance: float = 1e-8) -> bool:
    rows = list(values)
    return all(after + tolerance >= before for before, after in zip(rows, rows[1:]))


def _nonincreasing(values: Iterable[float], *, tolerance: float = 1e-8) -> bool:
    rows = list(values)
    return all(after <= before + tolerance for before, after in zip(rows, rows[1:]))


def _temporary_scenario(
    chokepoint_id: str,
    *,
    closure: float,
    duration: int,
    insurance_share: float,
    trapped_days: int = 14,
) -> dict[str, Any]:
    return {
        "id": "temporary_validation_only",
        "chokepoint_id": chokepoint_id,
        "event_type": "temporary_validation_only",
        "closure_fraction": closure,
        "residual_throughput_rate": 1.0 - closure,
        "duration_days": duration,
        "horizon_days": 28,
        "waiting_days": 14,
        "onboard_waiting_share": 0.60,
        "trapped_days": trapped_days,
        "insurance_unavailable_share": insurance_share,
    }


def _case_failures(result: dict[str, Any]) -> list[str]:
    failures = []
    checks = {
        "blockage_plus_residual_equals_one": math.isclose(
            result["effective_blockage_fraction"] + result["residual_throughput_rate"],
            1.0,
            abs_tol=1e-8,
        ),
        "response_partition_equals_affected": math.isclose(
            result["rerouted_flow_share"]
            + result["waiting_flow_share"]
            + result["cancelled_flow_share"],
            result["affected_flow_share"],
            abs_tol=1e-8,
        ),
        "waiting_partition_is_conserved": math.isclose(
            result["cleared_waiting_flow_share"] + result["backlog_flow_share"],
            result["waiting_flow_share"],
            abs_tol=1e-8,
        ),
        "served_backlog_in_transit_cancelled_equals_one": math.isclose(
            result["served_flow_index"]
            + result["backlog_flow_share"]
            + result["rerouted_in_transit_flow_share"]
            + result["cancelled_flow_share"],
            1.0,
            abs_tol=1e-8,
        ),
        "cargo_tonnes_are_conserved": math.isclose(
            result["served_cargo_tonnes_horizon"]
            + result["backlog_cargo_tonnes_horizon"]
            + result["rerouted_in_transit_cargo_tonnes_horizon"]
            + result["lost_cargo_tonnes_horizon"],
            result["total_annual_cargo_tonnes"] / 365.0 * 28.0,
            rel_tol=1e-9,
            abs_tol=1e-5,
        ),
        "commercial_dwt_is_conserved": math.isclose(
            result["commercially_available_dwt"]
            + result["commercially_unavailable_dwt"],
            result["allocated_dwt_with_reserve"],
            rel_tol=1e-9,
            abs_tol=1e-5,
        ),
        "capacity_gap_identity": math.isclose(
            result["commercial_capacity_gap_dwt"],
            max(
                0.0,
                result["continuity_required_dwt"]
                - result["commercially_available_dwt"],
            ),
            rel_tol=1e-9,
            abs_tol=1e-5,
        ),
    }
    nonnegative_fields = (
        "affected_flow_share",
        "rerouted_flow_share",
        "rerouted_in_transit_flow_share",
        "waiting_flow_share",
        "backlog_flow_share",
        "cancelled_flow_share",
        "trapped_loaded_dwt",
        "insurance_excluded_dwt",
        "commercially_available_dwt",
        "commercially_unavailable_dwt",
        "commercial_capacity_gap_dwt",
    )
    checks["all_state_values_are_nonnegative"] = all(
        result[field] >= -1e-8 for field in nonnegative_fields
    )
    return [name for name, passed in checks.items() if not passed]


def run_temporary_scenario_grid(
    routes: list[dict[str, Any]],
    fleet_by_type: dict[str, float],
) -> dict[str, Any]:
    """Run temporary boundary/stress values without adding them to public presets."""

    failures: list[dict[str, Any]] = []
    monotonic_failures: list[dict[str, Any]] = []
    case_count = 0
    exposure_count = 0
    representative_cases: dict[str, dict[str, Any]] = {}

    for route in routes:
        for exposure in route.get("chokepoints", []):
            exposure_count += 1
            chokepoint_id = exposure["id"]
            fleet_dwt = fleet_by_type[route["ship_type"]]
            for closure in TEMPORARY_CLOSURE_FRACTIONS:
                for duration in TEMPORARY_DURATIONS:
                    for insurance_share in TEMPORARY_INSURANCE_SHARES:
                        scenario = _temporary_scenario(
                            chokepoint_id,
                            closure=closure,
                            duration=duration,
                            insurance_share=insurance_share,
                        )
                        result = simulate_route(route, scenario, fleet_dwt)
                        case_count += 1
                        for failed_check in _case_failures(result):
                            failures.append(
                                {
                                    "route_id": route["id"],
                                    "chokepoint_id": chokepoint_id,
                                    "closure_fraction": closure,
                                    "duration_days": duration,
                                    "insurance_unavailable_share": insurance_share,
                                    "check": failed_check,
                                }
                            )
                        if closure == 0.80 and duration == 28 and insurance_share == 0.50:
                            representative_cases.setdefault(
                                route["ship_type"],
                                {
                                    "route_id": route["id"],
                                    "chokepoint_id": chokepoint_id,
                                    "temporary_inputs": scenario,
                                    "served_flow_index": result["served_flow_index"],
                                    "backlog_cargo_tonnes_horizon": result[
                                        "backlog_cargo_tonnes_horizon"
                                    ],
                                    "trapped_loaded_dwt": result["trapped_loaded_dwt"],
                                    "insurance_excluded_dwt": result[
                                        "insurance_excluded_dwt"
                                    ],
                                    "commercially_available_dwt": result[
                                        "commercially_available_dwt"
                                    ],
                                    "commercial_capacity_gap_dwt": result[
                                        "commercial_capacity_gap_dwt"
                                    ],
                                },
                            )

            def simulate_sweep(**changes: Any) -> dict[str, Any]:
                scenario = _temporary_scenario(
                    chokepoint_id,
                    closure=changes.get("closure", 0.80),
                    duration=changes.get("duration", 28),
                    insurance_share=changes.get("insurance_share", 0.50),
                    trapped_days=changes.get("trapped_days", 14),
                )
                return simulate_route(route, scenario, fleet_dwt)

            closure_rows = [
                simulate_sweep(closure=value, insurance_share=0.0)
                for value in TEMPORARY_CLOSURE_FRACTIONS
            ]
            duration_rows = [simulate_sweep(duration=value) for value in TEMPORARY_DURATIONS]
            insurance_rows = [
                simulate_sweep(insurance_share=value)
                for value in TEMPORARY_INSURANCE_SHARES
            ]
            trapped_rows = [
                simulate_sweep(trapped_days=value) for value in TEMPORARY_DURATIONS
            ]
            monotonic_checks = {
                "closure_increases_affected_flow": _nondecreasing(
                    row["affected_flow_share"] for row in closure_rows
                ),
                "closure_does_not_reduce_backlog": _nondecreasing(
                    row["backlog_flow_share"] for row in closure_rows
                ),
                "closure_does_not_reduce_cancellation": _nondecreasing(
                    row["cancelled_flow_share"] for row in closure_rows
                ),
                "duration_increases_affected_flow": _nondecreasing(
                    row["affected_flow_share"] for row in duration_rows
                ),
                "duration_does_not_increase_available_dwt": _nonincreasing(
                    row["commercially_available_dwt"] for row in duration_rows
                ),
                "insurance_reduces_available_dwt": _nonincreasing(
                    row["commercially_available_dwt"] for row in insurance_rows
                ),
                "trapped_days_increase_trapped_dwt": _nondecreasing(
                    row["trapped_loaded_dwt"] for row in trapped_rows
                ),
            }
            monotonic_failures.extend(
                {
                    "route_id": route["id"],
                    "chokepoint_id": chokepoint_id,
                    "check": name,
                }
                for name, passed in monotonic_checks.items()
                if not passed
            )

    return {
        "status": "passed" if not failures and not monotonic_failures else "failed",
        "scope": "temporary validation values only; never published as observed data or scenario presets",
        "temporary_grid": {
            "closure_fractions": list(TEMPORARY_CLOSURE_FRACTIONS),
            "duration_days": list(TEMPORARY_DURATIONS),
            "insurance_unavailable_shares": list(TEMPORARY_INSURANCE_SHARES),
            "waiting_days": 14,
            "onboard_waiting_share": 0.60,
            "trapped_days": 14,
        },
        "route_count": len(routes),
        "exposure_count": exposure_count,
        "case_count": case_count,
        "accounting_failure_count": len(failures),
        "monotonic_failure_count": len(monotonic_failures),
        "accounting_failures": failures,
        "monotonic_failures": monotonic_failures,
        "representative_cases": representative_cases,
    }


def run_temporary_environment_grid(
    routes: list[dict[str, Any]],
    fleet_by_type: dict[str, float],
) -> dict[str, Any]:
    """Stress the effective-DWT simulator with temporary response values."""

    failures: list[dict[str, Any]] = []
    monotonic_failures: list[dict[str, Any]] = []
    representative_cases: dict[str, dict[str, Any]] = {}
    case_count = 0

    for route in routes:
        baseline = simulate_route(route, None, fleet_by_type[route["ship_type"]])
        environment_route = dict(route)
        environment_route["_baseline_required_dwt"] = baseline["baseline_required_dwt"]
        environment_route["_allocated_dwt_with_reserve"] = baseline[
            "allocated_dwt_with_reserve"
        ]

        def simulate(
            speed_response_share: float,
            speed_reduction_fraction: float,
            retrofit_offhire_share: float,
        ) -> dict[str, Any]:
            scenario = {
                "id": "temporary_environment_validation_only",
                "year": 2030,
                "ship_type_assumptions": {
                    route["ship_type"]: {
                        "speed_response_share": speed_response_share,
                        "speed_reduction_fraction": speed_reduction_fraction,
                        "retrofit_offhire_share": retrofit_offhire_share,
                    }
                },
            }
            return simulate_environment_route(environment_route, scenario)

        for response_share in TEMPORARY_SPEED_RESPONSE_SHARES:
            for reduction in TEMPORARY_SPEED_REDUCTIONS:
                for offhire in TEMPORARY_RETROFIT_OFFHIRE_SHARES:
                    result = simulate(response_share, reduction, offhire)
                    case_count += 1
                    checks = {
                        "physical_dwt_is_unchanged": math.isclose(
                            result["physical_allocated_dwt"],
                            baseline["allocated_dwt_with_reserve"],
                            rel_tol=1e-9,
                        ),
                        "effective_plus_loss_equals_physical": math.isclose(
                            result["effective_service_capacity_dwt"]
                            + result["effective_dwt_loss"],
                            result["physical_allocated_dwt"],
                            rel_tol=1e-9,
                            abs_tol=1e-5,
                        ),
                        "retention_matches_effective_dwt": math.isclose(
                            result["effective_capacity_retention_rate"],
                            result["effective_service_capacity_dwt"]
                            / result["physical_allocated_dwt"],
                            rel_tol=1e-9,
                        ),
                        "same_service_requirement_identity": math.isclose(
                            result["same_service_required_dwt"],
                            result["baseline_required_dwt"]
                            / result["effective_capacity_retention_rate"],
                            rel_tol=1e-9,
                        ),
                        "slowing_does_not_shorten_cycle": (
                            result["adjusted_cycle_days"] + 1e-8
                            >= result["baseline_cycle_days"]
                        ),
                        "effective_states_are_nonnegative": all(
                            result[field] >= -1e-8
                            for field in (
                                "effective_service_capacity_dwt",
                                "effective_dwt_loss",
                                "same_service_required_dwt",
                                "capacity_gap_vs_allocated_dwt",
                            )
                        ),
                    }
                    failures.extend(
                        {
                            "route_id": route["id"],
                            "speed_response_share": response_share,
                            "speed_reduction_fraction": reduction,
                            "retrofit_offhire_share": offhire,
                            "check": name,
                        }
                        for name, passed in checks.items()
                        if not passed
                    )
                    if response_share == 1.0 and reduction == 0.10 and offhire == 0.05:
                        representative_cases.setdefault(
                            route["ship_type"],
                            {
                                "route_id": route["id"],
                                "temporary_inputs": {
                                    "speed_response_share": response_share,
                                    "speed_reduction_fraction": reduction,
                                    "retrofit_offhire_share": offhire,
                                },
                                "physical_allocated_dwt": result["physical_allocated_dwt"],
                                "effective_service_capacity_dwt": result[
                                    "effective_service_capacity_dwt"
                                ],
                                "effective_dwt_loss": result["effective_dwt_loss"],
                                "effective_capacity_retention_rate": result[
                                    "effective_capacity_retention_rate"
                                ],
                                "same_service_required_dwt": result[
                                    "same_service_required_dwt"
                                ],
                            },
                        )

        response_rows = [simulate(value, 0.10, 0.05) for value in TEMPORARY_SPEED_RESPONSE_SHARES]
        reduction_rows = [simulate(1.0, value, 0.05) for value in TEMPORARY_SPEED_REDUCTIONS]
        offhire_rows = [simulate(1.0, 0.10, value) for value in TEMPORARY_RETROFIT_OFFHIRE_SHARES]
        monotonic_checks = {
            "more_speed_response_reduces_effective_capacity": _nonincreasing(
                row["effective_service_capacity_dwt"] for row in response_rows
            ),
            "more_speed_reduction_reduces_effective_capacity": _nonincreasing(
                row["effective_service_capacity_dwt"] for row in reduction_rows
            ),
            "more_offhire_reduces_effective_capacity": _nonincreasing(
                row["effective_service_capacity_dwt"] for row in offhire_rows
            ),
            "more_speed_reduction_increases_required_dwt": _nondecreasing(
                row["same_service_required_dwt"] for row in reduction_rows
            ),
        }
        monotonic_failures.extend(
            {
                "route_id": route["id"],
                "check": name,
            }
            for name, passed in monotonic_checks.items()
            if not passed
        )

    return {
        "status": "passed" if not failures and not monotonic_failures else "failed",
        "scope": "temporary environmental response values only; physical DWT remains unchanged",
        "temporary_grid": {
            "speed_response_shares": list(TEMPORARY_SPEED_RESPONSE_SHARES),
            "speed_reduction_fractions": list(TEMPORARY_SPEED_REDUCTIONS),
            "retrofit_offhire_shares": list(TEMPORARY_RETROFIT_OFFHIRE_SHARES),
        },
        "route_count": len(routes),
        "case_count": case_count,
        "accounting_failure_count": len(failures),
        "monotonic_failure_count": len(monotonic_failures),
        "accounting_failures": failures,
        "monotonic_failures": monotonic_failures,
        "representative_cases": representative_cases,
    }
