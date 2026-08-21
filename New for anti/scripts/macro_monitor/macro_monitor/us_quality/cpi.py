"""CPI relationship gates: context, evidence, and current relevance."""

from __future__ import annotations

from typing import Any


RELATION_TYPES = {
    "accounting",
    "measurement_link",
    "market_hypothesis",
    "common_driver",
    "external_input_required",
}


def assess_current_cpi_pathway(
    relation: dict[str, Any],
    *,
    historical_status: str | None = None,
    source_impulse_now: bool = False,
    target_response_observed: bool = False,
    external_inputs_present: bool = False,
) -> dict[str, Any]:
    """Describe current relevance without converting it into a forecast."""
    relation_type = relation.get("type")
    if relation_type not in RELATION_TYPES:
        raise ValueError(f"unknown CPI relationship type: {relation_type}")

    if relation_type in {"accounting", "measurement_link", "common_driver"}:
        state = "context_only"
        eligible = False
    elif relation_type == "external_input_required" and not external_inputs_present:
        state = "external_data_missing"
        eligible = False
    elif relation_type == "market_hypothesis" and historical_status not in {
        "historically_supported",
        "conditional",
    }:
        state = "unvalidated_hypothesis"
        eligible = False
    elif source_impulse_now and target_response_observed:
        state = "source_and_target_observed"
        eligible = True
    elif source_impulse_now:
        state = "candidate_lag_window"
        eligible = True
    else:
        state = "not_currently_active"
        eligible = True

    return {
        "relationship_id": relation.get("id"),
        "relationship_type": relation_type,
        "historical_status": historical_status or relation.get("status") or "hypothesis",
        "current_state": state,
        "display_eligible": eligible,
        "source_impulse_now": bool(source_impulse_now),
        "target_response_observed": bool(target_response_observed),
        "interpretation": "current_relevance_not_causal_finding_or_forecast",
    }
