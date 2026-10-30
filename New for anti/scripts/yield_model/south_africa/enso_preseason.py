"""
Pre-season maize outlook conditioned on ENSO at planting.

Usage: python3 -m south_africa.enso_preseason   # backtest -> models/enso_preseason_backtest.json

From October the next harvest year's belt is being planted, but its critical
January-February weather is months away, so there is no climate row to run
the model on. Without this the panel kept showing the harvest that finished
in May. Instead, every past season's critical-window anomalies are run
through the model as a scenario, and the scenarios are weighted by how close
that season's Niño3.4 at planting (August-September of the year before
harvest) was to this one's, with a 0.5 °C Gaussian kernel fixed before
scoring. El Niño summers are dry over the belt: 2015/16 and 2023/24, the two
nearest analogues after 1997/98, finished 19% and 26% under trend.

Niño3.4 comes from public/data/sst_regions_v1.json (OISST v2.1, weekly via
sst_refresh.yml), the same series the backtest reads.

Pre-season forward chaining from 2007 (the first season with 15 prior years
of climate anomalies): the even average of scenarios scores 0% against
trend-only, the ENSO-weighted one +6.2% (+9.3% over the last ten). Only 19
seasons are scored, so the band is the trend-only error, not the model's.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SST_FILE = HERE.parents[2] / "public" / "data" / "sst_regions_v1.json"
OUT = HERE / "models" / "enso_preseason_backtest.json"

BANDWIDTH = 0.5
PLANTING_MONTHS = (8, 9)
FEATURES = ["root_sm_critical_z", "vpd_critical_kpa_z"]


def load_nino34(path: Path = SST_FILE) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    region = next(r for r in payload["regions"] if r["id"] == "nino34")
    return {month: float(v) for month, v in region["series"]}


def planting_nino34(series: dict, harvest_year: int):
    vals = [series.get(f"{harvest_year - 1}-{m:02d}") for m in PLANTING_MONTHS]
    return float(np.mean(vals)) if None not in vals else None


def weights(past, now: float) -> np.ndarray:
    past = np.asarray(past, dtype=float)
    return np.exp(-0.5 * ((past - now) / BANDWIDTH) ** 2)


def effective_n(w) -> float:
    w = np.asarray(w, dtype=float)
    return float(w.sum() ** 2 / (w ** 2).sum()) if w.sum() > 0 else 0.0


def backtest(frame: pd.DataFrame) -> dict:
    from sklearn.linear_model import RidgeCV
    from sklearn.preprocessing import StandardScaler

    series = load_nino34()
    df = frame[frame.target_status == "final"].dropna(subset=["yield_kg_ha"] + FEATURES).copy()
    df["n34"] = [planting_nino34(series, int(y)) for y in df.year]
    df = df.dropna(subset=["n34"]).reset_index(drop=True)
    years = df.year.values.astype(int)
    logy = np.log(df.yield_kg_ha.values.astype(float))
    X = df[FEATURES].values.astype(float)

    truth, even, enso, used = [], [], [], []
    for i, target in enumerate(years):
        train = years < target
        if train.sum() < 15:
            continue
        coef = np.polyfit(years[train], logy[train], 1)
        resid = logy[train] - np.polyval(coef, years[train])
        scaler = StandardScaler().fit(X[train])
        ridge = RidgeCV(alphas=np.logspace(-2, 4, 40)).fit(scaler.transform(X[train]), resid)
        scen = ridge.predict(scaler.transform(X[train]))
        w = weights(df.n34.values[train], df.n34.values[i])
        truth.append(logy[i] - np.polyval(coef, target))
        even.append(scen.mean())
        enso.append(float(np.sum(w * scen) / w.sum()))
        used.append(int(target))
    truth, even, enso = map(np.array, (truth, even, enso))

    def skill(pred, sl=slice(None)):
        return float(1 - np.sqrt(np.mean((truth[sl] - pred[sl]) ** 2))
                     / np.sqrt(np.mean(truth[sl] ** 2)))

    last10 = slice(-10, None)
    return {
        "bandwidth_c": BANDWIDTH,
        "planting_months": list(PLANTING_MONTHS),
        "seasons_scored": used,
        "skill_even_fill": round(skill(even), 4),
        "skill_enso_fill": round(skill(enso), 4),
        "skill_even_fill_last10": round(skill(even, last10), 4),
        "skill_enso_fill_last10": round(skill(enso, last10), 4),
    }


def outlook(model: dict, frame: pd.DataFrame, year: int):
    """ENSO-weighted pre-season point for `year`, or None without Niño3.4."""
    try:
        series = load_nino34()
    except (OSError, ValueError, StopIteration):
        return None
    now = planting_nino34(series, year)
    if now is None:
        return None
    past = frame[(frame.target_status == "final") & (frame.year < year)]
    past = past.dropna(subset=model["selected_features"]).copy()
    past["n34"] = [planting_nino34(series, int(y)) for y in past.year]
    past = past.dropna(subset=["n34"])
    if len(past) < 15:
        return None
    w = weights(past.n34.values, now)
    X = past[model["selected_features"]].values.astype(float)

    trends, points, evens = [], [], []
    scen_mean = np.zeros(len(past))
    for component in model["components"]:
        trend_log = float(np.polyval(component["trend"]["log_poly_coef"], year))
        z = (X - np.asarray(component["scaler"]["mean"])) / np.asarray(component["scaler"]["scale"])
        logs = component["ridge"]["intercept"] + z @ np.asarray(component["ridge"]["coef"])
        scen_mean += logs / len(model["components"])
        trends.append(np.exp(trend_log))
        points.append(np.exp(trend_log + np.sum(w * logs) / w.sum()))
        evens.append(np.exp(trend_log + logs.mean()))
    order = np.argsort(-w)[:4]
    return {
        "trend": float(np.mean(trends)),
        "point": float(np.mean(points)),
        "even_fill_point": float(np.mean(evens)),
        "nino34_planting": round(now, 2),
        "planting_months": [f"{year - 1}-{m:02d}" for m in PLANTING_MONTHS],
        "bandwidth_c": BANDWIDTH,
        "effective_seasons": round(effective_n(w), 1),
        "beyond_record": bool(now > past.n34.max() + 0.5 or now < past.n34.min() - 0.5),
        "analogs": [
            {"year": int(past.year.values[j]),
             "nino34_planting": round(float(past.n34.values[j]), 2),
             "weight": round(float(w[j] / w.sum()), 3),
             "weather_effect_pct": round(float((np.exp(scen_mean[j]) - 1) * 100), 1)}
            for j in order
        ],
    }


def main() -> None:
    frame = pd.read_csv(HERE / "training" / "commercial_maize_belt.csv")
    result = backtest(frame)
    OUT.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "seasons_scored"}))


if __name__ == "__main__":
    main()
