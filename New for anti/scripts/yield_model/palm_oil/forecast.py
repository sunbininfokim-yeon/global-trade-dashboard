"""
Palm-oil production region for a country's forecast JSON.

Usage: python3 -m palm_oil.forecast            # malaysia, colombia, nigeria JSON
                                               # + palm region into thailand JSON
thailand/run_forecast.py also adds the region through region(), so its own
weekly rewrite keeps it.

Trend only, as for Indonesia (indonesia/palm_psd.py): the forecast is the
trend of USDA PSD production, published beside USDA's own figure for the
same marketing year, with the lagged-drought read-out from conditions.py as
context. Countries without another crop model get a file of their own,
public/data/{country}_yield_forecast.json.
"""

import json
import os
import sys
from datetime import date, datetime, timezone

import pandas as pd

from . import conditions as K
from . import psd
from .producers import BY_COUNTRY

HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.normpath(os.path.join(HERE, "..", "..", "..", "public", "data"))
OWN_FILE = ["malaysia", "colombia", "nigeria"]


def log(msg):
    print(f"[palm-oil:forecast] {msg}", flush=True)


def _complete(year, today):
    """Label year Y is market year Y-1, which ends on 30 September of Y."""
    return date(int(year), 9, 30) < today


def region(producer, today=None):
    """Region payload, or None without the PSD slice."""
    from indonesia.model import predict_target, train_target

    if not os.path.exists(psd.PSD_CSV):
        return None
    today = today or date.today()
    labels = psd.labels(producer)
    done = labels[[_complete(y, today) for y in labels.year]].reset_index(drop=True)
    model = train_target(done, "psd_production_kt", {"trend_only": []}, min_train=10)
    if model is None:
        return None
    last = done.iloc[-1]
    target = int(last.year) + 1
    p = predict_target(model, target, {})
    publishable = model["forecast_gate"]["publishable"]
    usda = labels.set_index("year").psd_production_kt.get(target)

    conditions, nino = None, None
    try:
        frame = pd.read_csv(K.features_path(producer))
        with open(K.backtest_path(producer), encoding="utf-8") as f:
            history = json.load(f)
        conditions = K.assess(producer, target, frame, history)
        hit = frame[frame.year == target]
        if len(hit) and not pd.isna(hit.iloc[0].nino34_lag1):
            nino = round(float(hit.iloc[0].nino34_lag1), 2)
    except (OSError, ValueError) as exc:
        log(f"{producer.key}: weather conditions unavailable: {exc}")

    validation = model["validation"][model["configuration"]]
    return {
        "label": producer.label,
        "label_ko": producer.label_ko,
        "crop": "palm_oil",
        "season": target,
        "marketing_year": f"{target - 1}/{str(target)[-2:]} (Oct-Sep)",
        "unit": "천 t",
        "point": round(p["point"], 0) if publishable else None,
        "range_68": [round(v, 0) for v in p["range_68"]] if publishable else None,
        "range_95": [round(v, 0) for v in p["range_95"]] if publishable else None,
        "trend": round(p["trend"], 0),
        "weather_effect_pct": 0.0,
        "point_basis": "trend",
        "usda_estimate": None if usda is None else float(usda),
        "last_actual": {"year": int(last.year), "value": float(last.psd_production_kt),
                        "source": "USDA PSD estimate"},
        "enso": {"nino34_year_before": nino,
                 "window": K.season_label(target, 1),
                 "note": ("El Nino in the year before tends to cut output 6-24 "
                          "months later; context only, not applied.")},
        "weather_conditions": conditions,
        "skill": {
            "beats_trend": False,
            "skill_vs_trend_only": 0.0,
            "low_confidence": True,
            "forward_folds": validation["n_folds"],
            "recent_mape": round(validation["recent_baseline_mape"], 4),
            "trend_form": model["trend"]["name"],
            "conditions_backtest": os.path.relpath(K.backtest_path(producer), HERE),
        },
        "forecast_gate": model["forecast_gate"],
        "provenance": {
            "label_source": f"USDA FAS PSD Oilseeds, Oil, Palm, {producer.psd_name}",
            "url": psd.URL,
            "weather": "NASA POWER daily at production-weighted points; Niño3.4 OISST v2.1",
            "caveat": ("USDA marketing-year estimates, not a census; the current "
                       "year is revised monthly."),
        },
    }


def write_country(country):
    producer = BY_COUNTRY[country]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "country": country.capitalize(),
        "methodology": (
            "USDA PSD crude palm oil production trend (forward-chained against "
            "itself), USDA's own estimate alongside, and a lagged-drought weather "
            "read-out that does not move the number (scripts/yield_model/palm_oil/)."),
        "regions": {}, "skipped": {},
    }
    entry = region(producer)
    if entry is None:
        payload["skipped"][producer.key] = "USDA PSD slice missing"
        return 1
    payload["season"] = entry["season"]
    payload["regions"][producer.key] = entry
    out = os.path.join(PUBLIC, f"{country}_yield_forecast.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    wc = entry["weather_conditions"] or {}
    log(f"{country}: {entry['season']} trend {entry['trend']:.0f} kt, USDA "
        f"{entry['usda_estimate']}, conditions {wc.get('verdict')} -> {out}")
    return 0


def merge_into(country):
    """Insert or refresh the palm region in a country JSON another model writes."""
    producer = BY_COUNTRY[country]
    out = os.path.join(PUBLIC, f"{country}_yield_forecast.json")
    entry = region(producer)
    if entry is None or not os.path.exists(out):
        return 1
    with open(out, encoding="utf-8") as f:
        payload = json.load(f)
    payload["regions"][producer.key] = entry
    payload.get("skipped", {}).pop(producer.key, None)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    log(f"{country}: palm region {entry['season']} merged -> {out}")
    return 0


def main(argv):
    status = [write_country(c) for c in (argv or OWN_FILE)]
    if not argv:
        status.append(merge_into("thailand"))
    return max(status)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
