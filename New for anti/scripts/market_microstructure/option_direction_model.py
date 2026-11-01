"""Frozen option-only direction model; explicit train/evaluate/predict commands.

Target: next XKRX session's ETF close > open. DOWN includes a flat close.
Historical source availability and common-factor OHLC adjustment are unverified;
all outputs are research_only. Model probabilities are uncalibrated estimates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from build_kospi200_price_panel import PUBLIC

OPTION_FEATURES = ["call_relative_60", "put_relative_60", "call_mean_5", "put_mean_5"]
PRICE_FEATURES = ["momentum_5", "volatility_20"]
FEATURE_VERSION = "option-direction-v1"
LIMITATIONS = ["Historical publication times unknown", "Adjusted OHLC common factor unverified",
               "Probabilities are not calibrated", "Retrospective evaluation already explored",
               "DOWN means nonpositive next-session close/open return, including flat"]


def digest(doc):
    return hashlib.sha256(json.dumps(doc, sort_keys=True, allow_nan=False).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, doc):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def calendar():
    import exchange_calendars as xc
    return xc.get_calendar("XKRX", start="2018-01-01", end="2027-12-31")


def next_day(cal, day):
    if not cal.is_session(day):
        raise ValueError(f"not an XKRX session: {day}")
    return cal.next_session(day).strftime("%Y-%m-%d")


def window(cal, day, previous):
    position = cal.sessions.get_loc(day)
    if position < previous:
        return []
    return cal.sessions[position-previous:position+1].strftime("%Y-%m-%d").tolist()


def unique(rows):
    out = {}
    for row in rows:
        day = row["date"]
        if day in out:
            raise ValueError(f"duplicate date: {day}")
        out[day] = row
    return out


def option_features(board, cal):
    products = board["kr"]["investor_nets"]["detailed_15007"]["products"]
    series = []
    for product in ("options_call", "options_put"):
        values = {}
        for day, row in unique(products[product]["series"]).items():
            total, net = row.get("market_total", {}).get("buy_krw"), row.get("foreign", {}).get("net_krw")
            if row.get("quality") != "observed" or total is None or net is None:
                continue
            if not math.isfinite(total) or not math.isfinite(net) or total <= 0:
                continue
            if not cal.is_session(day):
                continue
            values[day] = net / total
        series.append(values)
    common = sorted(set(series[0]) & set(series[1]))
    result = {}
    for day in common:
        # Exchange sessions, not 60 arbitrary available observations.
        sessions = window(cal, day, 60)
        if len(sessions) != 61 or any(d not in s for s in series for d in sessions):
            continue
        features = []
        means = []
        for values in series:
            past = [values[d] for d in sessions[:-1]]
            # Rank based solely on prior 60 sessions, bounded even under regime change.
            features.append(sum(v < values[day] for v in past) / 60 - 0.5)
            means.append(sum(values[d] for d in sessions[-5:]) / 5)
        result[day] = features + means
    return result


def latest_source_day(board):
    products = board["kr"]["investor_nets"]["detailed_15007"]["products"]
    # Use the latest claimed input date; incomplete latest data must not fall back.
    days = [r["date"] for k in ("options_call", "options_put") for r in products[k]["series"]]
    if not days:
        raise ValueError("no option observations")
    return max(days)


def coverage_audit(board, etfs, cal, rows):
    products = board["kr"]["investor_nets"]["detailed_15007"]["products"]
    calls = set(unique(products["options_call"]["series"]))
    puts = set(unique(products["options_put"]["series"]))
    start, end = min(calls | puts), max(calls | puts)
    expected = set(cal.sessions_in_range(start,end).strftime("%Y-%m-%d"))
    features = set(option_features(board,cal))
    prices = set(unique(next(c["rows"] for c in etfs["candidates"] if c["ticker"] == "069500")))
    return {"option_dates": {"call":len(calls),"put":len(puts)}, "calendar_expected":len(expected),
            "calendar_version_warning": "Third-party calendar; disagreements need source review",
            "missing_call_dates": sorted(expected-calls), "missing_put_dates":sorted(expected-puts),
            "option_dates_outside_calendar":sorted((calls|puts)-expected),
            "missing_price_dates":sorted(expected-prices), "complete_feature_dates":len(features),
            "source_dates_without_complete_61_session_features":sorted((calls & puts & expected)-features),
            "labelled_common_rows":len(rows)}


def price_data(etfs, cal, ticker="069500"):
    rows = unique(next(c["rows"] for c in etfs["candidates"] if c["ticker"] == ticker))
    features, labels = {}, {}
    for day, row in rows.items():
        if not cal.is_session(day):
            continue
        target = next_day(cal, day)
        if target in rows:
            following = rows[target]
            o, c = following.get("open"), following.get("close")
            if o and c and min(o, c) > 0 and math.isfinite(o) and math.isfinite(c):
                labels[day] = {"target_date": target, "return": c / o - 1,
                               "y": int(c > o)}
        sessions = window(cal, day, 20)
        if len(sessions) != 21 or any(d not in rows for d in sessions):
            continue
        closes = np.array([rows[d]["close"] for d in sessions], dtype=float)
        if not np.isfinite(closes).all() or min(closes) <= 0:
            continue
        features[day] = [float(closes[-1] / closes[-6] - 1), float(np.std(closes[1:] / closes[:-1] - 1))]
    return features, labels


def dataset(board, etfs, cal):
    options = option_features(board, cal)
    prices, labels = price_data(etfs, cal)
    return [{"date": d, **labels[d], "option_only": options[d], "price_only": prices[d],
             "combined": prices[d] + options[d]}
            for d in sorted(set(options) & set(prices) & set(labels))]


def fit(rows, kind):
    from sklearn.linear_model import LogisticRegression
    x, y = np.array([r[kind] for r in rows]), np.array([r["y"] for r in rows])
    if len(rows) < 250 or len(set(y)) < 2:
        raise ValueError("need >=250 labelled sessions and both outcomes")
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale == 0] = 1
    model = LogisticRegression(C=1.0, max_iter=2000, random_state=0).fit((x-mean)/scale, y)
    return {"kind": kind, "mean": mean.tolist(), "scale": scale.tolist(),
            "coef": model.coef_[0].tolist(), "intercept": float(model.intercept_[0])}


def probability(model, x):
    z = sum(w * (v-m)/s for w,v,m,s in zip(model["coef"], x, model["mean"], model["scale"])) + model["intercept"]
    if len(x) != len(model["coef"]):
        raise ValueError("feature dimension mismatch")
    return 1/(1+math.exp(-max(-700, min(700, z))))


def metrics(records):
    if not records:
        return {"n": 0}
    y = np.array([r["y"] for r in records]); p = np.array([r["p"] for r in records])
    ret = np.array([r["return"] for r in records]); trade = p > 0.5
    report = {"n": len(y), "accuracy": float(np.mean((p > .5) == y)),
              "up_rate": float(y.mean()), "brier": float(np.mean((p-y)**2)),
              "log_loss": float(-np.mean(y*np.log(np.clip(p, 1e-9, 1-1e-9))+(1-y)*np.log(np.clip(1-p, 1e-9, 1-1e-9)))),
              "trades": int(trade.sum()), "exposure": float(trade.mean()), "cost_sensitivity": {}}
    for bps in (0, 5, 10, 20):
        daily = np.where(trade, ret-bps/10000, 0)
        equity = np.concatenate(([1.], np.cumprod(1+daily)))
        trimmed = sorted(daily.tolist(), reverse=True)[5:]
        report["cost_sensitivity"][str(bps)] = {
            "mean_per_trade_pct": float(daily.sum()/trade.sum()*100) if trade.sum() else None,
            "full_period_return_pct": float((equity[-1]-1)*100),
            "max_drawdown_pct": float(np.min(equity/np.maximum.accumulate(equity)-1)*100),
            "mean_daily_excluding_best_5_pct": float(np.mean(trimmed)*100) if trimmed else None}
    return report


def evaluate(rows):
    all_records = {k: [] for k in ("prior", "price_only", "option_only", "combined")}
    folds = []
    quarters = sorted({r["date"][:4] + "-" + str((int(r["date"][5:7])-1)//3+1) for r in rows if r["date"] >= "2022"})
    for quarter in quarters:
        year, q = map(int, quarter.split("-")); start = f"{year:04d}-{3*q-2:02d}-01"
        end = f"{year+1:04d}-01-01" if q == 4 else f"{year:04d}-{3*q+1:02d}-01"
        train = [r for r in rows if r["target_date"] < start]
        test = [r for r in rows if start <= r["date"] < end]
        if len(train) < 250 or not test:
            continue
        prior = sum(r["y"] for r in train)/len(train)
        fold = {"quarter": quarter, "train_last_target": max(r["target_date"] for r in train), "scores": {}}
        for kind in all_records:
            model = None if kind == "prior" else fit(train, kind)
            records = [{"date": r["date"], "target_date": r["target_date"], "y": r["y"], "return": r["return"],
                        "p": prior if model is None else probability(model, r[kind])} for r in test]
            fold["scores"][kind] = metrics(records)
            all_records[kind].extend(records)
        folds.append(fold)
    paired_delta = np.array([(a["p"]-a["y"])**2-(b["p"]-b["y"])**2
                             for a,b in zip(all_records["combined"], all_records["price_only"])])
    comparison = {"interpretation": "combined minus price-only Brier; negative is better"}
    if len(paired_delta):
        rng = np.random.default_rng(42)
        blocks = [paired_delta[i:i+5] for i in range(0, len(paired_delta)-4)]
        samples = [float(np.concatenate([blocks[i] for i in rng.integers(0,len(blocks),size=math.ceil(len(paired_delta)/5))])[:len(paired_delta)].mean()) for _ in range(1000)]
        comparison.update(mean_delta=float(paired_delta.mean()),
            block_bootstrap_95_interval=np.quantile(samples,[.025,.975]).tolist(),
            block_length=5, resamples=1000, seed=42,
            caveat="Exploratory dependence-aware interval, not multiple-testing adjusted")
    return {"schema_version": FEATURE_VERSION, "status": "research_only", "limitations": LIMITATIONS,
            "specification": {"target": "next XKRX session close > open; flat is class 0", "C": 1,
             "features": {"option_only": OPTION_FEATURES, "price_only": PRICE_FEATURES},
             "window": "expanding train, next quarter evaluation, label target strictly before quarter",
             "threshold": .5, "cost_bps_roundtrip": [0,5,10,20]},
            "folds": folds, "incremental_option_information": comparison,
            "overall": {k: metrics(v) for k,v in all_records.items()},
            "by_year": {str(y): {k: metrics([r for r in v if r["target_date"].startswith(str(y))]) for k,v in all_records.items()}
                        for y in range(2022, 2027)}, "predictions": all_records}


def train_artifact(rows, cutoff, inputs):
    if not rows or cutoff > max(r["target_date"] for r in rows):
        raise ValueError("cutoff exceeds latest complete training outcome")
    sample = [r for r in rows if r["target_date"] <= cutoff]
    artifact = {"schema_version": FEATURE_VERSION, "features": OPTION_FEATURES,
        "target": "next XKRX session ETF 069500 close > open; DOWN includes flat",
        "model": fit(sample, "option_only"), "trained_through": cutoff,
        "last_train_target": sample[-1]["target_date"], "n_train": len(sample),
        "input_hashes": inputs, "status": "research_only", "limitations": LIMITATIONS,
        "training_policy": "explicit train only; predict never retrains"}
    import sklearn
    artifact["training_runtime"] = {"numpy":np.__version__, "scikit_learn":sklearn.__version__}
    artifact["model_id"] = digest(artifact)
    return artifact


def predict(artifact, board, cal, as_of):
    unsigned = {k:v for k,v in artifact.items() if k != "model_id"}
    if digest(unsigned) != artifact["model_id"] or artifact["schema_version"] != FEATURE_VERSION or artifact["features"] != OPTION_FEATURES:
        raise ValueError("model hash or feature schema mismatch")
    import exchange_calendars as xc
    if artifact.get("calendar", {}).get("version", xc.__version__) != xc.__version__:
        raise ValueError("calendar version changed; review and version the model")
    if as_of < artifact["trained_through"]:
        raise ValueError("prediction precedes training cutoff")
    target = next_day(cal, as_of)
    result = {"schema_version": FEATURE_VERSION, "model_id": artifact["model_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(), "as_of": as_of, "target_date": target,
        "target": artifact["target"], "trained_through": artifact["trained_through"],
        "source_hash": digest(board), "status": "unavailable", "direction": None, "probability_up": None,
        "limitations": LIMITATIONS}
    features = option_features(board, cal).get(as_of)
    if features is None:
        result["reason"] = "missing/invalid observed call-put inputs within 61 required sessions"
        return result
    p = probability(artifact["model"], features)
    result.update(status="research_only", direction="UP" if p > .5 else "DOWN", probability_up=p,
                  feature_values=dict(zip(OPTION_FEATURES, features)), provider_published_at="unknown")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["evaluate", "train", "predict"])
    parser.add_argument("--board", type=Path, default=PUBLIC / "derivatives_board_v1.json")
    parser.add_argument("--prices", type=Path, default=PUBLIC / "kospi200_etf_candidates_daily_v1.json")
    parser.add_argument("--model", type=Path)
    parser.add_argument("--as-of", help="explicit source session / training cutoff")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); cal = calendar(); board = read(args.board)
    if args.output.resolve() in {args.board.resolve(), args.prices.resolve()}:
        parser.error("output cannot overwrite an input")
    if args.command == "predict":
        if not args.model:
            parser.error("predict requires --model")
        args.as_of = args.as_of or latest_source_day(board)
        if args.output.resolve() == args.model.resolve():
            parser.error("prediction output cannot overwrite model")
        result = predict(read(args.model), board, cal, args.as_of)
    else:
        prices = read(args.prices); rows = dataset(board, prices, cal)
        inputs = {"board": digest(board), "prices": digest(prices)}
        if args.command == "train":
            if not args.as_of:
                parser.error("train requires --as-of")
            if args.output.exists():
                parser.error("model output exists; use a new version path")
            result = train_artifact(rows, args.as_of, inputs)
        else:
            result = evaluate(rows); result["input_hashes"] = inputs
            result["coverage"] = coverage_audit(board,prices,cal,rows)
    import exchange_calendars as xc
    result["calendar"] = {"name": "XKRX", "version": xc.__version__, "source": "exchange_calendars; not an exchange-certified calendar"}
    if args.command == "train":
        result["model_id"] = digest({k:v for k,v in result.items() if k != "model_id"})
    if args.command == "predict" and args.output.exists():
        previous = read(args.output)
        stable_keys = ("model_id", "as_of", "source_hash", "status", "direction", "probability_up")
        if all(previous.get(k) == result.get(k) for k in stable_keys):
            print(json.dumps(previous, ensure_ascii=False))
            return
        parser.error("prediction exists with different inputs/model; use a new revision path")
    write(args.output, result)
    print(json.dumps({k:result[k] for k in ("status", "model_id", "as_of", "target_date", "direction", "probability_up") if k in result}))


if __name__ == "__main__":
    main()
