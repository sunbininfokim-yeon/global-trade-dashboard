#!/usr/bin/env python3
"""Build public/data/oil_balance_v1.json: the world oil balance from EIA's STEO, a Brent fair value from OECD
stocks, OPEC spare capacity and the dollar, and a forecast from the assumptions in config/assumptions_v1.json
(see oil_balance/forecast.py for the three layers). Free, keyless sources only.

    python3 build_oil_balance.py                   # current STEO + FRED + Yahoo; archived history from the cache
    python3 build_oil_balance.py --every-days 14   # skip unless the last successful build is 14 days old
                                                   # (the daily workflow calls it this way: a failed run
                                                   # leaves the old file, so the next day tries again)
    python3 build_oil_balance.py --rebuild-history [--archive-dir DIR]
                                                   # re-read the December STEO archives (2007-2022 history,
                                                   # 2007-2025 vintages for the back-test) into the cache

A read that fails leaves the previous file and exits 1. Brent futures are optional: without them the
futures line and its score are left out.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics as st
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "macro_monitor"))

from oil_balance import forecast as fc  # noqa: E402
from oil_balance import steo  # noqa: E402

OUT = ROOT.parent.parent / "public" / "data" / "oil_balance_v1.json"
HISTORY = ROOT / "config" / "steo_history_v1.json"
REFERENCE = ROOT / "config" / "bank_views_v1.json"
ASSUMPTIONS = ROOT / "config" / "assumptions_v1.json"
LOG = ROOT / "config" / "forecast_log_v1.json"
MONTH_CODES = "FGHJKMNQUVXZ"


def fred_monthly(sid: str) -> tuple[dict[str, float], tuple[str, float]]:
    from macro_monitor import us_public_series as ups
    pts = ups.fetch_fred(sid)
    by: dict[str, list[float]] = {}
    for d, v in pts:
        by.setdefault(d[:7], []).append(v)
    return {k: sum(v) / len(v) for k, v in by.items()}, pts[-1]


def brent_futures(months: list[str]) -> dict[str, float]:
    """Market-implied monthly Brent: the NYMEX BZ contract two months out trades as the front month during
    a given month, so month M reads contract M+2. Yahoo, keyless; quotes older than ten days are dropped."""
    out = {}
    now = time.time()
    for m in months:
        c = fc.next_month(m, 2)
        sym = f"BZ{MONTH_CODES[int(c[5:7]) - 1]}{c[2:4]}.NYM"
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5d&interval=1d"
        try:
            proc = subprocess.run(["curl", "-sS", "-m", "20", "-A", "Mozilla/5.0", url], capture_output=True, check=False)
            meta = (json.loads(proc.stdout or b"{}").get("chart", {}).get("result") or [{}])[0].get("meta", {})
            px, ts = meta.get("regularMarketPrice"), meta.get("regularMarketTime") or 0
            if isinstance(px, (int, float)) and now - ts < 10 * 86400:
                out[m] = round(float(px), 2)
        except (ValueError, OSError):
            continue
    return out


def annual(series: dict[str, float], year: str) -> float | None:
    v = [x for m, x in series.items() if m.startswith(year)]
    return round(st.mean(v), 2) if len(v) == 12 else None


def resolve_inputs(a: dict, eng: dict) -> dict:
    inp = {k: v["value"] for k, v in a["inputs"].items()}
    if inp.get("half_life") is None:
        inp["half_life"] = round(eng["half_life"], 2)
    if inp.get("spare") is None:
        inp["spare"] = round(st.mean(eng["spare_eia"]), 2)
    return inp


def build() -> dict:
    hist_doc = json.loads(HISTORY.read_text(encoding="utf-8"))
    hist, vintages = hist_doc["series"], hist_doc.get("vintages", {})
    A = json.loads(ASSUMPTIONS.read_text(encoding="utf-8"))
    raw = steo.fetch(steo.CURRENT)
    cur = steo.parse(raw)
    vdate = steo.vintage_date(raw, False)
    first_fc = vdate[:7] if vdate else None
    series = {}
    for f in steo.CODES.values():
        s = {k: v for k, v in hist.get(f, {}).items() if k < "2022-01"}
        s.update(cur.get(f, {}))
        series[f] = dict(sorted(s.items()))
    brent, last_day = fred_monthly("DCOILBRENTEU")
    dxy, _ = fred_monthly("DTWEXBGS")
    stocks, supply, demand, spare = (series["oecd_stocks_mb"], series["world_supply_mbd"],
                                     series["world_demand_mbd"], series["opec_spare_mbd"])
    X = fc.features(stocks, series["oecd_demand_mbd"], spare, dxy)
    S = A["structure"]
    vars_ = tuple(S["vars"])
    coef = fc.fit(brent, X, vars_, S["fit_from"], S["fit_to"])
    fv_hist = fc.fair_value(coef, X)
    anchor = max(m for m in brent if m in fv_hist)
    horizon = max(stocks)
    eng = fc.build_engine(coef, X, brent, stocks, spare, supply, demand, dxy, anchor, horizon)
    inp = resolve_inputs(A, eng)
    spreads = {k: v.get("spread", 0) for k, v in A["inputs"].items() if "spread" in v}
    scen = [dict(s, prob=s["prob"]) for s in A["scenarios"]["list"]]
    sim = fc.simulate(eng, inp, scen, spreads)
    central = fc.project(eng, inp)
    futures = brent_futures(eng["months"])

    # layer 2 checks
    years = list(range(2016, int(S["fit_to"][:4]) + 1))
    board, common = fc.compete(brent, X, years, hi=S["fit_to"])
    windows = fc.rolling(brent, X, vars_, hi=S["fit_to"])
    flags = fc.stability_flags(coef, windows)
    a1 = fc.ar1(list(coef["resid"].values()))
    gap = {m: brent[m] - fv_hist[m] for m in coef["months"]}
    above = fc.runs([gap[m] > 10 for m in coef["months"]])

    # layer 1: where the surplus goes
    outside = fc.outside_oecd(supply, demand, stocks)
    T = len(eng["months"])
    hz = eng["months"]
    ident = {"months": [hz[0], hz[-1]],
             "supply": round(st.mean(supply[m] for m in hz), 2), "demand": round(st.mean(demand[m] for m in hz), 2),
             "oecd_build_eia": round((stocks[hz[-1]] - stocks[anchor]) / (T * fc.MONTH_DAYS), 2),
             "outside_oecd_eia": round(st.mean(outside[m] for m in hz if m in outside), 2)}
    ident["surplus"] = round(ident["supply"] - ident["demand"], 2)
    past = [m for m in sorted(outside) if first_fc and m < first_fc][-12:]
    ident["outside_oecd_last12"] = {"from": past[0], "to": past[-1], "value": round(st.mean(outside[m] for m in past), 2)}
    full_years = sorted({m[:4] for m in outside if "2015" <= m[:4] and first_fc and f"{m[:4]}-12" < first_fc})
    ident["outside_oecd_annual"] = {y: round(st.mean(v for m, v in outside.items() if m.startswith(y)), 2) for y in full_years}

    # scoring
    bt = fc.backtest(brent, X, stocks, dxy, vintages, vars_, spreads)
    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {"schema": "oil_forecast_log_v1", "entries": []}
    if vdate and not any(e["steo"] == vdate for e in log["entries"]):
        log["entries"].append({
            "steo": vdate, "made": datetime.now(timezone.utc).date().isoformat(), "anchor": anchor,
            "anchor_price": round(brent[anchor], 2), "structure": list(vars_), "inputs": inp,
            "scenarios": {s["id"]: s["prob"] for s in scen},
            "p10": dict(zip(hz, sim["p10"])), "p50": dict(zip(hz, sim["p50"])), "p90": dict(zip(hz, sim["p90"])),
            "eia": {m: round(series["brent_steo"][m], 2) for m in hz if m in series.get("brent_steo", {})},
            "futures": futures})
    last_full = fc.next_month(last_day[0][:7], -1)
    live = fc.score_log(log["entries"], brent, last_full)

    # display path
    months = [m for m in sorted(stocks) if m >= "2019-01"]
    cidx = {m: i for i, m in enumerate(hz)}
    path = []
    for m in months:
        i = cidx.get(m)
        path.append({"month": m, "forecast": bool(first_fc and m >= first_fc), "projected": i is not None,
                     "supply": round(supply.get(m, float("nan")), 2), "demand": round(demand.get(m, float("nan")), 2),
                     "oecd_stocks_mb": round(stocks[m], 1), "dev_mb": round(X["dev_mb"][m], 1) if m in X["dev_mb"] else None,
                     "spare": round(spare[m], 2) if m in spare else None,
                     "fair_value": round(central[i]["fv"], 2) if i is not None else (round(fv_hist[m], 2) if m in fv_hist else None),
                     "brent": round(brent[m], 2) if m in brent and i is None else None,
                     "brent_eia": round(series["brent_steo"][m], 2) if m in series.get("brent_steo", {}) else None,
                     "p10": sim["p10"][i] if i is not None else None, "p50": sim["p50"][i] if i is not None else None,
                     "p90": sim["p90"][i] if i is not None else None, "futures": futures.get(m)})
    ann = []
    for y in sorted({m[:4] for m in months if m >= "2024"}):
        row = {"year": y, "fair_value": annual({m: p["fair_value"] for m, p in zip(months, path) if p["fair_value"] is not None}, y),
               "brent": annual(brent, y), "brent_eia": annual(series.get("brent_steo", {}), y),
               "balance": annual({m: supply[m] - demand[m] for m in supply if m in demand}, y),
               "supply": annual(supply, y), "demand": annual(demand, y), "forecast": sim["annual"].get(y)}
        if any(m.startswith(y) for m in brent):
            row["brent_ytd"] = round(st.mean(v for m, v in brent.items() if m.startswith(y)), 2)
        fy = [futures[m] for m in hz if m.startswith(y) and m in futures]
        known = [brent[m] for m in brent if m.startswith(y) and m <= anchor]
        if fy:                                  # far contracts can be unquoted: average what is there and say how many
            row["futures"] = round((sum(fy) + sum(known)) / (len(fy) + len(known)), 1)
            row["futures_months"] = len(fy) + len(known)
        ann.append(row)
    ref = json.loads(REFERENCE.read_text(encoding="utf-8")) if REFERENCE.exists() else {"views": []}
    doc = {
        "schema": "oil_balance_v2",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "steo": {"vintage": vdate, "first_forecast_month": first_fc, "url": "https://www.eia.gov/outlooks/steo/"},
        "brent_last": {"date": last_day[0], "value": last_day[1], "fair_value_month": round(fv_hist[anchor], 2)},
        "model": {"vars": list(vars_), "labels": [fc.LABELS[v] for v in vars_], "from": coef["from"], "to": coef["to"],
                  "n": coef["n"], "r2": round(coef["r2"], 3), "beta": [round(b, 6) for b in coef["beta"]],
                  "se": [round(s, 6) for s in coef["se"]], "rho": round(a1["rho"], 3), "half_life": round(a1["half_life"], 2),
                  "resid_sd": round(a1["sd"], 4), "max_premium": round(max(gap.values()), 1),
                  "max_premium_month": max(gap, key=gap.get), "max_discount": round(min(gap.values()), 1),
                  "max_discount_month": min(gap, key=gap.get), "episodes_above_10": len(above),
                  "avg_months_above_10": round(st.mean(above), 1) if above else None,
                  "oos": {str(y): round(v, 1) for y, v in fc.oos(brent, X, vars_, S["fit_from"], years).items()},
                  "stability": flags, "windows": windows},
        "compete": {"common_years": common, "rows": board},
        "engine": {k: eng[k] for k in ("vars", "beta", "cov", "anchor", "months", "r0", "rho", "half_life", "sd",
                                        "stocks_anchor", "stocks_eia", "base5", "spare_eia", "supply", "demand",
                                        "log_dxy", "dxy_month", "dxy", "actual")},
        "inputs": {"resolved": inp, "spec": A["inputs"], "spreads": spreads},
        "scenarios": A["scenarios"],
        "forecast": {"central": [{"month": m, "fv": round(p["fv"], 2), "price": round(p["price"], 2), "stocks": round(p["stocks"], 1)}
                                 for m, p in zip(hz, central)], **{k: sim[k] for k in ("p10", "p50", "p90", "annual")}},
        "identity": ident,
        "futures": futures,
        "backtest": bt,
        "live_scores": live,
        "cadence": A.get("cadence", []),
        "path": path, "annual": ann, "bank_views": ref.get("views", []),
        "sources": ["EIA Short-Term Energy Outlook (STEO_m.xlsx; December archives 2007-2025)",
                    "FRED DCOILBRENTEU, DTWEXBGS", "Yahoo Finance NYMEX BZ futures"],
    }
    return doc, log


def due(out: Path, every_days: float | None, now: datetime | None = None) -> bool:
    """True when there is no previous build, or it is at least every_days old (half a day of slack so a
    daily cron at the same hour lands on day 14, not 15)."""
    if not every_days or not out.exists():
        return True
    try:
        made = datetime.fromisoformat(json.loads(out.read_text(encoding="utf-8"))["generated_at"])
    except (ValueError, KeyError, OSError):
        return True
    now = now or datetime.now(timezone.utc)
    return (now - made).total_seconds() >= (every_days - 0.5) * 86400


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rebuild-history", action="store_true")
    ap.add_argument("--archive-dir", help="local copies of decYY_base.xls/xlsx to read before fetching")
    ap.add_argument("--every-days", type=float, help="run only if the last build is this many days old")
    a = ap.parse_args()
    if not a.rebuild_history and not due(OUT, a.every_days):
        made = json.loads(OUT.read_text(encoding="utf-8"))["generated_at"]
        print(f"oil balance: last build {made}, next after {a.every_days:g} days -- skipped")
        return 0
    if a.rebuild_history or not HISTORY.exists():
        series, vint = steo.history_from_archives(local_dir=a.archive_dir)
        HISTORY.write_text(json.dumps({"schema": "steo_history_v1",
                                       "note": "series: year Y from the December Y+1 STEO archive. vintages: each December STEO's own "
                                               "figures for that year and the next (the back-test's inputs).",
                                       "series": series, "vintages": vint}, separators=(",", ":")) + "\n", encoding="utf-8")
    try:
        doc, log = build()
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED oil balance: {exc}", file=sys.stderr)
        return 1
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    m = doc["model"]
    f = doc["forecast"]["annual"]
    print(f"oil balance: STEO {doc['steo']['vintage']}, fit {m['from']}..{m['to']} R2 {m['r2']:.2f}, half-life {m['half_life']}m; "
          + "; ".join(f"{y} P10/50/90 {v['p10']}/{v['p50']}/{v['p90']}" for y, v in f.items())
          + f"; futures {len(doc['futures'])} months; back-test {len(doc['backtest'])} years")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
