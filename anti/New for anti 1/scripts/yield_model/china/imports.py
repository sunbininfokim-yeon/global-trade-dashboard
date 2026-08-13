"""
China import-demand model -- Regions/중국/거시_수입수요.

Usage: python3 -m china.imports [--refresh-comtrade]

Structurally unlike the five field models. The target is a national trade
volume rather than a field outcome, so it does not fit RegionCrop and lives
here instead.

Why this one is worth building even though the yield models found nothing:
its target is actually measured. Chinese soybean imports went from 10 Mt to
100 Mt with real year-to-year swings that customs authorities count at the
dock, against a PSD yield series that moves 1.6-6% a year in rounded
increments. There is something here to explain.

The guide's frame, from §3:

    Import_Demand(t) = Required_Demand(t) - Predicted_Production(t)
                       + Strategic_Reserve_Delta

Implemented as: model imports on domestic production (known once the harvest
is in), the demand trajectory carried by lagged consumption, the stock buffer
carried by lagged ending stocks, and the Northeast weather anomaly that drove
production. Same validation discipline as the yield models -- forward chaining
against a trend-only baseline, trend refit inside every fold.

Leakage matters more here than anywhere else in this package. Same-year
domestic consumption is *not* a feature, even though PSD publishes it: on a
balance sheet imports are roughly consumption minus production plus stock
change, so regressing imports on same-year consumption would recover an
accounting identity and report it as forecasting skill. Only quantities known
before the marketing year opens, plus that year's own harvest, are used.

Departures from the guide, all stated rather than papered over:
  - No Temporal Fusion Transformer. ~40 annual observations cannot fit one;
    a ridge on a log trend is what this sample size supports.
  - Hog inventory IS implemented, contrary to an earlier note here: USDA PSD
    estimates China's sow and total swine herd even though China no longer
    publishes it usefully. It does not help. Hog-cycle variables alone score
    -0.2% against trend and adding them to the demand block changes nothing,
    which is a result about this target's annual resolution rather than about
    the guide's reasoning.
  - No NLP policy-risk score from CSIS / Chatham House text.
  - No MIDAS mixed-frequency structure: the target is annual, so there is no
    high-frequency side to mix in.
"""

import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler

from . import labels as L

HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training")
MODELS = os.path.join(HERE, "models")

ALPHAS = np.logspace(-2, 4, 40)
MIN_TRAIN = 18
RECENT_FOLDS = 10
TREND_FORMS = [("deg1", 1, None), ("deg2", 2, None), ("recent20", 1, 20)]

# HS codes for the Comtrade cross-check. PSD is USDA's estimate of the
# marketing year; Comtrade is what China's customs administration reported for
# the calendar year. They will not agree exactly and are not meant to -- the
# comparison is a check that the PSD series is not drifting from what actually
# crossed the dock.
HS = {"soybeans": "1201", "corn": "1005"}

# `regime_start` is not a tuning knob. Both series contain a change of trade
# regime that a single trend cannot span, and fitting across it corrupts the
# trend, the scaling and the coefficients at once -- the same reason
# brazil/regions.py restricts MATOPIBA cotton to 2000 onward.
#
# Soybeans: China was a net *exporter* into the early 1990s and imported
# essentially nothing (1 thousand MT in some years against 113 million today).
# Import liberalisation in the mid-1990s is the break. A log trend fitted over
# five orders of magnitude extrapolates absurdly -- it produced a baseline RMSE
# of 298,000 thousand MT against a series whose maximum is 113,000.
#
# Corn: imports were rounding error until the 2009 tariff-rate quota started
# being filled, then jumped to 29 Mt in 2020-21 as reserves were rebuilt after
# African swine fever. Even restricted, this leaves ~17 observations, which is
# very thin -- reported rather than hidden.
COMMODITIES = {
    "soybeans": {
        "psd": "Oilseed, Soybean",
        "meal": "Meal, Soybean",
        "label": "China soybean imports",
        "regime_start": 1996,
        "min_train": 15,
    },
    "corn": {
        "psd": "Corn",
        "meal": None,
        "label": "China corn imports",
        "regime_start": 2009,
        "min_train": 10,
    },
}


def log(msg):
    print(f"[imports] {msg}", flush=True)


def build_table(name):
    """
    Assemble the supply-demand panel for one commodity.

    Every feature is either known before the marketing year opens (lagged) or
    is that year's own harvest. Same-year consumption is deliberately absent --
    see the module docstring.
    """
    spec = COMMODITIES[name]
    psd = spec["psd"]

    prod = L.psd_series(psd, "Production").rename(columns={"value": "production"})
    imp = L.psd_series(psd, "Imports").rename(columns={"value": "imports"})
    cons = L.psd_series(psd, "Domestic Consumption").rename(
        columns={"value": "consumption"})
    stocks = L.psd_series(psd, "Ending Stocks").rename(
        columns={"value": "ending_stocks"})

    df = (prod[["year", "production"]]
          .merge(imp[["year", "imports"]], on="year", how="inner")
          .merge(cons[["year", "consumption"]], on="year", how="left")
          .merge(stocks[["year", "ending_stocks"]], on="year", how="left")
          .sort_values("year").reset_index(drop=True))

    # Lagged, therefore known when the marketing year opens.
    df["consumption_lag1"] = df.consumption.shift(1)
    df["consumption_growth"] = df.consumption.shift(1) / df.consumption.shift(2)
    df["stocks_lag1"] = df.ending_stocks.shift(1)
    df["stock_use_lag1"] = df.ending_stocks.shift(1) / df.consumption.shift(1)
    df["imports_lag1"] = df.imports.shift(1)

    if spec["meal"]:
        meal = L.psd_series(spec["meal"], "Domestic Consumption").rename(
            columns={"value": "meal_consumption"})
        df = df.merge(meal[["year", "meal_consumption"]], on="year", how="left")
        # The feed-demand proxy standing in for the hog inventory the guide
        # wants: soybean meal is fed almost entirely to pigs and poultry.
        df["meal_lag1"] = df.meal_consumption.shift(1)
        df["meal_growth"] = (df.meal_consumption.shift(1)
                             / df.meal_consumption.shift(2))

    # Hog cycle -- 거시_수입수요 §2A. The guide puts hog inventory at the centre
    # of Chinese feed demand and it is right to: soybeans are imported to feed
    # pigs, not people. All three enter lagged, so nothing here is known later
    # than the start of the marketing year being forecast.
    #
    # The sow herd is the one that leads. A sow bred this year is a finishing
    # pig eating meal the next, so its growth rate anticipates feed demand
    # about a year out -- which is the horizon the guide asks the model to
    # forecast over.
    try:
        sows = L.psd_livestock_series("Animal Numbers, Swine",
                                      "Sow Beginning Stocks")
        herd = L.psd_livestock_series("Animal Numbers, Swine",
                                      "Beginning Stocks")
        pork = L.psd_livestock_series("Meat, Swine", "Production")
        df = (df.merge(sows.rename(columns={"value": "sow_herd"}), on="year",
                       how="left")
                .merge(herd.rename(columns={"value": "hog_herd"}), on="year",
                       how="left")
                .merge(pork.rename(columns={"value": "pork_production"}),
                       on="year", how="left"))
        df["sow_herd_lag1"] = df.sow_herd.shift(1)
        df["sow_growth"] = df.sow_herd.shift(1) / df.sow_herd.shift(2)
        df["hog_herd_lag1"] = df.hog_herd.shift(1)
        df["hog_growth"] = df.hog_herd.shift(1) / df.hog_herd.shift(2)
        df["pork_growth"] = df.pork_production.shift(1) / df.pork_production.shift(2)
    except Exception as e:  # noqa: BLE001 - livestock is an addition, not a floor
        log(f"  livestock series unavailable, hog-cycle features skipped: {e}")

    # The production shortfall the guide's Import_Gap is built on, using last
    # year's demand level against this year's harvest.
    df["shortfall"] = df.consumption.shift(1) - df.production

    # Weather anomaly behind that harvest, from the Northeast field model. This
    # is what wires Predicted_Production to an actual production model rather
    # than asserting the link.
    ne_key = "northeast_soy" if name == "soybeans" else "northeast_corn"
    ne_path = os.path.join(TRAINING, f"{ne_key}.csv")
    if os.path.exists(ne_path):
        ne = pd.read_csv(ne_path)
        keep = [c for c in ("frost_penalty", "gdd_season", "precip_podfill",
                            "precip_silking", "heat_days_podfill",
                            "heat_days_silking") if c in ne.columns]
        df = df.merge(ne[["year"] + keep], on="year", how="left")

    return df


def fit_trend(years, values, degree, window=None):
    if window:
        mask = years >= years.max() - window + 1
        if mask.sum() >= max(degree + 2, 8):
            years, values = years[mask], values[mask]
    return np.poly1d(np.polyfit(years, np.log(values), degree))


def run_cv(df, features, degree, window, min_train):
    years = df.year.values.astype(float)
    values = df.imports.values.astype(float)
    X = df[features].astype(float).values

    preds, bases, truth, used = [], [], [], []
    for i, target_year in enumerate(years):
        train = years < target_year
        if train.sum() < min_train:
            continue
        trend = fit_trend(years[train], values[train], degree, window)
        resid_train = np.log(values[train]) - trend(years[train])

        scaler = StandardScaler().fit(X[train])
        model = RidgeCV(alphas=ALPHAS).fit(scaler.transform(X[train]), resid_train)
        pred = float(model.predict(scaler.transform(X[i:i + 1]))[0])

        preds.append(float(np.exp(trend(target_year) + pred)))
        bases.append(float(np.exp(trend(target_year))))
        truth.append(values[i])
        used.append(int(target_year))

    if not truth:
        return None
    return np.array(truth), np.array(preds), np.array(bases), used


def score(truth, pred, base):
    recent = slice(-min(RECENT_FOLDS, len(truth)), None)
    rmse = float(np.sqrt(np.mean((truth - pred) ** 2)))
    base_rmse = float(np.sqrt(np.mean((truth - base) ** 2)))
    r_rmse = float(np.sqrt(np.mean((truth[recent] - pred[recent]) ** 2)))
    r_base = float(np.sqrt(np.mean((truth[recent] - base[recent]) ** 2)))
    return {
        "rmse": rmse, "baseline_rmse": base_rmse,
        "recent_rmse": r_rmse, "recent_baseline_rmse": r_base,
        "skill": 1 - rmse / base_rmse if base_rmse > 0 else float("nan"),
        "recent_skill": 1 - r_rmse / r_base if r_base > 0 else float("nan"),
        "n": len(truth),
    }


def cross_check_comtrade(name, df):
    """
    Compare PSD's import estimate against what customs actually reported.

    A persistent gap is worth knowing about: PSD is a marketing-year estimate
    and Comtrade a calendar-year customs total, so a steady offset is expected,
    but a widening one would mean the modelled series has drifted from the
    physical trade.
    """
    years = [int(y) for y in df.year.values if y >= 2000]
    try:
        ct = L.comtrade_imports_mt(HS[name], years)
    except Exception as e:  # noqa: BLE001 - a trade gap must not stop the model
        log(f"  comtrade cross-check unavailable: {e}")
        return None
    if ct.empty:
        return None

    merged = df.merge(ct, on="year", how="inner").dropna(
        subset=["imports", "import_mt"])
    if merged.empty:
        return None

    # PSD is in 1000 MT, Comtrade converted to tonnes.
    psd_mt = merged.imports * 1000.0
    ratio = (merged.import_mt / psd_mt).replace([np.inf, -np.inf], np.nan).dropna()
    if ratio.empty:
        return None

    log(f"  comtrade cross-check on {len(ratio)} years: customs / PSD "
        f"median {ratio.median():.2f}, range {ratio.min():.2f}-{ratio.max():.2f}")
    return {"n_years": int(len(ratio)),
            "median_ratio": float(ratio.median()),
            "min_ratio": float(ratio.min()),
            "max_ratio": float(ratio.max())}


def model_one(name):
    spec = COMMODITIES[name]
    df = build_table(name)

    # Raw level series are dropped from the candidate pool: they are either
    # contemporaneous (leakage) or already represented by their own lag.
    candidates = [c for c in df.columns
                  if c not in ("year", "imports", "consumption",
                               "ending_stocks", "meal_consumption",
                               "sow_herd", "hog_herd", "pork_production")]
    df = df.dropna(subset=["imports"] + candidates).reset_index(drop=True)
    # Imports are logged, so a zero-import year cannot be carried.
    df = df[df.imports > 0].reset_index(drop=True)

    regime = spec["regime_start"]
    before = len(df)
    df = df[df.year >= regime].reset_index(drop=True)
    candidates = [c for c in candidates if df[c].std() > 0]

    min_train = spec["min_train"]
    if len(df) < min_train + 5:
        log(f"{name}: only {len(df)} usable years, skipped")
        return None

    log(f"{spec['label']}")
    log(f"  regime restriction from {regime} ({before} -> {len(df)} years)")
    log(f"  {len(df)} years {int(df.year.min())}-{int(df.year.max())}, "
        f"{len(candidates)} features")
    log(f"  imports {df.imports.min():,.0f}-{df.imports.max():,.0f} thousand MT")

    # Guide's core: shortfall plus the demand trajectory.
    # The guide's own frame: the production shortfall, the demand trajectory
    # (now carried by the hog cycle it actually names), and the stock buffer.
    core = [c for c in ("shortfall", "sow_growth", "hog_growth",
                        "consumption_growth", "stock_use_lag1", "meal_growth",
                        "imports_lag1") if c in candidates]

    # The pre-registered specification is the one that counts.
    #
    # An earlier version reported +20.3% skill for this model. That number came
    # from the 13-feature "all" set and survives no scrutiny: the guide's own
    # a-priori specification scores -18.6%, hog-cycle variables alone -0.2%,
    # and adding five more plausible predictors to the winning set flips it to
    # -0.0%. With 15 forward folds and 18-odd combinations tried, one of them
    # landing at +20% is what search noise looks like, not what skill looks
    # like. Reporting it as the headline would have been picking the winner
    # after the race.
    #
    # So `core` -- the variables 거시_수입수요 §2-3 names before seeing any
    # result -- decides beats_trend. The exploratory sets are still run and
    # recorded, but flagged, and they cannot promote the model.
    results = {}
    for label, feats in (("core", core), ("all", candidates)):
        if not feats:
            continue
        for tlabel, degree, window in TREND_FORMS:
            out = run_cv(df, feats, degree, window, min_train)
            if out is None:
                continue
            truth, pred, base, yrs = out
            key = f"{label}_{tlabel}"
            results[key] = score(truth, pred, base)
            results[key].update({"features": feats, "degree": degree,
                                 "window": window, "trend_form": tlabel,
                                 "years": [yrs[0], yrs[-1]]})

    if not results:
        log("  no fold had enough history\n")
        return None

    # Selection is restricted to the pre-registered set; only the trend form
    # is chosen by fit, which is a single nuisance parameter rather than a
    # feature search.
    core_keys = [k for k in results if k.startswith("core_")]
    best_key = min(core_keys or list(results), key=lambda k: results[k]["rmse"])
    best = results[best_key]

    exploratory = {k: v["skill"] for k, v in results.items()
                   if not k.startswith("core_")}
    if exploratory:
        top = max(exploratory.values())
        log(f"  exploratory sets reached {top:+.1%} but are not used to judge "
            "the model -- see the note in this module.")
    best_baseline = min(v["baseline_rmse"] for v in results.values())
    best_baseline_recent = min(v["recent_baseline_rmse"] for v in results.values())

    for k in sorted(results):
        r = results[k]
        mark = " <-" if k == best_key else ""
        log(f"    {k:16} n={r['n']:3d}  RMSE={r['rmse']:9,.0f}  "
            f"recent={r['recent_rmse']:9,.0f}  vs trend={r['skill']:+7.1%}{mark}")

    full_skill = 1 - best["rmse"] / best_baseline if best_baseline > 0 else float("nan")
    recent_skill = (1 - best["recent_rmse"] / best_baseline_recent
                    if best_baseline_recent > 0 else float("nan"))
    beats_trend = full_skill > 0 and recent_skill > 0

    if beats_trend:
        log(f"  VERDICT: beats the best trend baseline by {full_skill:.1%} "
            f"over all folds, {recent_skill:.1%} over the last {RECENT_FOLDS}.")
    else:
        log("  VERDICT: does not beat a trend-only baseline out of sample.")

    check = cross_check_comtrade(name, df)

    # Final fit for forecasting.
    years = df.year.values.astype(float)
    trend = fit_trend(years, df.imports.values.astype(float),
                      best["degree"], best["window"])
    X = df[best["features"]].astype(float).values
    scaler = StandardScaler().fit(X)
    resid = np.log(df.imports.values) - trend(years)
    final = RidgeCV(alphas=ALPHAS).fit(scaler.transform(X), resid)

    coefs = sorted(zip(best["features"], final.coef_.tolist()),
                   key=lambda kv: -abs(kv[1]))[:4]
    log("  effect of +1 SD: "
        + ", ".join(f"{k} {(np.exp(v) - 1) * 100:+.1f}%" for k, v in coefs))
    log("")

    artifact = {
        "key": f"import_{name}",
        "label": spec["label"],
        "doc": "Regions/중국/거시_수입수요/사료_곡물/수입수요_갭_분석_및_수식.md",
        "target_label": f"{name} imports",
        "target_unit": "1000 MT",
        "label_source": "USDA PSD, national, marketing year",
        "regime_start": regime,
        "trained_years": [int(df.year.min()), int(df.year.max())],
        "n_years": int(len(df)),
        "trend": {"log_poly_coef": [float(c) for c in trend.coefficients],
                  "degree": int(best["degree"]),
                  "form": best["trend_form"],
                  "window": best["window"],
                  "space": "log(1000 MT)"},
        "features": best["features"],
        "feature_set": best_key.split("_")[0],
        "scaler": {"mean": scaler.mean_.tolist(),
                   "scale": scaler.scale_.tolist()},
        "ridge": {"alpha": float(final.alpha_),
                  "coef": final.coef_.tolist(),
                  "intercept": float(final.intercept_)},
        "beats_trend": bool(beats_trend),
        "selection": ("pre-registered feature set from the guide; only the "
                      "trend form is fitted. Exploratory sets are recorded in "
                      "`validation` but cannot promote the model."),
        "exploratory_best_skill": (float(max(exploratory.values()))
                                   if exploratory else None),
        "skill_vs_best_trend": float(full_skill),
        "recent_skill_vs_trend": float(recent_skill),
        "uncertainty": {
            "sigma": float(best["recent_rmse"] if beats_trend
                           else best_baseline_recent),
            "unit": "1000 MT",
            "basis": (f"out-of-sample RMSE over the last {RECENT_FOLDS} "
                      "forward-chaining folds" if beats_trend else
                      f"trend-only baseline RMSE over the last {RECENT_FOLDS} "
                      "folds (model showed no skill)"),
        },
        "comtrade_cross_check": check,
        "departures": [
            "No Temporal Fusion Transformer: ~40 annual rows cannot support "
            "one, so the model is a ridge on a log trend.",
            "No hog inventory or ASF series -- not openly published at usable "
            "frequency. Soybean meal consumption is the feed-demand proxy.",
            "No NLP policy-risk score from CSIS / Chatham House text.",
            "Same-year domestic consumption is excluded as a feature: on a "
            "balance sheet it would recover an accounting identity and report "
            "it as skill.",
        ],
        "validation": {k: {kk: vv for kk, vv in v.items() if kk != "features"}
                       for k, v in results.items()},
    }

    os.makedirs(MODELS, exist_ok=True)
    with open(os.path.join(MODELS, f"import_{name}.json"), "w",
              encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)
    return artifact


def main():
    names = [a for a in sys.argv[1:] if not a.startswith("--")] or list(COMMODITIES)
    built = [a for a in (model_one(n) for n in names) if a]

    log("=" * 76)
    log(f"{'model':22} {'years':>6} {'vs trend':>10} {'recent':>10} "
        f"{'sigma (kt)':>12}  verdict")
    log("-" * 76)
    for a in built:
        tag = "usable" if a["beats_trend"] else "no skill - use trend"
        log(f"{a['key']:22} {a['n_years']:6d} "
            f"{a['skill_vs_best_trend']:+9.1%} "
            f"{a['recent_skill_vs_trend']:+9.1%} "
            f"{a['uncertainty']['sigma']:12,.0f}  {tag}")
    log("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())
