"""Presentation-currency policy; calculations always retain filing currency.

The important distinction is deliberate:

* filing facts and every model calculation use ``calculation_currency``;
* only display cards may be converted to ``display_currency``;
* an external monetary input (market cap, SOTP value, etc.) must carry a
  currency and is accepted only when it can be reconciled to the filing
  currency with the same explicit FX contract.

This keeps an USD filing from accidentally combining a KRW market cap with
USD debt/FCF merely because the UI happens to display KRW.
"""

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
        return {
            "status": "unavailable",
            "reason": "missing:source_currency",
            "source_currency": None,
            "calculation_currency": None,
            "display_currency": None,
            "rate": None,
            "model_currency_policy": "filing_currency_only",
        }
    allowed = {"KRW"} if source in {"dart", "opendart"} else ({"USD", "KRW"} if currency == "USD" else {currency})
    if target not in allowed:
        return {
            "status": "not_allowed",
            "reason": f"not_allowed:{source or 'unknown'}_display_currency:{target}",
            "source_currency": currency,
            "calculation_currency": currency,
            "display_currency": currency,
            "allowed_display_currencies": sorted(allowed),
            "rate": None,
            "model_currency_policy": "filing_currency_only",
        }
    if target == currency:
        return {
            "status": "ready",
            "reason": None,
            "source_currency": currency,
            "calculation_currency": currency,
            "display_currency": target,
            "allowed_display_currencies": sorted(allowed),
            "rate": 1.0,
            "provenance": {"kind": "filing_currency_no_conversion"},
            "model_currency_policy": "filing_currency_only",
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
            "calculation_currency": currency,
            "display_currency": currency,
            "requested_display_currency": target,
            "allowed_display_currencies": sorted(allowed),
            "rate": None,
            "required_inputs": ["fx.rate", "fx.source", "fx.as_of"],
            "model_currency_policy": "filing_currency_only",
        }
    return {
        "status": "ready",
        "reason": None,
        "source_currency": currency,
        "calculation_currency": currency,
        "display_currency": target,
        "allowed_display_currencies": sorted(allowed),
        "rate": rate,
        "provenance": {
            "kind": "explicit_fx_input",
            "source": source_ref,
            "as_of": as_of,
            "pair": f"{currency}/{target}",
        },
        "model_currency_policy": "filing_currency_only",
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


def convert_monetary_input_to_calculation_currency(
    value: Any,
    *,
    input_currency: str | None,
    contract: dict[str, Any],
) -> tuple[float | None, str | None]:
    """Return an auditable money input in the filing/model currency.

    Bare numbers are intentionally rejected.  A consumer must state whether a
    market value is USD or KRW; accepting an unlabelled number is how mixed
    currency EV bridges arise.  The only accepted conversion is the exact
    source/display pair described by the already-validated FX contract.
    """
    if value is None or isinstance(value, bool):
        return None, "missing:monetary_input"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None, "invalid:monetary_input"
    if not math.isfinite(numeric):
        return None, "invalid:monetary_input"

    source = str(contract.get("calculation_currency") or contract.get("source_currency") or "").upper()
    supplied = str(input_currency or "").strip().upper()
    if not source:
        return None, "missing:filing_calculation_currency"
    if not supplied:
        return None, "missing:monetary_input_currency"
    if supplied == source:
        return numeric, None

    target = str(contract.get("display_currency") or "").upper()
    rate = contract.get("rate")
    if contract.get("status") == "ready" and supplied == target and target != source:
        try:
            numeric_rate = float(rate)
        except (TypeError, ValueError):
            numeric_rate = 0.0
        if math.isfinite(numeric_rate) and numeric_rate > 0:
            return numeric / numeric_rate, None
    return None, f"incompatible:monetary_input_currency:{supplied}:{source}"
