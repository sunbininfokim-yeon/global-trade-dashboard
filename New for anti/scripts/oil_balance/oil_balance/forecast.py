"""Brent: estimate a fair value, then forecast from assumptions that will keep changing.

Three layers, kept apart so that a change in one does not hide in another:

  1 identity     supply - demand = stock change (OECD + China + everything else). Cannot be wrong; used to
                 catch assumptions that contradict each other.
  2 relation     log Brent = b0 + b1 * OECD stocks vs the same month's five-year average (mb)
                          + b2 * OPEC spare capacity (mbd) + b3 * log broad dollar (FRED DTWEXBGS)
                 Monthly, nominal, 2006-2025. Chosen by reverse-engineering a bank's published diagnostics
                 (largest premium ~$24, premiums above $10 lasting ~4 months); re-run against rival
                 structures every build (`compete`) and checked for coefficient drift (`rolling`).
  3 assumptions  the forward path of stocks, spare capacity and the dollar, plus scenarios with
                 probabilities -- config/assumptions_v1.json, every number with its source and date.

Forecast = fair value on the assumed path + today's premium decaying at the rate the residual has decayed
historically (AR(1)), with Monte Carlo bands from coefficient uncertainty (Newey-West), residual shocks,
the input ranges and the scenario draw. `backtest` replays the method from each December's STEO since
2012 and scores it against EIA's own Brent forecast and a no-change forecast.

The same engine runs in the browser (oil-balance.js) so the inputs can be changed on screen; keep the two
in step.
"""

from __future__ import annotations

import math
import random
import statistics as st
from typing import Any

SPEC = ("dev_mb", "spare", "log_dxy")
FIT_FROM, FIT_TO = "2008-01", "2025-12"   # stock deviations need five years of history from 2003
MONTH_DAYS = 30.4
NW_LAGS = 12
LABELS = {"dev_mb": "OECD 재고 편차(백만 배럴)", "dev_days": "OECD 재고 일수 편차", "spare": "OPEC 여유능력", "log_dxy": "달러(로그)"}


# ---------------------------------------------------------------- data shaping

def dev5(x: dict[str, float]) -> dict[str, float]:
    """Each month minus the average of the same month in the five years before."""
    out = {}
    for m, v in x.items():
        prev = [x.get(f"{int(m[:4]) - k}{m[4:]}") for k in range(1, 6)]
        if all(p is not None for p in prev):
            out[m] = v - sum(prev) / 5
    return out


def features(stocks: dict[str, float], oecd_demand: dict[str, float], spare: dict[str, float],
             dxy: dict[str, float]) -> dict[str, dict[str, float]]:
    days = {m: stocks[m] / oecd_demand[m] for m in stocks if oecd_demand.get(m)}
    return {"dev_mb": dev5(stocks), "dev_days": dev5(days), "spare": dict(spare),
            "log_dxy": {m: math.log(v) for m, v in dxy.items() if v > 0}}


def next_month(m: str, k: int = 1) -> str:
    y, mo = int(m[:4]), int(m[5:7]) - 1 + k
    return f"{y + mo // 12}-{mo % 12 + 1:02d}"


# ---------------------------------------------------------------- least squares

def _inv(a: list[list[float]]) -> list[list[float]]:
    n = len(a)
    m = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        piv = m[c][c]
        m[c] = [v / piv for v in m[c]]
        for r in range(n):
            if r != c and m[r][c]:
                f = m[r][c]
                m[r] = [a_ - f * b_ for a_, b_ in zip(m[r], m[c])]
    return [row[n:] for row in m]


def _mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[sum(a[i][k] * b[k][j] for k in range(len(b))) for j in range(len(b[0]))] for i in range(len(a))]


def ols(y: list[float], x: list[list[float]], lags: int = NW_LAGS) -> dict[str, Any]:
    """y on a constant and x. Covariance is Newey-West (Bartlett, `lags`): monthly residuals here are
    strongly autocorrelated, and plain OLS errors would make the coefficients look three times surer."""
    rows = [[1.0] + list(r) for r in x]
    n, k = len(rows), len(rows[0])
    xtx = [[sum(r[a] * r[b] for r in rows) for b in range(k)] for a in range(k)]
    xty = [sum(r[a] * yy for r, yy in zip(rows, y)) for a in range(k)]
    inv = _inv(xtx)
    beta = [sum(inv[a][b] * xty[b] for b in range(k)) for a in range(k)]
    e = [yy - sum(b * v for b, v in zip(beta, r)) for r, yy in zip(rows, y)]
    s = [[sum(e[t] ** 2 * rows[t][a] * rows[t][b] for t in range(n)) for b in range(k)] for a in range(k)]
    for lag in range(1, min(lags, n - 1) + 1):
        w = 1 - lag / (lags + 1)
        for a in range(k):
            for b in range(k):
                g = sum(e[t] * e[t - lag] * (rows[t][a] * rows[t - lag][b] + rows[t - lag][a] * rows[t][b]) for t in range(lag, n))
                s[a][b] += w * g
    cov = _mul(_mul(inv, s), inv)
    my = st.mean(y)
    r2 = 1 - sum(v * v for v in e) / sum((yy - my) ** 2 for yy in y)
    return {"beta": beta, "cov": cov, "se": [math.sqrt(max(cov[i][i], 0.0)) for i in range(k)], "r2": r2,
            "sigma": math.sqrt(sum(v * v for v in e) / max(n - k, 1)), "n": n, "resid": e}


def usable(price: dict[str, float], X: dict[str, dict[str, float]], vars_, lo: str, hi: str) -> list[str]:
    return [m for m in sorted(price) if lo <= m <= hi and all(m in X[v] for v in vars_)]


def fit(price: dict[str, float], X: dict[str, dict[str, float]], vars_=SPEC, lo: str = FIT_FROM, hi: str = FIT_TO) -> dict[str, Any]:
    ms = usable(price, X, vars_, lo, hi)
    o = ols([math.log(price[m]) for m in ms], [[X[v][m] for v in vars_] for m in ms])
    o.update({"vars": list(vars_), "months": ms, "from": ms[0], "to": ms[-1], "resid": dict(zip(ms, o["resid"]))})
    return o


def log_fv(beta: list[float], vars_, X: dict[str, dict[str, float]], m: str) -> float:
    return beta[0] + sum(b * X[v][m] for b, v in zip(beta[1:], vars_))


def fair_value(coef: dict[str, Any], X: dict[str, dict[str, float]]) -> dict[str, float]:
    vs = coef["vars"]
    ms = set.intersection(*(set(X[v]) for v in vs))
    return {m: math.exp(log_fv(coef["beta"], vs, X, m)) for m in sorted(ms)}


def ar1(resid: list[float]) -> dict[str, float]:
    rho = sum(a * b for a, b in zip(resid[1:], resid[:-1])) / sum(a * a for a in resid[:-1])
    return {"rho": rho, "half_life": math.log(0.5) / math.log(rho) if 0 < rho < 1 else None,
            "sd": st.pstdev(resid), "innov_sd": st.pstdev([a - rho * b for a, b in zip(resid[1:], resid[:-1])])}


def runs(flags: list[bool]) -> list[int]:
    out, n = [], 0
    for f in flags + [False]:
        if f:
            n += 1
        elif n:
            out.append(n)
            n = 0
    return out


# ---------------------------------------------------------------- layer 2 checks

def oos(price, X, vars_, lo: str, years: list[int], min_train: int = 36) -> dict[int, float]:
    """Fit through December of the year before, then price each month of the year from that month's actual
    stocks, spare capacity and dollar: the error of the structure alone, before any assumption is wrong."""
    out = {}
    for y in years:
        tr = usable(price, X, vars_, lo, f"{y - 1}-12")
        te = usable(price, X, vars_, f"{y}-01", f"{y}-12")
        if len(tr) < min_train or not te:
            continue
        b = ols([math.log(price[m]) for m in tr], [[X[v][m] for v in vars_] for m in tr], lags=0)["beta"]
        out[y] = st.mean(abs(price[m] - math.exp(log_fv(b, vars_, X, m))) for m in te)
    return out


def compete(price, X, years: list[int], windows=(FIT_FROM, "2015-01"), hi: str = FIT_TO) -> list[dict[str, Any]]:
    """Every combination of an inventory measure, spare capacity and the dollar, on two fit windows.
    Scored on the out-of-sample years all candidates share, and on how closely the premium episodes match
    the published diagnostics (largest premium, months a premium above $10 lasts)."""
    cands = []
    for inv in ("dev_mb", "dev_days"):
        for sp in (0, 1):
            for dx in (0, 1):
                for lo in windows:
                    cands.append(([inv] + (["spare"] if sp else []) + (["log_dxy"] if dx else []), lo))
    rows = []
    for vars_, lo in cands:
        c = fit(price, X, vars_, lo, hi)
        ev = usable(price, X, vars_, FIT_FROM, hi)
        gap = {m: price[m] - math.exp(log_fv(c["beta"], vars_, X, m)) for m in ev}
        big = runs([gap[m] > 10 for m in ev])
        rows.append({"vars": vars_, "from": c["from"], "to": c["to"], "r2": round(c["r2"], 3),
                     "oos": oos(price, X, vars_, lo, years), "max_premium": round(max(gap.values()), 1),
                     "max_premium_month": max(gap, key=gap.get),
                     "avg_months_above_10": round(st.mean(big), 1) if big else None})
    common = sorted(set.intersection(*(set(r["oos"]) for r in rows)))
    for r in rows:
        r["oos_mae"] = round(st.mean(r["oos"][y] for y in common), 2)
        r["oos"] = {str(y): round(v, 1) for y, v in sorted(r["oos"].items())}
    rows.sort(key=lambda r: r["oos_mae"])
    return rows, common


def rolling(price, X, vars_=SPEC, starts=("2006-01", "2011-01", "2016-01", "2021-01"), length: int = 60, hi: str = FIT_TO):
    """The same structure on separate five-year windows: a coefficient whose sign or size swings between
    windows is one the forecast should not lean on."""
    out = []
    for lo in starts:
        end = next_month(lo, length - 1)
        ms = usable(price, X, vars_, lo, min(end, hi))
        if len(ms) < 40:
            continue
        o = ols([math.log(price[m]) for m in ms], [[X[v][m] for v in vars_] for m in ms])
        out.append({"from": ms[0], "to": ms[-1], "n": len(ms), "r2": round(o["r2"], 2),
                    "beta": {v: round(b, 5) for v, b in zip(vars_, o["beta"][1:])},
                    "se": {v: round(s, 5) for v, s in zip(vars_, o["se"][1:])}})
    return out


def stability_flags(full: dict[str, Any], windows: list[dict[str, Any]]) -> dict[str, str]:
    """Per variable: 'stable' when every window has the full-sample sign, 'weakening' when the latest window
    is under half the full-sample size, 'flipped' when any window has the opposite sign."""
    out = {}
    for i, v in enumerate(full["vars"]):
        b = full["beta"][i + 1]
        ws = [w["beta"][v] for w in windows]
        if any(math.copysign(1, x) != math.copysign(1, b) for x in ws):
            out[v] = "flipped"
        elif ws and abs(ws[-1]) < abs(b) / 2:
            out[v] = "weakening"
        else:
            out[v] = "stable"
    return out


# ---------------------------------------------------------------- layer 3: forecast engine

def chol(a: list[list[float]]) -> list[list[float]]:
    n = len(a)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = a[i][j] - sum(L[i][k] * L[j][k] for k in range(j))
            L[i][j] = math.sqrt(max(s, 1e-18)) if i == j else s / L[j][j]
    return L


def project(eng: dict[str, Any], inp: dict[str, Any], sc: dict[str, Any] | None = None,
            beta: list[float] | None = None, shocks: list[float] | None = None,
            extra_build: float = 0.0, spare_offset: float = 0.0) -> list[dict[str, float]]:
    """One path over eng['months'] (the months after the anchor). Returns per month the OECD stocks,
    fair value and price. Must match project() in oil-balance.js."""
    beta = beta or eng["beta"]
    rho = 0.5 ** (1 / inp["half_life"])
    sc = sc or {}
    s0, n0 = sc.get("start", 0), sc.get("months", 0)
    stocks = eng["stocks_anchor"]
    cum = 0.0
    r = eng["r0"]
    ldx = eng["log_dxy"] + math.log(1 + inp["dxy_pct"] / 100)
    out = []
    for i in range(len(eng["months"])):
        live = s0 <= i < s0 + n0
        add = (sc.get("oecd_add", 0.0) if live else 0.0) + extra_build
        if inp["oecd_mode"] == "eia":
            cum += add * MONTH_DAYS
            stocks = eng["stocks_eia"][i] + cum
        else:
            if inp["oecd_mode"] == "identity":
                b = (eng["supply"][i] + inp["supply_delta"]) - (eng["demand"][i] + inp["demand_delta"]) - inp["china_build"] - inp["other_build"]
            else:
                b = inp["oecd_build"]
            stocks += (b + add) * MONTH_DAYS
        spare = (eng["spare_eia"][i] if inp["spare_mode"] == "eia" else inp["spare"]) + spare_offset \
            + (sc.get("spare_add", 0.0) if live else 0.0)
        lfv = beta[0] + beta[1] * (stocks - eng["base5"][i]) + beta[2] * spare + beta[3] * ldx
        r = r * rho + (shocks[i] if shocks else 0.0)
        if n0 and i == s0:
            r += math.log(1 + sc.get("premium_pct", 0.0) / 100)
        out.append({"stocks": stocks, "fv": math.exp(lfv), "price": math.exp(lfv + r)})
    return out


def quantile(xs: list[float], q: float) -> float:
    s = sorted(xs)
    i = q * (len(s) - 1)
    lo = int(i)
    return s[lo] + (s[min(lo + 1, len(s) - 1)] - s[lo]) * (i - lo)


def simulate(eng: dict[str, Any], inp: dict[str, Any], scenarios: list[dict[str, Any]], spreads: dict[str, float],
             n: int = 2000, seed: int = 7) -> dict[str, Any]:
    """Monte Carlo: scenario by probability, coefficients from their (Newey-West) covariance, the input
    ranges (uniform +-spread), and AR(1) residual shocks. Quantiles per month and per calendar year."""
    rng = random.Random(seed)
    L = chol(eng["cov"])
    tot = sum(max(s.get("prob", 0), 0) for s in scenarios) or 1
    cdf, acc = [], 0.0
    for s in scenarios:
        acc += max(s.get("prob", 0), 0) / tot
        cdf.append(acc)
    T = len(eng["months"])
    paths = []
    for _ in range(n):
        u = rng.random()
        sc = scenarios[next((i for i, c in enumerate(cdf) if u <= c), len(scenarios) - 1)]
        z = [rng.gauss(0, 1) for _ in eng["beta"]]
        beta = [b + sum(L[i][j] * z[j] for j in range(len(z))) for i, b in enumerate(eng["beta"])]
        ji = dict(inp)
        ji["dxy_pct"] = inp["dxy_pct"] + rng.uniform(-1, 1) * spreads.get("dxy_pct", 0)
        ji["half_life"] = max(0.5, inp["half_life"] + rng.uniform(-1, 1) * spreads.get("half_life", 0))
        sp_off = rng.uniform(-1, 1) * spreads.get("spare", 0)
        extra = rng.uniform(-1, 1) * spreads.get("oecd_build", 0)
        rho = 0.5 ** (1 / ji["half_life"])
        sh_sd = eng["sd"] * math.sqrt(1 - rho * rho)
        shocks = [rng.gauss(0, sh_sd) for _ in range(T)]
        paths.append([p["price"] for p in project(eng, ji, sc, beta, shocks, extra, sp_off)])
    months = eng["months"]
    out = {"months": months, "p10": [], "p50": [], "p90": []}
    for t in range(T):
        col = [p[t] for p in paths]
        for q, k in ((0.1, "p10"), (0.5, "p50"), (0.9, "p90")):
            out[k].append(round(quantile(col, q), 2))
    years: dict[str, Any] = {}
    for y in sorted({m[:4] for m in months}):
        idx = [t for t, m in enumerate(months) if m.startswith(y)]
        known = [eng["actual"][m] for m in eng.get("actual", {}) if m.startswith(y)]
        if len(idx) + len(known) != 12:
            continue
        avg = [(sum(p[t] for t in idx) + sum(known)) / 12 for p in paths]
        years[y] = {k: round(quantile(avg, q), 1) for q, k in ((0.1, "p10"), (0.5, "p50"), (0.9, "p90"))}
    out["annual"] = years
    return out


def build_engine(coef: dict[str, Any], X: dict[str, dict[str, float]], price: dict[str, float],
                 stocks: dict[str, float], spare: dict[str, float], supply: dict[str, float], demand: dict[str, float],
                 dxy: dict[str, float], anchor: str, horizon_to: str) -> dict[str, Any]:
    """Everything the projection needs, as plain lists, so the browser can run the same arithmetic."""
    months = []
    m = next_month(anchor)
    while m <= horizon_to:
        months.append(m)
        m = next_month(m)
    base5 = [sum(stocks[f"{int(mm[:4]) - k}{mm[4:]}"] for k in range(1, 6)) / 5 for mm in months]
    a = ar1(list(coef["resid"].values()))
    r0 = math.log(price[anchor]) - log_fv(coef["beta"], coef["vars"], X, anchor)
    dm = max(dxy)
    return {"vars": coef["vars"], "beta": coef["beta"], "cov": coef["cov"], "anchor": anchor, "months": months,
            "r0": r0, "rho": a["rho"], "half_life": a["half_life"], "sd": a["sd"],
            "stocks_anchor": stocks[anchor], "stocks_eia": [stocks[mm] for mm in months], "base5": base5,
            "spare_eia": [spare[mm] for mm in months], "supply": [supply[mm] for mm in months],
            "demand": [demand[mm] for mm in months], "log_dxy": math.log(dxy[dm]), "dxy_month": dm, "dxy": dxy[dm],
            "actual": {mm: price[mm] for mm in price if mm[:4] in {x[:4] for x in months} and mm <= anchor}}


def outside_oecd(supply: dict[str, float], demand: dict[str, float], stocks: dict[str, float]) -> dict[str, float]:
    """(supply - demand) minus the OECD stock change, mb/d: what the balance says went into China's and other
    non-OECD tanks, ships, or the statistical gap. The free measurable stand-in for 'where did the surplus go'."""
    out = {}
    for m in sorted(stocks):
        p = next_month(m, -1)
        if p in stocks and m in supply and m in demand:
            out[m] = (supply[m] - demand[m]) - (stocks[m] - stocks[p]) / MONTH_DAYS
    return out


# ---------------------------------------------------------------- scoring

def backtest(price, X, stocks: dict[str, float], dxy: dict[str, float], vintages: dict[str, dict[str, dict[str, float]]],
             vars_=SPEC, spreads: dict[str, float] | None = None, n: int = 400, seed: int = 11) -> list[dict[str, Any]]:
    """Replay the method from each December STEO: fit on data through November, take EIA's stock and spare
    capacity forecast for the next year (stock changes laid on the revised November level), hold the dollar,
    decay November's premium. Score the next calendar year against EIA's own Brent forecast from the same
    workbook and a no-change forecast. The P10-P90 band is drawn with the same input ranges (`spreads`) as
    the live forecast, so its coverage says whether the published bands are honest. History is today's
    revised history (a little hindsight on levels)."""
    out = []
    for vk in sorted(vintages):
        y = int(vk[:4])
        anchor = f"{y}-11"
        v = vintages[vk]
        vs, vsp = v.get("oecd_stocks_mb", {}), v.get("opec_spare_mbd", {})
        targets = [f"{y + 1}-{mm:02d}" for mm in range(1, 13)]
        have = [t for t in targets if t in price]
        if anchor not in price or anchor not in vs or anchor not in stocks or not have or anchor not in dxy:
            continue
        if not all(t in vs and t in vsp for t in [f"{y}-12"] + targets):
            continue
        if len(usable(price, X, vars_, FIT_FROM, anchor)) < 60 or anchor not in X["dev_mb"]:
            continue
        coef = fit(price, X, vars_, FIT_FROM, anchor)
        lv = {m: stocks[anchor] + (vs[m] - vs[anchor]) for m in [f"{y}-12"] + targets}
        path_stocks = dict(stocks)
        path_stocks.update(lv)
        eng = {"beta": coef["beta"], "cov": coef["cov"], "r0": math.log(price[anchor]) - log_fv(coef["beta"], vars_, X, anchor),
               "months": [f"{y}-12"] + targets, "stocks_anchor": stocks[anchor],
               "stocks_eia": [lv[m] for m in [f"{y}-12"] + targets],
               "base5": [sum(path_stocks[f"{int(m[:4]) - k}{m[4:]}"] for k in range(1, 6)) / 5 for m in [f"{y}-12"] + targets],
               "spare_eia": [vsp[m] for m in [f"{y}-12"] + targets], "supply": [0.0] * 13, "demand": [0.0] * 13,
               "log_dxy": math.log(dxy[anchor]), "sd": ar1(list(coef["resid"].values()))["sd"], "actual": {}}
        a = ar1(list(coef["resid"].values()))
        inp = {"oecd_mode": "eia", "spare_mode": "eia", "dxy_pct": 0.0, "half_life": a["half_life"] or 2.6,
               "spare": 0.0, "supply_delta": 0, "demand_delta": 0, "china_build": 0, "other_build": 0, "oecd_build": 0}
        central = {m: p["price"] for m, p in zip(eng["months"], project(eng, inp))}
        sim = simulate(eng, inp, [{"id": "base", "prob": 1}], spreads or {}, n=n, seed=seed)
        band = {m: (sim["p10"][i], sim["p90"][i]) for i, m in enumerate(sim["months"])}
        eia = v.get("brent_steo", {})
        rw = price[anchor]
        row = {"vintage": vk, "target": str(y + 1), "months": len(have),
               "mae_model": round(st.mean(abs(central[t] - price[t]) for t in have), 1),
               "mae_rw": round(st.mean(abs(rw - price[t]) for t in have), 1),
               "mae_eia": round(st.mean(abs(eia[t] - price[t]) for t in have), 1) if all(t in eia for t in have) else None,
               "coverage": round(sum(band[t][0] <= price[t] <= band[t][1] for t in have) / len(have), 2),
               "avg_actual": round(st.mean(price[t] for t in have), 1),
               "avg_model": round(st.mean(central[t] for t in have), 1),
               "avg_eia": round(st.mean(eia[t] for t in have), 1) if all(t in eia for t in have) else None}
        out.append(row)
    return out


def score_log(entries: list[dict[str, Any]], price: dict[str, float], last_full: str) -> list[dict[str, Any]]:
    """Live forecasts saved at each STEO vintage, scored on months that have since closed."""
    out = []
    for e in entries:
        ms = [m for m in e.get("p50", {}) if m <= last_full and m in price]
        if not ms:
            out.append({"steo": e["steo"], "made": e["made"], "months": 0})
            continue
        row = {"steo": e["steo"], "made": e["made"], "months": len(ms),
               "mae_model": round(st.mean(abs(e["p50"][m] - price[m]) for m in ms), 1),
               "mae_rw": round(st.mean(abs(e["anchor_price"] - price[m]) for m in ms), 1),
               "coverage": round(sum(e["p10"][m] <= price[m] <= e["p90"][m] for m in ms) / len(ms), 2)}
        for k in ("eia", "futures"):
            src = e.get(k) or {}
            if all(m in src for m in ms):
                row[f"mae_{k}"] = round(st.mean(abs(src[m] - price[m]) for m in ms), 1)
        out.append(row)
    return out
