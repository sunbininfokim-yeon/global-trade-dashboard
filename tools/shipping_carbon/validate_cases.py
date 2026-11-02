"""Validate design arithmetic only; not a production/legal compliance engine."""
import json
from decimal import Decimal as D
from pathlib import Path


def validate():
    data = json.loads(Path(__file__).with_name("acceptance_cases.json").read_text())
    checks = 0

    def check(actual, expected):
        nonlocal checks
        target = None if expected is None else D(expected)
        if actual != target:
            raise AssertionError((actual, target))
        checks += 1

    s = data["shipowner"]
    q = D(s["raw_eligible_ghg_tco2e"]) * D(s["route_weight"]) * D(s["phase_in"])
    gap = max(D(0), q - D(s["available_eua"]) - D(s["delivery_before_deadline_eua"]))
    check(q, s["expected_obligation_eua"])
    check(gap, s["expected_procurement_gap_eua"])
    check(gap * D(s["scenario_eur_per_eua"]), s["expected_new_purchase_cash_eur"])
    gross = gap * D(s["price_shock_eur"])
    hedge = D(s["cash_settled_hedge_delta_eua"]) * D(s["price_shock_eur"])
    check(gross, s["expected_gross_extra_purchase_cash_eur"])
    check(hedge, s["expected_hedge_gain_eur"])
    check(gross - hedge, s["expected_net_extra_economic_cost_eur"])

    d = data["dealer"]
    future_q = D(d["matched_long_futures_lots"]) * D(d["contract_size_eua"])
    customer_q = D(d["customer_fixed_price_delivery_eua"])
    shock = D(d["parallel_price_shock_eur"])
    future_pnl = future_q * shock
    customer_pnl = -customer_q * shock
    check(future_q - customer_q, d["expected_net_delta_eua"])
    check(future_pnl, d["expected_futures_pnl_eur"])
    check(customer_pnl, d["expected_customer_obligation_pnl_eur"])
    check(future_pnl + customer_pnl, d["expected_net_pnl_eur"])
    check(max(D(0), -future_pnl), d["expected_vm_outflow_eur"])

    f = data["fueleu"]
    balance = (D(f["input_target_gco2e_per_mj"]) - D(f["input_actual_gco2e_per_mj"])) * D(f["input_scoped_energy_mj"])
    check(balance, f["expected_balance_gco2e"])
    check(balance / D(1000000), f["expected_balance_tco2e"])
    check(max(D(0), -balance / D(1000000)) * D(f["pool_quote_eur_per_t_balance"]), f["expected_pool_purchase_eur"])
    check(f["penalty_eur"], None)

    m = data["missing_price"]
    cost = None if m["price_eur"] is None else D(m["quantity_eua"]) * D(m["price_eur"])
    check(cost, m["expected_cost_eur"])
    print(f"PASS: {checks} design arithmetic checks; synthetic inputs only; no live API or legal engine validated.")


if __name__ == "__main__":
    validate()
