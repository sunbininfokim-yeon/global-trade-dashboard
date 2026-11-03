"""Diagnostic research only. Never modifies the frozen model or its forecasts."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from option_direction_model import (PUBLIC, calendar, dataset, digest, evaluate, fit,
    next_day, option_features, probability, read, unique, window, write)

REVIEWED_CLOSURES = ["2024-10-01", "2025-01-27", "2025-06-03", "2026-05-25", "2026-06-03", "2026-07-17"]
SOURCES = [
    {"supports": REVIEWED_CLOSURES[:-1],
     "url": "https://github.com/gerrymanoim/exchange_calendars/blob/7062399f48d9a7ee89c454b4273e3bebf8a4d01e/exchange_calendars/xkrx_holidays.py"},
    {"supports": ["2026-06-03", "2026-07-17"],
     "url": "https://stock.mk.co.kr/news/disclosure/template/1028611",
     "type": "exchange closure notice republished by MK, not independently fetched from KRX"}]


class ReviewedCalendar:
    def __init__(self, base):
        self.sessions = base.sessions[~base.sessions.strftime("%Y-%m-%d").isin(REVIEWED_CLOSURES)]

    def is_session(self, day):
        return day in self.sessions

    def next_session(self, day):
        return self.sessions[self.sessions.get_loc(day)+1]

    def sessions_in_range(self, start, end):
        return self.sessions[(self.sessions >= start) & (self.sessions <= end)]


def bootstrap_mean(values, block=5, trials=1000):
    a = np.array(values, dtype=float)
    if len(a) < block:
        return None
    rng = np.random.default_rng(42)
    blocks = np.lib.stride_tricks.sliding_window_view(a, block)
    samples = np.array([blocks[rng.integers(0,len(blocks),size=math.ceil(len(a)/block))].ravel()[:len(a)].mean()
                        for _ in range(trials)])
    return np.quantile(samples,[.025,.975]).tolist()


def directional_scores(records):
    if not records:
        return {"n":0}
    y = np.array([r["y"] for r in records]); p = np.array([r["p"] for r in records])
    predicted = p > .5
    correct = predicted == y
    accuracy = float(correct.mean())
    up_recall = float(predicted[y == 1].mean()) if (y == 1).any() else None
    down_recall = float((~predicted[y == 0]).mean()) if (y == 0).any() else None
    bins = []
    for lo, hi in ((0,.4),(.4,.45),(.45,.5),(.5,.55),(.55,.6),(.6,1.000001)):
        use = (p >= lo)&(p < hi)
        bins.append({"p_range":[lo,min(hi,1)],"n":int(use.sum()),
                     "estimated_p_mean":float(p[use].mean()) if use.any() else None,
                     "realized_up_rate":float(y[use].mean()) if use.any() else None})
    annual = {str(year): directional_scores_no_recursion([r for r in records if r["target_date"].startswith(str(year))])
              for year in range(2022,2027)}
    return {"n":len(y),"accuracy":accuracy,"accuracy_block95":bootstrap_mean(correct),
        "always_up_accuracy":float(y.mean()),"always_down_accuracy":float(1-y.mean()),
        "up_recall":up_recall,"down_recall":down_recall,
        "balanced_accuracy":(up_recall+down_recall)/2 if up_recall is not None and down_recall is not None else None,
        "mean_p":float(p.mean()),"brier":float(np.mean((p-y)**2)),
        "calibration_bins":bins,"by_year":annual}


def directional_scores_no_recursion(records):
    if not records: return {"n":0}
    y = np.array([r["y"] for r in records]); p = np.array([r["p"] for r in records])
    return {"n":len(y),"accuracy":float(((p>.5)==y).mean()),"up_rate":float(y.mean()),
            "brier":float(((p-y)**2).mean())}


def richer_price_features(rows, prices, cal):
    out = []
    for r in rows:
        days = window(cal,r["date"],20)
        if len(days) != 21 or any(d not in prices for d in days):
            continue
        current, previous = prices[days[-1]], prices[days[-2]]
        if min(current["open"],current["close"],previous["close"],prices[days[0]]["close"]) <= 0:
            continue
        extra = [current["close"]/previous["close"]-1, current["open"]/previous["close"]-1,
                 current["close"]/current["open"]-1, current["close"]/prices[days[0]]["close"]-1]
        # Same fixed C, no search. This diagnoses a weak price baseline.
        q = dict(r); q["price_only"] = r["price_only"] + extra
        q["combined"] = q["price_only"] + r["option_only"]
        out.append(q)
    return out


def flow_identity_check(board):
    result = {}
    products=board["kr"]["investor_nets"]["detailed_15007"]["products"]
    for kind in ("options_call","options_put"):
        bad_net,bad_total,missing=[],[],[]
        for r in products[kind]["series"]:
            f,t=r["foreign"],r["market_total"]
            if any(f.get(k) is None for k in ("buy_krw","sell_krw","net_krw")):
                missing.append(r["date"]); continue
            if abs(f["buy_krw"]-f["sell_krw"]-f["net_krw"]) > 1:
                bad_net.append(r["date"])
            if t.get("buy_krw") is not None and t.get("sell_krw") is not None and abs(t["buy_krw"]-t["sell_krw"]) > 1:
                bad_total.append(r["date"])
        result[kind]={"net_identity_failures":bad_net,"market_buy_sell_disagreements":bad_total,"incomplete_foreign":missing}
    return result


def supplemental_experiment(board, etfs, deriv, cal, rows, prices):
    dates=deriv["dates"]
    if len(dates)!=len(set(dates)): raise ValueError("duplicate supplemental flow dates")
    arrays={"fut_net":deriv["flow"]["futures"]["foreign_net"],
            "fut_total":deriv["flow"]["futures"]["market_total_buy"],
            "call_inst":deriv["flow"]["options_call"]["institution_net"],
            "call_total":deriv["flow"]["options_call"]["market_total_buy"],
            "put_inst":deriv["flow"]["options_put"]["institution_net"],
            "put_total":deriv["flow"]["options_put"]["market_total_buy"],
            "pc_oi":deriv["option_oi"]["pc_oi"],"atm_iv":deriv["option_oi"]["atm_iv"]}
    if any(len(v)!=len(dates) for v in arrays.values()): raise ValueError("supplemental arrays do not match date axis")
    extra={}
    partial=set().union(*(set(v) for v in deriv["partial_days"].values()))
    for i,day in enumerate(dates):
        v={k:a[i] for k,a in arrays.items()}
        if day in partial or any(x is None or not math.isfinite(x) for x in v.values()): continue
        if min(v["fut_total"],v["call_total"],v["put_total"],v["pc_oi"],v["atm_iv"])<=0: continue
        extra[day]=[v["fut_net"]/v["fut_total"],v["call_inst"]/v["call_total"],
                    v["put_inst"]/v["put_total"],math.log(v["pc_oi"]),v["atm_iv"]/100]
    original=richer_price_features([r for r in rows if r["date"] in extra],prices,cal)
    extended=[]
    for r in original:
        q=dict(r);q["option_only"]=r["option_only"]+extra[r["date"]]
        q["combined"]=r["price_only"]+q["option_only"]
        extended.append(q)
    old=evaluate(original);new=evaluate(extended)
    # Check whether the other 15007 copy agrees in the overlap before judging its features.
    comparison={}
    for product in ("options_call","options_put"):
        present=unique(board["kr"]["investor_nets"]["detailed_15007"]["products"][product]["series"])
        conflicts=[];tested=0
        for i,day in enumerate(dates):
            net=deriv["flow"][product]["foreign_net"][i]
            if day not in present or net is None: continue
            tested+=1
            if abs(net*1e6-present[day]["foreign"]["net_krw"])>1:
                conflicts.append(day)
        comparison[product]={"overlap_tested":tested,"foreign_net_disagreements":conflicts}
    coverage={}
    for name,axis,group in (("flow_futures",dates,deriv["flow"]["futures"]),
                            ("futures_front",dates,deriv["futures_front"]),
                            ("option_oi",dates,deriv["option_oi"]),
                            ("program",deriv["program"]["dates"],deriv["program"])):
        coverage[name]={}
        for field,values in group.items():
            if not isinstance(values,list) or len(values)!=len(axis) or field=="dates": continue
            valid=[d for d,v in zip(axis,values) if v is not None]
            coverage[name][field]={"n":len(valid),"last":max(valid) if valid else None,
                "dates_after_last_on_option_axis":[d for d in sorted(set(prices)) if valid and max(valid)<d<=max(prices)]}
    return {"status":"research_only", "supplemental_input_hash":digest(deriv),
        "extra_features":["foreign_futures_net/market_buy","institution_call_net/market_buy",
                          "institution_put_net/market_buy","log_put_call_oi","atm_iv/100"],
        "n_common_rows":len(extended),"last_feature_date":extended[-1]["date"] if extended else None,
        "source_copy_reconciliation":comparison,"coverage":coverage,
        "old_on_same_dates":{k:directional_scores(v) for k,v in old["predictions"].items()},
        "extended_on_same_dates":{k:directional_scores(v) for k,v in new["predictions"].items()},
        "incremental_vs_price":new["incremental_option_information"],
        "performance_illustrative":new["overall"],
        "caveat":"One exploratory fixed 5-feature extension. Same dates for comparisons; no live model update. OI is whole-market front-month, not foreign holdings; weekly excluded. Reconciliation conflicts prohibit using these inputs to promote a model."}


def run(board,etfs,deriv):
    base=calendar(); cal=ReviewedCalendar(base)
    raw_rows=dataset(board,etfs,base); rows=dataset(board,etfs,cal)
    prices=unique(next(c["rows"] for c in etfs["candidates"] if c["ticker"]=="069500"))
    products=board["kr"]["investor_nets"]["detailed_15007"]["products"]
    dates=set(unique(products["options_call"]["series"]))&set(unique(products["options_put"]["series"]))
    expected=set(cal.sessions_in_range(min(dates),max(dates)).strftime("%Y-%m-%d"))
    report={"status":"research_only","input_hashes":{"board":digest(board),"etfs":digest(etfs)},
        "frozen_model_updated":False,"calendar_overlay":{"removed":REVIEWED_CLOSURES,"sources":SOURCES,
        "labelled_rows_before":len(raw_rows),"labelled_rows_after":len(rows),
        "observed_option_dates":len(dates),"expected_sessions":len(expected),
        "missing_expected":sorted(expected-dates),"unexpected_observed":sorted(dates-expected)},
        "flow_accounting_audit":flow_identity_check(board),"experiments":{},
        "limitations":["Retrospective, multiple exploratory diagnostics; no untouched holdout",
        "Six-date calendar overlay is reviewed research only; frozen model stays unchanged",
        "Overnight returns cannot be captured by entry at the following open",
        "OHLC adjustment and pre-open availability unverified",
        "No independent option-contract prices/delta or futures positioning; flows are premium cash not directional exposure"]}
    for target in ("intraday","overnight_gap","close_to_close"):
        sample=[]
        for r in rows:
            q=dict(r); current,following=prices[r["date"]],prices[r["target_date"]]
            if target=="overnight_gap": q["return"]=following["open"]/current["close"]-1
            elif target=="close_to_close": q["return"]=following["close"]/current["close"]-1
            q["y"]=int(q["return"]>0);sample.append(q)
        evaluated=evaluate(sample)
        report["experiments"][target]={"n_rows":len(sample),"n_folds":len(evaluated["folds"]),
            "scores":{k:directional_scores(v) for k,v in evaluated["predictions"].items()},
            "incremental_option_information":evaluated["incremental_option_information"],
            "performance_illustrative":evaluated["overall"],
            "coefficients_by_fold":fold_coefficients(sample)}
    rich=evaluate(richer_price_features(rows,prices,cal))
    report["experiments"]["intraday_richer_price_control"]={
        "extra_price_features":["today_return","today_gap","today_intraday","momentum20"],
        "scores":{k:directional_scores(v) for k,v in rich["predictions"].items()},
        "incremental_option_information":rich["incremental_option_information"]}
    report["supplemental_data_experiment"]=supplemental_experiment(board,etfs,deriv,cal,rows,prices)
    return report


def fold_coefficients(rows):
    out=[]
    quarters=sorted({r["date"][:4]+"-"+str((int(r["date"][5:7])-1)//3+1) for r in rows if r["date"]>="2022"})
    for quarter in quarters:
        year,q=map(int,quarter.split("-"));start=f"{year:04d}-{3*q-2:02d}-01"
        train=[r for r in rows if r["target_date"]<start]
        if len(train)<250: continue
        m=fit(train,"option_only")
        out.append({"quarter":quarter,"n_train":len(train),"standardized_coef":m["coef"]})
    return out


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    board=read(PUBLIC/"derivatives_board_v1.json");etfs=read(PUBLIC/"kospi200_etf_candidates_daily_v1.json")
    deriv=read(PUBLIC/"krx_deriv_flow_v1.json")
    result=run(board,etfs,deriv)
    write(args.output,result)
    print(json.dumps(result["calendar_overlay"],ensure_ascii=False))
    for k,v in result["experiments"].items():
        s=v["scores"]["option_only"]
        print(k,"n",s["n"],"accuracy",s["accuracy"],"brier",s["brier"],"delta",v["incremental_option_information"])


if __name__=="__main__": main()
