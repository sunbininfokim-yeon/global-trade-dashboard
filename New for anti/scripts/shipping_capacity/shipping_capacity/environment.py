"""Environmental-regulation response scenarios for effective route capacity."""

from __future__ import annotations

import copy
from typing import Any

from shipping_capacity.engine import InputError, route_cycle_days


def _share(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise InputError(f"{name} must be numeric") from exc
    if not 0.0 <= result <= 1.0:
        raise InputError(f"{name} must be between 0 and 1")
    return result


def _nonnegative(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise InputError(f"{name} must be numeric") from exc
    if result < 0.0:
        raise InputError(f"{name} must be nonnegative")
    return result


def expand_environment_scenarios(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand UI pathways into explicit, reproducible annual model scenarios.

    Regulatory targets and operator responses intentionally remain separate.
    The former describes an adopted or counterfactual policy path; only the
    explicitly declared response multipliers alter model assumptions.
    """

    base_scenarios = config.get("scenarios", [])
    pathways = config.get("pathways", [])
    if not pathways:
        return copy.deepcopy(base_scenarios)

    expanded: list[dict[str, Any]] = []
    for pathway in pathways:
        pathway_id = pathway["id"]
        response_multipliers = pathway.get("response_multipliers", {})
        regulatory_path = pathway.get("regulatory_path", {})
        for base in base_scenarios:
            year = int(base["year"])
            year_facts = regulatory_path.get(str(year))
            if year_facts is None:
                raise InputError(
                    f"missing regulatory_path for {pathway_id} in {year}"
                )
            scenario = copy.deepcopy(base)
            scenario.update(
                {
                    "id": f"{pathway_id}_{year}",
                    "name_ko": f"{year} {pathway['name_ko']}",
                    "pathway_id": pathway_id,
                    "pathway_name_ko": pathway["name_ko"],
                    "pathway_policy_status": pathway["policy_status"],
                    "pathway_description_ko": pathway["description_ko"],
                    "regulatory_facts": copy.deepcopy(year_facts),
                    "behavior_assumption_status": (
                        "provisional_sensitivity_seed_not_observed_operator_behavior"
                    ),
                }
            )
            scaled_by_type: dict[str, dict[str, float]] = {}
            for ship_type, assumptions in base.get(
                "ship_type_assumptions", {}
            ).items():
                scaled_by_type[ship_type] = {
                    field: min(
                        0.95,
                        _share(value, field)
                        * _nonnegative(
                            response_multipliers.get(field, 1.0),
                            f"response_multipliers.{field}",
                        ),
                    )
                    for field, value in assumptions.items()
                }
            scenario["ship_type_assumptions"] = scaled_by_type
            expanded.append(scenario)
    return expanded


def simulate_environment_route(
    route: dict[str, Any],
    scenario: dict[str, Any],
) -> dict[str, Any]:
    """Estimate service-capacity loss from an explicit speed/off-hire response.

    Regulations do not remove physical DWT.  This model translates a stated
    share of ships slowing down, plus temporary retrofit off-hire, into the DWT
    that can provide the baseline route service over the same period.
    """

    assumptions = scenario.get("ship_type_assumptions", {}).get(route["ship_type"])
    if not assumptions:
        raise InputError(f"missing environmental assumptions for {route['ship_type']}")
    speed_response_share = _share(
        assumptions.get("speed_response_share", 0.0),
        "speed_response_share",
    )
    speed_reduction = _share(
        assumptions.get("speed_reduction_fraction", 0.0),
        "speed_reduction_fraction",
    )
    retrofit_offhire = _share(
        assumptions.get("retrofit_offhire_share", 0.0),
        "retrofit_offhire_share",
    )
    retirement_share = _share(
        assumptions.get("retirement_share", 0.0),
        "retirement_share",
    )
    if speed_reduction >= 1.0:
        raise InputError("speed_reduction_fraction must be below 1")

    speed = float(route["speed_knots"])
    adjusted_speed = speed * (1.0 - speed_reduction)
    base_cycle = route_cycle_days(route)
    adjusted_route = dict(route)
    adjusted_route["speed_knots"] = adjusted_speed
    adjusted_cycle = route_cycle_days(adjusted_route)
    slowed_capacity_retention = base_cycle / adjusted_cycle
    mixed_capacity_retention = (
        (1.0 - speed_response_share)
        + speed_response_share * slowed_capacity_retention
    )
    service_capacity_retention = (
        (1.0 - retirement_share)
        * (1.0 - retrofit_offhire)
        * mixed_capacity_retention
    )

    baseline = float(route["_baseline_required_dwt"])
    allocated = float(route["_allocated_dwt_with_reserve"])
    effective_service_dwt = allocated * service_capacity_retention
    effective_dwt_loss = allocated - effective_service_dwt
    same_service_required = baseline / service_capacity_retention
    return {
        "route_id": route["id"],
        "ship_type": route["ship_type"],
        "scenario_id": scenario["id"],
        "pathway_id": scenario.get("pathway_id", "legacy"),
        "year": scenario["year"],
        "physical_allocated_dwt": allocated,
        "baseline_required_dwt": baseline,
        "baseline_speed_knots": speed,
        "adjusted_speed_knots": adjusted_speed,
        "baseline_cycle_days": base_cycle,
        "adjusted_cycle_days": adjusted_cycle,
        "speed_response_share": speed_response_share,
        "speed_reduction_fraction": speed_reduction,
        "retrofit_offhire_share": retrofit_offhire,
        "retirement_share": retirement_share,
        "retired_or_withdrawn_dwt": allocated * retirement_share,
        "effective_capacity_retention_rate": service_capacity_retention,
        "effective_service_capacity_dwt": effective_service_dwt,
        "effective_dwt_loss": effective_dwt_loss,
        "same_service_required_dwt": same_service_required,
        "additional_required_vs_baseline_dwt": same_service_required - baseline,
        "capacity_gap_vs_allocated_dwt": max(0.0, same_service_required - allocated),
        "method": "route-cycle-effective-dwt-v2",
        "warning": (
            "Allocated DWT is the pre-response reference. Slowdown and retrofit off-hire "
            "reduce service-equivalent capacity; retirement is a scenario withdrawal, not "
            "an observed demolition forecast."
        ),
    }


def _scaled_assumptions(
    assumptions: dict[str, Any],
    case: dict[str, Any],
) -> dict[str, float]:
    """Return a bounded environmental response case from transparent multipliers."""

    def scaled(name: str, multiplier_name: str) -> float:
        base = _share(assumptions.get(name, 0.0), name)
        multiplier = float(case.get(multiplier_name, 1.0))
        if multiplier < 0:
            raise InputError(f"{multiplier_name} must be nonnegative")
        return min(0.95, base * multiplier)

    return {
        "speed_response_share": scaled(
            "speed_response_share", "speed_response_multiplier"
        ),
        "speed_reduction_fraction": scaled(
            "speed_reduction_fraction", "speed_reduction_multiplier"
        ),
        "retrofit_offhire_share": scaled(
            "retrofit_offhire_share", "retrofit_offhire_multiplier"
        ),
        "retirement_share": scaled("retirement_share", "retirement_multiplier"),
    }


def simulate_environment_route_range(
    route: dict[str, Any],
    scenario: dict[str, Any],
    profile_config: dict[str, Any],
) -> dict[str, Any]:
    """Calculate a route-level effective-DWT range without inventing ship-level CII.

    Free public sources do not expose a complete vessel-by-vessel construction year,
    fuel and attained-CII panel.  The output therefore carries those availability
    limits explicitly and varies only declared response assumptions.
    """

    route_overrides = profile_config.get("route_overrides", {})
    override = route_overrides.get(route["id"], {})
    defaults = profile_config.get("defaults", {})
    dimensions = {
        "ship_type": route["ship_type"],
        "vessel_size_class": route.get("vessel_class", "unknown"),
        "reference_size": route.get("reference_size", {}),
        "build_year_band": override.get(
            "build_year_band", defaults.get("build_year_band", "not_observed")
        ),
        "fuel_profile": override.get(
            "fuel_profile", defaults.get("fuel_profile", "not_observed")
        ),
        "eu_route_exposure_share": _share(
            override.get(
                "eu_route_exposure_share",
                defaults.get("eu_route_exposure_share", 0.0),
            ),
            "eu_route_exposure_share",
        ),
        "cii_grade_status": override.get(
            "cii_grade_status",
            defaults.get(
                "cii_grade_status", "ship_level_free_public_data_unavailable"
            ),
        ),
        "cii_d_or_e_share_range": override.get(
            "cii_d_or_e_share_range",
            defaults.get("cii_d_or_e_share_range", [0.10, 0.35]),
        ),
        "cargo_segment": route.get("cargo_segment", route["ship_type"]),
    }
    cases = profile_config.get("response_cases", [])
    if not cases:
        raise InputError("environment response_cases must not be empty")
    base_assumptions = scenario.get("ship_type_assumptions", {}).get(
        route["ship_type"]
    )
    if not base_assumptions:
        raise InputError(f"missing environmental assumptions for {route['ship_type']}")

    case_results = []
    for case in cases:
        adjusted_scenario = dict(scenario)
        adjusted_scenario["id"] = f"{scenario['id']}__{case['id']}"
        assumptions = _scaled_assumptions(base_assumptions, case)
        eu_uplift = 1.0 + dimensions["eu_route_exposure_share"] * float(
            case.get("eu_exposure_response_uplift", 0.0)
        )
        assumptions["speed_response_share"] = min(
            0.95, assumptions["speed_response_share"] * eu_uplift
        )
        assumptions["retrofit_offhire_share"] = min(
            0.95, assumptions["retrofit_offhire_share"] * eu_uplift
        )
        adjusted_scenario["ship_type_assumptions"] = {
            route["ship_type"]: assumptions
        }
        result = simulate_environment_route(route, adjusted_scenario)
        case_results.append(
            {
                "case_id": case["id"],
                "case_label_ko": case.get("label_ko", case["id"]),
                **result,
            }
        )

    central_id = profile_config.get("central_case_id", "central")
    central = next(
        (row for row in case_results if row["case_id"] == central_id),
        case_results[len(case_results) // 2],
    )
    retentions = [row["effective_capacity_retention_rate"] for row in case_results]
    effective_values = [row["effective_service_capacity_dwt"] for row in case_results]
    required_values = [row["same_service_required_dwt"] for row in case_results]
    return {
        **central,
        "scenario_id": scenario["id"],
        "regulatory_dimensions": dimensions,
        "range_status": "scenario_range_not_ship_level_forecast",
        "effective_capacity_retention_rate_range": {
            "low": min(retentions),
            "central": central["effective_capacity_retention_rate"],
            "high": max(retentions),
        },
        "effective_service_capacity_dwt_range": {
            "low": min(effective_values),
            "central": central["effective_service_capacity_dwt"],
            "high": max(effective_values),
        },
        "same_service_required_dwt_range": {
            "low": min(required_values),
            "central": central["same_service_required_dwt"],
            "high": max(required_values),
        },
        "response_cases": case_results,
    }


def aggregate_environment_scenario(
    scenario: dict[str, Any],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
        physical = sum(row["physical_allocated_dwt"] for row in rows)
        effective = sum(row["effective_service_capacity_dwt"] for row in rows)
        baseline = sum(row["baseline_required_dwt"] for row in rows)
        same_service = sum(row["same_service_required_dwt"] for row in rows)
        retention_range = {
            key: (
                sum(
                    row["physical_allocated_dwt"]
                    * row.get("effective_capacity_retention_rate_range", {}).get(
                        key, row["effective_capacity_retention_rate"]
                    )
                    for row in rows
                )
                / physical
                if physical
                else 1.0
            )
            for key in ("low", "central", "high")
        }
        required_range = {
            key: sum(
                row.get("same_service_required_dwt_range", {}).get(
                    key, row["same_service_required_dwt"]
                )
                for row in rows
            )
            for key in ("low", "central", "high")
        }
        return {
            "representative_route_count": len(rows),
            "physical_allocated_dwt": physical,
            "effective_service_capacity_dwt": effective,
            "effective_dwt_loss": physical - effective,
            "effective_capacity_retention_rate": (
                effective / physical if physical else 1.0
            ),
            "effective_capacity_retention_rate_range": retention_range,
            "baseline_required_dwt": baseline,
            "same_service_required_dwt": same_service,
            "same_service_required_dwt_range": required_range,
            "additional_required_vs_baseline_dwt": same_service - baseline,
            "capacity_gap_vs_allocated_dwt": max(0.0, same_service - physical),
        }

    aggregate = summarize(results)
    by_ship_type = []
    for ship_type in ("container", "dry_bulk", "tanker"):
        rows = [row for row in results if row["ship_type"] == ship_type]
        if rows:
            by_ship_type.append({"ship_type": ship_type, **summarize(rows)})
    return {
        "id": scenario["id"],
        "name_ko": scenario["name_ko"],
        "year": scenario["year"],
        "status": scenario["status"],
        "pathway_id": scenario.get("pathway_id", "legacy"),
        "pathway_name_ko": scenario.get("pathway_name_ko"),
        "pathway_policy_status": scenario.get("pathway_policy_status"),
        "pathway_description_ko": scenario.get("pathway_description_ko"),
        "behavior_assumption_status": scenario.get("behavior_assumption_status"),
        "regulatory_inputs": scenario["regulatory_facts"],
        "cii_reduction_vs_2019_pct": scenario["regulatory_facts"][
            "cii_reduction_vs_2019_pct"
        ],
        **aggregate,
        "ship_type_breakdown": by_ship_type,
        "scope": "active representative routes, not the full world fleet",
    }
