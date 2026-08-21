"""GDP composition labels from BEA expenditure contributions."""

from __future__ import annotations

from typing import Any


def _sum(parts: dict[str, Any], keys: tuple[str, ...]) -> float:
    return round(sum(float(parts.get(key) or 0.0) for key in keys), 4)


def classify_gdp_quality(
    release: dict[str, Any],
    *,
    private_demand_floor: float = 1.0,
    dominance_margin_pp: float = 0.25,
) -> dict[str, Any]:
    """Describe what drove GDP, retaining BEA contribution units (pp)."""
    contributions = release.get("contributions_pp")
    final_private = release.get("final_sales_private_domestic_purchasers_pct")
    if not isinstance(contributions, dict) or not isinstance(final_private, (int, float)):
        return {
            "state": "insufficient_data",
            "missing": ["contributions_pp", "final_sales_private_domestic_purchasers_pct"],
            "interpretation": "composition_label_not_value_judgment",
        }

    private = _sum(
        contributions,
        (
            "personal_consumption",
            "residential_investment",
            "structures",
            "equipment",
            "intellectual_property",
        ),
    )
    government_inventory = _sum(contributions, ("inventory_change", "federal_government", "state_local_government"))
    external = _sum(contributions, ("exports", "imports"))

    if float(final_private) >= private_demand_floor and private >= max(government_inventory, external) + dominance_margin_pp:
        state = "private_demand_led"
    elif government_inventory >= max(private, external) + dominance_margin_pp:
        state = "government_inventory_supported"
    elif external >= max(private, government_inventory) + dominance_margin_pp:
        state = "external_trade_led"
    else:
        state = "mixed"

    return {
        "state": state,
        "headline_real_gdp_pct": release.get("real_gdp_pct"),
        "final_sales_private_domestic_purchasers_pct": float(final_private),
        "contribution_groups_pp": {
            "private_domestic": private,
            "government_inventory": government_inventory,
            "external_trade": external,
        },
        "contributions_pp": dict(contributions),
        "interpretation": "composition_label_not_value_judgment",
        "warning": "수입 기여도는 BEA 표의 부호를 그대로 입력해야 합니다.",
    }
