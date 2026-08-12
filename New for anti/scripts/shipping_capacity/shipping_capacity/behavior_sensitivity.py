"""Deterministic co-movement paths for unobserved disruption behavior."""

from __future__ import annotations

import copy
from typing import Any


RESPONSE_MULTIPLIER_KEYS = (
    "reroute_multiplier",
    "wait_multiplier",
    "cancel_multiplier",
)


def _factor(path: dict[str, Any], key: str) -> float:
    value = path.get(key, 1.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{key} must be a non-negative number")
    return float(value)


def _bounded_share(value: float) -> float:
    return max(0.0, min(1.0, value))


def apply_behavior_path(
    scenario: dict[str, Any],
    path: dict[str, Any],
) -> dict[str, Any]:
    """Apply one named joint sensitivity path without changing event throughput.

    The path is a deterministic stress combination, not a sampled correlation
    matrix or an empirical probability distribution. Closure and residual
    throughput remain fixed so only response behavior is being tested.
    """

    variant = copy.deepcopy(scenario)
    adjustment = copy.deepcopy(variant.get("response_adjustment", {}))
    response_factors = path.get("response_multiplier_factors", {})
    for key in RESPONSE_MULTIPLIER_KEYS:
        adjustment[key] = float(adjustment.get(key, 1.0)) * _factor(
            response_factors,
            key,
        )
    variant["response_adjustment"] = adjustment

    for key in ("waiting_days", "trapped_days"):
        if key in variant:
            variant[key] = max(0.0, float(variant[key]) * _factor(path, f"{key}_factor"))
    if "onboard_waiting_share" in variant:
        variant["onboard_waiting_share"] = _bounded_share(
            float(variant["onboard_waiting_share"])
            * _factor(path, "onboard_waiting_share_factor")
        )
    if "insurance_unavailable_share" in variant:
        variant["insurance_unavailable_share"] = _bounded_share(
            float(variant["insurance_unavailable_share"])
            * _factor(path, "insurance_unavailable_share_factor")
        )

    path_id = str(path["id"])
    variant["id"] = f"{scenario.get('id', 'scenario')}__behavior_{path_id}"
    variant["behavior_sensitivity_path_id"] = path_id
    variant["behavior_sensitivity_path_name_ko"] = path.get("name_ko", path_id)
    variant["behavior_sensitivity_status"] = "deterministic_joint_path_not_probability"
    return variant


def behavior_paths_for_scenario(
    scenario: dict[str, Any],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    event_type = str(scenario.get("event_type", "operational_restriction"))
    profile = config.get("profiles", {}).get(event_type, {})
    paths = profile.get("paths", [])
    if not isinstance(paths, list):
        raise ValueError(f"behavior paths for {event_type} must be a list")
    return [apply_behavior_path(scenario, path) for path in paths]
