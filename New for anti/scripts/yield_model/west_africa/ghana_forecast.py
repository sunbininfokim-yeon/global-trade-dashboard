"""Hard go/no-go gate for a Ghana cocoa-purchases forecast.

The module never publishes a forecast merely because a regression can be fit.
It accepts only COCOBOD purchase labels and enables forecasting only when a
predeclared feature set beats the forward trend benchmark in both the complete
and recent evaluation windows.  FAOSTAT production is deliberately excluded
from this decision because it is a different target.
"""

import argparse
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
DEFAULT_SCREEN = HERE / "models" / "feasibility_screen.json"
DEFAULT_DECISION = HERE / "models" / "ghana_forecast_decision.json"
PURCHASE_TARGETS = {"purchases_tonnes", "regional_purchases_tonnes"}


def _score(run):
    """Conservative skill: the weaker of the full and recent windows."""
    values = [run.get("skill_vs_trend"), run.get("recent_skill_vs_trend")]
    return min(value for value in values if value is not None)


def decide(screens, minimum_skill=0.10):
    candidates = []
    for screen in screens:
        if screen.get("country") != "Ghana":
            continue
        if screen.get("target") not in PURCHASE_TARGETS:
            continue
        for feature_set, run in screen.get("runs", {}).items():
            all_skill = run.get("skill_vs_trend")
            recent_skill = run.get("recent_skill_vs_trend")
            passes = (
                all_skill is not None and recent_skill is not None
                and all_skill >= minimum_skill and recent_skill >= minimum_skill
            )
            candidates.append({
                "target": screen["target"],
                "feature_set": feature_set,
                "skill_vs_trend": all_skill,
                "recent_skill_vs_trend": recent_skill,
                "conservative_skill": _score(run),
                "passes": passes,
                "fold_years": run.get("fold_years", []),
            })
    candidates.sort(key=lambda item: item["conservative_skill"], reverse=True)
    passing = [candidate for candidate in candidates if candidate["passes"]]
    best = candidates[0] if candidates else None
    enabled = bool(passing)
    return {
        "country": "Ghana",
        "forecast_target": "COCOBOD cocoa purchases, not biological production or yield",
        "forecast_enabled": enabled,
        "status": "validated_candidate" if enabled else "abandoned_with_current_data",
        "minimum_skill_gate": minimum_skill,
        "decision_rule": (
            "At least one predeclared model must improve RMSE over an expanding "
            "time-trend by 10% or more in both all held-out years and the most "
            "recent eight held-out years."
        ),
        "selected_candidate": passing[0] if passing else None,
        "best_failed_candidate": None if enabled else best,
        "evaluated_candidates": candidates,
        "forecast_file_created": False,
        "reason": (
            "A COCOBOD-labelled candidate passed the forward-validation gate. "
            "A separate operational forecast may now be fitted with vintage checks."
            if enabled else
            "Neither the national COCOBOD total nor the six-region COCOBOD panel "
            "beat the trend benchmark by the required margin. No forecast values "
            "are published; district production labels are also unavailable."
        ),
        "reactivation_requirements": [
            "newer vintage-consistent COCOBOD country or regional purchase labels",
            "cocoa-mask-weighted climate and canopy features available at forecast time",
            "the same forward-validation gate passed on the independent COCOBOD target",
        ],
    }


def run(screen_path=DEFAULT_SCREEN, output_path=DEFAULT_DECISION, minimum_skill=0.10):
    screens = json.loads(Path(screen_path).read_text(encoding="utf-8"))
    decision = decide(screens, minimum_skill=minimum_skill)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(decision, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return decision


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", type=Path, default=DEFAULT_SCREEN)
    parser.add_argument("--output", type=Path, default=DEFAULT_DECISION)
    parser.add_argument("--minimum-skill", type=float, default=0.10)
    args = parser.parse_args(argv)
    decision = run(args.screen, args.output, args.minimum_skill)
    print(json.dumps(decision, ensure_ascii=False, indent=2))
    return 0 if decision["forecast_enabled"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
