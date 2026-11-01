"""Pure scenario calculations. No automatic legal eligibility or trade execution."""
from datetime import date
from decimal import Decimal as D

ZERO = D(0)


def number(value, name, minimum=None):
    try:
        n = D(str(value))
    except Exception as exc:
        raise ValueError(f"{name}: 숫자를 입력하세요") from exc
    if not n.is_finite() or abs(n) > D('1e18') or (minimum is not None and n < minimum):
        raise ValueError(f"{name}: 허용 범위 밖입니다")
    return n


def reference(snapshot, key, price_type, unit, as_of):
    source = snapshot.get("sources", {}).get(key, {})
    records = source.get("latest_observations", [])
    result = {"value": None, "status": "missing", "price_type": price_type,
              "unit": unit, "source_url": source.get("source_url"),
              "retrieved_at": snapshot.get("retrieved_at")}
    if source.get("status") not in ("observed", "synthetic") or source.get("price_type") != price_type or source.get("unit") != unit:
        return result
    if len(records) != 1:
        return {**result, "status": "ambiguous" if records else "missing"}
    r = records[0]
    age = (as_of - date.fromisoformat(r["observation_date"])).days
    if age < 0:
        return {**result, "status": "future_observation_rejected"}
    return {**result, "value": number(r["price"], key, ZERO),
            "observation_date": r["observation_date"], "calendar_age_days": age,
            "status": "synthetic" if source.get("status") == "synthetic" else ("stale" if age > 7 else "observed"), "stale_policy": "calendar_age_gt_7_days"}


def defaults(snapshot):
    return {"as_of": snapshot.get("as_of", "2026-11-01"), "scope_confirmed": True,
            "emissions_tco2e": "200000", "emissions_basis": "raw",
            "route_weight": "0.5", "phase_factor": "1", "gases_complete": True,
            "emissions_year": 2026, "available_eua": "20000",
            "scheduled_eua": "30000", "delivery_date": "2027-09-01",
            "surrender_date": "2027-09-30", "price_mode": "auction_reference",
            "manual_price": None, "price_shock": "-10", "ship_hedge_delta": "20000",
            "dealer_role": "principal", "dealer_lots": "50", "future_price": "80",
            "customer_bucket": "2027-09", "future_bucket": "2027-09",
            "future_delivery_date": "2027-09-01", "cash_buffer": "100000",
            "initial_margin": None, "fuel_target": "89.3368", "fuel_actual": "90",
            "fuel_energy_mj": "1000000000", "pool_quote": "200"}


def calculate(p, snapshot):
    as_of = date.fromisoformat(p["as_of"])
    auction = reference(snapshot, "eex_eua_auction", "auction_clearing", "EUR/EUA", as_of)
    fx = reference(snapshot, "ecb_eurkrw", "reference_fx", "KRW/EUR", as_of)
    n = lambda key: number(p[key], key, ZERO)
    signed = lambda key: number(p[key], key)
    emissions, route, phase = n("emissions_tco2e"), n("route_weight"), n("phase_factor")
    if route > 1 or phase > 1:
        raise ValueError("적용비중·단계비율은 0~1 사이입니다")
    if p["emissions_basis"] not in ("raw", "scope_adjusted"):
        raise ValueError("배출량 입력 기준을 확인하세요")
    if p["dealer_role"] not in ("principal", "agency"):
        raise ValueError("금융사 거래 역할을 확인하세요")
    if p["price_mode"] not in ("auction_reference", "manual"):
        raise ValueError("가격 종류를 확인하세요")
    known = p.get("scope_confirmed") is True and p.get("gases_complete") is True
    obligation = emissions * (route if p["emissions_basis"] == "raw" else D(1)) * phase if known else None
    due = date.fromisoformat(p["surrender_date"])
    timely = date.fromisoformat(p["delivery_date"]) <= due
    scheduled = n("scheduled_eua") if timely else ZERO
    gap = max(ZERO, obligation - n("available_eua") - scheduled) if known else None
    price = auction["value"] if p["price_mode"] == "auction_reference" else (
        None if p.get("manual_price") in (None, "") else n("manual_price"))
    shock = signed("price_shock")
    if price is not None and price + shock < 0:
        raise ValueError("가격 충격 후 EUA 가격은 음수가 될 수 없습니다")
    baseline = None if p.get("future_price") in (None, "") else n("future_price")
    if baseline is not None and baseline + shock < 0:
        raise ValueError("가격 충격 후 선물 가정가격은 음수가 될 수 없습니다")
    budget = gap * price if gap is not None and price is not None else None
    hedge = n("ship_hedge_delta")
    ship = {"status": "scenario" if known else "held", "obligation_eua": obligation,
            "scheduled_eua": scheduled, "late_delivery_eua": ZERO if timely else n("scheduled_eua"),
            "procurement_gap_eua": gap, "budget_eur": budget,
            "budget_krw": budget * fx["value"] if budget is not None and fx["value"] is not None else None,
            "gross_cost_change_eur": gap * shock if gap is not None else None,
            "hedge_gain_eur": hedge * shock,
            "net_cost_change_eur": (gap - hedge) * shock if gap is not None else None,
            "overhedged_eua": max(ZERO, hedge - gap) if gap is not None else None}
    principal = p["dealer_role"] == "principal"
    lots = n("dealer_lots")
    if lots != lots.to_integral_value():
        raise ValueError("선물 계약 수는 정수 lot으로 입력하세요")
    future_q = lots * D(1000) if principal else ZERO
    customer_q = gap if principal else ZERO
    buckets = {}
    if customer_q is not None:
        buckets[p["customer_bucket"]] = -customer_q
    buckets[p["future_bucket"]] = buckets.get(p["future_bucket"], ZERO) + future_q
    pnl = future_q * shock
    customer_pnl = -customer_q * shock if customer_q is not None else None
    cash = n("cash_buffer")
    margin = None if p.get("initial_margin") in (None, "") else n("initial_margin")
    if not principal:
        margin = ZERO
    # One shock and recovery. VM is the cash realization of futures P&L, not an extra P&L.
    vm_cash, peak = ZERO, ZERO
    path = []
    previous = ZERO
    for day, level in enumerate((ZERO, shock, ZERO)):
        vm = future_q * (level - previous)
        previous = level
        vm_cash += vm
        gap_cash = max(ZERO, -vm_cash - cash)
        peak = max(peak, gap_cash)
        path.append({"day": day, "price_change": level, "vm_flow_eur": vm,
                     "cumulative_vm_eur": vm_cash, "vm_only_funding_gap_eur": gap_cash})
    timely_future = date.fromisoformat(p["future_delivery_date"]) <= due
    dealer = {"role": p["dealer_role"], "customer_supply_eua": customer_q,
              "hedge_eua": future_q, "delta_by_bucket": buckets,
              "net_delta_eua": future_q - customer_q if customer_q is not None else None,
              "futures_pnl_eur": pnl, "customer_pnl_eur": customer_pnl,
              "net_pnl_eur": pnl + customer_pnl if customer_pnl is not None else None,
              "vm_outflow_at_shock_eur": max(ZERO, -pnl), "cash_path": path,
              "vm_only_peak_funding_gap_eur": peak,
              "vm_and_im_peak_funding_gap_eur": max(ZERO, max(ZERO, -pnl) + margin - cash) if margin is not None else None,
              "initial_margin_eur": margin, "future_price_input": baseline,
              "future_price_status": "synthetic" if baseline is not None else "missing",
              "delivery_gap_eua": max(ZERO, customer_q - (future_q if timely_future else ZERO)) if customer_q is not None else None,
              "valuation_method": "parallel_shock_delta_approximation",
              "curve_risk": len([v for v in buckets.values() if v != 0]) > 1}
    balance = (n("fuel_target") - n("fuel_actual")) * n("fuel_energy_mj") / D(1000000)
    pool = None if p.get("pool_quote") in (None, "") else n("pool_quote")
    fuel = {"status": "illustrative", "balance_tco2e": balance,
            "pool_cost_eur": max(ZERO, -balance) * pool if pool is not None else None,
            "penalty_eur": None, "penalty_status": "held_pending_annex_verification"}
    return {"schema": "shipping_carbon_scenario_v1", "as_of": as_of.isoformat(),
            "scenario_data": True, "references": {"auction": auction, "fx": fx},
            "price_mode": p["price_mode"], "budget_price_eur": price,
            "shipowner": ship, "dealer": dealer, "fueleu": fuel}


def json_value(value):
    if isinstance(value, D):
        return format(value, "f")
    if isinstance(value, dict):
        return {k: json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_value(v) for v in value]
    return value
