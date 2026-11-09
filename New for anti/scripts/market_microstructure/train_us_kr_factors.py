"""Explicit offline training. The pre-open runner only reads the frozen artifact."""

import argparse
import gzip
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from option_direction_model import calendar, digest, fit, option_features, probability, read, unique, window, write
from research_option_dynamics import logit, sigmoid_calibration
from research_short_horizon_prediction import holm
from us_kr_factors import CONFIG, HEADS, SYMBOLS, VERSION, calendars, calibrated, flow_index, flow_vector, us_input


def fitted(train, calibration):
    model = fit(train, "x")
    scores = [logit(probability(model, row["x"])) for row in calibration]
    return {"fit": model, "calibration": sigmoid_calibration(scores, [row["y"] for row in calibration])}


def split(rows, boundary, final=False):
    start = (boundary - pd.DateOffset(months=6)).strftime("%Y-%m-%d")
    end = boundary.strftime("%Y-%m-%d")
    train = [r for r in rows if r["target_date"] < start]
    cal = [r for r in rows if start <= r["date"] and r["target_date"] < end]
    if len(train) < 250 or len(cal) < 60 or len({r["y"] for r in cal}) < 2 or len({r["y"] for r in train}) < 2:
        if final:
            raise ValueError("insufficient temporal training or calibration history")
        return None
    return train, cal


def evaluate(rows, cutoff):
    result = []
    for quarter in pd.date_range("2021-01-01", cutoff, freq="QS"):
        start, end = quarter.strftime("%Y-%m-%d"), (quarter + pd.DateOffset(months=3)).strftime("%Y-%m-%d")
        test = [r for r in rows if start <= r["target_date"] < end]
        parts = split(rows, quarter)
        if not test or not parts:
            continue
        train, cal = parts
        model = fitted(train, cal)
        prior = sum(r["y"] for r in cal) / len(cal)
        result.extend({**r, "p": calibrated(model, r["x"]), "base": prior} for r in test)
    if not result or len({r["y"] for r in result}) < 2:
        raise ValueError("insufficient out-of-sample directions")
    return result


def summarize(rows):
    y = np.array([r["y"] for r in rows], dtype=bool)
    p = np.array([r["p"] for r in rows])
    prior = np.array([r["base"] for r in rows])
    hit = np.where(y, p > .5, p < .5)
    return {
        "period": {"start": min(r["target_date"] for r in rows), "end": max(r["target_date"] for r in rows)},
        "n": len(rows), "hit": float(hit.mean()), "balanced_hit": float((hit[y].mean() + hit[~y].mean())/2),
        "base_rate": float(y.mean()), "brier": float(np.mean((p-y)**2)),
        "brier_base": float(np.mean((prior-y)**2)),
    }


def comparison(rows):
    # Keep contemporaneous ticker/target errors together in a daily block.
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["target_date"]].append((row["p"]-row["y"])**2-(row["base"]-row["y"])**2)
    daily = np.array([np.mean(v) for _, v in sorted(grouped.items())])
    blocks = np.lib.stride_tricks.sliding_window_view(daily, 5)
    rng = np.random.default_rng(42)
    sampled = rng.integers(len(blocks), size=(2000, int(np.ceil(len(daily)/5))))
    means = blocks[sampled].reshape(2000, -1)[:, :len(daily)].mean(axis=1)
    observed = float(daily.mean())
    p = (1 + int((np.abs(means-observed) >= abs(observed)).sum())) / (len(means)+1)
    return {"brier_delta": observed, "block95": np.quantile(means,[.025,.975]).tolist(),
            "two_sided_centered_block_p": p}


def train(board, kr_doc, us_doc, flow_rows, cutoff, created):
    kr, us = calendars()
    if not kr.is_session(cutoff) or created < calendar().session_close(cutoff):
        raise ValueError("training cutoff must be a closed KRX session")
    prices = {tk: unique(rows) for tk, rows in kr_doc.items()}
    us_data = {symbol: unique(us_doc[symbol]) for symbol in SYMBOLS}
    options = option_features(board, kr)
    flows = flow_index(flow_rows, created)
    targets = kr.sessions[(kr.sessions >= "2019-01-02") & (kr.sessions <= cutoff)].strftime("%Y-%m-%d")
    aligned = [(target, window(kr, target, 1)[0], us_input(us_data, us, target)[0]) for target in targets]
    artifact = {"schema_version": VERSION, "trained_through": cutoff, "created_at": created.isoformat(),
                "training_input_hashes": {"board": digest(board), "kr": digest(kr_doc), "us": digest(us_doc),
                                          "12009": digest(flow_rows)}, "factors": {}}
    reports = {}
    for group, (label, names, tickers) in CONFIG.items():
        models, detailed, pooled = {}, {}, []
        for tk in tickers:
            models[tk], detailed[tk] = {}, {}
            observations = []
            bars = prices[tk]
            for target, source, market in aligned:
                if source not in bars or target not in bars:
                    continue
                if group == "options":
                    x = options.get(source)
                elif group == "us_price":
                    x = market
                else:
                    x = flow_vector(flows, kr, tk, source)
                if x is not None:
                    observations.append((source, target, x, bars[source]["close"], bars[target]))
            for head, price_key in HEADS.items():
                rows = [{"date": source, "target_date": target, "x": x, "y": int(bar[price_key] > prev)}
                        for source, target, x, prev, bar in observations
                        if prev > 0 and bar[price_key] > 0 and bar[price_key] != prev]
                predicted = evaluate(rows, cutoff)
                detailed[tk][head] = summarize(predicted)
                pooled.extend(predicted)
                train_rows, cal = split(rows, pd.Timestamp(cutoff) + pd.Timedelta(days=1), final=True)
                models[tk][head] = {**fitted(train_rows, cal), "n_train": len(train_rows),
                                    "n_calibration": len(cal), "outcomes_through": cal[-1]["target_date"]}
        validation = {**summarize(pooled), "by_ticker": detailed, "method": "quarterly expanding fit; preceding six months calibration; next three months test; nonflat"}
        reports[group] = comparison(pooled)
        artifact["factors"][group] = {"label_ko": label, "inputs": list(names), "models": models, "validation": validation}
    holm(reports)
    for group, factor in artifact["factors"].items():
        validation, evidence = factor["validation"], reports[group]
        skill = "none"
        if evidence["brier_delta"] < 0 and evidence["holm_adjusted_p"] < .05 and validation["balanced_hit"] > .5:
            skill = "yes" if all(h["brier"] < h["brier_base"] for t in validation["by_ticker"].values() for h in t.values()) else "weak"
        validation.update(skill=skill, paired_daily_brier=evidence)
        factor["model_id"] = digest(factor)
    return artifact


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("board", "kr", "us", "flow-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--cutoff", required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("use a new output path")
    rows = []
    parts = sorted(args.flow_dir.rglob("*.jsonl.gz"))
    for part in parts:
        with gzip.open(part, "rt") as handle:
            for line in handle:
                rows.append(json.loads(line))
    model = train(read(args.board), read(args.kr), read(args.us), rows, args.cutoff, datetime.now(timezone.utc))
    write(args.output, model)
