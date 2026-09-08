"""Dated, listing-aware overseas LETF liquidity and exposure contracts.

Market turnover is separate from portfolio exposure. No current AUM backfill,
calendar filling, constant FX, inferred option holdings, or cap-as-leverage.
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import math
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(str(value).replace(",", "").replace("%", "").replace("$", ""))
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def positive(value):
    n = number(value)
    return n if n is not None and n > 0 else None


def iso_day(value):
    return date.fromisoformat(value).isoformat()


def strict_sum(values):
    values = list(values)
    return sum(values) if values and all(v is not None for v in values) else None


def ratio(numerator, denominator):
    return numerator / denominator if numerator is not None and positive(denominator) else None


def usd_rate(currency, day, fx):
    """USD per quote unit, including pence. Require exact FX date."""
    if currency == "USD":
        return 1.0
    r = (fx.get(day) or {}).get(currency)
    if currency == "GBp":
        r = (fx.get(day) or {}).get("GBP")
        return r / 100 if positive(r) else None
    return positive(r)


def leverage_on(product, day):
    periods = product.get("leverage_periods")
    if periods:
        for p in periods:
            if p["start"] <= day and (p.get("end") is None or day <= p["end"]):
                return number(p.get("L")) if p["mode"] == "fixed_daily" else None
        return None
    return number(product.get("leverage")) if product["leverage_mode"] == "fixed_daily" else None


def implied_rebalance(aum_prev, l_start, l_end, underlying_return):
    """Positive = buy/increase signed exposure; negative = sell.

    A0 [L_end(1+L_start*r) - L_start(1+r)], excluding flows, fees,
    dividends, intraday resets and hedge routing. Constant L -> A0*L*(L-1)*r.
    A daily cap cannot be substituted for an actual start/end target.
    """
    a, x, y, r = map(number, (aum_prev, l_start, l_end, underlying_return))
    if None in (a, x, y, r) or a <= 0 or 1 + x * r <= 0:
        return None
    return a * (y * (1 + x * r) - x * (1 + r))


def holding_type(name):
    s = name.upper()
    if "SWAP" in s or " SWP" in s or "-TRS-" in s:
        return "swap"
    if "FUTURE" in s or " FUT " in s or "E-MINI" in s:
        return "futures"
    if "OPTION" in s or " CALL " in s or " PUT " in s:
        return "options"
    if any(x in s for x in ("CASH", "TREASURY", "MONEY MARKET", "MNY MKT", "NET OTHER ASSETS", "BILL ZERO")):
        return "cash_collateral"
    return "unknown"


def parse_proshares_holdings(text, product, as_of):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(text, "html.parser")
    section = soup.select_one("section#Holdings")
    if section is None:
        raise ValueError("Holdings section not found")
    stamp = re.search(r"as of\s+(\d{1,2}/\d{1,2}/\d{4})", section.get_text(" ", strip=True))
    if not stamp:
        raise ValueError("Holdings date unavailable")
    d = datetime.strptime(stamp[1], "%m/%d/%Y").date().isoformat()
    if d > as_of:
        raise ValueError("future_dated_holdings: " + d)
    rows = []
    for i, tr in enumerate(section.select("table#holdings tbody tr")):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) != 7:
            raise ValueError("Unexpected holdings columns")
        w, ticker, name, exposure, market, shares, sedol = cells
        kind = holding_type(name)
        if kind == "unknown" and ticker != "--":
            kind = "fund" if "ETF" in name else "equity"
        rows.append(dict(date=d, as_of=d, product_id=product["product_id"], holding_id=name + ":" + sedol,
                         name=name, holding_type=kind, weight_pct=number(w), weight_basis="issuer_exposure_weight",
                         exposure_value_usd=number(exposure), market_value_usd=number(market), shares=number(shares),
                         currency="USD", source_unit="USD; percent; shares/contracts", source=product["source_urls"][0], quality="observed"))
    if not rows:
        raise ValueError("Empty holdings table")
    if len({r["holding_id"] for r in rows}) != len(rows):
        raise ValueError("Ambiguous duplicate holdings identifiers")
    return rows


def parse_themes_holdings(text, product, as_of):
    """Preserve issuer signed weights (can exceed 100%); never draw a pie.

    MarketValue for a swap is the publisher's exposure-style column, not its
    fair value. Preserve the original label instead of asserting accounting NAV.
    """
    rows, aums, rejected = [], {}, []
    for raw in csv.DictReader(io.StringIO(text.lstrip("\ufeff"))):
        d = datetime.strptime(raw["Date"], "%m/%d/%Y").date().isoformat()
        if raw["Account"] != product["product_id"]:
            raise ValueError("Holdings account does not match product")
        if d > as_of:
            rejected.append({"date": d, "reason": "future_dated_holdings"})
            continue
        name = raw["SecurityName"]
        aum = positive(raw.get("NetAssets"))
        if d in aums and aums[d] != aum:
            raise ValueError("Inconsistent NetAssets in one holdings date")
        aums[d] = aum
        rows.append(dict(date=d, as_of=d, product_id=product["product_id"],
                         holding_id=raw["StockTicker"], name=name,
                         holding_type=holding_type(name), weight_pct=number(raw["Weightings"]),
                         weight_basis="issuer_reported_signed_weight", shares=number(raw["Shares"]),
                         source_market_value=number(raw["MarketValue"]), currency="USD",
                         source_unit="USD; percent; shares", source=product["holdings_url"], quality="observed"))
    return rows, [dict(date=d, aum_native=a, currency="USD", product_id=product["product_id"],
                      source=product["holdings_url"], quality="observed") for d, a in sorted(aums.items())], rejected


def parse_proshares_nav(text, product, as_of):
    rows = []
    for raw in csv.DictReader(io.StringIO(text.lstrip("\ufeff"))):
        if raw["Ticker"] != product["product_id"]:
            raise ValueError("NAV ticker does not match product")
        d = datetime.strptime(raw["Date"], "%m/%d/%Y").date().isoformat()
        if d <= as_of:
            rows.append(dict(date=d, product_id=product["product_id"], aum_native=positive(raw["Assets Under Management"]),
                             nav=positive(raw["NAV"]), currency="USD", source=product["nav_history_url"], quality="observed"))
    return rows


def parse_leverage_shares(payload, product, as_of):
    """The issuer's own renderer binds etp_securities_issued to the AUM label.

    Do not interpret that field as units outstanding. Ignore simulated history.
    Only USD AUM is used so FX currency views cannot duplicate fund assets.
    """
    info = payload["Etp"][0]
    if info["Isin"] != product["product_id"]:
        raise ValueError("Issuer ISIN mismatch")
    aums = []
    for row in payload.get("Usd", []):
        d = datetime.strptime(row["date"], "%d/%m/%Y").date().isoformat()
        if str(row.get("IsSimulated")) != "0" or not product.get("inception", "1900-01-01") <= d <= as_of:
            continue
        aums.append(dict(date=d, product_id=product["product_id"], currency="USD",
                         aum_native=positive(row["etp_securities_issued"]), nav=positive(row["price"]),
                         source=product["issuer_api_url"], quality="observed"))
    d = datetime.strptime(info["date"], "%d %b %Y").date().isoformat()
    if d > as_of:
        return aums, None
    assets, debt, aum = map(number, (info["value_underlying_assets"], info["liabilities"], info["etp_securities_issued"]))
    if None in (assets, debt, aum) or abs(assets - debt - aum) > max(3, abs(aum) * .0001):
        raise ValueError("Issuer capital structure does not reconcile")
    return aums, dict(date=d, as_of=d, product_id=product["product_id"], source=product["issuer_api_url"],
                      source_unit="USD", quality="observed", underlying_holding=info["Underlying_holding"],
                      structure={"KRX shares": "physical_margin", "KRX futures": "futures"}.get(info["Underlying_holding"], "unknown"),
                      underlying_assets_usd=assets, liabilities_usd=debt, aum_usd=aum,
                      leverage=number(info["Leverage"]))


def normalize_bars(product, listing, bars, fx, *, as_of):
    out = []
    seen = set()
    for b in sorted(bars, key=lambda x: x["date"]):
        d = iso_day(b["date"])
        if d > as_of or d < max(product.get("inception", "1900-01-01"), listing.get("first_trade_date", "1900-01-01")) or d > listing.get("last_trade_date", "9999-12-31"):
            continue
        if d in seen:
            raise ValueError("Duplicate listing bar: " + listing["listing_id"] + d)
        seen.add(d)
        c, v = positive(b.get("close")), number(b.get("volume"))
        if v is not None and v < 0:
            raise ValueError("Negative volume")
        if c is None:
            continue
        rate = usd_rate(listing["currency"], d, fx)
        tv_observed = number(b.get("trading_value_native"))
        if tv_observed is not None and tv_observed < 0:
            raise ValueError("Negative trading value")
        proxy = c * v if v is not None else None
        tv = tv_observed if tv_observed is not None else proxy
        out.append(dict(date=d, as_of=d, product_id=product["product_id"], listing_id=listing["listing_id"],
                        ticker=listing["ticker"], venue=listing["venue"], currency=listing["currency"],
                        source=b.get("source") or "Yahoo Finance chart (unadjusted OHLC)",
                        source_unit="shares; " + listing["currency"], quality="partial_observed",
                        close_native=c, volume=v, trading_value_native=tv,
                        trading_value_usd=tv * rate if tv is not None and rate is not None else None,
                        trading_value_quality="observed" if tv_observed is not None else "proxy" if tv is not None else "missing",
                        trading_value_method="exchange_turnover" if tv_observed is not None else "close_times_volume",
                        fx_usd_per_native=rate, fx_as_of=d if rate is not None else None,
                        fx_source="identity" if listing["currency"] == "USD" else "Yahoo Finance FX daily close" if rate else None,
                        split_factor=number(b.get("splits")),
                        leverage=leverage_on(product, d), leverage_ceiling=product.get("leverage_ceiling")))
    return out


def build_board(registry, observations, holdings, aums, fx, cash_rows, returns, *, as_of, diagnostics=None):
    """Latest table + dated comparable groups + history. AUM counted per fund."""
    as_of = iso_day(as_of)
    products = {p["product_id"]: p for p in registry["products"]}
    by_product = defaultdict(list)
    aum_map = {(a["product_id"], a["date"]): a for a in aums if a["date"] <= as_of}
    cash = {(r["ticker"], r["date"]): r for r in cash_rows}
    ret = {(r["reference"], r["date"]): r for r in returns}
    for r in observations:
        if r["date"] <= as_of:
            by_product[r["product_id"]].append(r)
    history, cards = [], []
    for pid, p in products.items():
        dates = sorted({r["date"] for r in by_product[pid]})
        prior = None
        for d in dates:
            rows = [r for r in by_product[pid] if r["date"] == d]
            expected = [l for l in p["listings"] if l.get("first_trade_date", "1900-01-01") <= d <= l.get("last_trade_date", "9999-12-31")]
            present = {r["listing_id"] for r in rows}
            valued = {r["listing_id"] for r in rows if r["trading_value_usd"] is not None}
            complete = all(l["listing_id"] in valued for l in expected)
            subtotal = strict_sum(r["trading_value_usd"] for r in rows if r["trading_value_usd"] is not None)
            # Never silently call a partial set of currency counters total turnover.
            total = subtotal if complete else None
            a = aum_map.get((pid, d)) or {}
            arate = usd_rate(a.get("currency"), d, fx)
            au = a["aum_native"] * arate if positive(a.get("aum_native")) and arate else None
            prev = aum_map.get((pid, prior)) or {}
            rr = ret.get((p["return_reference"], d)) or {}
            l0, l1 = leverage_on(p, prior or d), leverage_on(p, d)
            reb = None
            # A return must explicitly identify the same previous session and unit.
            # Non-USD AUM requires a return in the fund's currency; KR equity return
            # alone is not a USD fund return. Flexible products need observed targets.
            if prior and rr.get("previous_date") == prior and rr.get("currency") == prev.get("currency") and prev.get("quality") == "observed":
                reb = implied_rebalance(prev.get("aum_native"), l0, l1, rr.get("return"))
            fxr = usd_rate(prev.get("currency"), d, fx)
            reb_usd = reb * fxr if reb is not None and fxr else None
            c = cash.get((p.get("underlying_ticker"), d)) or {}
            cash_krw = positive(c.get("spot_trading_value_krw"))
            kr_rate = usd_rate("KRW", d, fx)
            # US ADR and index baskets must not use the Korean common-stock denominator.
            spot_ratio = ratio(total, cash_krw * kr_rate) if cash_krw and kr_rate and p["scope"] == "kr_single_stock" else None
            entry = dict(date=d, as_of=d, product_id=pid, scope=p["scope"], underlying_ticker=p.get("underlying_ticker"),
                         return_reference=p["return_reference"], structure=p["structure"] if d >= p.get("structure_as_of", "1900-01-01") else "historical_structure_unverified", direction="inverse" if (p.get("leverage_ceiling") or p.get("leverage") or 0) < 0 else "long",
                         volume_by_listing=[dict(listing_id=r["listing_id"], volume=r["volume"]) for r in rows],
                         primary_listing_id=p["listings"][0]["listing_id"],
                         primary_volume=next((r["volume"] for r in rows if r["listing_id"] == p["listings"][0]["listing_id"]), None),
                         covered_trading_value_usd=subtotal, trading_value_usd=total,
                         expected_listing_count=len(expected), observed_listing_count=len(present), valued_listing_count=len(valued),
                         coverage_complete=complete, aum_usd=au, aum_as_of=d if au is not None else None,
                         aum_source=a.get("source"), leverage=l1,
                         notional_exposure_usd=au * abs(l1) if au is not None and l1 is not None else None,
                         ceiling_notional_usd=au * abs(p["leverage_ceiling"]) if au is not None and p.get("leverage_ceiling") else None,
                         turnover_over_aum=ratio(total, au), etf_to_kr_cash_tv_ratio=spot_ratio,
                         spot_as_of=d if spot_ratio is not None else None,
                         implied_rebalance_usd=reb_usd, implied_rebalance_quality="estimated",
                         rebalance_inputs=dict(aum_prev=prev.get("aum_native"), aum_prev_date=prior if prev else None,
                                               currency=prev.get("currency"), L_start=l0, L_end=l1, underlying_return=rr.get("return"), reference=p["return_reference"]),
                         rebalance_missing_reason=None if reb_usd is not None else "dated_previous_aum_and_same_reference_currency_return_and_actual_leverage_required",
                         quality="partial_observed", source=sorted({r["source"] for r in rows}), source_unit="USD; ratio")
            history.append(entry)
            prior = d
        ph = [h for h in holdings if h["product_id"] == pid and h["date"] <= as_of]
        hd = max((h["date"] for h in ph), default=None)
        current_holdings = [h for h in ph if h["date"] == hd]
        composition = defaultdict(list)
        for h in current_holdings:
            composition[h["holding_type"]].append(h.get("weight_pct"))
        dated_aums = sorted((a for a in aums if a["product_id"] == pid and a["date"] <= as_of), key=lambda a: a["date"])
        latest = next((h for h in reversed(history) if h["product_id"] == pid), None)
        cards.append(dict(**p, latest=latest, latest_aum=dated_aums[-1] if dated_aums else None,
                          holdings_as_of=hd, holdings=current_holdings,
                          composition=[dict(holding_type=k, signed_weight_pct=strict_sum(v)) for k, v in composition.items()],
                          composition_basis="issuer_signed_weight_not_normalized_to_100" if ph else "strategy_only_no_observed_weights",
                          history_observations=len(dates), line_chart_available=len(dates) >= 5,
                          trend_alert_available=len(dates) >= 20))
    groups = defaultdict(list)
    for h in history:
        # Shares are within this curated, date-aligned group, not world market share.
        key = (h["date"], h["scope"], h["underlying_ticker"] or h["return_reference"])
        groups[key].append(h)
    summaries = []
    for (d, scope, underlying), rows in sorted(groups.items()):
        tv = strict_sum(r["trading_value_usd"] for r in rows)
        covered = strict_sum(r["covered_trading_value_usd"] for r in rows if r["covered_trading_value_usd"] is not None)
        estimates = [r["implied_rebalance_usd"] for r in rows]
        net = strict_sum(estimates)
        for r in rows:
            r["turnover_share_pct"] = 100 * r["trading_value_usd"] / tv if positive(tv) and r["trading_value_usd"] is not None else None
            r["covered_turnover_share_pct"] = 100 * r["covered_trading_value_usd"] / covered if positive(covered) and r["covered_trading_value_usd"] is not None else None
        summaries.append(dict(date=d, scope=scope, underlying=underlying, product_count=len(rows),
                              denominator_product_ids=[r["product_id"] for r in rows],
                              trading_value_usd=tv, covered_trading_value_usd=covered,
                              share_basis="date_aligned_observed_catalogue_products_not_total_market",
                              implied_rebalance_usd=net, abs_net_implied_rebalance_usd=abs(net) if net is not None else None,
                              gross_implied_rebalance_usd=strict_sum(abs(e) if e is not None else None for e in estimates)))
    return dict(schema_version="overseas-letf-board-v1", as_of=as_of,
                generated_at=datetime.now(timezone.utc).isoformat(), coverage=registry["coverage"],
                products=cards, groups=summaries, diagnostics=diagnostics or [],
                definitions=dict(volume="listing units traded; do not compare raw unit counts across funds",
                                 trading_value="close × same-session volume proxy unless exchange turnover supplied",
                                 share="covered catalogue only, same date; total market share unavailable",
                                 composition="signed issuer weights; >100% and negative cash retained; no pie normalization",
                                 rebalance="A_prev*[L_end*(1+L_start*r)-L_start*(1+r)]; positive buy; model estimate, not KR spot orders")), history


def upsert_history(path, rows, key_fields, replace_groups=None):
    """Replace only identical keys; atomically write stable compressed JSONL."""
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    existing = []
    if path.exists():
        with opener(path, "rt", encoding="utf-8") as f:
            existing = [json.loads(line) for line in f if line.strip()]
    replaced = {tuple(r[k] for k in replace_groups) for r in rows} if replace_groups else set()
    merged = {tuple(r[k] for k in key_fields): r for r in existing
              if not replace_groups or tuple(r[k] for k in replace_groups) not in replaced}
    for r in rows:
        iso_day(r["date"])
        json.dumps(r, allow_nan=False)
        merged[tuple(r[k] for k in key_fields)] = r
    ordered = [merged[k] for k in sorted(merged)]
    payload = "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n" for r in ordered).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(gzip.compress(payload, mtime=0) if path.suffix == ".gz" else payload)
    tmp.replace(path)
    dates = sorted({r["date"] for r in ordered})
    return dict(row_count=len(ordered), date_count=len(dates), date_min=dates[0] if dates else None, date_max=dates[-1] if dates else None)
