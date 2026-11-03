"""FuelEU Maritime compliance balance, penalty and pooling choices for one ship.

Source: Regulation (EU) 2023/1805, OJ L 234, 22.9.2023 (read 2026-11-03).
  Art. 2(1)  scope: at berth and intra-EU voyages 100 %, voyages to/from a
             third-country port 50 %.
  Art. 4(2)  limit = 91.16 gCO2e/MJ reduced by 2/6/14.5/31/62/80 % from
             2025/2030/2035/2040/2045/2050.
  Annex I    Equation (1) well-to-wake intensity, RWD = 2 for RFNBO until
             2033, f_wind 0.99/0.97/0.95 for P_wind/P_prop 0.05/0.1/>=0.15.
  Annex II   default LCV, WtT and TtW factors (fossil fuels below).
  Annex IV   CB = (target - actual) x energy; penalty = |CB| /
             (actual x 41 000) x 2 400 EUR.
  Art. 20    borrow at most 2 % of target x energy, repay x 1.1, not in two
             consecutive periods.
  Art. 21(4) pool valid only if total > 0, no deficit ship ends worse, no
             surplus ship ends in deficit.
  Art. 23(2) consecutive penalty multiplier 1 + (n - 1) / 10.

Annex I/IV equations are images on EUR-Lex; their structure here follows the
symbol tables printed beside them and reproduces the commonly cited fossil
intensities (HFO 91.74, MGO 90.77 gCO2e/MJ), which test_engine.py pins.
GWP100 (CH4 25, N2O 298) is Directive 2018/2001 Annex V Part C(4), which
Annex I refers to.

Fuel masses are inputs. Nothing here estimates a real ship's consumption.

Work is voyage-leg based, the way compliance tools in the industry do it:
each leg (port A -> port B) carries its own fuel use from MRV/noon reports,
Art. 2(1) decides from the two ports how much of it counts, legs add up to the
ship's year, actual legs plus planned legs give the year-end forecast, and each
leg's cost is the change in the ship's year result with versus without it
(what a charter-party FuelEU clause recharges). Ships then pool at fleet level.
"""
REFERENCE = 91.16
REDUCTIONS = ((2050, 80.0), (2045, 62.0), (2040, 31.0), (2035, 14.5), (2030, 6.0), (2025, 2.0))
GWP = {"CH4": 25.0, "N2O": 298.0}
VLSFO_MJ_PER_T = 41_000.0
PENALTY_EUR_PER_T_VLSFO = 2_400.0
SCOPE_SHARE = {"at_berth": 1.0, "intra_eu": 1.0, "extra_eu": 0.5}
RFNBO_REWARD_UNTIL = 2033

# Annex II defaults: LCV MJ/g, WtT gCO2e/MJ, Cf gGHG/gFuel, Cslip % of mass.
FUELS = {
    "hfo": {"label": "HFO (ISO 8217 RME-RMK)", "lcv": 0.0405, "wtt": 13.5, "cf_co2": 3.114, "cf_ch4": 0.00005, "cf_n2o": 0.00018, "slip": 0.0},
    "lfo": {"label": "LFO (ISO 8217 RMA-RMD)", "lcv": 0.041, "wtt": 13.2, "cf_co2": 3.151, "cf_ch4": 0.00005, "cf_n2o": 0.00018, "slip": 0.0},
    "mdo_mgo": {"label": "MDO/MGO (ISO 8217 DMX-DMB)", "lcv": 0.0427, "wtt": 14.4, "cf_co2": 3.206, "cf_ch4": 0.00005, "cf_n2o": 0.00018, "slip": 0.0},
    "lng_otto_ms": {"label": "LNG Otto (dual fuel medium speed)", "lcv": 0.0491, "wtt": 18.5, "cf_co2": 2.750, "cf_ch4": 0.0, "cf_n2o": 0.00011, "slip": 3.1},
    "lng_otto_ss": {"label": "LNG Otto (dual fuel slow speed)", "lcv": 0.0491, "wtt": 18.5, "cf_co2": 2.750, "cf_ch4": 0.0, "cf_n2o": 0.00011, "slip": 1.7},
    "lng_diesel_ss": {"label": "LNG Diesel (dual fuel slow speed)", "lcv": 0.0491, "wtt": 18.5, "cf_co2": 2.750, "cf_ch4": 0.0, "cf_n2o": 0.00011, "slip": 0.2},
    "lng_lbsi": {"label": "LNG LBSI", "lcv": 0.0491, "wtt": 18.5, "cf_co2": 2.750, "cf_ch4": 0.0, "cf_n2o": 0.00011, "slip": 2.6},
}
# Biofuels and e-fuels have no fixed WtT default: Annex II derives it from the
# certified pathway (Directive 2018/2001). Pass them as custom fuels with the
# certified "wtt" and the Annex II TtW factors, plus "rfnbo": True for e-fuels.


# EU-27 ISO codes. EEA states (NO, IS, LI) are left out on purpose: whether
# FuelEU has been incorporated into the EEA Agreement is not verified here.
# Pass them via extra_member_codes once checked.
EU27 = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT",
        "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"}


def port_in_scope(port, extra_member_codes=()):
    """port: {"country": "NL", "outermost": bool, "transhipment_excluded": bool}.

    outermost: an EU outermost region (Canaries, Azores, Madeira, French
    overseas departments...). transhipment_excluded: a neighbouring container
    transhipment port on the Commission list, which does not count as a port
    of call; the list is an implementing act and is not hard-coded here.
    """
    return port.get("country", "").upper() in EU27 | set(extra_member_codes)


def leg_share(origin, destination, extra_member_codes=()):
    """Art. 2(1)(b)-(d) share of a voyage's energy that counts."""
    o, d = port_in_scope(origin, extra_member_codes), port_in_scope(destination, extra_member_codes)
    if not (o or d):
        return 0.0, "out_of_scope"
    if o and d:
        if origin.get("outermost") or destination.get("outermost"):
            return 0.5, "outermost_region"
        return 1.0, "intra_eu"
    return 0.5, "extra_eu"


def legs_to_consumption(legs, extra_member_codes=()):
    """Flatten voyage legs into the consumption rows intensity() takes.

    leg: {"id", "origin": port, "destination": port, "status": actual|planned,
          "at_sea": {fuel: tonnes}, "at_berth": {fuel: tonnes}}
    at_berth is fuel burnt while alongside at the destination port.
    Fuels may be keys of FUELS or entries of the optional "custom_fuels" map.
    """
    rows = []
    for leg in legs:
        share, basis = leg_share(leg["origin"], leg["destination"], extra_member_codes)
        custom = leg.get("custom_fuels", {})
        for fuel, t in (leg.get("at_sea") or {}).items():
            if share:
                rows.append({"fuel": custom.get(fuel, fuel), "tonnes": t, "share": share,
                             "scope": basis, "leg": leg.get("id")})
        if port_in_scope(leg["destination"], extra_member_codes):
            for fuel, t in (leg.get("at_berth") or {}).items():
                rows.append({"fuel": custom.get(fuel, fuel), "tonnes": t, "share": 1.0,
                             "scope": "at_berth", "leg": leg.get("id")})
    return rows


def target(year):
    for start, pct in REDUCTIONS:
        if year >= start:
            return REFERENCE * (1 - pct / 100)
    raise ValueError("FuelEU applies from reporting year 2025")


def fuel_factors(fuel):
    if isinstance(fuel, str):
        if fuel not in FUELS:
            raise ValueError(f"unknown fuel {fuel}; pass a dict with lcv/wtt/cf_*/slip for others")
        return FUELS[fuel]
    missing = {"lcv", "wtt", "cf_co2", "cf_ch4", "cf_n2o", "slip"} - set(fuel)
    if missing:
        raise ValueError(f"custom fuel missing {sorted(missing)}")
    return fuel


def wind_factor(p_wind_over_p_prop):
    r = p_wind_over_p_prop or 0.0
    if r >= 0.15:
        return 0.95
    if r >= 0.1:
        return 0.97
    if r >= 0.05:
        return 0.99
    return 1.0


def intensity(consumption, year, p_wind_over_p_prop=0.0):
    """Annex I Equation (1) for in-scope fuel use.

    consumption: [{"fuel": key-or-dict, "tonnes": t, "scope": at_berth|intra_eu|extra_eu}]
    Returns WtT, TtW, total intensity (gCO2e/MJ) and in-scope energy (MJ).
    """
    wtt_num = ttw_num = denom = energy = 0.0
    lines = []
    for row in consumption:
        f = fuel_factors(row["fuel"])
        share = row.get("share", SCOPE_SHARE.get(row.get("scope")))
        if share is None:
            raise ValueError("scope must be at_berth, intra_eu or extra_eu (or give share)")
        tonnes = float(row["tonnes"])
        if tonnes < 0:
            raise ValueError("fuel mass cannot be negative")
        grams = tonnes * 1e6 * share
        mj = grams * f["lcv"]
        rwd = 2.0 if f.get("rfnbo") and year <= RFNBO_REWARD_UNTIL else 1.0
        slip = f["slip"] / 100
        combusted = f["cf_co2"] + f["cf_ch4"] * GWP["CH4"] + f["cf_n2o"] * GWP["N2O"]
        # Slipped fuel is methane: Csf CO2 = Csf N2O = 0, Csf CH4 = 1.
        ttw = grams * ((1 - slip) * combusted + slip * GWP["CH4"])
        wtt_num += grams * f["wtt"] * f["lcv"]
        ttw_num += ttw
        denom += mj * rwd
        energy += mj
        lines.append({"fuel": row["fuel"] if isinstance(row["fuel"], str) else f.get("label", "custom"),
                      "scope": row.get("scope"), "leg": row.get("leg"), "tonnes": tonnes,
                      "share": share, "in_scope_mj": mj})
    if denom <= 0:
        raise ValueError("no in-scope energy")
    fwind = wind_factor(p_wind_over_p_prop)
    wtt, ttw = wtt_num / denom, ttw_num / denom
    return {"wtt": wtt, "ttw": ttw, "f_wind": fwind, "ghg_intensity": fwind * (wtt + ttw),
            "energy_mj": energy, "lines": lines}


def penalty_eur(cb_g, actual, consecutive_periods=1):
    if cb_g >= 0:
        return 0.0
    n = max(1, int(consecutive_periods))
    return abs(cb_g) / (actual * VLSFO_MJ_PER_T) * PENALTY_EUR_PER_T_VLSFO * (1 + (n - 1) / 10)


def penalty_per_tco2e(actual, consecutive_periods=1):
    """The penalty restated per tonne of CO2e of deficit -- the ceiling a buyer would pay a pool."""
    return penalty_eur(-1e6, actual, consecutive_periods)


def ship(consumption, year, p_wind_over_p_prop=0.0, consecutive_deficits=0, borrowed_last_period=False):
    i = intensity(consumption, year, p_wind_over_p_prop)
    tgt = target(year)
    cb_g = (tgt - i["ghg_intensity"]) * i["energy_mj"]
    n = consecutive_deficits + 1
    return {**i, "year": year, "target": tgt,
            "compliance_balance_tco2e": cb_g / 1e6,
            "penalty_eur": penalty_eur(cb_g, i["ghg_intensity"], n),
            "penalty_eur_per_tco2e": penalty_per_tco2e(i["ghg_intensity"], n),
            "consecutive_multiplier": 1 + (n - 1) / 10,
            "borrow_limit_tco2e": 0.0 if borrowed_last_period else 0.02 * tgt * i["energy_mj"] / 1e6}


def ship_year(legs, year, pool_price=None, extra_member_codes=(), **kw):
    """Year view from voyage legs: actual-to-date, full-year forecast, and each leg's cost.

    A leg's cost is exact, not pro-rated: the ship's full-year result is run
    again without that leg, and the difference in compliance balance is priced
    at pool_price (and at the penalty rate). RFNBO reward factors make the
    intensity non-additive, which is why it is not done by simple shares.
    """
    actual = [l for l in legs if l.get("status", "actual") == "actual"]
    full = ship(legs_to_consumption(legs, extra_member_codes), year, **kw)
    to_date = ship(legs_to_consumption(actual, extra_member_codes), year, **kw) if actual else None
    per_leg = []
    for leg in legs:
        share, basis = leg_share(leg["origin"], leg["destination"], extra_member_codes)
        rest = [l for l in legs if l is not leg]
        rows = legs_to_consumption(rest, extra_member_codes)
        without = ship(rows, year, **kw)["compliance_balance_tco2e"] if rows else 0.0
        delta = full["compliance_balance_tco2e"] - without
        per_leg.append({"id": leg.get("id"), "status": leg.get("status", "actual"),
                        "route": f'{leg["origin"].get("name") or leg["origin"]["country"]} -> '
                                 f'{leg["destination"].get("name") or leg["destination"]["country"]}',
                        "share": share, "scope_basis": basis, "cb_delta_tco2e": delta,
                        "cost_at_pool_eur": None if pool_price is None else max(0.0, -delta) * pool_price,
                        "value_at_pool_eur": None if pool_price is None else max(0.0, delta) * pool_price})
    return {"full_year": full, "actual_to_date": to_date, "legs": per_leg}


def fleet_pool(ships):
    """Net a fleet's balances inside one pool before going to the market.

    ships: {ship_id: CB tCO2e}. Deficits are covered from surpluses largest
    first, which always satisfies Art. 21(4) when the pool total is positive.
    Returns the allocation and what is left to buy or sell outside.
    """
    total = sum(ships.values())
    surplus = {k: v for k, v in ships.items() if v > 0}
    deficit = {k: v for k, v in ships.items() if v < 0}
    need = -sum(deficit.values())
    after = dict(ships)
    if total > 0:
        for k in deficit:
            after[k] = 0.0
        left = need
        for k, v in sorted(surplus.items(), key=lambda kv: -kv[1]):
            take = min(v, left)
            after[k] = v - take
            left -= take
        check = pool_valid(ships, after)
    else:
        check = {"valid": False, "problems": ["fleet total is not positive: buy outside or pay penalty"]}
        after = dict(ships)
    return {"total_tco2e": total, "internal_netting_tco2e": min(need, sum(surplus.values())),
            "external_need_tco2e": max(0.0, -total), "external_surplus_tco2e": max(0.0, total),
            "allocation": after, "check": check}


def options(result, pool_price, next_pool_price=None):
    """Compare ways to close a deficit, or to use a surplus, at given pool prices (EUR/tCO2e).

    next_pool_price is the price the user expects next period; borrowing and
    banking are only priced when it is given. Costs are cash in EUR for this
    ship alone, before broker fees, financing and credit terms.
    """
    cb = result["compliance_balance_tco2e"]
    nxt = next_pool_price
    if cb < 0:
        deficit = -cb
        borrow = min(deficit, result["borrow_limit_tco2e"])
        rest = deficit - borrow
        rows = [
            {"option": "pool_buy", "label": "풀에서 잉여분 매입", "cost_eur": deficit * pool_price},
            {"option": "penalty", "label": "부담금 납부", "cost_eur": result["penalty_eur"]},
            {"option": "borrow_then_pool", "label": f"차입 {borrow:,.0f} t + 나머지 풀 매입",
             "cost_eur": None if nxt is None else 1.1 * borrow * nxt + rest * pool_price,
             "note": "차입분은 다음 기간에 1.1배를 갚는다. 다음 기간 풀 가격 가정이 필요하다."},
        ]
        priced = [r for r in rows if r["cost_eur"] is not None]
        best = min(priced, key=lambda r: r["cost_eur"])
        return {"position": "deficit", "tco2e": deficit, "rows": rows, "cheapest": best["option"],
                "breakeven_pool_price": result["penalty_eur_per_tco2e"],
                "borrow_beats_pool_if_next_below": pool_price / 1.1}
    surplus = cb
    rows = [
        {"option": "pool_sell", "label": "풀에 잉여분 판매", "value_eur": surplus * pool_price},
        {"option": "bank", "label": "다음 기간으로 이월", "value_eur": None if nxt is None else surplus * nxt,
         "note": "이월분 가치는 다음 기간 가격 가정에 달려 있다. 이월은 문서 발급 전에만 가능하다."},
    ]
    priced = [r for r in rows if r["value_eur"] is not None]
    best = max(priced, key=lambda r: r["value_eur"])
    return {"position": "surplus", "tco2e": surplus, "rows": rows, "best": best["option"],
            "bank_beats_sale_if_next_above": pool_price}


def pool_valid(before, after):
    """Art. 21(4) check. before/after: {ship_id: CB tCO2e} for the same ships."""
    if set(before) != set(after):
        raise ValueError("pool allocation must cover the same ships")
    problems = []
    if sum(before.values()) <= 0:
        problems.append("total pooled compliance is not positive")
    if abs(sum(after.values()) - sum(before.values())) > 1e-6:
        problems.append("allocation changes the pool total")
    for k, cb in before.items():
        if cb < 0 and after[k] < cb:
            problems.append(f"{k}: deficit ship ends with a larger deficit")
        if cb >= 0 and after[k] < 0:
            problems.append(f"{k}: surplus ship ends in deficit")
    return {"valid": not problems, "problems": problems}


def quick_check(gross_tonnage, fuels, eu_share=None, year=2025, p_wind_over_p_prop=0.0, pool_price=None):
    """Is this ship a surplus or a deficit ship, and from which year does that flip?

    The FuelEU limit is the same gCO2e/MJ for every ship in scope -- it does not
    depend on ship type or size, unlike CII/EEXI. Size decides two things only:
    whether the ship is in scope at all (above 5 000 GT, Art. 2(1)) and how big
    the balance is, through the energy it burns. The sign comes from the fuel
    mix alone.

    fuels: {fuel: tonnes per year on EU-related voyages}.
    eu_share: {"at_berth"|"intra_eu"|"extra_eu": fraction of those tonnes};
              defaults to all extra-EU (counted 50 %).
    """
    if gross_tonnage is not None and gross_tonnage <= 5_000:
        return {"in_scope": False, "reason": "FuelEU는 5,000 GT 초과 여객·화물선에만 적용된다 (제2조(1))."}
    share = eu_share or {"extra_eu": 1.0}
    if abs(sum(share.values()) - 1.0) > 1e-6:
        raise ValueError("eu_share fractions must add up to 1")
    rows = [{"fuel": f, "tonnes": t * frac, "scope": scope}
            for f, t in fuels.items() for scope, frac in share.items() if frac]
    now = ship(rows, year, p_wind_over_p_prop)
    timeline = []
    for start, _ in sorted(REDUCTIONS):
        r = ship(rows, max(start, year), p_wind_over_p_prop)
        timeline.append({"from_year": start, "target": r["target"],
                         "compliance_balance_tco2e": r["compliance_balance_tco2e"],
                         "position": "surplus" if r["compliance_balance_tco2e"] >= 0 else "deficit",
                         "penalty_eur": r["penalty_eur"]})
    flip = next((t["from_year"] for t in timeline if t["position"] == "deficit"), None)
    cb = now["compliance_balance_tco2e"]
    return {"in_scope": True, "year": year, "ghg_intensity": now["ghg_intensity"], "target": now["target"],
            "position": "surplus" if cb >= 0 else "deficit", "compliance_balance_tco2e": cb,
            "margin_gco2e_per_mj": now["target"] - now["ghg_intensity"],
            "penalty_eur": now["penalty_eur"],
            "value_at_pool_eur": None if pool_price is None else abs(cb) * pool_price,
            "first_deficit_period": flip, "timeline": timeline}


# ------------------------------------------------------------------ biofuel blends
# Directive (EU) 2018/2001 (RED II), read 2026-11-03:
#   Annex V totals, waste cooking oil biodiesel: typical 11.2, default 14.9 gCO2e/MJ
#   (GHG savings 88 % / 84 % against the 94 gCO2e/MJ transport comparator).
#   Annex III: FAME lower calorific value 37 MJ/kg.
# FuelEU Annex II: bio-diesel Cf CO2 2.834 g/g; CH4/N2O are TBM, so the highest
# default in the biofuel class (HVO: 0.00005 / 0.00018) applies. Annex II note
# (a): WtT = E - Cf_CO2 / LCV, so the biogenic CO2 burnt on board is netted off.
# Food/feed-crop or uncertified biofuels get the worst fossil factor (Art. 10(1)(a)):
# no credit at all, which bio_fuel(certified=False) reproduces.
UCO_FAME_E = {"default": 14.9, "typical": 11.2}


def bio_fuel(e_value=UCO_FAME_E["default"], lcv=0.037, cf_co2=2.834, certified=True, worst_fossil="hfo"):
    if not certified:
        return dict(FUELS[worst_fossil], label="인증 없는 바이오연료 (최악 화석 계수)")
    return {"label": f"UCO 바이오디젤 (E {e_value:g})", "lcv": lcv, "wtt": e_value - cf_co2 / lcv,
            "cf_co2": cf_co2, "cf_ch4": 0.00005, "cf_n2o": 0.00018, "slip": 0.0}


def blend_economics(base, bio_mass_share, tonnes, year=2025, eu_share=None, pool_price=None,
                    bio_premium_eur_per_t=None, e_value=UCO_FAME_E["default"], certified=True):
    """What a biofuel blend does to one ship's balance, and what it is worth at the pool price.

    base: fossil fuel key. bio_mass_share: 0..1 of the fuel mass (B30 = 0.3).
    tonnes: annual fuel on EU-related voyages. eu_share as in quick_check.
    Returns the balance with and without the blend, the surplus each tonne of
    biofuel creates, the premium per tonne at which blending costs the same as
    buying that surplus from a pool, the mass share that just reaches zero
    balance, and a B0..B100 curve.
    """
    if not 0 <= bio_mass_share <= 1:
        raise ValueError("bio share must be between 0 and 1")
    share = eu_share or {"extra_eu": 1.0}
    bio = bio_fuel(e_value, certified=certified)

    def run(s):
        rows = [{"fuel": base, "tonnes": tonnes * (1 - s) * f, "scope": k} for k, f in share.items() if f and s < 1]
        rows += [{"fuel": bio, "tonnes": tonnes * s * f, "scope": k} for k, f in share.items() if f and s > 0]
        return ship(rows, year)

    without, with_blend = run(0.0), run(bio_mass_share)
    pure_bio = run(1.0)
    bio_t = tonnes * bio_mass_share
    gain_per_t = (pure_bio["compliance_balance_tco2e"] - without["compliance_balance_tco2e"]) / tonnes
    # CB is linear in the mass share (energy and emissions both are), so zero crossing is exact.
    span = pure_bio["compliance_balance_tco2e"] - without["compliance_balance_tco2e"]
    zero = None if span <= 0 else -without["compliance_balance_tco2e"] / span
    curve = [{"bio_pct": p, "compliance_balance_tco2e": run(p / 100)["compliance_balance_tco2e"],
              "ghg_intensity": run(p / 100)["ghg_intensity"]} for p in range(0, 101, 10)]
    out = {"bio_fuel": bio["label"], "certified": certified, "e_value": e_value, "bio_tonnes": bio_t,
           "without": {k: without[k] for k in ("ghg_intensity", "compliance_balance_tco2e", "penalty_eur")},
           "with_blend": {k: with_blend[k] for k in ("ghg_intensity", "compliance_balance_tco2e", "penalty_eur")},
           "pure_bio_intensity": pure_bio["ghg_intensity"],
           "surplus_per_t_bio_tco2e": gain_per_t,
           "bio_share_for_zero_balance": None if zero is None else max(0.0, zero),
           "curve": curve}
    if pool_price is not None:
        out["breakeven_premium_eur_per_t"] = gain_per_t * pool_price
    if bio_premium_eur_per_t is not None and gain_per_t > 0:
        out["cost_per_tco2e_of_blending"] = bio_premium_eur_per_t / gain_per_t
    return out
