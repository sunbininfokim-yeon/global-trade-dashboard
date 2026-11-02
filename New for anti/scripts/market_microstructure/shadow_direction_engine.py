"""Explicitly versioned calibrated shadow engine; does not replace the v1 engine."""
import argparse
import hashlib
import math
from datetime import datetime, timezone
from pathlib import Path

from scipy.special import expit

from option_direction_model import (PUBLIC, calendar, dataset, digest, fit, latest_source_day,
    option_features, price_data, probability, read, unique, write)
from research_direction_diagnostics import ReviewedCalendar, richer_price_features
from research_option_dynamics import BASE_NAMES, logit, sigmoid_calibration

VERSION="calibrated-direction-shadow-v2"


def code_hashes():
    return {name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ("shadow_direction_engine.py","option_direction_model.py",
                         "research_direction_diagnostics.py","research_option_dynamics.py",
                         "research_pr791_evaluation.py")}


def train_shadow(board, prices, cutoff):
    import pandas as pd
    cal=ReviewedCalendar(calendar());rows=dataset(board,prices,cal)
    bars=unique(next(c["rows"] for c in prices["candidates"] if c["ticker"]=="069500"))
    rows=richer_price_features(rows,bars,cal)
    start=(pd.Timestamp(cutoff)+pd.Timedelta(days=1)-pd.DateOffset(months=6)).strftime("%Y-%m-%d")
    base=[{**r,"baseline":r["price_only"]+r["option_only"]} for r in rows if r["target_date"]<start]
    calibration=[{**r,"baseline":r["price_only"]+r["option_only"]} for r in rows
                 if r["date"]>=start and r["target_date"]<=cutoff]
    if not calibration or max(r["target_date"] for r in rows)<cutoff:
        raise ValueError("cutoff beyond complete outcomes")
    if len(calibration)<60: raise ValueError("insufficient independent calibration observations")
    model=fit(base,"baseline")
    c=sigmoid_calibration([logit(probability(model,r["baseline"])) for r in calibration],[r["y"] for r in calibration])
    import exchange_calendars as xc
    artifact={"schema_version":VERSION,"features":BASE_NAMES,"model":model,"calibrator":c,
        "trained_through":cutoff,"last_base_target":max(r["target_date"] for r in base),
        "first_calibration_source":min(r["date"] for r in calibration),
        "last_calibration_target":max(r["target_date"] for r in calibration),
        "n_base":len(base),"n_calibration":len(calibration),
        "calendar_version":xc.__version__,"calendar_overlay":"reviewed-six-closures-20261101",
        "input_hashes":{"board":digest(board),"prices":digest(prices)},
        "created_at":datetime.now(timezone.utc).isoformat(),"status":"shadow_only",
        "implementation_sha256":code_hashes(),
        "validation":"selected after retrospective research; incremental skill not established",
        "target":"069500 next KRX session close > open; DOWN includes flat"}
    if artifact["last_base_target"]>=artifact["first_calibration_source"]: raise AssertionError("calibration leakage")
    artifact["model_id"]=digest(artifact)
    return artifact


def predict_shadow(artifact,board,prices,as_of,generated_at=None):
    import exchange_calendars as xc
    if digest({k:v for k,v in artifact.items() if k!="model_id"})!=artifact["model_id"]:
        raise ValueError("model integrity check failed")
    if artifact["schema_version"]!=VERSION or artifact["features"]!=BASE_NAMES or artifact["calendar_version"]!=xc.__version__:
        raise ValueError("model feature/calendar version mismatch")
    if artifact.get("implementation_sha256")!=code_hashes():
        raise ValueError("frozen implementation changed; create a reviewed model version")
    if as_of<artifact["trained_through"]: raise ValueError("source day precedes training cutoff")
    base_cal=calendar();cal=ReviewedCalendar(base_cal)
    if not cal.is_session(as_of): raise ValueError("source day is not a reviewed KRX session")
    target=cal.next_session(as_of).strftime("%Y-%m-%d")
    generated_at=generated_at or datetime.now(timezone.utc)
    if generated_at.tzinfo is None: raise ValueError("timezone-aware generation timestamp required")
    opening=base_cal.session_open(target).to_pydatetime()
    source_close=base_cal.session_close(as_of).to_pydatetime()
    output={"schema_version":VERSION,"model_id":artifact["model_id"],"as_of":as_of,"target_date":target,
        "generated_at":generated_at.isoformat(),"target_open":opening.isoformat(),
        "trained_through":artifact["trained_through"],"target":artifact["target"],
        "input_hashes":{"board":digest(board),"prices":digest(prices)},
        "status":"unavailable","direction":None,"probability_up":None,
        "validation":artifact["validation"],"provider_published_at":"unknown"}
    if generated_at<datetime.fromisoformat(artifact["created_at"]):
        output["reason"]="model did not exist at requested forecast time";return output
    if generated_at<source_close:
        output["reason"]="source session has not closed";return output
    option=option_features(board,cal).get(as_of)
    price,_=price_data(prices,cal)
    if option is None or as_of not in price:
        output["reason"]="missing fresh option or ETF price features";return output
    bars=unique(next(c["rows"] for c in prices["candidates"] if c["ticker"]=="069500"))
    rich=richer_price_features([{"date":as_of,"price_only":price[as_of],"option_only":option}],bars,cal)
    if not rich:
        output["reason"]="incomplete ETF price window";return output
    x=rich[0]["price_only"]+option
    if not all(math.isfinite(v) for v in x):
        output["reason"]="nonfinite feature";return output
    raw=probability(artifact["model"],x)
    c=artifact["calibrator"];p=float(expit(c["slope"]*logit(raw)+c["intercept"]))
    output.update(status="shadow_research" if generated_at<opening else "retrospective_research",
        direction="UP" if p>.5 else "DOWN",probability_up=p,probability_non_up=1-p,
        raw_probability_up=raw,feature_values=dict(zip(BASE_NAMES,x)),
        calibration_slope=c["slope"],calibration_has_zero_slope=c["at_zero_slope"],
        information_state="recent_base_rate_only" if c["at_zero_slope"] else "model_score_with_calibration",
        timing_evidence="local generation time; public first-seen time not verified")
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=["train","predict"])
    parser.add_argument("--board",type=Path,default=PUBLIC/"derivatives_board_v1.json")
    parser.add_argument("--prices",type=Path,default=PUBLIC/"kospi200_etf_candidates_daily_v1.json")
    parser.add_argument("--as-of");parser.add_argument("--model",type=Path)
    parser.add_argument("--output",type=Path,required=True);args=parser.parse_args()
    if args.output.resolve() in {p.resolve() for p in [args.board,args.prices]+([args.model] if args.model else [])}:
        parser.error("output would overwrite an input")
    board,prices=read(args.board),read(args.prices)
    if args.command=="train":
        if args.output.exists(): parser.error("new model version path required")
        if not args.as_of: parser.error("train requires --as-of")
        result=train_shadow(board,prices,args.as_of)
    else:
        if not args.model: parser.error("predict requires --model")
        result=predict_shadow(read(args.model),board,prices,args.as_of or latest_source_day(board))
        if args.output.exists():
            previous=read(args.output)
            if all(previous.get(k)==result.get(k) for k in ("model_id","as_of","target_date","input_hashes","status","probability_up")):
                print("unchanged forecast",args.output);return
            parser.error("forecast changed; preserve original using a revision path")
    write(args.output,result)
    print({k:result.get(k) for k in ("status","model_id","as_of","target_date","direction","probability_up")})


if __name__=="__main__":main()
