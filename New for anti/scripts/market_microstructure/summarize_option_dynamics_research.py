"""Publish compact derived research results, without the private chain supports."""
import argparse
import hashlib
from pathlib import Path

from option_direction_model import read,write
from research_pr791_evaluation import compare,score


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory",type=Path,required=True)
    args=parser.parse_args();root=args.directory
    names=["option_dynamics_calibration_20261102.json","option_dynamics_lag1_calibration_20261102.json",
           "option_surface_probe_20261102.json","option_surface_features_20261102.json","shadow_forecast_replay_20261102.json"]
    a,b,surface,features,replay=[read(root/n) for n in names]
    lag_compare={}
    for family in ("baseline_calibrated","dynamics_calibrated"):
        common=set(r["date"] for r in a["predictions"][family])&set(r["date"] for r in b["predictions"][family])
        lag_compare[family]={"paired":compare(b["predictions"][family],a["predictions"][family]),
                            "lag0_same_dates":score([r for r in a["predictions"][family] if r["date"] in common]),
                            "lag1_same_dates":score([r for r in b["predictions"][family] if r["date"] in common])}
    valid=[d for d,p in features["points"].items() if p["status"]=="observed_research"]
    summary={"status":"research_only_no_promotion","analysis_date":"2026-11-02",
        "source_commit":a["source_commit"],"private_source":features["private_source"],
        "source_report_sha256":{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in names},
        "current_alignment":{k:a[k] for k in ("coverage","scores","comparisons","folds")},
        "one_session_delay":{k:b[k] for k in ("coverage","scores","comparisons","folds")},
        "lag_comparison_same_dates":lag_compare,
        "surface_experiment":{k:surface[k] for k in ("n_complete_rows","last_feature_date","scores",
            "baseline_calibrated_vs_recent_prior","surface_calibrated_vs_recent_prior",
            "surface_calibrated_vs_baseline_calibrated")},
        "all_available_baseline_check":{k:surface["all_available_baseline_check"][k]
            for k in ("n_complete_rows","scores","calibrated_vs_recent_prior","calibrated_vs_raw","folds")},
        "surface_extraction":{"n_private_parts":len(features["receipts"]),"n_valid_dates":len(valid),
            "last_valid_date":max(valid),"krx_requests":0},
        "replay_contract_example":replay,
        "decision":"Keep v1 unchanged. New artifact is shadow-only. Improved point accuracy does not establish probability reliability or executable profitability.",
        "limitations":a["limitations"]}
    # Dates of unusable OI changes remain in the full local research files.
    for section in ("current_alignment","one_session_delay"):
        summary[section]["coverage"]={k:v for k,v in summary[section]["coverage"].items() if k!="excluded_dates"}
    write(root/"option_calibration_research_summary_20261102.json",summary)
    write(root/"option_surface_source_manifest_20261102.json",{
        "private_source":features["private_source"],"public_ref":features["public_ref"],
        "public_sha256":features["public_sha256"],"receipts":features["receipts"],
        "n_valid_surface_dates":len(valid),"raw_chain_rows_published":False})
    print("compact summary written; raw chain/support points excluded")


if __name__=="__main__":main()
