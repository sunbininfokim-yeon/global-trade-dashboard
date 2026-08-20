"""Presentation-currency policy; calculations always retain filing currency."""

from __future__ import annotations

from datetime import date
import math
from typing import Any


def build_currency_contract(
    *,
    source_adapter: str | None,
    source_currency: str | None,
    display_currency: str | None = None,
    fx_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = str(source_adapter or "").lower()
    currency = str(source_currency or "").upper() or None
    target = str(display_currency or currency or "").upper() or None
    if currency is None:
        return {"status": "unavailable", "reason": "missing:source_currency", "source_currency": None, "display_currency": None, "rate": None}
    allowed = {"KRW"} if source in {"dart", "opendart"} else ({"USD", "KRW"} if currency == "USD" else {currency})
    if target not in allowed:
        return {
            "status": "not_allowed",
            "reason": f"not_allowed:{source or 'unknown'}_display_currency:{target}",
            "source_currency": currency,
            "display_currency": currency,
            "allowed_display_currencies": sorted(allowed),
            "rate": None,
        }
    if target == currency:
        return {
            "status": "ready",
            "reason": None,
            "source_currency": currency,
            "display_currency": target,
            "allowed_display_currencies": sorted(allowed),
            "rate": 1.0,
            "provenance": {"kind": "filing_currency_no_conversion"},
        }

    fx = fx_input or {}
    try:
        rate = float(fx.get("rate"))
    except (TypeError, ValueError):
        rate = None
    source_ref = str(fx.get("source") or "").strip()
    as_of = str(fx.get("as_of") or "").strip()
    try:
        date.fromisoformat(as_of)
        valid_date = True
    except ValueError:
        valid_date = False
    if rate is None or not math.isfinite(rate) or rate <= 0 or not source_ref or not valid_date:
        return {
            "status": "inputs_required",
            "reason": "missing:positive_fx_rate_source_and_as_of",
            "source_currency": currency,
            "display_currency": currency,
            "requested_display_currency": target,
            "allowed_display_currencies": sorted(allowed),
            "rate": None,
            "required_inputs": ["fx.rate", "fx.source", "fx.as_of"],
        }
    return {
        "status": "ready",
        "reason": None,
        "source_currency": currency,
        "display_currency": target,
        "allowed_display_currencies": sorted(allowed),
        "rate": rate,
        "provenance": {
            "kind": "explicit_fx_input",
            "source": source_ref,
            "as_of": as_of,
            "pair": f"{currency}/{target}",
        },
    }


def convert_currency_value(value: Any, contract: dict[str, Any]) -> Any:
    """Convert a numeric money-card value; mixed-unit models stay untouched."""
    if contract.get("status") != "ready":
        return value
    rate = float(contract.get("rate") or 1.0)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value * rate
    if isinstance(value, dict):
        return {key: convert_currency_value(item, contract) for key, item in value.items()}
    return value
