"""Dated, end-of-day funding scenario for a principal supply transaction.

VM and the final physical invoice together reproduce the futures acquisition cost.
Interest uses actual calendar days / 365 on previous negative closing cash only.
"""
from datetime import date, timedelta
from decimal import Decimal as D

ZERO = D(0)


def schedule(*, as_of, delivery, customer_delivery, customer_payment, customer_q,
             future_q, future_price, customer_price, replacement_price, shock,
             recovery, cash_buffer, initial_margin, fees, annual_rate, principal):
    dates = [date.fromisoformat(x) for x in (as_of, delivery, customer_delivery, customer_payment)]
    start, delivery, customer_delivery, customer_payment = dates
    if any(x < start for x in dates):
        raise ValueError("지급·인도·수금일은 분석 기준일 이후여야 합니다")
    if not principal:
        return {"status": "not_applicable", "events": [], "days": [], "missing_inputs": [],
                "peak_funding_gap_eur": ZERO, "financing_cost_eur": ZERO,
                "gross_spread_eur": None, "net_contribution_eur": None,
                "residual_inventory_eua": ZERO}
    if customer_q is None:
        return {"status": "held", "events": [], "days": [],
                "missing_inputs": ["customer_supply_eua"], "peak_funding_gap_eur": None,
                "financing_cost_eur": None, "gross_spread_eur": None,
                "net_contribution_eur": None, "residual_inventory_eua": None}
    terminal_shock = ZERO if recovery else shock
    if future_price is not None and min(future_price, future_price + shock) < 0:
        raise ValueError("선물 가격 경로는 음수가 될 수 없습니다")
    if replacement_price is not None and replacement_price < 0:
        raise ValueError("보충 매입가격은 음수가 될 수 없습니다")
    allocated = min(customer_q, future_q) if delivery <= customer_delivery else ZERO
    replacement_q = customer_q - allocated
    residual_inventory = future_q - allocated
    events, missing = [], []

    def add(day, kind, amount):
        if amount is None:
            missing.append(kind)
        else:
            events.append({"date": day.isoformat(), "kind": kind, "cash_eur": amount})

    if future_q:
        # A short-dated scenario must not put simulated VM after physical delivery.
        if delivery < start + timedelta(days=2):
            raise ValueError("선물 인도일은 2일의 가상 가격 경로 이후여야 합니다")
        add(start, "initial_margin_post", -initial_margin if initial_margin is not None else None)
        add(start + timedelta(days=1), "variation_margin", future_q * shock)
        if recovery:
            add(start + timedelta(days=2), "variation_margin", -future_q * shock)
        add(delivery, "physical_future_payment", -future_q * (future_price + terminal_shock) if future_price is not None else None)
        add(delivery, "initial_margin_release", initial_margin)
    add(start, "fees", -fees)
    if replacement_q:
        add(customer_delivery, "replacement_purchase", -replacement_q * replacement_price if replacement_price is not None else None)
    if customer_q:
        add(customer_payment, "customer_receipt", customer_q * customer_price if customer_price is not None else None)
    # Preserve events on the same day and aggregate before measuring EOD funding.
    events.sort(key=lambda x: (x["date"], x["kind"]))
    grouped = {}
    for e in events:
        grouped.setdefault(e["date"], []).append(e)
    balance, peak, interest_total = cash_buffer, ZERO, ZERO
    previous_day = start
    days = []
    for text, items in sorted(grouped.items()):
        day = date.fromisoformat(text)
        interest = max(ZERO, -balance) * annual_rate / D(100) * D((day - previous_day).days) / D(365)
        flow = sum((e["cash_eur"] for e in items), ZERO)
        balance += flow - interest
        interest_total += interest
        need = max(ZERO, -balance)
        peak = max(peak, need)
        days.append({"date": text, "flow_eur": flow, "financing_eur": interest,
                     "closing_cash_eur": balance, "funding_gap_eur": need,
                     "kinds": [e["kind"] for e in items]})
        previous_day = day
    complete = not missing
    # Only matched, timely physical supply has a comparable spread here.
    spread = (customer_q * (customer_price - future_price)
              if future_q == customer_q and allocated == customer_q
              and customer_price is not None and future_price is not None else None)
    return {"status": "scenario" if complete else "partial", "missing_inputs": missing,
            "events": events, "days": days,
            "known_components_peak_eur": peak,
            "peak_funding_gap_eur": peak if complete else None,
            "financing_cost_eur": interest_total if complete else None,
            "closing_cash_eur": balance if complete else None,
            "gross_spread_eur": spread,
            "net_contribution_eur": spread - fees - interest_total if spread is not None and complete else None,
            "replacement_eua": replacement_q, "residual_inventory_eua": residual_inventory,
            "measurement": "end_of_day_same_date_netting",
            "interest_convention": "negative_closing_cash_actual_calendar_days_365",
            "horizon_end": previous_day.isoformat()}
