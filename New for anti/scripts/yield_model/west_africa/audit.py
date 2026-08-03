"""Assess whether each proposed West Africa cocoa analysis has usable labels."""

import csv
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
TRAINING = HERE / "training"
MODELS = HERE / "models"


def read_rows(path):
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def year_summary(rows, key="year"):
    years = sorted({int(row[key]) for row in rows if row.get(key)})
    return {
        "count": len(years),
        "first": years[0] if years else None,
        "last": years[-1] if years else None,
    }


def table_summary(rows):
    result = year_summary(rows)
    result["rows"] = len(rows)
    if rows and "region" in rows[0]:
        result["regions"] = len({row["region"] for row in rows})
        counts = {}
        for row in rows:
            counts[row["region"]] = counts.get(row["region"], 0) + 1
        result["minimum_seasons_per_region"] = min(counts.values()) if counts else 0
    return result


def overlap_with_label(rows, field):
    usable = [row for row in rows if row.get(field) not in {None, ""}]
    return year_summary(usable)


def run(output_path=None):
    fao = read_rows(DATA / "faostat_cocoa_country_year.csv")
    civ = read_rows(DATA / "civ_regional_cocoa.csv")
    ghana = read_rows(DATA / "ghana_regional_purchases.csv")
    training = read_rows(TRAINING / "cocoa_faostat_country.csv")
    ghana_training = read_rows(TRAINING / "ghana_cocoa_purchases.csv")
    ee_path = DATA / "earth_engine_status.json"
    earth_engine = json.loads(ee_path.read_text(encoding="utf-8")) if ee_path.exists() else {
        "initialized": False, "reason": "probe not run"
    }
    screen_path = MODELS / "feasibility_screen.json"
    screens = json.loads(screen_path.read_text(encoding="utf-8")) if screen_path.exists() else []

    fao_by_country = {
        country: [row for row in fao if row["country"] == country]
        for country in {row["country"] for row in fao}
    }
    training_by_country = {
        country: [row for row in training if row["country"] == country]
        for country in {row["country"] for row in training}
    }
    result = {
        "data": {
            "faostat": {country: table_summary(rows) for country, rows in fao_by_country.items()},
            "civ_regional_production": table_summary(civ),
            "ghana_regional_purchases": table_summary(ghana),
            "earth_engine": earth_engine,
        },
        "feasibility": {},
    }
    for country in ["Côte d'Ivoire", "Ghana"]:
        rows = training_by_country.get(country, [])
        overlap = overlap_with_label(rows, "production_tonnes")
        result["feasibility"][country + " national climate-production screen"] = {
            "status": "feasible_for_validation" if overlap["count"] >= 25 else "insufficient_overlap",
            "overlap": overlap,
            "warning": "Country totals cannot identify regional mechanisms; cocoa-year alignment is provisional.",
        }
    civ_summary = table_summary(civ)
    result["feasibility"]["Côte d'Ivoire regional model"] = {
        "status": "not_trainable",
        "evidence": civ_summary,
        "reason": "The open CCC regional table currently has only two seasons.",
    }
    ghana_summary = table_summary(ghana)
    ghana_ready = ghana_summary.get("minimum_seasons_per_region", 0) >= 15
    result["feasibility"]["Ghana regional purchases model"] = {
        "status": "candidate_for_validation" if ghana_ready else "insufficient_regional_history",
        "evidence": ghana_summary,
        "warning": "The label is cocoa purchases, not harvested area or farm yield.",
    }
    purchase_overlap = overlap_with_label(ghana_training, "purchases_tonnes")
    result["feasibility"]["Ghana climate-purchases screen"] = {
        "status": "feasible_for_validation" if purchase_overlap["count"] >= 20 else "insufficient_overlap",
        "overlap": purchase_overlap,
    }
    result["feasibility"]["satellite cocoa-area monitoring"] = {
        "status": "feasible_as_separate_monitor" if earth_engine.get("initialized") else "awaiting_ee_probe",
        "reason": "S1/S2/SMAP/CHIRPS/Hansen are available, but a validated cocoa mask is still required.",
    }
    result["feasibility"]["black-pod loss model"] = {
        "status": "proxy_only",
        "reason": "Climate can produce a disease-risk proxy, but no open region-year incidence/loss label is wired in.",
    }
    result["feasibility"]["EUDR eligible supply"] = {
        "status": "scenario_only",
        "reason": "Forest-loss exposure is observable; legal compliance also requires plot geolocation, traceability and due diligence.",
    }
    reproducible = [screen for screen in screens
                    if screen.get("target") in {"purchases_tonnes", "regional_purchases_tonnes"}]
    validated = [screen for screen in reproducible
                 if screen.get("status") in {"candidate_signal", "robust_candidate"}]
    screen_summaries = [{
        "country": screen.get("country"),
        "target": screen.get("target"),
        "status": screen.get("status"),
        "passing_feature_sets": screen.get("passing_feature_sets", []),
        "skills_vs_trend": {
            name: {
                "all_folds": run.get("skill_vs_trend"),
                "recent_folds": run.get("recent_skill_vs_trend"),
            }
            for name, run in screen.get("runs", {}).items()
        },
    } for screen in screens]
    result["empirical_screen"] = {
        "status": "not_yet_validated" if screens and not validated else (
            "candidate_signal" if validated else "screen_not_run"),
        "decision_rule": (
            "A feature set must improve RMSE over an expanding time-trend by at least 10% "
            "both across all held-out years and across the most recent eight folds."),
        "interpretation": (
            "The Ghana FAOSTAT production signal is not treated as validated because it did "
            "not reproduce in COCOBOD national purchases or the six-region panel."
            if screens and not validated else
            "Run west_africa.screen and compare independent label definitions before use."),
        "screens": screen_summaries,
    }
    output = Path(output_path or DATA / "model_feasibility.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
