"""Visible-surface policy for unified KFA views.

Calculation and audit output may retain unavailable results.  A rendered view
must not: it contains only computed results or a narrowly actionable
``needs_input`` model.  Financial issuers also fail closed for every
industrial cash-flow, working-capital, leverage and EV model.
"""

from __future__ import annotations

from typing import Any


VISIBLE_MODEL_STATUSES = frozenset({"computed", "partial", "needs_input"})

FINANCIAL_ALLOWED_CARDS = frozenset({
    "operating_income",
    "net_income",
    "total_assets",
    "equity",
    "roe",
    "roa",
})


def has_value(value: Any) -> bool:
    """Treat a calculated zero as present and reject empty structures."""
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value == value and value not in (float("inf"), float("-inf"))
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(has_value(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(has_value(item) for item in value)
    return False


def card_decision(
    card_id: str,
    card: dict[str, Any] | None,
    *,
    financial_entity: bool,
) -> dict[str, Any]:
    if financial_entity and card_id not in FINANCIAL_ALLOWED_CARDS:
        return {
            "visible": False,
            "status": "not_applicable",
            "reason": "not_applicable:financial_entity_industrial_card",
        }
    if not isinstance(card, dict) or not (
        has_value(card.get("value")) or has_value(card.get("trend_3y"))
    ):
        reason = (card or {}).get("reason") or "missing:computed_value"
        status = "not_applicable" if str(reason).startswith("not_applicable:") else "omitted"
        return {"visible": False, "status": status, "reason": reason}
    return {"visible": True, "status": "computed", "reason": None}


def model_decision(
    model_id: str,
    model: dict[str, Any] | None,
    *,
    financial_entity: bool,
) -> dict[str, Any]:
    if financial_entity:
        return {
            "visible": False,
            "status": "not_applicable",
            "reason": "not_applicable:financial_entity_industrial_model",
        }
    if not isinstance(model, dict):
        return {"visible": False, "status": "omitted", "reason": "missing:model_result"}
    status = str(model.get("status") or "omitted")
    if status in VISIBLE_MODEL_STATUSES:
        if status == "needs_input" and not model.get("required_inputs"):
            return {"visible": False, "status": "omitted", "reason": "invalid:needs_input_without_fields"}
        if status != "needs_input" and not (
            has_value(model.get("value")) or has_value(model.get("components"))
        ):
            return {"visible": False, "status": "omitted", "reason": "missing:computed_model_value"}
        return {"visible": True, "status": status, "reason": None}
    reasons = model.get("reasons") or []
    return {
        "visible": False,
        "status": "not_applicable" if status == "not_applicable" else "omitted",
        "reason": model.get("reason") or (reasons[0] if reasons else "missing:computed_model_value"),
    }
