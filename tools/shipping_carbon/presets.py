"""Provisional transaction sizes, never a firm's observed positions or limits."""
from decimal import Decimal as D


def catalog(vessels):
    records = vessels.get("records", [])
    sample = sorted(D(r["ets_reported_co2_t"]) for r in records
                    if r.get("report_scope") == "full" and r.get("ship_type") == "Container ship"
                    and r.get("ets_reported_co2_t") is not None and D(r["ets_reported_co2_t"]) > 0)
    benchmark = {"status": "observed_report_statistics" if sample else "missing",
        "reporting_year": vessels.get("reporting_year"), "version": vessels.get("version"),
        "count": len(sample), "unit": "reported_CO2_metric_tonnes_not_EUA_surrender_quantity",
        "selection": "Container ship; Full ERs; positive ETS reported CO2; no DoC-status filter",
        "quantile_method": "sorted_values[floor((n-1)*p)]",
        "quantiles": {str(q): str(sample[int((len(sample)-1)*q)]) for q in (.25, .5, .75)} if sample else {},
        "source_url": vessels.get("source_url")}
    presets = []
    for key, label, q in (("single", "1척 수준 가안", 5000),
                          ("fleet", "소규모 선대 거래 가안", 50000),
                          ("portfolio", "여러 고객 묶음 가안", 200000)):
        lots = q // 1000
        presets.append({"id": key, "label": label, "quality": "assumed_transaction_not_firm_position",
            "demand_eua": q, "lots": lots, "notional_eur_at_80": q * 80,
            "initial_margin_eur": lots * 5000, "cash_buffer_eur": q * 8,
            "inputs": {"preset_id": key, "emissions_tco2e": str(q),
                "emissions_basis": "scope_adjusted", "phase_factor": "1", "route_weight": "1",
                "available_eua": "0", "scheduled_eua": "0", "ship_hedge_delta": str(q // 2),
                "dealer_role": "principal", "dealer_lots": str(lots), "future_price": "80",
                "customer_price": "85", "initial_margin": str(lots * 5000),
                "cash_buffer": str(q * 8), "trade_fees": str(lots * 20), "hedge_basis_shock": "0"}})
    return {"schema": "carbon_provisional_levels_v1", "benchmark": benchmark, "presets": presets,
        "assumptions": {"futures_eur_per_eua": "80", "initial_margin_eur_per_lot": "5000",
            "cash_buffer_share_of_reference_notional": "0.10", "ship_price_hedge_ratio": "0.50",
            "dealer_matched_hedge_ratio": "1.00", "fee_eur_per_lot": "20"},
        "notice": "모든 포지션·헤지비율·증거금·현금 여유는 가정이며 IBK 또는 선사의 실제 운용규모·통상 한도가 아닙니다. MRV 통계에 제출비율을 적용해 만든 값도 아닙니다."}
