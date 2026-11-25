#!/usr/bin/env python3
"""CTA-style trend signal on the KOSPI 200 -> public/data/krx_cta_v1.json.

CTAs (managed futures) follow price trends with mechanical rules: direction
from 1/3/6/12-month returns, size from a volatility target. Because the rule
is mechanical, the position and the prices at which it flips can be backed
out from prices alone. This is that model -- an estimate of what a trend
follower would hold, not an observed position.

Prices: the KOSPI 200 index close (FinanceDataReader KS200, --live). The
index has no roll gaps and does not depend on the krx-month-paste checkout.
Without --live (or if FDR fails) the front-month futures close published in
krx_deriv_flow_v1.json is used instead, and the output says which.

Model (validated in the macro-monitor session, handoff 2026-11-25):

    LB     = (20, 60, 125, 250) trading days  (~1, 3, 6, 12 months)
    vol    = stdev of the last 60 daily log returns
    s_k    = clip( ln(P_t / P_{t-k}) / (vol * sqrt(k)), -1, +1 )
    signal = mean(s_k)                       -1 max short ... +1 max long
    flip price for tomorrow, lookback k = P_{t+1-k}

Added on top of the handoff model:

  * trigger levels -- the close tomorrow at which the *combined* signal is 0,
    and at which it reaches full long / full short, found by bisection on a
    full recomputation (the new close also enters the 60-day vol);
  * volatility-target sizing -- exposure = signal * (target vol / realized
    vol), capped, as a share of capital and as contracts per 1조원 of AUM;
  * model PnL -- yesterday's exposure times today's return, its drawdown
    from the peak, and the one-month PnL along each scenario path (the
    upside/downside skew of the current positioning);
  * lead/lag -- weekly signal change against investor futures net buying in
    the same week, the next week and the previous week, and split by the
    sign of the signal.

Observed days only: a day without a close is skipped, never filled.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "../../public/data"
SCHEMA_VERSION = "krx-cta-v1"
LOOKBACKS = (20, 60, 125, 250)
LOOKBACK_KO = {20: "1개월", 60: "3개월", 125: "6개월", 250: "12개월"}
VOL_WINDOW = 60
HORIZON = 21
SCENARIOS = (("flat", "보합", 0.0), ("up_small", "소폭 상승", 1.0), ("up_big", "대폭 상승", 2.5),
             ("down_small", "소폭 하락", -1.0), ("down_big", "대폭 하락", -2.5))
NEAR_PCT = 5.0
HISTORY_DAYS = 500
# Volatility target: a typical CTA runs ~10-15% annualised; exposure is
# capped so a calm market cannot imply unlimited gross.
TARGET_VOL_ANN = 0.15
MAX_EXPOSURE = 2.0
K200_MULTIPLIER = 250_000      # 원 per index point (KOSPI 200 futures)
TRADING_DAYS = 252
LADDER_PCT = (-10, -7, -5, -3, -2, -1, 0, 1, 2, 3, 5, 7, 10)
QUAD_MONTHS = (3, 6, 9, 12)
# Liquid futures a typical CTA book holds. Yahoo continuous front-month
# symbols (free); fetched only with --live, in CI.
ASSETS = (
    ("sp500", "S&P 500 선물", "ES=F", "주식"), ("nasdaq", "나스닥100 선물", "NQ=F", "주식"),
    ("nikkei", "니케이225", "^N225", "주식"), ("ust10", "미국 10년 국채선물", "ZN=F", "채권"),
    ("gold", "금", "GC=F", "원자재"), ("wti", "WTI 원유", "CL=F", "원자재"),
    ("copper", "구리", "HG=F", "원자재"), ("usdkrw", "달러/원", "KRW=X", "통화"),
    ("usdjpy", "달러/엔", "JPY=X", "통화"),
)
# SG CTA Index replication ETF: a free, daily check on whether a multi-asset
# version of this model tracks what CTAs actually earned.
CTA_PROXY = ("DBMF", "DBMF (SG CTA 지수 복제 ETF)")


# --- core model ---------------------------------------------------------------

def daily_vol(prices: list[float], end: int, window: int = VOL_WINDOW) -> float | None:
    """Stdev of the `window` log returns ending at index `end` (inclusive)."""
    if end - window < 0:
        return None
    rets = [math.log(prices[i] / prices[i - 1]) for i in range(end - window + 1, end + 1)]
    m = sum(rets) / len(rets)
    var = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) if var > 0 else None


def components(prices: list[float], t: int, vol: float) -> dict[int, float] | None:
    if t - max(LOOKBACKS) < 0 or not vol:
        return None
    out = {}
    for k in LOOKBACKS:
        z = math.log(prices[t] / prices[t - k]) / (vol * math.sqrt(k))
        out[k] = max(-1.0, min(1.0, z))
    return out


def signal_at(prices: list[float], t: int, vol: float | None = None) -> tuple[float | None, dict[int, float] | None]:
    v = vol if vol is not None else daily_vol(prices, t)
    c = components(prices, t, v) if v else None
    return (sum(c.values()) / len(c), c) if c else (None, None)


def exposure(signal: float | None, vol: float | None) -> float | None:
    """Vol-targeted exposure as a share of capital (1.0 = 100% notional)."""
    if signal is None or not vol:
        return None
    ann = vol * math.sqrt(TRADING_DAYS)
    return max(-MAX_EXPOSURE, min(MAX_EXPOSURE, signal * TARGET_VOL_ANN / ann))


def scenario_paths(prices: list[float], vol: float, horizon: int = HORIZON) -> dict[str, Any]:
    """Signal and model PnL on each of the next `horizon` days along each path.

    The volatility is held at today's value along the path so the paths differ
    only by price direction, as in a conditional projection.
    """
    sigma = vol * math.sqrt(horizon)
    p0 = prices[-1]
    sig_out, pnl_out = {}, {}
    for key, _ko, m in SCENARIOS:
        ext = list(prices)
        expo_prev = exposure(signal_at(ext, len(ext) - 1, vol)[0], vol)
        path, pnl, cum = [], [], 0.0
        for d in range(1, horizon + 1):
            ext.append(p0 * math.exp(m * sigma * d / horizon))
            r = ext[-1] / ext[-2] - 1
            cum += (expo_prev or 0.0) * r
            s, _ = signal_at(ext, len(ext) - 1, vol)
            path.append(round(s, 4) if s is not None else None)
            pnl.append(round(cum * 100, 3))
            expo_prev = exposure(s, vol)
        sig_out[key] = path
        pnl_out[key] = pnl
    return {"signal": sig_out, "pnl_pct": pnl_out}


def trigger_levels(prices: list[float]) -> dict[str, Any]:
    """Tomorrow's close at which the combined signal hits 0, +1 and -1.

    Bisection on a full recomputation with the candidate close appended (it
    also enters the 60-day vol). Searched within +-60% of today's close; a
    level outside that range is reported as unreachable (None).
    """
    p0 = prices[-1]

    def s_of(p: float) -> float:
        ext = prices + [p]
        return signal_at(ext, len(ext) - 1)[0]

    lo_p, hi_p = p0 * 0.4, p0 * 1.6
    s_lo, s_hi = s_of(lo_p), s_of(hi_p)

    def solve(target: float) -> float | None:
        if not (min(s_lo, s_hi) <= target <= max(s_lo, s_hi)):
            return None
        a, b = lo_p, hi_p
        for _ in range(60):
            mid = math.sqrt(a * b)
            if (s_of(mid) - target) * (s_of(a) - target) <= 0:
                b = mid
            else:
                a = mid
        return math.sqrt(a * b)

    out = {}
    for key, target in (("zero", 0.0), ("full_long", 0.999), ("full_short", -0.999)):
        p = solve(target)
        out[key] = None if p is None else {"price": round(p, 2), "dist_pct": round((p / p0 - 1) * 100, 2)}
    return out


def model_pnl(prices: list[float], sig: list[float | None]) -> list[float | None]:
    """Cumulative model PnL in % of capital: exposure_{t-1} * return_t."""
    out: list[float | None] = []
    cum = 0.0
    started = False
    for t in range(len(prices)):
        if t == 0 or sig[t - 1] is None:
            out.append(round(cum * 100, 3) if started else None)
            continue
        e = exposure(sig[t - 1], daily_vol(prices, t - 1))
        cum += (e or 0.0) * (prices[t] / prices[t - 1] - 1)
        started = True
        out.append(round(cum * 100, 3))
    return out


def next_weekdays(start: str, n: int) -> list[str]:
    """Approximate future trading dates: weekdays only, holidays not modelled."""
    d = date.fromisoformat(start)
    out = []
    while len(out) < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            out.append(d.isoformat())
    return out


def threshold_calendar(prices: list[float], dates: list[str], horizon: int = HORIZON) -> list[dict[str, Any]]:
    """For each of the next `horizon` trading days, each lookback's reference
    price P_{t+d-k} and its distance from today's close."""
    t = len(prices) - 1
    p = prices[t]
    future = next_weekdays(dates[t], horizon)
    rows = []
    for d in range(1, horizon + 1):
        refs = {}
        near = []
        for k in LOOKBACKS:
            i = t + d - k
            if 0 <= i <= t:
                dist = (prices[i] / p - 1) * 100
                refs[str(k)] = {"ref_date": dates[i], "ref_price": round(prices[i], 2), "dist_pct": round(dist, 2)}
                if abs(dist) <= NEAR_PCT:
                    near.append(k)
        rows.append({"d": d, "date_est": future[d - 1], "refs": refs, "near": near})
    return rows


# --- realized comparison ------------------------------------------------------

def _corr(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 10:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sxx * syy), 3)


def _weeks(dates: list[str], sig: list[float | None], flow_by_date: dict[str, float]) -> list[dict[str, Any]]:
    weeks: dict[str, dict[str, Any]] = {}
    for d, s in zip(dates, sig):
        if s is None:
            continue
        y, w, _ = date.fromisoformat(d).isocalendar()
        wk = weeks.setdefault(f"{y}-W{w:02d}", {"last_sig": None, "flow": 0.0, "n": 0})
        wk["last_sig"] = s
        if d in flow_by_date:
            wk["flow"] += flow_by_date[d]
            wk["n"] += 1
    keys = sorted(weeks)
    out = []
    for a, b in zip(keys, keys[1:]):
        out.append({"dsig": weeks[b]["last_sig"] - weeks[a]["last_sig"], "sig": weeks[b]["last_sig"],
                    "flow": weeks[b]["flow"] if weeks[b]["n"] else None})
    return out


def weekly_corr(dates: list[str], sig: list[float | None], flow_by_date: dict[str, float]) -> dict[str, Any]:
    """Weekly signal change vs net buying: same week, next week (signal
    leads), previous week (flow leads), and same week split by signal sign."""
    w = _weeks(dates, sig, flow_by_date)

    def pairs(lag: int, cond=None):
        xs, ys = [], []
        for i in range(len(w)):
            j = i + lag
            if not 0 <= j < len(w) or w[j]["flow"] is None:
                continue
            if cond and not cond(w[i]):
                continue
            xs.append(w[i]["dsig"])
            ys.append(w[j]["flow"])
        return xs, ys

    same = pairs(0)
    return {
        "corr": _corr(*same), "n_weeks": len(same[0]),
        "next_week": _corr(*pairs(1)), "prev_week": _corr(*pairs(-1)),
        "when_long": _corr(*pairs(0, lambda x: x["sig"] > 0)),
        "when_short": _corr(*pairs(0, lambda x: x["sig"] < 0)),
    }


# --- price translation ----------------------------------------------------------

def contracts_per_1jo(expo: float | None, price: float) -> int | None:
    return None if expo is None else round(expo * 1e12 / (price * K200_MULTIPLIER))


def price_ladder(prices: list[float], kospi_ratio: float | None) -> list[dict[str, Any]]:
    """Tomorrow's close at fixed % moves -> signal, exposure, and the contracts a
    1조원 book would trade to get there (full recomputation, vol included)."""
    p0 = prices[-1]
    vol0 = daily_vol(prices, len(prices) - 1)
    e0 = exposure(signal_at(prices, len(prices) - 1, vol0)[0], vol0)
    c0 = contracts_per_1jo(e0, p0)
    rows = []
    for pct in LADDER_PCT:
        px = p0 * (1 + pct / 100)
        ext = prices + [px]
        v = daily_vol(ext, len(ext) - 1)
        sgl = signal_at(ext, len(ext) - 1, v)[0]
        e = exposure(sgl, v)
        c = contracts_per_1jo(e, px)
        rows.append({"pct": pct, "price": round(px, 2),
                     "kospi": round(px * kospi_ratio, 1) if kospi_ratio else None,
                     "signal": round(sgl, 4), "exposure_pct": round(e * 100, 1),
                     "contracts_per_1jo": c, "trade_per_1jo": None if c is None or c0 is None else c - c0})
    return rows


def scenario_flows(prices: list[float], vol: float, paths: dict[str, list[float | None]]) -> dict[str, Any]:
    """Contracts a 1조원 book would have bought (+) or sold (-) after 5 and 21
    days along each scenario path."""
    p0 = prices[-1]
    sigma = vol * math.sqrt(HORIZON)
    c0 = contracts_per_1jo(exposure(signal_at(prices, len(prices) - 1, vol)[0], vol), p0)
    out = {}
    for key, _ko, m in SCENARIOS:
        row = {}
        for d in (5, HORIZON):
            sgl = paths[key][d - 1]
            px = p0 * math.exp(m * sigma * d / HORIZON)
            c = contracts_per_1jo(exposure(sgl, vol), px)
            row[f"d{d}"] = None if c is None or c0 is None else c - c0
        out[key] = row
    return out


# --- quarterly expiry (네 마녀의 날) ------------------------------------------------

def second_thursday(y: int, m: int) -> date:
    d = date(y, m, 1)
    d += timedelta(days=(3 - d.weekday()) % 7)
    return d + timedelta(days=7)


def quad_witching_days(dates: list[str]) -> list[str]:
    """Quarterly KOSPI 200 futures/options expiry: the 2nd Thursday of
    Mar/Jun/Sep/Dec, or the last trading day before it when it is a holiday."""
    out = []
    years = sorted({int(d[:4]) for d in dates})
    for y in years:
        for m in QUAD_MONTHS:
            t = second_thursday(y, m).isoformat()
            cand = [d for d in dates if d[:7] == t[:7] and d <= t]
            if cand and dates[-1] >= t:
                out.append(cand[-1])
    return out


def _median(v: list[float]) -> float | None:
    if not v:
        return None
    v = sorted(v)
    n = len(v)
    return round(v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2, 2)


def expiry_vol(ohlc: dict[str, dict[str, float]]) -> dict[str, Any] | None:
    """|close-to-close move| and intraday range on quad-witching days, the day
    before and the day after, against every other day."""
    dates = sorted(ohlc)
    if len(dates) < 60:
        return None
    idx = {d: i for i, d in enumerate(dates)}
    stats = []
    for i in range(1, len(dates)):
        prev, r = ohlc[dates[i - 1]]["c"], ohlc[dates[i]]
        ret = (r["c"] / prev - 1) * 100
        rng = (r["h"] - r["l"]) / prev * 100 if r.get("h") and r.get("l") else None
        stats.append((dates[i], ret, rng))
    by_date = {d: (ret, rng) for d, ret, rng in stats}
    qw = [d for d in quad_witching_days(dates) if d in by_date]
    qset = set(qw)
    near = {dates[idx[d] + k] for d in qw for k in (-1, 1) if 0 <= idx[d] + k < len(dates)}

    def summ(ds):
        rets = [abs(by_date[d][0]) for d in ds if d in by_date]
        rngs = [by_date[d][1] for d in ds if d in by_date and by_date[d][1] is not None]
        if not rets:
            return None
        return {"n": len(rets), "abs_ret_pct": round(sum(rets) / len(rets), 2),
                "range_pct": round(sum(rngs) / len(rngs), 2) if rngs else None,
                "big_move_share": round(sum(1 for x in rets if x >= 2) / len(rets) * 100, 1)}

    events = []
    for d in qw:
        i = idx[d]
        prior = [by_date[x][1] for x in dates[max(1, i - 20):i] if by_date.get(x) and by_date[x][1] is not None]
        base = sum(prior) / len(prior) if prior else None
        ret, rng = by_date[d]
        nxt = by_date.get(dates[i + 1]) if i + 1 < len(dates) else None
        events.append({"date": d, "ret_pct": round(ret, 2), "range_pct": round(rng, 2) if rng is not None else None,
                       "range_vs_20d": round(rng / base, 2) if rng is not None and base else None,
                       "next_ret_pct": round(nxt[0], 2) if nxt else None})
    today = date.fromisoformat(dates[-1])
    nxt_dates = [second_thursday(y, m) for y in (today.year, today.year + 1) for m in QUAD_MONTHS]
    upcoming = min(d for d in nxt_dates if d > today)
    return {
        "dates": qw, "upcoming": upcoming.isoformat(),
        "summary": {"witching": summ(qw), "day_before": summ([dates[idx[d] - 1] for d in qw if idx[d] > 0]),
                    "day_after": summ([dates[idx[d] + 1] for d in qw if idx[d] + 1 < len(dates)]),
                    "other": summ([d for d, _, _ in stats if d not in qset and d not in near])},
        "range_vs_20d_median": _median([e["range_vs_20d"] for e in events if e["range_vs_20d"] is not None]),
        "range_vs_20d_above_share": round(sum(1 for e in events if (e["range_vs_20d"] or 0) > 1) / len(events) * 100, 1) if events else None,
        "events": events[-12:],
        "from": dates[0], "to": dates[-1],
    }


# --- other markets ----------------------------------------------------------------

def asset_block(dates: list[str], prices: list[float]) -> dict[str, Any] | None:
    if len(prices) < max(LOOKBACKS) + VOL_WINDOW:
        return None
    t = len(prices) - 1
    vol = daily_vol(prices, t)
    sgl, comps = signal_at(prices, t, vol)
    sig = [signal_at(prices, i)[0] for i in range(len(prices))]
    pnl = model_pnl(prices, sig)
    trig = trigger_levels(prices)
    return {"as_of": dates[t], "close": round(prices[t], 4), "signal": round(sgl, 4),
            "components": {str(k): round(v, 4) for k, v in comps.items()},
            "exposure_pct": round(exposure(sgl, vol) * 100, 1),
            "vol_ann_pct": round(vol * math.sqrt(TRADING_DAYS) * 100, 1),
            "zero": trig["zero"],
            "pnl_20d_pct": round(pnl[-1] - pnl[-21], 3) if pnl[-21] is not None else None,
            "_pnl": dict(zip(dates, pnl))}


def multi_asset(series: dict[str, dict[str, float]], proxy: dict[str, float] | None,
                kospi_pnl: dict[str, float | None]) -> dict[str, Any] | None:
    """Same model on each market, an equal-risk book of all of them (the K200
    leg included), and that book's correlation with a CTA replication ETF."""
    blocks = {}
    for key, ko, sym, cls in ASSETS:
        px = series.get(key) or {}
        ds = sorted(px)
        b = asset_block(ds, [px[d] for d in ds]) if ds else None
        if b:
            blocks[key] = {"label_ko": ko, "symbol": sym, "class_ko": cls, **b}
    if not blocks:
        return None
    # Each leg is already vol-targeted, so an equal-weight average of their
    # daily PnL changes is an equal-risk book.
    legs = [b["_pnl"] for b in blocks.values()] + [kospi_pnl]
    all_dates = sorted(set().union(*[set(l) for l in legs]))
    book, cum, prev = [], 0.0, [None] * len(legs)
    for d in all_dates:
        chg = []
        for j, l in enumerate(legs):
            v = l.get(d)
            if v is not None and prev[j] is not None:
                chg.append(v - prev[j])
            if v is not None:
                prev[j] = v
        if chg:
            cum += sum(chg) / len(chg)
        book.append(round(cum, 3))
    peak = max(book)
    out = {"assets": {k: {kk: vv for kk, vv in b.items() if kk != "_pnl"} for k, b in blocks.items()},
           "book": {"dates": all_dates[-HISTORY_DAYS:], "pnl_pct": book[-HISTORY_DAYS:],
                    "pnl_20d_pct": round(book[-1] - book[-21], 3) if len(book) > 21 else None,
                    "drawdown_pct": round(book[-1] - peak, 3)}}
    if proxy:
        bd = dict(zip(all_dates, book))
        ds = [d for d in sorted(proxy) if d in bd]
        xs, ys = [], []
        for a, b in zip(ds, ds[1:]):
            xs.append(bd[b] - bd[a])
            ys.append((proxy[b] / proxy[a] - 1) * 100)
        wk = lambda v: [sum(v[i:i + 5]) for i in range(0, len(v) - 4, 5)]
        out["proxy"] = {"label_ko": CTA_PROXY[1], "daily_corr": _corr(xs[-250:], ys[-250:]),
                        "weekly_corr": _corr(wk(xs[-250:]), wk(ys[-250:])), "n_days": min(len(xs), 250)}
    return out


# --- assembly -----------------------------------------------------------------

def price_series(flow: dict[str, Any], k200: dict[str, float] | None) -> tuple[list[str], list[float], str, list[str]]:
    if k200:
        dates = sorted(k200)
        return dates, [k200[d] for d in dates], "코스피200 지수 종가", []
    front = flow.get("futures_front") or {}
    closes = front.get("close") or []
    contracts = front.get("contract") or []
    obs = [(d, float(c), contracts[i] if i < len(contracts) else None)
           for i, (d, c) in enumerate(zip(flow["dates"], closes)) if isinstance(c, (int, float)) and c > 0]
    rolls = [obs[i][0] for i in range(1, len(obs)) if obs[i][2] and obs[i - 1][2] and obs[i][2] != obs[i - 1][2]]
    return [o[0] for o in obs], [o[1] for o in obs], "코스피200 선물 최근월물 종가 (정규장, 롤 보정 없음)", rolls


def build(flow: dict[str, Any], k200: dict[str, float] | None = None,
          kospi: dict[str, float] | None = None, ohlc: dict[str, dict[str, float]] | None = None,
          markets: dict[str, dict[str, float]] | None = None, proxy: dict[str, float] | None = None) -> dict[str, Any]:
    dates, prices, source_ko, rolls = price_series(flow, k200)
    if len(prices) < max(LOOKBACKS) + VOL_WINDOW:
        raise ValueError("not enough observed closes for the 12-month lookback")

    sig: list[float | None] = []
    for t in range(len(prices)):
        s, _ = signal_at(prices, t)
        sig.append(round(s, 4) if s is not None else None)

    t = len(prices) - 1
    vol = daily_vol(prices, t)
    s_now, comps = signal_at(prices, t, vol)
    sigma_1m = vol * math.sqrt(HORIZON)
    flips = []
    for k in LOOKBACKS:
        ref = prices[t + 1 - k]
        flips.append({"k": k, "label_ko": LOOKBACK_KO[k], "component": round(comps[k], 4),
                      "flip_price": round(ref, 2), "flip_ref_date": dates[t + 1 - k],
                      "dist_pct": round((ref / prices[t] - 1) * 100, 2),
                      "dist_sigma_1m": round(math.log(ref / prices[t]) / sigma_1m, 2)})
    expo = exposure(s_now, vol)
    pnl = model_pnl(prices, sig)
    pnl_obs = [p for p in pnl if p is not None]
    peak = max(pnl_obs) if pnl_obs else None
    scen = scenario_paths(prices, vol)
    ratio = kospi[dates[t]] / prices[t] if kospi and dates[t] in kospi and k200 else None
    triggers = trigger_levels(prices)
    if ratio:
        for x in triggers.values():
            if x:
                x["kospi"] = round(x["price"] * ratio, 1)
        for f in flips:
            f["kospi"] = round(f["flip_price"] * ratio, 1)
    kh = [kospi.get(d) for d in dates] if kospi else None

    all_dates = flow["dates"]
    fl = (flow.get("flow") or {}).get("futures") or {}

    def series(col: str) -> dict[str, float]:
        vals = fl.get(col) or []
        return {d: float(v) for d, v in zip(all_dates, vals) if isinstance(v, (int, float))}

    foreign = series("foreign_net")
    corr = {inv: weekly_corr(dates, sig, series(f"{inv}_net")) for inv in ("foreign", "institution", "retail")}

    def roll_sum(m: dict[str, float], n: int) -> list[float | None]:
        out = []
        for i in range(len(dates)):
            win = [m[d] for d in dates[max(0, i - n + 1): i + 1] if d in m]
            out.append(round(sum(win)) if len(win) >= n * 0.8 else None)
        return out

    foreign_60 = roll_sum(foreign, 60)
    lvl = [(s, f) for s, f in zip(sig, foreign_60) if s is not None and f is not None]
    flow_dates = [d for d in all_dates if d in foreign]
    last_flow = flow_dates[-1] if flow_dates else None
    h = slice(-HISTORY_DAYS, None)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": dates[t],
        "price_source_ko": source_ko,
        "model": {"lookbacks": list(LOOKBACKS), "vol_window": VOL_WINDOW, "horizon": HORIZON, "near_pct": NEAR_PCT,
                  "target_vol_ann": TARGET_VOL_ANN, "max_exposure": MAX_EXPOSURE,
                  "scenarios": [{"key": k, "label_ko": ko, "m": m} for k, ko, m in SCENARIOS]},
        "latest": {
            "date": dates[t], "close": prices[t], "signal": round(s_now, 4),
            "daily_vol": round(vol, 5), "vol_ann_pct": round(vol * math.sqrt(TRADING_DAYS) * 100, 1),
            "sigma_1m_pct": round(sigma_1m * 100, 2), "flips": flips,
            "triggers": triggers, "kospi_ratio": round(ratio, 4) if ratio else None,
            "kospi_close": kospi.get(dates[t]) if kospi else None,
            "exposure_pct": round(expo * 100, 1),
            # contracts per 1조원 of AUM at that exposure
            "contracts_per_1jo": round(expo * 1e12 / (prices[t] * K200_MULTIPLIER)),
            "pnl_pct": pnl[-1], "pnl_peak_pct": peak,
            "pnl_drawdown_pct": round(pnl[-1] - peak, 3) if peak is not None and pnl[-1] is not None else None,
            "pnl_20d_pct": round(pnl[-1] - pnl[-21], 3) if len(pnl) > 21 and pnl[-21] is not None else None,
            "pnl_60d_pct": round(pnl[-1] - pnl[-61], 3) if len(pnl) > 61 and pnl[-61] is not None else None,
        },
        "history": {"dates": dates[h], "close": prices[h], "kospi": kh[h] if kh else None,
                    "signal": sig[h], "pnl_pct": pnl[h],
                    "foreign_net_60d": foreign_60[h]},
        "scenarios": {"dates_est": next_weekdays(dates[t], HORIZON), **scen["signal"],
                      "pnl_pct": scen["pnl_pct"], "flows_per_1jo": scenario_flows(prices, vol, scen["signal"])},
        "ladder": price_ladder(prices, ratio),
        "expiry_vol": expiry_vol(ohlc) if ohlc else None,
        "multi_asset": multi_asset(markets, proxy, dict(zip(dates, pnl))) if markets else None,
        "threshold_calendar": threshold_calendar(prices, dates),
        "realized": {
            "flow_as_of": last_flow,
            "weekly_change_corr": corr,
            "level_corr_foreign_60d": _corr([a for a, _ in lvl], [b for _, b in lvl]),
            "foreign_20d_krw": round(sum(foreign[d] for d in flow_dates[-20:]) * 1e6),
            "foreign_60d_krw": round(sum(foreign[d] for d in flow_dates[-60:]) * 1e6),
        },
        "rolls": rolls,
        "notes_ko": [
            "CTA(추세추종 선물 펀드)의 기계적 규칙을 코스피200에 적용한 추정입니다. 실제 CTA 포지션이 아닙니다.",
            "신호 = 1·3·6·12개월 수익률을 각각 60일 변동성으로 나눠 ±1로 자른 값의 평균. -1 최대 숏, +1 최대 롱.",
            f"노출 = 신호 × (목표 변동성 연 {TARGET_VOL_ANN * 100:.0f}% ÷ 실현 변동성), ±{MAX_EXPOSURE * 100:.0f}% 상한. 모델 PnL = 전날 노출 × 당일 수익률 (비용·금리 제외).",
            "트리거 레벨 = 내일 종가가 그 값이면 종합 신호가 0(롱·숏 전환), +1(최대 롱), -1(최대 숏)이 되는 가격. 새 종가가 60일 변동성에도 들어가도록 전체를 다시 계산해 구합니다.",
            "운용자산 규모를 모르므로 원화 포지션은 계산하지 않고, 운용자산 1조원당 계약 수로만 보입니다.",
            "외국인 선물 계좌에는 현물 헤지·차익·스왑이 섞여 있어 CTA 신호와의 연결이 약합니다. 상관을 그대로 적습니다.",
        ],
    }


def _k200_file() -> dict[str, dict[str, float]]:
    """KRX 개별지수 history committed to the repo (OHLC, observed rows only)."""
    path = DATA / "kospi200_index_daily_v1.json"
    if not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8")).get("rows") or []
    return {r["date"]: {"o": r.get("open"), "h": r.get("high"), "l": r.get("low"), "c": float(r["close"])}
            for r in rows if isinstance(r.get("close"), (int, float)) and r["close"] > 0 and r.get("quality", "observed") == "observed"}


def _fdr(symbol: str, start: str = "2018-01-01") -> dict[str, dict[str, float]]:
    import FinanceDataReader as fdr

    df = fdr.DataReader(symbol, start)
    out = {}
    for i, r in df.iterrows():
        c = r.get("Close")
        if c is None or c != c or c <= 0:
            continue
        out[i.strftime("%Y-%m-%d")] = {"o": float(r.get("Open") or 0) or None, "h": float(r.get("High") or 0) or None,
                                       "l": float(r.get("Low") or 0) or None, "c": float(c)}
    return out


def _yahoo(symbols: list[str], start: str = "2018-01-01") -> dict[str, dict[str, float]]:
    try:
        import yfinance as yf
    except ImportError as exc:
        print(f"yfinance unavailable, no other markets: {exc}", file=sys.stderr)
        return {}

    out = {}
    for sym in symbols:
        try:
            df = yf.Ticker(sym).history(start=start, auto_adjust=False)
        except Exception as exc:  # noqa: BLE001
            print(f"{sym}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        if df is None or df.empty or "Close" not in df:
            print(f"{sym}: no rows", file=sys.stderr)
            continue
        out[sym] = {i.strftime("%Y-%m-%d"): float(c) for i, c in df["Close"].items() if c == c and c > 0}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--flow", type=Path, default=DATA / "krx_deriv_flow_v1.json")
    ap.add_argument("--out", type=Path, default=DATA / "krx_cta_v1.json")
    ap.add_argument("--live", action="store_true", help="price the model on FDR KS200 (default: futures close)")
    ap.add_argument("--print-stats", action="store_true")
    args = ap.parse_args()
    flow = json.loads(args.flow.read_text(encoding="utf-8"))
    ohlc = _k200_file()
    kospi = markets = proxy = None
    if args.live:
        try:
            ohlc.update(_fdr("KS200"))
        except Exception as exc:  # noqa: BLE001
            print(f"KS200 unavailable, using the committed KRX index file: {type(exc).__name__}: {exc}", file=sys.stderr)
        try:
            kospi = {d: r["c"] for d, r in _fdr("KS11").items()}
        except Exception as exc:  # noqa: BLE001
            print(f"KS11 unavailable, no KOSPI translation: {type(exc).__name__}: {exc}", file=sys.stderr)
        got = _yahoo([sym for _, _, sym, _ in ASSETS] + [CTA_PROXY[0]])
        markets = {key: got[sym] for key, _, sym, _ in ASSETS if got.get(sym)}
        proxy = got.get(CTA_PROXY[0])
    k200 = {d: r["c"] for d, r in ohlc.items()} or None
    payload = build(flow, k200, kospi, ohlc, markets or None, proxy)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    if args.print_stats:
        L = payload["latest"]
        print(json.dumps({"as_of": L["date"], "source": payload["price_source_ko"], "close": L["close"],
                          "signal": L["signal"], "sigma_1m_pct": L["sigma_1m_pct"], "triggers": L["triggers"],
                          "exposure_pct": L["exposure_pct"], "contracts_per_1jo": L["contracts_per_1jo"],
                          "pnl": [L["pnl_pct"], L["pnl_peak_pct"], L["pnl_drawdown_pct"], L["pnl_20d_pct"]],
                          "flips": [(f["k"], f["component"], f["flip_price"], f["dist_pct"]) for f in L["flips"]],
                          "scen_pnl": {k: v[-1] for k, v in payload["scenarios"]["pnl_pct"].items()},
                          "corr": payload["realized"]["weekly_change_corr"]["foreign"],
                          "expiry": (payload["expiry_vol"] or {}).get("summary"),
                          "assets": sorted(((payload["multi_asset"] or {}).get("assets") or {})),
                          "bytes": args.out.stat().st_size}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
