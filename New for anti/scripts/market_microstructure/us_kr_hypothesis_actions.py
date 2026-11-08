"""Adapt the existing pre-open trigger and closed-price snapshot for research forecasts."""

import argparse
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from option_direction_model import digest, read
from us_kr_hypothesis_shadow import (
    ARCHIVE, FAMILIES, calendars, first_path, score, sessions, stamp, utc_now, validate_model, write_once,
)

KST = ZoneInfo("Asia/Seoul")
TICKERS = {ticker for ticker, _ in FAMILIES.values()}


def plan(archive, model, now, requested=None):
    validate_model(model)
    kr, us = calendars()
    today = now.astimezone(KST).date().isoformat()
    if requested:
        target = requested
    else:
        days = kr.sessions.strftime("%Y-%m-%d")
        i = days.searchsorted(today)
        if i == len(days):
            raise ValueError("no future reviewed KRX session")
        target = days[i]
    timing = sessions(target, kr, us)
    pending = [
        family for family in FAMILIES
        if not first_path(archive, {"target_date": target, "model_id": model["model_id"], "family": family}).is_file()
    ]
    if target <= model["training_cutoff"]:
        reason = "target overlaps training"
    elif now < stamp(model["created_at"]):
        reason = "model is not yet available"
    elif now >= stamp(timing["cutoff_kst"]):
        reason = "08:30 KST cutoff reached"
    elif now < max(stamp(timing["kr_close_utc"]), stamp(timing["us_close_utc"])):
        reason = "waiting for required market closes"
    elif not pending:
        reason = "all shadow forecasts already recorded"
    else:
        reason = None
    return {"target": target, "run": reason is None, "pending_families": pending, "reason": reason}


def evaluate_snapshot(archive, model, prices, now):
    bars = {}
    for item in prices["candidates"]:
        ticker = item["ticker"]
        if ticker not in TICKERS:
            continue
        if ticker in bars:
            raise ValueError(f"duplicate outcome ticker: {ticker}")
        bars[ticker] = item["rows"]
    errors = [e for e in prices.get("errors", []) if e.get("ticker") in TICKERS]
    comparisons = score(archive, model, {"collected_at": prices["collected_at"], "kr": bars}, now)
    has_scores = any(head["candidate"]["n"] for pair in comparisons.values() for head in pair.values())
    return {
        "schema_version": "us-kr-hypothesis-forward-evaluation-v1",
        "status": "partial_outcomes" if errors else "scored" if has_scores else "awaiting_matched_outcomes",
        "model_id": model["model_id"], "generated_at": now.isoformat(),
        "outcomes_collected_at": prices["collected_at"], "outcome_snapshot_sha256": digest(prices),
        "outcome_errors": errors, "comparisons": comparisons,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "evaluate"))
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    parser.add_argument("--target")
    parser.add_argument("--outcomes", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    model, now = read(args.model), utc_now()
    if args.command == "plan":
        result = plan(args.archive, model, now, args.target)
        if github_output := os.environ.get("GITHUB_OUTPUT"):
            with Path(github_output).open("a") as handle:
                handle.write(f"target={result['target']}\nrun={str(result['run']).lower()}\n")
        print(json.dumps(result))
        return
    if not args.outcomes or not args.output:
        parser.error("evaluate requires --outcomes and --output")
    if (args.output.resolve() in {args.model.resolve(), args.outcomes.resolve(), args.archive.resolve()}
            or args.archive.resolve() in args.output.resolve().parents):
        parser.error("output must be separate from the model, outcomes and forecast archive")
    result = evaluate_snapshot(args.archive, model, read(args.outcomes), now)
    if not write_once(args.output, result):
        raise ValueError("use a new evaluation output path")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
