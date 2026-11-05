"""Equal-energy financial scenarios using the unchanged FuelEU engine.

ETS factors/scopes are explicit inputs. FuelEU WtW factors never become ETS
factors automatically. No uncontracted surplus revenue is recognized.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation


def number(value, name, lower=0, upper=1e12):
    if value is None or value == "" or isinstance(value, bool):
        raise ValueError(f"{name}: input required")
    try:
        n = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{name}: invalid number") from exc
    if not n.is_finite() or n < Decimal(str(lower)) or n > Decimal(str(upper)):
        raise ValueError(f"{name}: outside allowed range")
    return n


def iso(value, name):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}: YYYY-MM-DD required") from exc


def money(value):
    return float(value.quantize(Decimal("0.01")))


def cash_ledger(events, cash_buffer, annual_pct, horizon):
    grouped = defaultdict(lambda: {"cash": Decimal(0), "items": []})
    for day, label, amount in events:
        grouped[day]["cash"] += amount
        grouped[day]["items"].append(label)
    if not grouped or horizon < max(grouped):
        raise ValueError("horizon must cover all payments and receipts")
    if (horizon - min(grouped)).days > 3660:
        raise ValueError("cash horizon exceeds ten years")
    grouped[horizon]["items"].append("analysis horizon")
    cash = cash_buffer
    previous = min(grouped)
    total_interest = Decimal(0)
    peak = Decimal(0)
    rows = []
    for day, event in sorted(grouped.items()):
        days = (day - previous).days
        interest = max(Decimal(0), -cash) * annual_pct / 100 * days / 365
        cash -= interest
        total_interest += interest
        cash += event["cash"]
        peak = max(peak, -cash)
        rows.append({"date": day.isoformat(), "items": event["items"],
                     "cash_eur": money(event["cash"]), "interest_eur": money(interest),
                     "closing_cash_eur": money(cash), "calendar_days": days})
        previous = day
    return {"status": "calculated_assumption", "peak_extra_funding_eur": money(max(Decimal(0), peak)),
            "interest_eur": money(total_interest), "ending_cash_eur": money(cash), "events": rows,
            "basis": "same-day flows netted; actual calendar days/365 on previous negative cash; no intraday peak/IM/VM/credit limits"}


def observed_reference(snapshot):
    source = snapshot.get("sources", {}).get("eex_eua_auction", {})
    if source.get("status") != "observed" or source.get("unit") != "EUR/EUA" or source.get("price_type") != "auction_clearing":
        raise ValueError("Observed EUA auction reference is unavailable")
    records = source.get("observations") or source.get("latest_observations") or []
    as_of = iso(snapshot["as_of"], "reference as_of")
    eligible = [r for r in records if iso(r["observation_date"], "observation_date") <= as_of]
    if not eligible:
        raise ValueError("No eligible observed auction reference")
    latest_date = max(r["observation_date"] for r in eligible)
    latest = [r for r in eligible if r["observation_date"] == latest_date]
    volume = sum(number(r["auction_volume_tco2"], "auction volume", lower="0.000001") for r in latest)
    price = sum(number(r["price"], "auction price", lower="0.000001") *
                number(r["auction_volume_tco2"], "auction volume", lower="0.000001") for r in latest) / volume
    age = (as_of - iso(latest_date, "latest date")).days
    return {"price_eur_eua": str(price), "observation_date": latest_date, "as_of": as_of.isoformat(),
            "status": "stale" if age > 7 else "observed", "calendar_age_days": age,
            "price_type": "auction_daily_volume_weighted_reference", "source_url": source["source_url"],
            "sha256": source.get("sha256"), "not_executable_quote": True}


def calculate(p, ref, fuel_engine, receipt):
    if p.get("scope_confirmed") is not True or p.get("technical_feasibility_confirmed") is not True:
        raise ValueError("ETS/FuelEU scope and blend feasibility must be explicitly confirmed for this scenario")
    year = int(number(p.get("year"), "year", 2025, 2050))
    if Decimal(str(p["year"])) != year:
        raise ValueError("year must be an integer")
    base = p.get("base_fuel")
    if base not in ("hfo", "lfo", "mdo_mgo"):
        raise ValueError("base fuel must be HFO/LFO/MGO")
    tonnes = number(p.get("baseline_tonnes"), "baseline fuel tonnes", ".000001", 1e9)
    bio_share = number(p.get("bio_energy_pct"), "bio energy share", 0, 100) / 100
    base_price = number(p.get("base_price_eur_t"), "fossil fuel price", ".000001", 1e6)
    bio_price = number(p.get("bio_price_eur_t"), "bio fuel price", ".000001", 1e6)
    pool_buy = number(p.get("pool_buy_eur_tco2e"), "pool buy quote", 0, 1e6)
    pool_sell = None if p.get("pool_sell_eur_tco2e") in (None, "") else number(p["pool_sell_eur_tco2e"], "pool sell quote", 0, 1e6)
    recognize_sale = p.get("surplus_sale_confirmed") is True
    if recognize_sale and pool_sell is None:
        raise ValueError("Confirmed surplus sale requires a sell quote")
    pool_year = number(p.get("pool_compliance_year"), "pool compliance year", 2025, 2050)
    if pool_year != year:
        raise ValueError("Pool quote compliance year must match the scenario")
    ets_share = number(p.get("ets_scope_share"), "ETS scope share", 0, 1)
    fe_share = number(p.get("fueleu_scope_share"), "FuelEU scope share", ".000001", 1)
    phase = number(p.get("ets_phase_factor"), "ETS phase factor", 0, 1)
    fossil_factor = number(p.get("ets_fossil_tco2e_t"), "ETS fossil factor", 0, 20)
    bio_factor = number(p.get("ets_bio_tco2e_t"), "ETS bio factor", 0, 20)
    if not str(p.get("ets_factor_basis", "")).strip():
        raise ValueError("ETS all-applicable-gases factor basis required")
    if bio_factor == 0 and p.get("ets_bio_zero_confirmed") is not True:
        raise ValueError("A zero ETS bio factor requires separate explicit eligibility confirmation")
    if p.get("fueleu_bio_certified") is not True:
        raise ValueError("Certified FuelEU bio pathway required; no default benefit for uncertified biofuel")
    e_value = number(p.get("bio_e_value"), "certified/assumed bio E value", 0, 200)
    fees = number(p.get("fees_eur"), "other fees", 0, 1e9)
    eua_price = number(ref.get("price_eur_eua"), "EUA reference", ".000001", 1e6)
    base_lcv = Decimal(str(fuel_engine.FUELS[base]["lcv"]))
    bio = fuel_engine.bio_fuel(e_value=float(e_value), certified=True)
    bio_lcv = Decimal(str(bio["lcv"]))
    energy = tonnes * base_lcv * 1_000_000
    mixed_base = tonnes * (1 - bio_share)
    mixed_bio = energy * bio_share / (bio_lcv * 1_000_000)

    def option(key, base_t, bio_t):
        rows = []
        if base_t:
            rows.append({"fuel": base, "tonnes": float(base_t), "share": float(fe_share)})
        if bio_t:
            rows.append({"fuel": bio, "tonnes": float(bio_t), "share": float(fe_share)})
        fe = fuel_engine.ship(rows, year)
        cb = Decimal(str(fe["compliance_balance_tco2e"]))
        pool_purchase = max(Decimal(0), -cb) * pool_buy
        sale_cash = max(Decimal(0), cb) * pool_sell if recognize_sale else Decimal(0)
        ets_eua = (base_t * fossil_factor + bio_t * bio_factor) * ets_share * phase
        fuel_cash = base_t * base_price + bio_t * bio_price
        eua_cash = ets_eua * eua_price
        total = fuel_cash + eua_cash + pool_purchase - sale_cash + fees
        return {"id": key, "fossil_tonnes": float(base_t), "bio_tonnes": float(bio_t),
                "energy_mj": float((base_t * base_lcv + bio_t * bio_lcv) * 1_000_000),
                "fueleu": {k: fe[k] for k in ("ghg_intensity", "target", "compliance_balance_tco2e", "penalty_eur")},
                "ets_eua": float(ets_eua), "fuel_cost_eur": money(fuel_cash),
                "ets_reference_cost_eur": money(eua_cash), "pool_purchase_cost_eur": money(pool_purchase),
                "recognized_surplus_sale_eur": money(sale_cash), "fees_eur": money(fees),
                "total_reference_cost_eur": money(total),
                "uncontracted_surplus_tco2e": float(max(Decimal(0), cb)) if not recognize_sale else 0,
                "_fuel_cash": fuel_cash, "_ets_cash": eua_cash, "_pool_cash": pool_purchase - sale_cash,
                "_total": total}

    original = option("fossil_plus_pool", tonnes, Decimal(0))
    blend = option("equal_energy_blend_plus_pool", mixed_base, mixed_bio)
    gap = original["_total"] - blend["_total"]
    breakeven = None if mixed_bio == 0 else bio_price + gap / mixed_bio
    finance_keys = ("fuel_payment_date", "eua_payment_date", "pool_payment_date", "fee_payment_date",
                    "customer_receipt_date", "customer_receipt_eur", "cash_buffer_eur", "funding_rate_pct", "horizon_date")
    missing = [key for key in finance_keys if p.get(key) in (None, "")]
    for opt in (original, blend):
        if missing:
            opt["funding"] = {"status": "held", "missing_inputs": missing}
            opt["cost_including_financing_eur"] = None
        else:
            horizon = iso(p["horizon_date"], "horizon_date")
            events = [(iso(p["fuel_payment_date"], "fuel payment"), "fuel payment", -opt["_fuel_cash"]),
                      (iso(p["eua_payment_date"], "EUA payment"), "EUA purchase at reference", -opt["_ets_cash"]),
                      (iso(p["pool_payment_date"], "pool payment"), "pool net settlement", -opt["_pool_cash"]),
                      (iso(p["fee_payment_date"], "fee payment"), "fees", -fees),
                      (iso(p["customer_receipt_date"], "customer receipt"), "same fixed customer receipt", number(p["customer_receipt_eur"], "customer receipt"))]
            opt["funding"] = cash_ledger(events, number(p["cash_buffer_eur"], "cash buffer"),
                                        number(p["funding_rate_pct"], "funding rate", 0, 100), horizon)
            opt["cost_including_financing_eur"] = money(opt["_total"] + Decimal(str(opt["funding"]["interest_eur"])))
        for key in [k for k in opt if k.startswith("_")]:
            del opt[key]
    return {"schema": "carbon_fueleu_equal_energy_scenario_v1", "status": "calculated_assumption",
            "year": year, "reference": ref, "fueleu_implementation_sha256": receipt,
            "energy_basis": "equal delivered lower-heating-value energy; same engine efficiency assumed",
            "baseline_energy_mj": float(energy), "bio_energy_pct": float(bio_share * 100),
            "ets_factor_basis": p["ets_factor_basis"], "surplus_sale_recognized": recognize_sale,
            "options": [original, blend], "saving_before_financing_eur": money(gap),
            "bio_delivered_breakeven_eur_t": None if breakeven is None else money(breakeven),
            "constraints": ["user-confirmed scopes and ETS factors; not legal scope determination",
                "FuelEU statutory calculation delegated unchanged to Claude engine",
                "EUA auction reference, not execution price; all fuel/pool prices user inputs",
                "no uncontracted surplus revenue; no fuel-efficiency/availability/engine conversion model",
                "borrowing/banking, initial margin, variation margin, credit/capital costs not included here"]}
