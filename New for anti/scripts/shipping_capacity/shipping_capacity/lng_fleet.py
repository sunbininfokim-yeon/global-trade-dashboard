"""Validate the free LNG-fleet evidence boundary before it reaches the model."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_lng_fleet_context(config: dict[str, Any]) -> dict[str, Any]:
    """Return only denominators whose vessel scope is explicitly identified.

    UNCTAD's public table reports liquefied-gas carriers (LNG and LPG together).
    It must therefore never silently become an LNG-only DWT denominator.
    """

    combined = config.get("liquefied_gas_carriers_dwt")
    lng_only = config.get("lng_only_dwt")
    if not isinstance(combined, (int, float)) or combined <= 0:
        raise ValueError("liquefied_gas_carriers_dwt must be a positive observed value")
    if lng_only is not None and (not isinstance(lng_only, (int, float)) or lng_only <= 0):
        raise ValueError("lng_only_dwt must be null or a positive value")
    return {
        "status": (
            "lng_only_dwt_observed" if lng_only is not None else "combined_lng_lpg_dwt_observed_lng_only_dwt_not_available_free"
        ),
        "as_of": config["as_of"],
        "liquefied_gas_carriers_dwt": combined,
        "lng_only_dwt": lng_only,
        "source": config["source"],
        "model_use": (
            "eligible_lng_only_denominator" if lng_only is not None else "context_only_not_eligible_lng_only_denominator"
        ),
        "warning_ko": config["warning_ko"],
    }


def load_lng_fleet_context(path: Path) -> dict[str, Any]:
    return build_lng_fleet_context(json.loads(path.read_text(encoding="utf-8")))
