"""Re-evaluate the #791 additions from pinned Git inputs without updating models."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

import numpy as np

from option_direction_model import calendar, dataset, fit, metrics, probability, unique, write
from research_direction_diagnostics import (ReviewedCalendar, REVIEWED_CLOSURES, SOURCES,
    bootstrap_mean, directional_scores, richer_price_features)

NAMES = ["prior", "price_only", "option_only", "option_futures", "option_institution",
         "option_oi_iv", "option_all", "price_all"]
FEATURES = {
    "price_only": ["momentum5", "volatility20", "today_return", "today_gap", "today_intraday", "momentum20"],
    "option_only": ["call_rank60", "put_rank60", "call_mean5", "put_mean5"],
    "extra": ["foreign_futures_net_over_market_buy", "institution_call_net_over_market_buy",
              "institution_put_net_over_market_buy", "log_pc_oi", "atm_iv_div100"],
}


def git_json(ref, name):
    raw = subprocess.check_output(["git", "show", f"{ref}:New for anti/public/data/{name}"])
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def extras(deriv):
    dates = deriv["dates"]
    if len(dates) != len(set(dates)):
        raise ValueError("duplicate flow dates")
    f = deriv["flow"]
    arrays = {
        "fnet": f["futures"]["foreign_net"], "ftotal": f["futures"]["market_total_buy"],
        "cnet": f["options_call"]["institution_net"], "ctotal": f["options_call"]["market_total_buy"],
        "pnet": f["options_put"]["institution_net"], "ptotal": f["options_put"]["market_total_buy"],
        "pc": deriv["option_oi"]["pc_oi"], "iv": deriv["option_oi"]["atm_iv"],
    }
    if any(len(v) != len(dates) for v in arrays.values()):
        raise ValueError("supplemental array length differs from date axis")
    partial = set().union(*(set(v) for v in deriv["partial_days"].values()))
    out, exclusions = {}, {}
    for i, day in enumerate(dates):
        v = {k: a[i] for k,a in arrays.items()}
        reasons = ["partial_source"] if day in partial else []
        reasons += [k for k,x in v.items() if x is None or not math.isfinite(x)]
        reasons += [k for k in ("ftotal", "ctotal", "ptotal", "pc", "iv") if v[k] is not None and v[k] <= 0]
        if reasons:
            exclusions[day] = sorted(set(reasons)); continue
        out[day] = [v["fnet"]/v["ftotal"], v["cnet"]/v["ctotal"], v["pnet"]/v["ptotal"],
                    math.log(v["pc"]), v["iv"]/100]
    return out, exclusions


def assemble(base_rows, extra):
    out = []
    for r in base_rows:
        if r["date"] not in extra: continue
        q = dict(r); x = extra[r["date"]]
        q["option_futures"] = r["option_only"] + x[:1]
        q["option_institution"] = r["option_only"] + x[1:3]
        q["option_oi_iv"] = r["option_only"] + x[3:]
        q["option_all"] = r["option_only"] + x
        q["price_all"] = r["price_only"] + q["option_all"]
        out.append(q)
    return out


def walk_forward(rows, names=NAMES):
    output = {k: [] for k in names}; folds = []
    quarters = sorted({r["date"][:4] + "-" + str((int(r["date"][5:7])-1)//3+1)
                       for r in rows if r["date"] >= "2022"})
    for quarter in quarters:
        y,q = map(int, quarter.split("-"))
        start = f"{y:04d}-{3*q-2:02d}-01"
        end = f"{y+1:04d}-01-01" if q == 4 else f"{y:04d}-{3*q+1:02d}-01"
        train = [r for r in rows if r["target_date"] < start]
        test = [r for r in rows if start <= r["date"] < end]
        if len(train) < 250 or not test: continue
        if max(r["target_date"] for r in train) >= min(r["date"] for r in test):
            raise AssertionError("label overlaps evaluation")
        folds.append({"quarter":quarter, "n_train":len(train), "n_test":len(test),
                      "last_train_target":max(r["target_date"] for r in train)})
        prior = sum(r["y"] for r in train)/len(train)
        for kind in names:
            model = None if kind == "prior" else fit(train, kind)
            output[kind] += [{"date":r["date"], "target_date":r["target_date"], "return":r["return"],
                             "y":r["y"], "p":prior if model is None else probability(model,r[kind])}
                            for r in test]
    return output, folds


def compare(candidate, baseline):
    a = {r["date"]:r for r in candidate}; b = {r["date"]:r for r in baseline}
    days = sorted(set(a) & set(b))
    if not days: return {"n":0}
    if any(a[d]["target_date"] != b[d]["target_date"] or a[d]["y"] != b[d]["y"] for d in days):
        raise AssertionError("unpaired outcomes")
    loss = [(a[d]["p"]-a[d]["y"])**2-(b[d]["p"]-b[d]["y"])**2 for d in days]
    accuracy = [int((a[d]["p"]>.5)==a[d]["y"])-int((b[d]["p"]>.5)==b[d]["y"]) for d in days]
    return {"n":len(days), "brier_delta":float(np.mean(loss)), "brier_delta_block95":bootstrap_mean(loss),
            "accuracy_delta":float(np.mean(accuracy)), "accuracy_delta_block95":bootstrap_mean(accuracy),
            "interpretation":"negative Brier delta / positive accuracy delta favors candidate; exploratory, not multiple-testing adjusted"}


def score(records):
    if not records: return {"n":0}
    return {"direction":directional_scores(records), "illustrative_long_only":metrics(records)}


def group_coverage_experiments(base, deriv):
    """Pair each block against baseline on its own dates, without requiring other blocks."""
    dates = deriv["dates"]; flow = deriv["flow"]
    group_rows = {k: {} for k in ("futures", "institution", "oi_iv")}
    for i, day in enumerate(dates):
        for group in group_rows:
            if group == "futures":
                vals = [flow["futures"]["foreign_net"][i], flow["futures"]["market_total_buy"][i]]
                invalid = day in deriv["partial_days"]["futures"]
                positive_positions = [1]
            elif group == "institution":
                vals = [flow["options_call"]["institution_net"][i],flow["options_call"]["market_total_buy"][i],
                        flow["options_put"]["institution_net"][i],flow["options_put"]["market_total_buy"][i]]
                invalid = any(day in deriv["partial_days"][p] for p in ("options_call","options_put"))
                positive_positions = [1,3]
            else:
                vals = [deriv["option_oi"]["pc_oi"][i],deriv["option_oi"]["atm_iv"][i]]
                invalid = False; positive_positions = [0,1]
            if invalid or any(v is None or not math.isfinite(v) for v in vals): continue
            if any(vals[j] <= 0 for j in positive_positions): continue
            x = ([vals[0]/vals[1]] if group == "futures" else
                 [vals[0]/vals[1],vals[2]/vals[3]] if group == "institution" else
                 [math.log(vals[0]),vals[1]/100])
            group_rows[group][day] = x
    results = {}
    for group, features in group_rows.items():
        sample = []
        for r in base:
            if r["date"] not in features: continue
            q = dict(r); q["candidate"] = r["option_only"]+features[r["date"]]
            q["price_all"] = r["price_only"]+q["candidate"]
            sample.append(q)
        predictions, folds = walk_forward(sample, ["prior","price_only","option_only","candidate","price_all"])
        results[group] = {"n_complete_rows":len(sample),"n_folds":len(folds),
            "last_feature_date":sample[-1]["date"],"last_target_date":sample[-1]["target_date"],
            "overall":{k:score(v) for k,v in predictions.items()},
            "candidate_vs_option_only":compare(predictions["candidate"],predictions["option_only"]),
            "price_all_vs_price_only":compare(predictions["price_all"],predictions["price_only"]),
            "october_source_dates":{k:score([r for r in v if r["date"].startswith("2026-10")]) for k,v in predictions.items()},
            "note":"Each group has its own complete-date sample; compare within a group, not across groups."}
    return results


def audit(board, deriv):
    comparisons = {}
    products = board["kr"]["investor_nets"]["detailed_15007"]["products"]
    for prod in ("options_call", "options_put"):
        source = unique(products[prod]["series"]); bad = []; checked = 0
        for day, net in zip(deriv["dates"], deriv["flow"][prod]["foreign_net"]):
            if day not in source or net is None: continue
            checked += 1
            if abs(net*1e6-source[day]["foreign"]["net_krw"]) > 1:
                bad.append(day)
        comparisons[prod] = {"n_compared":checked,"foreign_net_conflicts":bad}
    if any(v["foreign_net_conflicts"] for v in comparisons.values()):
        raise ValueError("15007 source copies conflict")
    return comparisons


def distribution_diagnostic(rows, predictions, added):
    """Train-only range checks; descriptive flags, never an optimized trading rule."""
    cache = {}; flagged = []; by_date = {r["date"]:r for r in rows}
    for record in predictions["price_all"]:
        day = record["date"]; year = int(day[:4]); q = (int(day[5:7])-1)//3
        start = f"{year:04d}-{q*3+1:02d}-01"
        if start not in cache:
            train = np.array([r["price_all"] for r in rows if r["target_date"] < start])
            cache[start] = (np.min(train,axis=0),np.max(train,axis=0),
                            np.quantile(train,.01,axis=0),np.quantile(train,.99,axis=0))
        low,high,p01,p99 = cache[start]; x = np.array(by_date[day]["price_all"])
        labels = FEATURES["price_only"]+FEATURES["option_only"]+FEATURES["extra"]
        outside = [labels[i] for i in np.flatnonzero((x<low)|(x>high))]
        tail = [labels[i] for i in np.flatnonzero((x<p01)|(x>p99))]
        flagged.append({**record,"outside_train_range":outside,"outside_train_01_99":tail})
    groups = {"outside_train_range":lambda r:bool(r["outside_train_range"]),
              "within_train_range":lambda r:not r["outside_train_range"]}
    return {"caveat":"Descriptive, multiple correlated features. Not evidence of cause or an optimized abstention rule.",
            "scores":{k:score([r for r in flagged if use(r)]) for k,use in groups.items()},
            "newly_added_rows":[r for r in flagged if r["date"] in added]}


def frozen_research_simulation(rows, quarterly):
    """Simulate the user's fixed-weight operation, separately from the actual saved model."""
    train = [r for r in rows if r["target_date"] < "2022-01-01"]
    test = [r for r in rows if r["date"] >= "2022-01-01"]
    result = {"train_cutoff":"2021-12-31", "last_train_target":max(r["target_date"] for r in train),
              "n_train":len(train), "note":"Historical frozen-weight simulation; actual production/research artifact is unchanged.",
              "scores":{},"frozen_minus_quarterly":{}}
    saved = {}
    for kind in ("price_only","option_only","price_all"):
        model = fit(train,kind)
        records = [{"date":r["date"],"target_date":r["target_date"],"return":r["return"],"y":r["y"],
                    "p":probability(model,r[kind])} for r in test]
        result["scores"][kind] = score(records)
        result["frozen_minus_quarterly"][kind] = compare(records,quarterly[kind])
        saved[kind] = records
    result["price_all_vs_price_only"] = compare(saved["price_all"],saved["price_only"])
    result["vs_always_up_accuracy"] = {}
    for kind, records in saved.items():
        differences = [int((r["p"]>.5)==r["y"])-r["y"] for r in records]
        result["vs_always_up_accuracy"][kind] = {"delta":float(np.mean(differences)),
                                                "block95":bootstrap_mean(differences)}
    return result


def run(ref, before_ref):
    names = ["derivatives_board_v1.json", "kospi200_etf_candidates_daily_v1.json", "krx_deriv_flow_v1.json"]
    loaded = [git_json(ref,n) for n in names]
    board, etfs, deriv = [x[0] for x in loaded]
    old, old_sha = git_json(before_ref,names[-1])
    cal = ReviewedCalendar(calendar())
    base = dataset(board,etfs,cal)
    prices = unique(next(c["rows"] for c in etfs["candidates"] if c["ticker"] == "069500"))
    base = richer_price_features(base,prices,cal)
    new_extra, exclusions = extras(deriv); old_extra, _ = extras(old)
    rows = assemble(base,new_extra); old_rows = assemble(base,old_extra)
    previous_by_date = {r["date"]:r for r in old_rows}
    retained = [r["date"] for r in rows if r["date"] in previous_by_date]
    for r in rows:
        if r["date"] in previous_by_date and r != previous_by_date[r["date"]]:
            raise AssertionError("previously complete feature row changed")
    predictions, folds = walk_forward(rows); prior_predictions, _ = walk_forward(old_rows)
    added = sorted({r["date"] for r in rows}-{r["date"] for r in old_rows})
    full = {k:score(v) for k,v in predictions.items()}
    paired = {k:compare(predictions[k], predictions["option_only"]) for k in NAMES if k not in ("prior", "option_only")}
    old_evaluation_dates = {r["date"] for r in prior_predictions["prior"]}
    added_eval = sorted({r["date"] for r in predictions["prior"]}-old_evaluation_dates)
    subsets = {
        "newly_evaluable_sources":lambda r:r["date"] in added_eval,
        "october_source_dates":lambda r:r["date"].startswith("2026-10"),
        "through_2025":lambda r:r["target_date"] < "2026",
        "year_2026":lambda r:r["target_date"].startswith("2026"),
    }
    # One-at-a-time deletion of each extra block on the SAME complete dates.
    ablations = {}
    for group, keep in (("without_futures",[1,2,3,4]),("without_institution",[0,3,4]),("without_oi_iv",[0,1,2])):
        reduced = []
        for r in rows:
            q = dict(r); x = new_extra[r["date"]]
            q["option_all"] = r["option_only"] + [x[i] for i in keep]
            q["price_all"] = r["price_only"] + q["option_all"]
            reduced.append(q)
        p, _ = walk_forward(reduced)
        ablations[group] = {"option_all":score(p["option_all"]),
                            "full_minus_reduced":compare(predictions["option_all"],p["option_all"])}
    report = {
        "status":"research_only", "source_commit":ref, "before_source_commit":before_ref,
        "input_sha256":{n:s for n,(_,s) in zip(names,loaded)},"before_flow_sha256":old_sha,
        "source_copy_audit":audit(board,deriv), "last_dates":deriv["last_dates"],
        "method":{"target":"069500 next session close > open; DOWN includes flat",
                  "features":FEATURES,"calendar_overlay":REVIEWED_CLOSURES,"calendar_sources":SOURCES,
                  "training":"expanding quarterly logistic C=1, train-only scaler, train target strictly before test source",
                  "threshold":.5, "probabilities":"uncalibrated", "model_selection":"none; all prespecified diagnostic variants reported"},
        "coverage":{"base_rows":len(base), "complete_rows_before":len(old_rows),"complete_rows_after":len(rows),
                    "retained_complete_rows_identical":len(retained),"added_feature_dates":added,
                    "new_evaluation_source_dates":added_eval,
                    "last_feature_date":rows[-1]["date"],"last_target_date":rows[-1]["target_date"],
                    "missing_required_october":{day:reason for day,reason in exclusions.items() if day.startswith("2026-10")}},
        "folds":folds,"overall_same_dates":full,"paired_vs_option_only":paired,
        "price_all_vs_price_only":compare(predictions["price_all"],predictions["price_only"]),
        "before_after_same_evaluation_dates":{k:compare(predictions[k],prior_predictions[k]) for k in NAMES},
        "subsets":{name:{k:score([r for r in records if use(r)]) for k,records in predictions.items()} for name,use in subsets.items()},
        "feature_group_ablations":ablations, "predictions":predictions,
        "group_specific_coverage":group_coverage_experiments(base,deriv),
        "distribution_diagnostic":distribution_diagnostic(rows,predictions,set(added_eval)),
        "frozen_weight_research_simulation":frozen_research_simulation(rows,predictions),
        "limitations":["Retrospective explored data, not untouched prospective evaluation",
                       "10月 additions are few, not an independent validation of improved skill",
                       "Pre-open data availability and adjusted OHLC common factor are not verified",
                       "Feature group comparisons/bootstrap intervals are not multiple-testing adjusted",
                       "Whole-market monthly OI does not identify foreign holdings or option delta",
                       "Remaining source gaps select the evaluated sample; no interpolation",
                       "Frozen model and prior forecast files not modified; no daily production integration"]}
    import sklearn
    import exchange_calendars as xc
    report["runtime"] = {"numpy":np.__version__,"sklearn":sklearn.__version__,"exchange_calendars":xc.__version__}
    report["implementation_sha256"] = {name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
        for name in ("research_pr791_evaluation.py","research_direction_diagnostics.py","option_direction_model.py")}
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ref",required=True);p.add_argument("--before-ref",default="514ea48a2fb0558a08d94254e9a88c6c593570b2")
    p.add_argument("--output",type=Path,required=True);args=p.parse_args()
    result=run(args.ref,args.before_ref);write(args.output,result)
    print(json.dumps(result["coverage"],ensure_ascii=False))
    for k,v in result["overall_same_dates"].items():
        d=v["direction"];print(k,"n",d["n"],"accuracy",d["accuracy"],"brier",d["brier"])


if __name__=="__main__": main()
