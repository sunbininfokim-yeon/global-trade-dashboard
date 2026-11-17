"""v2 shadow direction forecast beside the frozen v1 card (research only).

Why (2026-11-17 study, walk-forward on Yahoo history, see
docs/ops/handoff/2026-11-17-claude-to-codex-options-v2.md):
- v1's four option inputs added nothing; momentum5/20 and volatility20
  slightly hurt (Brier).
- EWY's US-hours move (open -> close of the last US session) and the
  overnight KRW move improved the opening-direction forecast
  (KOSPI open Brier -0.014 [-0.024, -0.004] over 5y, hit 74.5% -> 77.9%).

v2 inputs, per ticker (KOSPI, 005930, 000660) and head (opening_up, closing_up):
  US 8 (QQQ SPY SMH MU NVDA AMD ^VIX returns, log VIX) of the last US session,
  KR return1 / gap1 / intraday1 of the source session,
  EWY_intraday (EWY close/open - 1 on the US session),
  KRW_overnight (KRW=X at 06:00 KST target vs 15:00 KST source).
Logistic regression, standardized inputs clipped at +-3 sigma, no options.

Nothing here touches the public card or v1's records. Forecasts are written
once to data/forecasts/us_kr_v2_shadow/TARGET/MODEL16/first.json, before the
08:30 KST cutoff, and scored later against Yahoo closes beside v1's first
forecast for the same target.

Commands:
  train  --cutoff YYYY-MM-DD --output models/shadow/us_kr_v2_YYYYMMDD.json
  plan   --model M --archive A [--target T]       (writes run/target to $GITHUB_OUTPUT)
  predict --model M --archive A --target T        (exit 2 = inputs unavailable)
  score  --model M --archive A --v1-archive V --output summary.json
"""
import argparse
import glob
import hashlib
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

VERSION = "us-kr-v2-shadow-v1"
KST, NY = ZoneInfo("Asia/Seoul"), ZoneInfo("America/New_York")
CUTOFF = "08:30"
TICKERS = {"KOSPI": "^KS11", "005930": "005930.KS", "000660": "000660.KS"}
US = ["QQQ", "SPY", "SMH", "MU", "NVDA", "AMD", "^VIX"]
HEADS = ["opening_up", "closing_up"]
FEATURES = ["QQQ", "SPY", "SMH", "MU", "NVDA", "AMD", "^VIX", "log_VIX",
            "return1", "gap1", "intraday1", "EWY_intraday", "KRW_overnight"]
CLIP = 3.0
C = 0.5
ARCHIVE = Path("data/forecasts/us_kr_v2_shadow")


# ---------- data ----------

def yahoo(symbol, interval, rng, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                             params={"range": rng, "interval": interval},
                             headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            r.raise_for_status()
            c = r.json()["chart"]["result"][0]
            q = c["indicators"]["quote"][0]
            return [{"t": t, "open": q["open"][i], "close": q["close"][i]}
                    for i, t in enumerate(c.get("timestamp") or [])]
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def daily_frame(rows, tz):
    """date -> open/close (unadjusted quote). Bars with a missing value are dropped."""
    out = {}
    for r in rows:
        if r["open"] is None or r["close"] is None or r["open"] <= 0 or r["close"] <= 0:
            continue
        out[datetime.fromtimestamp(r["t"], tz).date().isoformat()] = (r["open"], r["close"])
    return out


def hourly_series(rows):
    """bar END time (UTC) -> close."""
    s = {pd.Timestamp(r["t"], unit="s", tz="UTC") + pd.Timedelta(hours=1): r["close"]
         for r in rows if r["close"] is not None and r["close"] > 0}
    return pd.Series(s, dtype=float).sort_index()


def fetch(daily_range, hourly_range):
    kr = {k: daily_frame(yahoo(s, "1d", daily_range), KST) for k, s in TICKERS.items()}
    us = {s: daily_frame(yahoo(s, "1d", daily_range), NY) for s in US + ["EWY"]}
    krw = hourly_series(yahoo("KRW=X", "60m", hourly_range))
    return kr, us, krw


# ---------- features ----------

def asof(series, ts):
    s = series[series.index <= ts]
    return (float(s.iloc[-1]), s.index[-1]) if len(s) else (None, None)


def features(kr_bars, us, krw, target, source, source_prev, us_day, us_prev):
    """Feature dict for one (target, source) pair, or (None, reason)."""
    need = [(kr_bars, source), (kr_bars, source_prev)]
    need += [(us[s], d) for s in US + ["EWY"] for d in (us_day, us_prev) if not (s == "EWY" and d == us_prev)]
    for frame, day in need:
        if day not in frame:
            return None, f"missing bar {day}"
    x = {}
    for s in US:
        x[s] = us[s][us_day][1] / us[s][us_prev][1] - 1
    x["log_VIX"] = math.log(us["^VIX"][us_day][1])
    so, sc = kr_bars[source]
    pc = kr_bars[source_prev][1]
    x["return1"], x["gap1"], x["intraday1"] = sc / pc - 1, so / pc - 1, sc / so - 1
    eo, ec = us["EWY"][us_day]
    x["EWY_intraday"] = ec / eo - 1
    k1, t1 = asof(krw, pd.Timestamp(source + " 15:00", tz=KST).tz_convert("UTC"))
    k2, t2 = asof(krw, pd.Timestamp(target + " 06:00", tz=KST).tz_convert("UTC"))
    # The 06:00 KST side is the last bar at or before then. FX is shut over the
    # weekend, so for a Monday target that is Friday's New York close -- still
    # after the source session, which is all the feature needs. Requiring a
    # fresh bar dropped every Monday from training and from the live run.
    if k1 is None or k2 is None or t2 <= t1 + pd.Timedelta(hours=6):
        return None, "missing KRW=X hourly bars"
    x["KRW_overnight"] = k2 / k1 - 1
    if not all(math.isfinite(v) for v in x.values()):
        return None, "non-finite feature"
    return x, None


def training_rows(kr, us, krw, cutoff):
    usdays = sorted(set.intersection(*[set(us[s]) for s in US]))
    out = {}
    for ticker, bars in kr.items():
        days = sorted(bars)
        rows = []
        for i in range(2, len(days)):
            t, s, sp = days[i], days[i - 1], days[i - 2]
            if t > cutoff:
                break
            prior = [d for d in usdays if d < t]
            if len(prior) < 2 or (pd.Timestamp(t) - pd.Timestamp(prior[-1])).days > 4:
                continue
            x, _ = features(bars, us, krw, t, s, sp, prior[-1], prior[-2])
            if x is None:
                continue
            pc, (o, c) = bars[s][1], bars[t]
            if o == pc or c == pc:
                continue
            rows.append({"target": t, "x": [x[f] for f in FEATURES],
                         "opening_up": int(o > pc), "closing_up": int(c > pc)})
        out[ticker] = rows
    return out


def fit(rows, head):
    from sklearn.linear_model import LogisticRegression
    X = np.array([r["x"] for r in rows]); y = np.array([r[head] for r in rows])
    mean, scale = X.mean(0), X.std(0)
    scale[scale == 0] = 1
    lr = LogisticRegression(C=C, max_iter=2000).fit(np.clip((X - mean) / scale, -CLIP, CLIP), y)
    return {"mean": mean.tolist(), "scale": scale.tolist(), "coef": lr.coef_[0].tolist(),
            "intercept": float(lr.intercept_[0]), "n": len(rows), "base_rate": float(y.mean())}


def probability(head, x):
    z = head["intercept"] + sum(w * max(-CLIP, min(CLIP, (v - m) / s))
                                for w, v, m, s in zip(head["coef"], x, head["mean"], head["scale"]))
    return 1 / (1 + math.exp(-z))


# ---------- calendars ----------

def calendars():
    import exchange_calendars as xc
    from option_direction_model import calendar
    from research_direction_diagnostics import ReviewedCalendar
    return ReviewedCalendar(calendar()), xc.get_calendar("XNYS", start="2018-01-01", end="2027-12-31")


def alignment(kr_cal, us_cal, target):
    if not kr_cal.is_session(target):
        raise ValueError(f"{target} is not a KRX session")
    days = kr_cal.sessions[kr_cal.sessions.strftime("%Y-%m-%d") < target]
    source, source_prev = days[-1].strftime("%Y-%m-%d"), days[-2].strftime("%Y-%m-%d")
    us_days = us_cal.sessions[us_cal.sessions.strftime("%Y-%m-%d") < target]
    us_day, us_prev = us_days[-1], us_days[-2]
    return {"source": source, "source_prev": source_prev,
            "us_day": us_day.strftime("%Y-%m-%d"), "us_prev": us_prev.strftime("%Y-%m-%d"),
            "us_close_utc": us_cal.session_close(us_day).isoformat(),
            "cutoff_kst": pd.Timestamp(f"{target} {CUTOFF}", tz=KST).isoformat()}


# ---------- records ----------

def impl_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def first_path(archive, target, model_id):
    return Path(archive) / target / model_id[:16] / "first.json"


def write_once(path, doc):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x") as f:
            f.write(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        return True
    except FileExistsError:
        return False


def validate_model(model):
    if model.get("schema_version") != VERSION or model.get("features") != FEATURES:
        raise ValueError("v2 model schema changed")
    body = {k: v for k, v in model.items() if k != "model_id"}
    if hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() != model["model_id"]:
        raise ValueError("model_id does not match model body")


# ---------- commands ----------

def cmd_train(args):
    if Path(args.output).exists():
        raise SystemExit("refusing to overwrite a frozen model; use a new path")
    kr, us, krw = fetch("5y", "730d")
    rows = training_rows(kr, us, krw, args.cutoff)
    models = {}
    for ticker, rs in rows.items():
        if len(rs) < 250:
            raise SystemExit(f"{ticker}: only {len(rs)} rows")
        models[ticker] = {h: fit(rs, h) for h in HEADS}
        models[ticker]["first_target"] = rs[0]["target"]
        models[ticker]["last_target"] = rs[-1]["target"]
    body = {"schema_version": VERSION, "features": FEATURES, "heads": HEADS, "tickers": list(TICKERS),
            "clip_sigma": CLIP, "C": C, "trained_through": args.cutoff,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "training_rows_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
            "implementation_sha256": impl_hash(), "source": "Yahoo Finance chart API (unadjusted quotes)",
            "status": "research_shadow", "models": models}
    body["model_id"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    Path(args.output).write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({t: {h: m[h]["n"] for h in HEADS} for t, m in models.items()}))


def plan(model, archive, now, requested=""):
    kr_cal, us_cal = calendars()
    today = now.astimezone(KST).date().isoformat()
    if requested:
        target = requested
    else:
        days = kr_cal.sessions.strftime("%Y-%m-%d")
        target = days[days.searchsorted(today)]
    a = alignment(kr_cal, us_cal, target)
    if target <= model["trained_through"]:
        why = "target overlaps training"
    elif first_path(archive, target, model["model_id"]).is_file():
        why = "already recorded"
    elif now >= pd.Timestamp(a["cutoff_kst"]):
        why = "08:30 KST cutoff reached"
    elif now < pd.Timestamp(a["us_close_utc"]) + pd.Timedelta(minutes=15):
        why = "waiting for US close"
    else:
        why = None
    return {"target": target, "run": why is None, "reason": why}


def predict(model, archive, target, now, data=None):
    kr_cal, us_cal = calendars()
    a = alignment(kr_cal, us_cal, target)
    if now >= pd.Timestamp(a["cutoff_kst"]):
        return 2, {"status": "unavailable", "reason": "after 08:30 KST cutoff"}
    kr, us, krw = data or fetch("1mo", "5d")
    results, reasons = {}, {}
    for ticker in model["tickers"]:
        x, why = features(kr[ticker], us, krw, target, a["source"], a["source_prev"], a["us_day"], a["us_prev"])
        if x is None:
            reasons[ticker] = why
            continue
        vec = [x[f] for f in FEATURES]
        results[ticker] = {"probabilities": {h: round(probability(model["models"][ticker][h], vec), 4)
                                             for h in HEADS},
                           "feature_values": {f: round(v, 6) for f, v in x.items()}}
    if reasons:
        return 2, {"status": "unavailable", "target_date": target, "reasons": reasons}
    doc = {"schema_version": VERSION, "status": "research_shadow_forecast", "target_date": target,
           "model_id": model["model_id"], "generated_at": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
           "alignment": a, "results": results}
    if not write_once(first_path(archive, target, model["model_id"]), doc):
        return 0, {"status": "already_recorded", "target_date": target}
    return 0, doc


def score(model, archive, v1_archive, kr):
    """Brier/hit of every recorded v2 first forecast, paired with v1's first forecast."""
    rows = []
    for path in sorted(glob.glob(str(Path(archive) / "*" / model["model_id"][:16] / "first.json"))):
        doc = json.loads(Path(path).read_text())
        t, s = doc["target_date"], doc["alignment"]["source"]
        v1 = sorted(glob.glob(str(Path(v1_archive) / t / "*" / "first.json")))
        v1doc = json.loads(Path(v1[0]).read_text()) if v1 else None
        for ticker, res in doc["results"].items():
            bars = kr.get(ticker, {})
            if t not in bars or s not in bars:
                continue
            pc, (o, c) = bars[s][1], bars[t]
            outcome = {"opening_up": None if o == pc else int(o > pc), "closing_up": None if c == pc else int(c > pc)}
            for h in HEADS:
                if outcome[h] is None:
                    continue
                p2 = res["probabilities"][h]
                p1 = None
                if v1doc and v1doc.get("status") == "research_preopen_forecast":
                    p1 = ((v1doc.get("results") or {}).get(ticker, {}).get("scores") or {}).get(h)
                    p1 = p1.get("probability") if isinstance(p1, dict) else p1
                rows.append({"target": t, "ticker": ticker, "head": h, "y": outcome[h], "v2": p2, "v1": p1})
    summary = {}
    for ticker in model["tickers"]:
        for h in HEADS:
            rs = [r for r in rows if r["ticker"] == ticker and r["head"] == h]
            paired = [r for r in rs if r["v1"] is not None]
            br = lambda key, xs: round(float(np.mean([(r[key] - r["y"]) ** 2 for r in xs])), 4) if xs else None
            hit = lambda key, xs: round(float(np.mean([(r[key] > .5) == r["y"] for r in xs])), 3) if xs else None
            summary[f"{ticker}:{h}"] = {"n": len(rs), "v2_brier": br("v2", rs), "v2_hit": hit("v2", rs),
                                        "n_paired": len(paired), "paired_v2_brier": br("v2", paired),
                                        "paired_v1_brier": br("v1", paired), "paired_v1_hit": hit("v1", paired),
                                        "paired_v2_hit": hit("v2", paired)}
    return {"schema_version": VERSION + "-score", "model_id": model["model_id"],
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "note": "Research shadow. Decide on v2 only after >=60 paired targets per head.",
            "summary": summary, "rows": rows}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=("train", "plan", "predict", "score"))
    p.add_argument("--model", type=Path); p.add_argument("--archive", type=Path, default=ARCHIVE)
    p.add_argument("--v1-archive", type=Path, default=Path("data/forecasts/us_kr_direction"))
    p.add_argument("--target", default=""); p.add_argument("--cutoff"); p.add_argument("--output", type=Path)
    args = p.parse_args()
    if args.command == "train":
        return cmd_train(args)
    model = json.loads(args.model.read_text()); validate_model(model)
    now = datetime.now(timezone.utc)
    if args.command == "plan":
        result = plan(model, args.archive, now, args.target.strip())
        if out := os.environ.get("GITHUB_OUTPUT"):
            with open(out, "a") as f:
                f.write(f"target={result['target']}\nrun={str(result['run']).lower()}\n")
        print(json.dumps(result)); return 0
    if args.command == "predict":
        code, doc = predict(model, args.archive, args.target, now)
        print(json.dumps(doc, ensure_ascii=False)); return code
    kr = {k: daily_frame(yahoo(s, "1d", "1y"), KST) for k, s in TICKERS.items()}
    result = score(model, args.archive, args.v1_archive, kr)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["summary"], ensure_ascii=False)); return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(main() or 0)
