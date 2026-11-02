"""Single prespecified IV-surface candidate on paired complete dates."""
import argparse
import json
from pathlib import Path

from option_direction_model import calendar, dataset, unique, read, write
from research_direction_diagnostics import ReviewedCalendar, richer_price_features
from research_pr791_evaluation import git_json, score, compare
from research_option_dynamics import evaluate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref",required=True);parser.add_argument("--surface",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True);args=parser.parse_args()
    board,board_sha=git_json(args.ref,"derivatives_board_v1.json")
    etfs,etf_sha=git_json(args.ref,"kospi200_etf_candidates_daily_v1.json")
    surface=read(args.surface)
    if surface["public_ref"]!=args.ref: raise ValueError("surface references a different public snapshot")
    cal=ReviewedCalendar(calendar());base=dataset(board,etfs,cal)
    prices=unique(next(c["rows"] for c in etfs["candidates"] if c["ticker"]=="069500"))
    base=richer_price_features(base,prices,cal);rows=[];all_base=[]
    for r in base:
        baseline=r["price_only"]+r["option_only"]
        all_base.append({"date":r["date"],"target_date":r["target_date"],"feature_source_date":r["date"],
                         "y":r["y"],"return":r["return"],"baseline":baseline})
        point=surface["points"].get(r["date"])
        if not point or point["status"]!="observed_research": continue
        rows.append({"date":r["date"],"target_date":r["target_date"],"feature_source_date":r["date"],
                     "y":r["y"],"return":r["return"],"baseline":baseline,"surface":baseline+point["features"]})
    predictions,folds=evaluate(rows,families=["baseline","surface"])
    all_predictions,all_folds=evaluate(all_base,families=["baseline"])
    report={"status":"research_only","source_commit":args.ref,
        "input_sha256":{"board":board_sha,"etfs":etf_sha},"private_source":surface["private_source"],
        "n_complete_rows":len(rows),"last_feature_date":rows[-1]["date"],
        "target":"069500 next KRX session close > open; flat is DOWN",
        "surface_features":surface["fields"],"folds":folds,
        "scores":{k:score(v) for k,v in predictions.items()},
        "baseline_calibrated_vs_recent_prior":compare(predictions["baseline_calibrated"],predictions["prior_recent"]),
        "surface_calibrated_vs_recent_prior":compare(predictions["surface_calibrated"],predictions["prior_recent"]),
        "surface_calibrated_vs_baseline_calibrated":compare(predictions["surface_calibrated"],predictions["baseline_calibrated"]),
        "surface_calibrated_vs_surface_raw":compare(predictions["surface_calibrated"],predictions["surface_raw"]),
        "all_available_baseline_check":{
            "n_complete_rows":len(all_base),"folds":all_folds,
            "scores":{k:score(v) for k,v in all_predictions.items()},
            "calibrated_vs_recent_prior":compare(all_predictions["baseline_calibrated"],all_predictions["prior_recent"]),
            "calibrated_vs_raw":compare(all_predictions["baseline_calibrated"],all_predictions["baseline_raw"]),
            "predictions":all_predictions,
            "note":"Same baseline procedure without requiring IV availability; checks sample-selection dependence, not a new feature search."},
        "predictions":predictions,"limitations":surface["limitations"]+[
            "Prespecified single moneyness variant; historical sample already explored",
            "Independent chronological calibration; not proof of future probabilities",
            "No model update or new KRX collection"]}
    write(args.output,report)
    for k,v in report["scores"].items():
        d=v["direction"];print(k,"n",d["n"],"accuracy",d["accuracy"],"brier",d["brier"])
    print("vs_prior",report["surface_calibrated_vs_recent_prior"])
    print("vs_baseline",report["surface_calibrated_vs_baseline_calibrated"])


if __name__=="__main__":main()
