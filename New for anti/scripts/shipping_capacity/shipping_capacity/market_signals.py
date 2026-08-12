"""Free-source market-signal registry with explicit licensing and scope checks."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUPPORTED_SIGNAL_CLASSES = {
    "freight_rate",
    "charter_rate",
    "war_risk_insurance_premium",
    "supply_chain_pressure_proxy",
    "insurance_area_status",
    "marine_insurance_market_aggregate",
}


def build_market_signal_registry(config: dict[str, Any]) -> dict[str, Any]:
    """Validate public-market sources without treating unavailable prices as zero.

    Paid Baltic/Worldscale/insurance data are recorded as unavailable rather
    than scraped. Public PDF and index proxies remain diagnostics only until a
    source provides a reproducible series with an allowed redistribution right.
    """

    signals: list[dict[str, Any]] = []
    for source in config.get("sources", []):
        signal_class = source.get("signal_class")
        if signal_class not in SUPPORTED_SIGNAL_CLASSES:
            raise ValueError(f"unsupported signal_class: {signal_class}")
        access = source.get("access")
        if access not in {
            "public_machine_readable",
            "public_pdf",
            "public_web_page",
            "commercial_or_license_required",
        }:
            raise ValueError(f"unsupported access: {access}")
        machine_series = access == "public_machine_readable"
        public_document = access in {"public_pdf", "public_web_page"}
        signals.append(
            {
                "id": source["id"],
                "signal_class": signal_class,
                "ship_type": source.get("ship_type"),
                "source_name": source["source_name"],
                "source_url": source["source_url"],
                "access": access,
                "status": (
                    "automatable_public_series"
                    if machine_series
                    else "automated_public_document_context"
                    if public_document
                    else "not_automated_without_permitted_public_series"
                ),
                "model_use": (
                    "external_validation_only"
                    if machine_series or public_document
                    else "not_used"
                ),
                "reason": source.get("reason"),
            }
        )
    return {
        "status": "source_registry_only_no_unlicensed_scraping",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "signals": signals,
        "identification_boundary": config["identification_boundary"],
        "warning_ko": config["warning_ko"],
    }


def load_market_signal_registry(path: Path) -> dict[str, Any]:
    return build_market_signal_registry(json.loads(path.read_text(encoding="utf-8")))
