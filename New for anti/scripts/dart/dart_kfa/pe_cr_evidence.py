"""Explicitly supplied, source-located disclosure facts; no name inference."""
from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit


# Definitions are part of the input contract. In particular, a gross liquidity
# maturity bucket is not principal, and total cash is not necessarily usable.
BASES = {
    "interest": "recognized_pnl_interest_expense",
    "PPE_DEPRECIATION": "operating_ppe_depreciation_without_double_counting_rou",
    "INTANGIBLE_AMORTIZATION": "operating_intangible_amortization",
    "financing_debt": "complete_financing_debt_carrying_amount_including_leases",
    "unrestricted_cash": "unrestricted_cash_and_equivalents",
    "principal_due_1y": "complete_contractual_principal_due_within_12m_including_leases",
    "cfads": "cash_available_for_debt_service_before_principal_and_interest",
    "principal_paid": "financing_principal_paid_including_leases",
    "interest_paid": "financing_cash_interest_paid_including_leases",
    "maintenance_capex": "explicitly_disclosed_cash_maintenance_capex",
    "order_backlog": "remaining_firm_customer_orders_reported_at_period_end",
    "new_orders": "firm_customer_orders_signed_in_selected_period",
    "wip_inventory": "net_work_in_process_included_in_total_inventory",
    "raw_material_inventory": "net_raw_materials_included_in_total_inventory",
    "inventory_note_total": "net_total_inventory_on_same_basis_as_note_components",
    "merchandise_purchases": "net_merchandise_purchases_matching_trade_payables_scope",
    "receivables": "current_trade_receivables_net_excluding_non_trade_and_settlement_receivables",
    "payables": "current_trade_payables_excluding_non_trade_and_settlement_payables",
    "rd_expense": "research_and_development_recognized_as_expense_in_profit_or_loss",
    "capitalized_development": "internally_generated_development_additions_excluding_acquisitions_and_reclassifications",
    "interest_income": "complete_recognized_pnl_interest_income",
    "preferred_dividends": "preferred_dividends_and_allocations_deductible_from_parent_net_income",
    "preferred_book_value": "preferred_equity_carrying_value_in_parent_equity",
    "noncontrolling_value": "noncontrolling_interest_book_value_at_reporting_date_or_explicit_zero",
}
BALANCES = {"financing_debt", "unrestricted_cash", "principal_due_1y", "order_backlog", "wip_inventory", "raw_material_inventory", "inventory_note_total", "receivables", "payables",
            "preferred_book_value", "noncontrolling_value"}


def reviewed_facts(pack, canonical):
    if pack is None:
        return {}
    if not isinstance(pack, Mapping) or pack.get("schema_version") != "kfa-pe-cr-reviewed/1":
        raise ValueError("invalid:reviewed_schema")
    for key in ("entity_id", "fs_div", "currency", "fiscal_year_end", "source"):
        if not pack.get(key) or pack[key] != canonical.get(key):
            raise ValueError("incompatible:reviewed_" + key)
    # A report from a separate publication channel can supply an annual
    # operating-income control, with a tolerance capped at source precision.
    reference = pack.get("annual_operating_income_control")
    if reference is not None:
        if not isinstance(reference, Mapping):
            raise ValueError("invalid:reviewed_annual_operating_income_control")
        op = ((canonical.get("series") or {}).get("PECR_op") or {}).get("annual") or {}
        target, precision = reference.get("value"), reference.get("source_scale")
        actual = op.get("value")
        if (type(target) is not int or type(precision) is not int or precision not in (1, 1000, 1000000)
                or op.get("availability") != "available" or type(actual) not in (int, float)
                or (op.get("unit") or {}).get("scale") != 1
                or not abs(actual - target) < precision):
            raise ValueError("incompatible:reviewed_annual_operating_income_control")
    if not isinstance(pack.get("rows"), list):
        raise ValueError("invalid:reviewed_rows")
    result = {}
    for row in pack["rows"]:
        if not isinstance(row, Mapping):
            raise ValueError("invalid:reviewed_row")
        key = row.get("key")
        if key not in BASES or row.get("basis") != BASES[key]:
            raise ValueError("invalid:reviewed_basis:" + str(key))
        start, end = row.get("period_start"), row.get("period_end")
        try:
            end_date = date.fromisoformat(end)
            if key in BALANCES:
                if start is not None:
                    raise ValueError
            elif date.fromisoformat(start) > end_date:
                raise ValueError
            if end_date > date.fromisoformat(pack["fiscal_year_end"]):
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid:reviewed_period:" + key) from exc
        evidence = row.get("evidence") or {}
        if not isinstance(evidence, Mapping) or not isinstance(evidence.get("url"), str):
            raise ValueError("missing:reviewed_source_locator:" + key)
        url = urlsplit(evidence.get("url") or "")
        if (url.scheme != "https" or not url.hostname
                or any(not isinstance(evidence.get(k), str) or not evidence[k].strip()
                       for k in ("document", "table", "row"))):
            raise ValueError("missing:reviewed_source_locator:" + key)
        scale = row.get("scale")
        if type(scale) is not int or scale not in (1, 1000, 1000000, 100000000):
            raise ValueError("invalid:reviewed_scale:" + key)
        try:
            amount = Decimal(str(row.get("amount")))
            value = amount * scale
            if not value.is_finite() or (value < 0 and key != "cfads") or abs(value) > 10**20 or value != value.to_integral_value():
                raise ValueError
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("invalid:reviewed_amount:" + key) from exc
        slot = (key, start, end)
        if slot in result:
            raise ValueError("conflict:duplicate_reviewed_fact:" + key)
        result[slot] = {
            "account_id": key, "value": int(value), "availability": "available",
            "quality": "reported", "reason": None, "source": "reviewed_disclosure",
            "nature": "balance" if key in BALANCES else "flow",
            "period_start": start, "period_end": end, "fs_div": pack["fs_div"],
            "unit": {"kind": "currency", "currency": pack["currency"], "scale": 1},
            "provenance": {**evidence, "basis": row["basis"], "source_value": str(amount), "source_scale": scale},
        }
    return result
