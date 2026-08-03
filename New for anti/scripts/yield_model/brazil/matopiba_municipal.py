"""
MATOPIBA soybean yield, modelled per municipality instead of state-averaged.

Usage: python3 -m brazil.matopiba_municipal [muni_key ...]

Why this file exists, and why it is a separate module rather than an
extension of regions.py: the state-level `matopiba_soja` model blends four
states (BA/MA/PI/TO) with different rainfall regimes and sowing calendars
into one production-weighted number every season. Reis et al. (2020,
Climate 11(10):1130) and the companion MATOPIBA climate-variability paper
find the weather-yield relationship varies by sowing date and location across
the region -- state averaging smooths away exactly the signal a
location-specific model needs. Their own validated approach (DSSAT-CROPGRO,
a mechanistic crop simulator) works at municipality level; this is the
statistical analogue of that granularity, not the same method, but the same
level.

This module intentionally does not touch collect.py, climate.py, regions.py,
predict.py or run_forecast.py beyond importing from them -- those files were
independently edited by a concurrent session on this same repository, and
adding new work to a new file avoids compounding that merge later. sidra.py's
new `municipality_yield()` was safe to add (that file was untouched by the
other session).

Feature set mirrors state-level `_matopiba_soja` minus the two terms already
shown to be constant-zero for MATOPIBA in that window (the 0.2-0.4 wilting
threshold never binds here; see NEXT_STEPS.md). No point re-testing a dead
feature at a finer grain before checking whether it's dead here too --
`gwetroot_stress_days`/`heat_x_drought` are computed below and dropped by
train.py's own constant-column filter if they're still always zero.
"""

import json
import os
import sys

import numpy as np
import pandas as pd

from . import climate as C
from . import sidra
from .collect import current_season, load_oni, oni_for, point_weather, ONI_SUMMER
from .train import (
    ALPHAS,
    MIN_TRAIN,
    RECENT_FOLDS,
    TREND_FORMS,
    evaluate,
    fit_trend,
    prepare,
    run_cv,
    window_rows,
)

from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler

HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training_muni")
MODELS = os.path.join(HERE, "models_muni")

# name -> (IBGE n6 code, uf, lat, lon, elevation_m). Geocoded via Nominatim,
# elevation via open-elevation, both 2026-08-03. Longest, cleanest-record
# municipalities first -- Barreiras and São Desidério are two of Reis et al.'s
# own four validation sites, so they double as a literature cross-check.
MUNICIPALITIES = {
    "barreiras":       (2903201, "BA", -12.1440, -44.9967, 449),
    "sao_desiderio":   (2928901, "BA", -12.3572, -44.9769, 499),
    "correntina":      (2909307, "BA", -13.3442, -44.6345, 574),
    "balsas":          (2101400, "MA", -7.5321, -46.0372, 256),
    "alto_parnaiba":   (2100501, "MA", -9.1125, -45.9310, 283),
    "tasso_fragoso":   (2112001, "MA", -8.4729, -45.7462, 244),
    "urucui":          (2211209, "PI", -7.7970, -44.5749, 306),
    "baixa_grande":    (2201150, "PI", -7.8629, -45.2113, 355),
    "bom_jesus_pi":    (2201903, "PI", -9.0712, -44.3584, 299),
    "pedro_afonso":    (1716505, "TO", -8.9757, -48.1733, 190),
    "formoso":         (1708205, "TO", -11.8060, -49.5257, 270),
    "campos_lindos":   (1703842, "TO", -7.9741, -46.8024, 301),
    # Luís Eduardo Magalhães excluded: only 24 seasons (municipality created
    # 2001), too short for a 5-year holdout plus 22-year minimum training.
}

CROP = "soja"


def log(msg):
    print(f"[muni] {msg}", flush=True)


def build_features(daily, y):
    """Same reproductive-window logic as state-level _matopiba_soja, at one
    point instead of a four-point production-weighted blend."""
    ors, _ = C.onset_doy(daily, y)
    rep = [(1, 0), (2, 0)]
    return {
        "heat_vpd_stress": C.vpd_heat_stress(daily, rep, y, 35.0),
        "heat_days_35": C.heat_days(daily, rep, y, 35.0),
        "heat_excess": C.heat_excess(daily, rep, y, 35.0),
        "days_late": C.days_late(ors),
        "precip_rep": C.window_totals(daily, rep, y),
        "gwetroot_rep_mean": C.soil_moisture_mean(daily, rep, y),
        "gwetroot_stress_days": C.soil_stress_days(daily, rep, y, 0.3),
        "heat_x_drought": C.heat_x_drought_days(daily, rep, y, 35.0, 0.3),
    }


def collect_one(key):
    code, uf, lat, lon, elev = MUNICIPALITIES[key]
    point = {"name": key, "lat": lat, "lon": lon, "elevation": elev}
    daily = point_weather(point)
    oni = load_oni()

    rows = []
    for year in range(1982, current_season() + 1):
        feats = build_features(daily, year)
        if not feats:
            continue
        feats["year"] = year
        feats["oni_season"] = oni_for(oni, year, ONI_SUMMER)
        rows.append(feats)

    df = pd.DataFrame(rows)
    yields = sidra.municipality_yield(CROP, code)
    df = df.merge(yields, on="year", how="left")
    df = df.sort_values("year").reset_index(drop=True)

    os.makedirs(TRAINING, exist_ok=True)
    out = os.path.join(TRAINING, f"{key}.csv")
    df.to_csv(out, index=False)
    labelled = df.dropna(subset=["yield_kg_ha"])
    log(f"{key} ({uf}): wrote {len(df)} seasons ({len(labelled)} with yield)")
    return df


def train_one(key):
    path = os.path.join(TRAINING, f"{key}.csv")
    if not os.path.exists(path):
        log(f"{key}: no training table, run collect first")
        return None

    df = pd.read_csv(path).sort_values("year").reset_index(drop=True)
    df = df.dropna(subset=["yield_kg_ha"])

    # Trim leading seasons that lack the weather features rather than
    # dropping the features. onset_doy's anomalous-accumulation window needs
    # a full prior year, so the first 1-2 seasons of any point's record come
    # back null; discarding those two rows out of 43 is far cheaper than
    # discarding six real weather features because of them.
    weather_cols = [c for c in df.columns if c not in {"year", "yield_kg_ha"}]
    complete = df[weather_cols].notna().all(axis=1)
    trimmed = int((~complete).sum())
    if trimmed and trimmed <= 5:
        df = df[complete].reset_index(drop=True)
        log(f"{key}: trimmed {trimmed} leading season(s) with incomplete features")

    candidates = [c for c in df.columns
                  if c not in {"year", "yield_kg_ha"}
                  and df[c].notna().all() and df[c].std() > 0]

    if len(df) < MIN_TRAIN + 5 or not candidates:
        log(f"{key}: only {len(df)} usable seasons or no candidates, skipped")
        return None

    # The guide's own headline variables (rainfed reproductive-window heat and
    # water balance), same as the state-level core list minus the two terms
    # already shown constant-zero for MATOPIBA. Compared against the full
    # 7-9 feature set as a guard against overfitting ~40 rows with too many
    # regressors -- the state-level model applies the same discipline.
    core_pool = ["days_late", "precip_rep", "heat_vpd_stress", "gwetroot_rep_mean"]
    core = [c for c in core_pool if c in candidates]

    log(f"{key}: {len(df)} seasons {int(df.year.min())}-{int(df.year.max())}, "
        f"{len(candidates)} usable features, {len(core)} core: {candidates}")

    results = {}
    sets = [("all", candidates)] + ([("core", core)] if core else [])
    for slabel, feats in sets:
        for tlabel, degree, window in TREND_FORMS:
            for mode in ("loo", "forward"):
                out = run_cv(df, feats, mode, degree, window, MIN_TRAIN)
                if out is None:
                    continue
                truth, pred, base, yrs = out
                rkey = f"{slabel}_{tlabel}_{mode}"
                results[rkey] = evaluate(truth, pred, base)
                results[rkey]["degree"] = degree
                results[rkey]["window"] = window
                results[rkey]["trend_form"] = tlabel
                results[rkey]["features"] = feats

    fwd = {k: v for k, v in results.items() if k.endswith("_forward")}
    if not fwd:
        log(f"{key}: no forward-chaining fold had enough history")
        return None

    best_key = min(fwd, key=lambda k: fwd[k]["rmse"])
    best = results[best_key]
    best_feats = best["features"]
    best_baseline = min(v["baseline_rmse"] for v in fwd.values())
    best_baseline_recent = min(v["recent_baseline_rmse"] for v in fwd.values())

    recent_skill = (1 - best["recent_rmse"] / best_baseline_recent
                    if best_baseline_recent > 0 else float("nan"))
    full_skill = (1 - best["rmse"] / best_baseline
                  if best_baseline > 0 else float("nan"))
    beats_trend = full_skill > 0 and recent_skill > 0

    degree, window = best["degree"], best["window"]
    years = df.year.values.astype(float)
    trend = fit_trend(years, df.yield_kg_ha.values, degree, window)
    X = prepare(df, best_feats, years, trend)
    fit = window_rows(years, np.ones(len(years), dtype=bool), degree, window)
    scaler = StandardScaler().fit(X[fit])
    resid = np.log(df.yield_kg_ha.values[fit]) - trend(years[fit])
    final = RidgeCV(alphas=ALPHAS).fit(scaler.transform(X[fit]), resid)

    sigma = best["recent_rmse"] if beats_trend else best_baseline_recent
    coefs = dict(zip(best_feats, final.coef_.tolist()))
    ranked = sorted(coefs.items(), key=lambda kv: -abs(kv[1]))
    top_effects = [{"feature": k, "effect_pct": round((np.exp(v) - 1) * 100, 2)}
                   for k, v in ranked]

    log(f"  best: {best_key}  vs-trend(full)={full_skill:+.1%}  "
        f"vs-trend(recent{RECENT_FOLDS})={recent_skill:+.1%}  "
        f"{'BEATS TREND' if beats_trend else 'no skill'}")
    log("  top effects: " + ", ".join(
        f"{e['feature']} {e['effect_pct']:+.1f}%" for e in top_effects[:4]))

    artifact = {
        "key": key, "crop": CROP,
        "n_seasons": int(len(df)),
        "trained_years": [int(df.year.min()), int(df.year.max())],
        "features": best_feats,
        "trend": {"log_poly_coef": [float(c) for c in trend.coefficients],
                  "degree": int(degree), "form": best["trend_form"], "window": window},
        "scaler": {"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist()},
        "ridge": {"alpha": float(final.alpha_), "coef": final.coef_.tolist(),
                  "intercept": float(final.intercept_)},
        "beats_trend": bool(beats_trend),
        "skill_vs_trend_full": float(full_skill),
        "skill_vs_trend_recent": float(recent_skill),
        "sigma_kg_ha": float(sigma),
        "top_effects": top_effects,
    }
    os.makedirs(MODELS, exist_ok=True)
    with open(os.path.join(MODELS, f"{key}.json"), "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)
    return artifact


def backtest_one(key, n_years=5):
    """Hold out the last n_years published seasons, same discipline as
    brazil/backtest.py: refit trend + ridge on strictly earlier years."""
    mpath = os.path.join(MODELS, f"{key}.json")
    tpath = os.path.join(TRAINING, f"{key}.csv")
    if not (os.path.exists(mpath) and os.path.exists(tpath)):
        return None
    model = json.load(open(mpath, encoding="utf-8"))
    df = pd.read_csv(tpath).dropna(subset=["yield_kg_ha"]).sort_values("year")
    feats = [f for f in model["features"] if f in df.columns]
    df = df.dropna(subset=feats).reset_index(drop=True)

    degree = model["trend"]["degree"]
    window = model["trend"].get("window")
    years = df.year.values.astype(float)
    yields = df.yield_kg_ha.values.astype(float)
    targets = years[-n_years:]

    rows = []
    for target in targets:
        train_mask = years < target
        if train_mask.sum() < 12:
            continue
        trend = fit_trend(years[train_mask], yields[train_mask], degree, window)
        X = prepare(df, feats, years, trend)
        fit = window_rows(years, train_mask, degree, window)
        resid = np.log(yields[fit]) - trend(years[fit])
        scaler = StandardScaler().fit(X[fit])
        ridge = RidgeCV(alphas=ALPHAS).fit(scaler.transform(X[fit]), resid)

        i = int(np.where(years == target)[0][0])
        pred_resid = float(ridge.predict(scaler.transform(X[i:i + 1]))[0])
        base = float(np.exp(trend(target)))
        pred = float(np.exp(trend(target) + pred_resid))
        actual = float(yields[i])
        rows.append({"year": int(target), "actual": actual, "predicted": pred,
                     "trend_only": base,
                     "err_pct": (pred - actual) / actual * 100,
                     "trend_err_pct": (base - actual) / actual * 100})

    if not rows:
        return None
    bt = pd.DataFrame(rows)
    mape = float(np.mean(np.abs(bt.err_pct)))
    tmape = float(np.mean(np.abs(bt.trend_err_pct)))
    return bt, mape, tmape


def main():
    keys = sys.argv[1:] or list(MUNICIPALITIES.keys())
    summary = []
    for key in keys:
        collect_one(key)
        artifact = train_one(key)
        if artifact is None:
            continue
        bt = backtest_one(key)
        if bt is not None:
            _, mape, tmape = bt
            log(f"  5yr holdout: model MAPE {mape:.1f}% vs trend {tmape:.1f}%")
        else:
            mape = tmape = None
        summary.append({
            "key": key, "n": artifact["n_seasons"],
            "skill": artifact["skill_vs_trend_recent"],
            "beats": artifact["beats_trend"],
            "mape": mape, "tmape": tmape,
        })
        log("")

    log("=" * 78)
    log(f"{'municipality':20} {'seasons':>7} {'vs trend':>10} {'holdout MAPE':>14} {'verdict'}")
    log("-" * 78)
    for s in sorted(summary, key=lambda x: -(x["skill"] or -9)):
        h = f"{s['mape']:.1f}% vs {s['tmape']:.1f}%" if s["mape"] is not None else "n/a"
        verdict = "usable" if s["beats"] else "no skill"
        log(f"{s['key']:20} {s['n']:7d} {s['skill']:+9.1%} {h:>14}  {verdict}")
    log("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
