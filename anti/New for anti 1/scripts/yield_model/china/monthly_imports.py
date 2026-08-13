"""
Direct 3- and 6-month forecasts of China's monthly soybean/corn imports.

This is the final, deliberately narrow test of the macro-import guide.  The
annual model has only 30 soybean and 17 corn observations; monthly customs data
raises that to roughly 300 without inventing a target.

Seasonality is not allowed to count as model skill.  China buys South American
soybeans after the Brazilian harvest and US soybeans after the US harvest, so
the target has a large and predictable month-of-year cycle.  Every model is
therefore judged against the *best* of three seasonal baselines on identical
forward folds:

  1. log trend + month fixed effects, refit at every forecast origin;
  2. the same month one year earlier;
  3. the mean of the same month over the prior three years.

The Ridge model predicts only the residual above baseline 1.  For horizon h,
all autoregressive features end at target_month - h, which is the latest month
known at forecast time.  No future monthly value, annual PSD accounting item,
or same-period consumption is allowed in.

Raw customs observations are stored separately from model caches in
``china/data/monthly_imports/``.  They are small, auditable model inputs and are
intended to be tracked.

Usage:
    python3 -m china.monthly_imports
    python3 -m china.monthly_imports soybeans
    python3 -m china.monthly_imports --refresh
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler


HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "monthly_imports")
MODELS = os.path.join(HERE, "models")
PROXY = ("https://global-trade-dashboard.sunbin-info-kim.workers.dev"
         "/api/comtrade")

CHINA = "156"
WORLD = "0"
START_YEAR = 2000
END_YEAR = 2025       # last complete calendar year; never train on a partial year
HORIZONS = (3, 6)
MIN_HISTORY = 72      # six complete years before the first forecast
RECENT_FOLDS = 36     # three years, so every month is represented three times
ALPHAS = np.logspace(-2, 4, 40)

COMMODITIES = {
    "soybeans": {"hs": "1201", "label": "China soybean imports"},
    "corn": {"hs": "1005", "label": "China corn imports"},
}


def log(message):
    print(f"[monthly-imports] {message}", flush=True)


def _fetch_json(url, timeout=180):
    request = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def download(name, refresh=False):
    """Download complete monthly customs imports and persist the raw table."""
    spec = COMMODITIES[name]
    os.makedirs(DATA, exist_ok=True)
    path = os.path.join(DATA, f"china_{name}_imports_monthly.csv")
    if os.path.exists(path) and not refresh:
        return pd.read_csv(path, parse_dates=["date"])

    rows = []
    # Five calendar years per request keeps URLs short while avoiding 26
    # separate upstream calls.  The Worker and Comtrade both accept a
    # comma-separated list of YYYYMM periods.
    years = list(range(START_YEAR, END_YEAR + 1))
    for start in range(0, len(years), 5):
        block = years[start:start + 5]
        periods = ",".join(f"{year}{month:02d}"
                           for year in block for month in range(1, 13))
        url = (f"{PROXY}?hs={spec['hs']}&reporters={CHINA}&partners={WORLD}"
               f"&freq=M&period={periods}")
        log(f"  download {name}: {block[0]}-{block[-1]}")
        body = _fetch_json(url)
        for row in body.get("data", []):
            if row.get("flowCode") != "M":
                continue
            period = str(row.get("period", ""))
            if len(period) != 6:
                continue
            weight = row.get("netWgt")
            if weight is None:
                continue
            rows.append({
                "date": f"{period[:4]}-{period[4:]}-01",
                "year": int(period[:4]),
                "month": int(period[4:]),
                # netWgt is kg; 1 thousand metric tonnes is 1e6 kg.
                "imports_kt": float(weight) / 1_000_000.0,
                "trade_value_usd": (float(row["primaryValue"])
                                    if row.get("primaryValue") is not None
                                    else np.nan),
                "source": "UN Comtrade via project Cloudflare Worker",
                "reporter_m49": CHINA,
                "partner_m49": WORLD,
                "hs_code": spec["hs"],
            })

    if not rows:
        raise RuntimeError(f"Comtrade returned no monthly rows for {name}")

    frame = (pd.DataFrame(rows)
             .drop_duplicates("date", keep="last")
             .sort_values("date").reset_index(drop=True))
    frame["date"] = pd.to_datetime(frame.date)

    # Missing months are not silently converted to zero.  No row can mean no
    # trade, but it can also mean an upstream omission; the distinction matters
    # enormously after log transformation.  Keep NA and report completeness.
    full = pd.DataFrame({"date": pd.date_range(f"{START_YEAR}-01-01",
                                                f"{END_YEAR}-12-01", freq="MS")})
    full = full.merge(frame, on="date", how="left")
    full["year"] = full.date.dt.year
    full["month"] = full.date.dt.month
    missing = int(full.imports_kt.isna().sum())
    full.to_csv(path, index=False)
    log(f"  stored {len(full) - missing}/{len(full)} observed months -> {path}")
    if missing:
        log(f"  WARNING: {missing} months have no customs observation; they remain NA")
    return full


def _seasonal_design(t, month):
    """Linear time trend plus 11 month dummies (January is the reference)."""
    month = np.asarray(month, dtype=int)
    dummies = np.column_stack([(month == m).astype(float) for m in range(2, 13)])
    return np.column_stack([np.ones(len(month)), np.asarray(t, float), dummies])


def _fit_seasonal_trend(t, month, y):
    design = _seasonal_design(t, month)
    return np.linalg.lstsq(design, np.log1p(y), rcond=None)[0]


def _predict_seasonal_trend(beta, t, month):
    design = _seasonal_design(np.atleast_1d(t), np.atleast_1d(month))
    return np.expm1(design @ beta)


def _feature_row(y, target_index, horizon):
    """Features known at target_index - horizon, never after that origin."""
    origin = target_index - horizon
    required = (list(range(origin - 5, origin + 1))
                + [origin - 12, target_index - 12,
                   target_index - 24, target_index - 36])
    if min(required) < 0 or any(not np.isfinite(y[i]) for i in required):
        return None
    known3 = y[origin - 2:origin + 1]
    known6 = y[origin - 5:origin + 1]
    return np.array([
        np.log1p(y[origin]),
        np.log1p(y[origin - 1]),
        np.log1p(y[origin - 2]),
        np.log1p(np.mean(known3)),
        np.log1p(np.mean(known6)),
        np.log1p(y[target_index - 12]),
        np.log1p(y[target_index - 24]),
        np.log1p(y[target_index - 36]),
        np.log1p(y[origin]) - np.log1p(y[origin - 12]),
    ], dtype=float)


FEATURES = [
    "last_known", "lag1_from_origin", "lag2_from_origin",
    "known_mean3", "known_mean6", "same_month_lag12",
    "same_month_lag24", "same_month_lag36", "known_yoy_change",
]


@dataclass
class FoldResult:
    date: str
    truth: float
    model: float
    seasonal_trend: float
    seasonal_naive: float
    seasonal_mean3: float


def forward_validate(frame, horizon):
    """Rolling-origin direct forecast with all preprocessing inside each fold."""
    frame = frame.sort_values("date").reset_index(drop=True)
    y = frame.imports_kt.to_numpy(dtype=float)
    t = np.arange(len(frame), dtype=float)
    months = frame.month.to_numpy(dtype=int)
    results = []

    for target in range(MIN_HISTORY + horizon, len(frame)):
        origin = target - horizon
        if not np.isfinite(y[target]):
            continue
        x_test = _feature_row(y, target, horizon)
        if x_test is None:
            continue

        observed = np.arange(origin + 1)
        observed = observed[np.isfinite(y[observed])]
        if len(observed) < MIN_HISTORY:
            continue
        beta = _fit_seasonal_trend(t[observed], months[observed], y[observed])
        base = float(_predict_seasonal_trend(beta, t[target], months[target])[0])

        train_x, train_r = [], []
        for j in observed:
            xj = _feature_row(y, int(j), horizon)
            if xj is None:
                continue
            fitted = float(_predict_seasonal_trend(beta, t[j], months[j])[0])
            train_x.append(xj)
            train_r.append(np.log1p(y[j]) - np.log1p(max(fitted, 0.0)))
        if len(train_x) < MIN_HISTORY - 36:
            continue

        train_x = np.asarray(train_x)
        scaler = StandardScaler().fit(train_x)
        model = RidgeCV(alphas=ALPHAS).fit(scaler.transform(train_x), train_r)
        residual = float(model.predict(scaler.transform(x_test.reshape(1, -1)))[0])
        prediction = max(0.0, float(np.expm1(np.log1p(max(base, 0.0)) + residual)))

        naive = y[target - 12] if target >= 12 else np.nan
        same_month = [y[target - k] for k in (12, 24, 36)
                      if target >= k and np.isfinite(y[target - k])]
        mean3 = float(np.mean(same_month)) if len(same_month) == 3 else np.nan
        if not np.isfinite(naive) or not np.isfinite(mean3):
            continue
        results.append(FoldResult(
            date=str(frame.date.iloc[target].date()), truth=float(y[target]),
            model=prediction, seasonal_trend=base,
            seasonal_naive=float(naive), seasonal_mean3=mean3,
        ))
    return pd.DataFrame([r.__dict__ for r in results])


def _metrics(truth, pred):
    truth, pred = np.asarray(truth), np.asarray(pred)
    return {
        "rmse": float(np.sqrt(np.mean((truth - pred) ** 2))),
        "mae": float(np.mean(np.abs(truth - pred))),
        "mape": float(np.mean(np.abs(truth - pred) / np.maximum(truth, 1.0))),
    }


def evaluate(folds, horizon):
    if folds.empty:
        raise RuntimeError(f"no valid {horizon}-month folds")
    truth = folds.truth.to_numpy()
    recent = folds.tail(min(RECENT_FOLDS, len(folds)))
    baselines = ("seasonal_trend", "seasonal_naive", "seasonal_mean3")
    validation = {}
    for name in ("model",) + baselines:
        validation[name] = _metrics(truth, folds[name])
        validation[name]["recent"] = _metrics(recent.truth, recent[name])

    # Compare with the strongest baseline, not whichever makes the model look
    # best.  Use RMSE for selection and require both RMSE and MAE improvement;
    # a few import spikes must not manufacture a win by themselves.
    best_name = min(baselines, key=lambda n: validation[n]["rmse"])
    best_recent = min(baselines, key=lambda n: validation[n]["recent"]["rmse"])
    skill = 1 - validation["model"]["rmse"] / validation[best_name]["rmse"]
    recent_skill = (1 - validation["model"]["recent"]["rmse"]
                    / validation[best_recent]["recent"]["rmse"])
    mae_skill = 1 - validation["model"]["mae"] / validation[best_name]["mae"]
    recent_mae_skill = (1 - validation["model"]["recent"]["mae"]
                        / validation[best_recent]["recent"]["mae"])
    usable = all(v > 0 for v in (skill, recent_skill, mae_skill, recent_mae_skill))
    return {
        "horizon_months": horizon,
        "n_folds": int(len(folds)),
        "fold_dates": [folds.date.iloc[0], folds.date.iloc[-1]],
        "best_baseline": best_name,
        "best_recent_baseline": best_recent,
        "skill_vs_best_baseline": float(skill),
        "recent_skill_vs_best_baseline": float(recent_skill),
        "mae_skill_vs_best_baseline": float(mae_skill),
        "recent_mae_skill_vs_best_baseline": float(recent_mae_skill),
        "usable": bool(usable),
        "validation": validation,
    }


def seasonality_summary(frame):
    """Descriptive seasonality only; never used as evidence of model skill."""
    observed = frame.dropna(subset=["imports_kt"]).copy()
    monthly = observed.groupby("month").imports_kt.mean()
    return {
        "monthly_mean_kt": {str(int(k)): float(v) for k, v in monthly.items()},
        "peak_month": int(monthly.idxmax()),
        "trough_month": int(monthly.idxmin()),
        "peak_to_trough_ratio": float(monthly.max() / max(monthly.min(), 1e-9)),
    }


def model_one(name, refresh=False):
    spec = COMMODITIES[name]
    frame = download(name, refresh=refresh)
    missing = int(frame.imports_kt.isna().sum())
    log(f"{spec['label']}: {len(frame) - missing} observed months, {missing} missing")
    seasonal = seasonality_summary(frame)
    log(f"  seasonality: peak month {seasonal['peak_month']}, trough month "
        f"{seasonal['trough_month']}, ratio {seasonal['peak_to_trough_ratio']:.2f}x")

    horizons = {}
    fold_dir = os.path.join(DATA, "validation")
    os.makedirs(fold_dir, exist_ok=True)
    for horizon in HORIZONS:
        folds = forward_validate(frame, horizon)
        folds.to_csv(os.path.join(fold_dir, f"{name}_h{horizon}_folds.csv"), index=False)
        result = evaluate(folds, horizon)
        horizons[str(horizon)] = result
        model_m = result["validation"]["model"]
        base_m = result["validation"][result["best_baseline"]]
        log(f"  h={horizon}: n={result['n_folds']} model RMSE {model_m['rmse']:,.0f} kt "
            f"vs {result['best_baseline']} {base_m['rmse']:,.0f} kt; "
            f"skill {result['skill_vs_best_baseline']:+.1%}, recent "
            f"{result['recent_skill_vs_best_baseline']:+.1%} -> "
            f"{'USABLE' if result['usable'] else 'NO SKILL'}")

    # The guide asks for a 3-6 month product, not a cherry-picked horizon.
    # Both direct horizons must pass all four improvement tests.
    usable = all(v["usable"] for v in horizons.values())
    artifact = {
        "key": f"import_{name}_monthly",
        "label": spec["label"],
        "source": "UN Comtrade monthly customs data via project Cloudflare Worker",
        "target_unit": "1000 MT",
        "data_path": f"data/monthly_imports/china_{name}_imports_monthly.csv",
        "period": [f"{START_YEAR}-01", f"{END_YEAR}-12"],
        "seasonality": seasonal,
        "features": FEATURES,
        "validation_design": (
            "Direct 3- and 6-month rolling-origin forecasts. Model predicts the "
            "residual above a log trend + month fixed effects baseline, refit "
            "inside every fold, and is compared with the strongest of that "
            "baseline, prior-year same month, and prior-three-year same-month mean."
        ),
        "usable": bool(usable),
        "verdict": ("usable at both 3- and 6-month horizons" if usable else
                    "monthly history does not beat strong seasonal baselines; stop"),
        "horizons": horizons,
    }
    os.makedirs(MODELS, exist_ok=True)
    with open(os.path.join(MODELS, f"import_{name}_monthly.json"), "w",
              encoding="utf-8") as handle:
        json.dump(artifact, handle, indent=2, ensure_ascii=False)
    return artifact


def main():
    refresh = "--refresh" in sys.argv
    names = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    names = names or list(COMMODITIES)
    artifacts = [model_one(name, refresh=refresh) for name in names]
    log("=" * 88)
    log(f"{'model':24} {'horizon':>7} {'folds':>6} {'skill':>9} "
        f"{'recent':>9} {'baseline':>18} verdict")
    log("-" * 88)
    for artifact in artifacts:
        for horizon, result in artifact["horizons"].items():
            log(f"{artifact['key']:24} {horizon + 'm':>7} {result['n_folds']:6d} "
                f"{result['skill_vs_best_baseline']:+8.1%} "
                f"{result['recent_skill_vs_best_baseline']:+8.1%} "
                f"{result['best_baseline']:>18} "
                f"{'usable' if result['usable'] else 'no skill'}")
    log("=" * 88)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
