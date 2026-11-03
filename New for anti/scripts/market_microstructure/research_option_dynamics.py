"""Time-separated OI dynamics / probability calibration research. No live updates."""
from __future__ import annotations

import argparse
import hashlib
import math
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit

from option_direction_model import calendar, dataset, fit, probability, unique, window, write
from research_direction_diagnostics import ReviewedCalendar, richer_price_features
from research_pr791_evaluation import FEATURES, compare, extras, git_json, score

BASE_NAMES = FEATURES["price_only"] + FEATURES["option_only"]
DYNAMIC_NAMES = BASE_NAMES + FEATURES["extra"][:3] + [
    "call_oi_log_change", "put_oi_log_change", "futures_oi_log_change", "iv_change_div100",
    "intraday_return_times_foreign_futures_flow"]
FAMILIES = ["baseline", "levels", "dynamics"]


def dynamic_features(deriv, cal):
    dates = deriv["dates"]
    if len(dates) != len(set(dates)): raise ValueError("duplicate supplemental dates")
    fields = {
        "call_oi":deriv["option_oi"]["call_oi"], "put_oi":deriv["option_oi"]["put_oi"],
        "futures_oi":deriv["futures_front"]["open_interest"], "iv":deriv["option_oi"]["atm_iv"],
        "expiry":deriv["option_oi"]["expiry"], "contract":deriv["futures_front"]["contract"]}
    if any(len(a)!=len(dates) for a in fields.values()): raise ValueError("date axis mismatch")
    by_date = {d:{k:a[i] for k,a in fields.items()} for i,d in enumerate(dates)}
    values, excluded = {}, {}
    for day, cur in by_date.items():
        history = window(cal,day,1) if cal.is_session(day) else []
        if len(history)!=2 or history[0] not in by_date:
            excluded[day]=["previous_KRX_session_missing"]; continue
        prev = by_date[history[0]]; reasons=[]
        for field in ("expiry","contract"):
            if not cur[field] or not prev[field]: reasons.append("missing_"+field)
            elif cur[field] != prev[field]: reasons.append(field+"_changed")
        for field in ("call_oi","put_oi","futures_oi","iv"):
            pair=[cur[field],prev[field]]
            if any(v is None or not math.isfinite(v) or v<=0 for v in pair):
                reasons.append("missing_or_nonpositive_"+field)
        if reasons:
            excluded[day]=reasons; continue
        values[day] = [math.log(cur[k]/prev[k]) for k in ("call_oi","put_oi","futures_oi")]+[(cur["iv"]-prev["iv"])/100]
    return values, excluded


def assemble(base, deriv, cal, lag):
    if lag not in (0,1): raise ValueError("only prespecified lag 0/1 supported")
    levels, _ = extras(deriv); changes, excluded = dynamic_features(deriv,cal)
    base_lookup = {r["date"]:r for r in base}; rows=[]
    for r in base:
        source = r["date"]
        if lag:
            previous = window(cal,source,1)
            if len(previous)!=2: continue
            source = previous[0]
        if source not in levels or source not in changes or source not in base_lookup: continue
        flow = base_lookup[source]["option_only"]
        baseline = r["price_only"]+flow
        current = levels[source]; dynamic = changes[source]
        rows.append({"date":r["date"],"target_date":r["target_date"],"y":r["y"],"return":r["return"],
            "feature_source_date":source, "baseline":baseline, "levels":baseline+current,
            "dynamics":baseline+current[:3]+dynamic+[r["price_only"][4]*current[0]]})
    return rows, excluded


def sigmoid_calibration(z, y):
    z=np.asarray(z,dtype=float);y=np.asarray(y,dtype=float)
    if not np.isfinite(z).all() or len(set(y))!=2: raise ValueError("invalid calibration sample")
    def objective(theta):
        a,b=theta;v=a*z+b;p=expit(v)
        loss=np.logaddexp(0,v).sum()-np.dot(y,v)+.5*a*a
        grad=np.array([np.dot(p-y,z)+a,(p-y).sum()])
        return float(loss),grad
    prior=y.mean()
    opt=minimize(objective,[1.,math.log(prior/(1-prior))],jac=True,method="L-BFGS-B",
                 bounds=[(0,None),(None,None)],options={"maxiter":1000,"ftol":1e-12})
    if not opt.success: raise ValueError("calibration optimization failed: "+str(opt.message))
    return {"slope":float(opt.x[0]),"intercept":float(opt.x[1]),"n":len(y),
            "at_zero_slope":bool(opt.x[0]<1e-8),"method":"monotone sigmoid, fixed slope penalty .5*a^2"}


def logit(p):
    p=float(np.clip(p,1e-12,1-1e-12));return math.log(p/(1-p))


def splits(rows):
    quarters=sorted({(int(r["date"][:4]),(int(r["date"][5:7])-1)//3+1)
                     for r in rows if r["date"]>="2022"})
    for year,quarter in quarters:
        start=f"{year:04d}-{3*quarter-2:02d}-01"
        end=f"{year+1:04d}-01-01" if quarter==4 else f"{year:04d}-{3*quarter+1:02d}-01"
        calibration_start=(pd.Timestamp(start)-pd.DateOffset(months=6)).strftime("%Y-%m-%d")
        train=[r for r in rows if r["target_date"]<calibration_start]
        calibration=[r for r in rows if r["date"]>=calibration_start and r["target_date"]<start]
        test=[r for r in rows if start<=r["date"]<end]
        if len(train)<250 or len(calibration)<60 or not test: continue
        if len({r["y"] for r in train})!=2 or len({r["y"] for r in calibration})!=2: continue
        assert max(r["target_date"] for r in train)<min(r["date"] for r in calibration)
        assert max(r["target_date"] for r in calibration)<min(r["date"] for r in test)
        yield start,train,calibration,test


def evaluate(rows, families=FAMILIES):
    predictions={"prior_base":[],"prior_recent":[]}
    predictions.update({f+"_"+s:[] for f in families for s in ("raw","calibrated")})
    folds=[]
    for start,train,calibration,test in splits(rows):
        fold={"test_start":start,"n_base":len(train),"n_calibration":len(calibration),"n_test":len(test),
              "last_base_target":max(r["target_date"] for r in train),
              "first_calibration_source":min(r["date"] for r in calibration),
              "last_calibration_target":max(r["target_date"] for r in calibration),"calibrators":{}}
        common=lambda r:{k:r[k] for k in ("date","target_date","feature_source_date","y","return")}
        for name,group in (("prior_base",train),("prior_recent",calibration)):
            prior=sum(r["y"] for r in group)/len(group)
            predictions[name]+=[{**common(r),"p":prior} for r in test]
        for family in families:
            model=fit(train,family)
            z=[logit(probability(model,r[family])) for r in calibration]
            calibrator=sigmoid_calibration(z,[r["y"] for r in calibration])
            fold["calibrators"][family]=calibrator
            for r in test:
                p=probability(model,r[family])
                adjusted=float(expit(calibrator["slope"]*logit(p)+calibrator["intercept"]))
                predictions[family+"_raw"].append({**common(r),"p":p})
                predictions[family+"_calibrated"].append({**common(r),"p":adjusted})
        folds.append(fold)
    return predictions,folds


def run(ref,lag):
    names=["derivatives_board_v1.json","kospi200_etf_candidates_daily_v1.json","krx_deriv_flow_v1.json"]
    loaded=[git_json(ref,n) for n in names];board,etfs,deriv=[r[0] for r in loaded]
    cal=ReviewedCalendar(calendar())
    base=dataset(board,etfs,cal)
    prices=unique(next(c["rows"] for c in etfs["candidates"] if c["ticker"]=="069500"))
    base=richer_price_features(base,prices,cal)
    rows,excluded=assemble(base,deriv,cal,lag)
    predictions,folds=evaluate(rows)
    if not folds: raise ValueError("no evaluable calibration folds")
    comparisons={}
    for family in FAMILIES:
        key=family+"_calibrated"
        comparisons[key]={"vs_raw":compare(predictions[key],predictions[family+"_raw"]),
                          "vs_recent_prior":compare(predictions[key],predictions["prior_recent"]),
                          "vs_base_prior":compare(predictions[key],predictions["prior_base"]),
                          "vs_calibrated_baseline":compare(predictions[key],predictions["baseline_calibrated"])}
    feature_names={"baseline":BASE_NAMES,"levels":BASE_NAMES+FEATURES["extra"],"dynamics":DYNAMIC_NAMES}
    return {"status":"research_only","analysis_date":"2026-11-02","source_commit":ref,"lag":lag,
        "input_sha256":{n:sha for n,(_,sha) in zip(names,loaded)},
        "implementation_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "target":"next KRX session ETF 069500 close > open; DOWN includes flat",
        "features":feature_names,"coverage":{"n_complete_rows":len(rows),"last_decision_date":rows[-1]["date"],
            "last_feature_source_date":rows[-1]["feature_source_date"],"last_target_date":rows[-1]["target_date"],
            "dynamic_exclusions":dict(Counter(reason for reasons in excluded.values() for reason in reasons)),
            "excluded_dates":excluded},
        "folds":folds,"scores":{k:score(v) for k,v in predictions.items()},"comparisons":comparisons,
        "october_source_scores":{k:score([r for r in v if r["date"].startswith("2026-10")]) for k,v in predictions.items()},
        "predictions":predictions,
        "limitations":["Retrospective explored sample; many historical diagnostics, no untouched holdout",
                       "Exact expiration dates / historical strike-level IV not available; no guessed DTE or skew",
                       "OI change unavailable across month rolls or missing immediately preceding sessions",
                       "Calibrated probabilities must beat recent-prior baseline to demonstrate new information",
                       "Lag 1 is a past-information sensitivity, not proof of timezone correction",
                       "Pre-open publication times and adjusted OHLC execution equivalence remain unverified",
                       "No model/forecast/UI/workflow update; prospective validation required before promotion"]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref",required=True);parser.add_argument("--lag",type=int,choices=[0,1],default=0)
    parser.add_argument("--output",type=Path,required=True);args=parser.parse_args()
    result=run(args.ref,args.lag);write(args.output,result)
    print("coverage",{k:v for k,v in result["coverage"].items() if k!="excluded_dates"})
    for k,v in result["scores"].items():
        d=v["direction"];print(k,"n",d["n"],"accuracy",d["accuracy"],"brier",d["brier"])
    print("comparisons",result["comparisons"])


if __name__=="__main__":main()
