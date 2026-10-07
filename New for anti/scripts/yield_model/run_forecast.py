"""
Produce the yield forecast the dashboard reads.

Run weekly from CI. Writes public/data/yield_forecast.json with, per crop:
the current season's central estimate and interval, the trend and weather
components, last season's actual for comparison, and enough provenance
(how much of the season is observed vs forecast, which ENSO state, when the
model was trained and how well it scored) that the number on screen can be
judged rather than just believed.
"""

import json
import os
import sys
from datetime import datetime, timezone

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "public", "data", "yield_forecast.json"))

from collect_us_cornbelt import load_oni, growing_season_oni  # noqa: E402
from predict_us import predict  # noqa: E402
from predict_wheat import predict as predict_wheat  # noqa: E402

# Regions the dashboard shows, and which crops belong to each. Wheat is a
# separate region from the Corn Belt because it is a different geography with
# its own states and weights -- putting it under "Corn Belt" would attach the
# forecast to the wrong map location.
REGIONS = {
    "corn_belt": {
        "label": "US Corn Belt",
        "label_ko": "콘벨트",
        "note": "8 states, production-weighted: IA IL NE MN IN OH MO SD",
        "crops": ["corn", "soybeans"],
    },
    "great_plains": {
        "label": "US Great Plains (winter wheat)",
        "label_ko": "대평원 (겨울밀)",
        "note": "KS OK TX CO NE MT, production-weighted",
        "crops": ["winter_wheat"],
    },
    "northern_plains": {
        "label": "US Northern Plains (spring wheat)",
        "label_ko": "북부대평원 (봄밀)",
        "note": "ND MT MN SD, production-weighted",
        "crops": ["spring_wheat"],
    },
    "cotton_belt": {
        "label": "US Cotton Belt (Texas High Plains)",
        "label_ko": "남부 텍사스 (면화)",
        "note": "TX GA MS AR AL, production-weighted · 파종면적 기준 단수",
        "crops": ["cotton"],
    },
}

CROP_LABELS_KO = {
    "corn": "옥수수", "soybeans": "대두",
    "winter_wheat": "겨울밀", "spring_wheat": "봄밀", "cotton": "면화",
}


def log(msg):
    print(f"[run] {msg}", flush=True)


def enso_label(oni):
    """NOAA's convention: +/-0.5 for El Nino / La Nina, +/-1.5 for strong."""
    if oni is None or pd.isna(oni):
        return "unknown", None
    if oni >= 1.5:
        return "strong El Nino", oni
    if oni >= 0.5:
        return "El Nino", oni
    if oni <= -1.5:
        return "strong La Nina", oni
    if oni <= -0.5:
        return "La Nina", oni
    return "neutral", oni


def selected_forward(model):
    """Forward-chaining scores of the feature set the trainer actually chose.

    Older artifacts do not record the choice; the trainers pick the set with
    the higher forward skill, so the same rule recovers it.
    """
    v = model["validation"]
    sel = model.get("selected")
    if sel is None:
        sel = max(("all", "core"),
                  key=lambda k: v.get(f"{k}_forward", {}).get("skill_vs_trend", -9))
    return v.get(f"{sel}_forward", {})


def last_actual(crop):
    """Most recent observed season, for a like-for-like comparison on screen."""
    path = os.path.join(HERE, f"us_{crop}_training.csv")
    df = pd.read_csv(path).sort_values("year")
    row = df.iloc[-1]
    return {"year": int(row.year), "yield": float(row["yield"])}


def main():
    year = int(sys.argv[1]) if len(sys.argv) > 1 else datetime.now(timezone.utc).year

    oni = growing_season_oni(load_oni(), year)
    label, value = enso_label(oni)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": year,
        "region": "US Corn Belt",
        "region_note": "8 states, production-weighted: IA IL NE MN IN OH MO SD",
        "enso": {"state": label, "oni_growing_season": value},
        "crops": {},
        "regions": {},
    }

    for region_key, region in REGIONS.items():
        entry = {"label": region["label"], "label_ko": region["label_ko"],
                 "note": region["note"], "crops": {}}

        for crop in region["crops"]:
            # predict_wheat handles every crop with its own collector
            # (both wheats and cotton); predict() is the Corn Belt one.
            use_south = crop.endswith("wheat") or crop == "cotton"
            r = predict_wheat(crop, year) if use_south else predict(crop, year)
            if r is None:
                log(f"{crop}: no forecast produced")
                continue

            with open(os.path.join(HERE, f"us_{crop}_model.json"), encoding="utf-8") as f:
                model = json.load(f)
            fwd = selected_forward(model)
            ins = r.get("inseason")
            # Corn and soy carry a skill for today's point in the season;
            # wheat and cotton only their end-of-season number.
            skill_now = ins["skill_now"] if ins else fwd.get("skill_vs_trend", float("nan"))

            # Corn/soy count provenance over July-August; wheat over its own
            # grain-fill window. Normalise the key so the frontend has one
            # shape to read.
            days = r.get("julaug_days") or r.get("critical_days")

            entry["crops"][crop] = {
                "label_ko": CROP_LABELS_KO.get(crop, crop),
                "unit": r["unit"],
                "point": round(r["point"], 1),
                "range_68": [round(r["range_68"][0], 1), round(r["range_68"][1], 1)],
                "range_95": [round(r["range_95"][0], 1), round(r["range_95"][1], 1)],
                "trend": round(r["trend"], 1),
                "weather_effect": round(r["weather_effect"], 1),
                "last_actual": last_actual(crop),
                "season_progress": {
                    "critical_days": days,
                    "observed_share": round(r["observed_share"], 3),
                },
                "skill": {
                    "method": "forward-chaining, trend refit inside each fold",
                    "skill_vs_trend_only": round(skill_now, 3),
                    "end_of_season_skill": round(fwd.get("skill_vs_trend", float("nan")), 3),
                    "detrended_r2": round(fwd.get("detrended_r2", float("nan")), 3),
                    "sigma_used": round(r["sigma"], 2),
                    "model_sigma": round(r["base_sigma"], 2),
                    # Spring wheat is fitted on a rolling window because its
                    # heat-yield relationship is non-stationary; surfacing this
                    # explains why its trained span is shorter than the record.
                    "train_window_years": model.get("train_window_years"),
                    # Below roughly 20% the weather term is barely beating a
                    # trend-only guess, and the panel should say so.
                    # Corn and soy are judged at today's date, so early-season
                    # numbers show as a reference until the backtest says the
                    # weather to date carries real information.
                    "low_confidence": (ins["mode"] == "reference") if ins
                                      else fwd.get("skill_vs_trend", 0) < 0.20,
                },
                "inseason": ins and {
                    **ins,
                    "skill_now": round(ins["skill_now"], 3),
                    "scenario_spread_sd": round(ins["scenario_spread_sd"], 2),
                    "percentiles": {k: round(v, 1) for k, v in r["percentiles"].items()},
                    "skill_by_date": {k: round(v["skill_vs_trend"], 3)
                                      for k, v in model["inseason"]["cutoffs"].items()},
                },
                "trained_years": model["trained_years"],
                # The standardised weather inputs the model actually saw this
                # season. Surfacing them lets the panel show *why* the forecast
                # sits where it does, instead of only the output number.
                "weather_inputs": {k: round(v, 3) for k, v in (r.get("features") or {}).items()},
            }
            log(f"{region_key}/{crop}: {r['point']:.1f} {r['unit']} "
                f"({r['range_68'][0]:.1f}-{r['range_68'][1]:.1f} at 68%)")

        if entry["crops"]:
            payload["regions"][region_key] = entry
            # Flat crop map retained so existing readers keep working.
            payload["crops"].update(entry["crops"])

    if not payload["crops"]:
        log("nothing to write")
        return 1

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    log(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
