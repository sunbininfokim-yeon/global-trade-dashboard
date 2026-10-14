"""
Blend the NASS crop condition index into the US weather forecast.

Usage: python3 condition_blend.py [crop ...]     # backtest, writes the weights

The weather model and the condition index see different things. Weather
says what the season should have done to the crop; the weekly condition
ratings say what scouts actually see in the field (disease, hail, stand
problems, management). condition_backtest.py showed the index alone beats
the weather model for both wheats and cotton, and that the two are close
for corn and soybeans -- so neither should replace the other.

Method, per crop and NASS week:

  1. Forward-chain both models over the same years: the weather model at
     the in-season cutoff that week falls in (corn, soybeans) or with its
     full-season inputs (wheat, cotton -- generous to weather, so the index
     is if anything under-weighted), and yield ~ trend + b * CCI.
  2. Weight each by the inverse of its mean squared error over those years
     (Bates & Granger 1969). With this few years an "optimal" weight that
     also estimates the error correlation swings wildly; inverse-MSE is the
     robust choice and is scored here out of sample (each year's weight
     comes only from the years before it).
  3. The index only enters from weeks where its own backtest clears the
     dashboard's forecast bar (skill >= 0.20). Before that -- early June,
     or the fall ratings for next year's winter wheat -- it is noise and
     the blend would only dilute the weather model.

Writes us_condition_blend.json: per crop and week the weight live use
applies, the blend's backtested skill next to each model's on the same
years, the error ratio that rescales the interval, and the full-sample
condition fit. run_forecast.py calls apply() with the season's latest week.
"""

import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.preprocessing import StandardScaler

HERE = os.path.dirname(os.path.abspath(__file__))
COND = os.path.join(HERE, "us_crop_condition.csv")
COND_BT = os.path.join(HERE, "us_condition_backtest.json")
OUT = os.path.join(HERE, "us_condition_blend.json")

sys.path.insert(0, HERE)
from us_scenarios import CUTOFFS, FORECAST_SKILL, cutoff_doy, feature_month  # noqa: E402

ALPHAS = np.logspace(-2, 4, 40)   # same grid as train_us / train_wheat
MIN_TRAIN = 15                    # condition starts 1986, weather 1992
MIN_WEIGHT = 0.8                  # as condition_backtest
MIN_PAIRS = 5                     # earlier years needed to set a weight
MIN_SCORED = 10                   # scored years a week needs before live use
CROPS = ["corn", "soybeans", "winter_wheat", "spring_wheat", "cotton"]


def log(msg):
    print(f"[blend] {msg}", flush=True)


def _labels(crop):
    df = pd.read_csv(os.path.join(HERE, f"us_{crop}_training.csv"))
    return df.dropna(subset=["yield"]).sort_values("year").reset_index(drop=True)


def weather_backtest(crop):
    """Forward-chained weather predictions per test year, as the models run."""
    with open(os.path.join(HERE, f"us_{crop}_model.json"), encoding="utf-8") as f:
        model = json.load(f)
    df = _labels(crop)
    feats = model["features"]
    window = model.get("train_window_years")
    years, y, X = df.year.values, df["yield"].values, df[feats].astype(float).values
    scen = "inseason" in model
    months = np.array([feature_month(f) for f in feats]) if scen else None
    out = {}
    for i, ty in enumerate(years):
        tr = years < ty
        if window:
            tr &= years >= ty - window
        if tr.sum() < MIN_TRAIN:
            continue
        k, b = np.polyfit(years[tr], y[tr], 1)
        trend = k * ty + b
        sc = StandardScaler().fit(X[tr])
        m = RidgeCV(alphas=ALPHAS).fit(sc.transform(X[tr]), y[tr] - (k * years[tr] + b))
        rec = {"truth": float(y[i]), "trend": float(trend),
               "end": float(trend + m.predict(sc.transform(X[i:i + 1]))[0])}
        if scen:
            # The scenario engine: unknown months borrowed from each past year.
            for label, known in CUTOFFS:
                Xs = np.repeat(X[i:i + 1], tr.sum(), axis=0)
                unknown = ~np.isin(months, known)
                Xs[:, unknown] = X[tr][:, unknown]
                rec[label] = float(trend + m.predict(sc.transform(Xs)).mean())
        out[int(ty)] = rec
    return out, scen


def condition_fit(years, y, x):
    """yield ~ trend + b * CCI, the condition_backtest form."""
    k = np.polyfit(years, y, 1)
    b = np.polyfit(x, y - np.polyval(k, years), 1)
    return k, b


def weather_key(scen, doy):
    """Which weather prediction is comparable with a condition week."""
    if not scen:
        return "end"
    key = CUTOFFS[0][0]
    for label, _ in CUTOFFS:
        if cutoff_doy(label) <= doy:
            key = label
    return key


def backtest_crop(crop, cond, cond_skill):
    W, scen = weather_backtest(crop)
    lab = _labels(crop)[["year", "yield"]]
    c = cond[(cond.crop == crop) & (cond.weight_reporting >= MIN_WEIGHT)]
    out = {}
    for week, g in c.groupby("week"):
        df = g.merge(lab, on="year").sort_values("year")
        yrs, y, x = df.year.values, df["yield"].values, df.cci.values
        C = {}
        for i, ty in enumerate(yrs):
            tr = yrs < ty
            if tr.sum() < MIN_TRAIN:
                continue
            k, b = condition_fit(yrs[tr], y[tr], x[tr])
            C[int(ty)] = float(np.polyval(k, ty) + np.polyval(b, x[i]))
        doy = int(pd.to_datetime(g.week_ending).dt.dayofyear.median())
        key = weather_key(scen, doy)
        paired = sorted(set(W) & set(C))
        if len(paired) < MIN_PAIRS + 6:
            continue

        def mse(src, ys):
            return float(np.mean([(src(p) - W[p]["truth"]) ** 2 for p in ys]))

        wpred, cpred = (lambda p: W[p][key]), (lambda p: C[p])
        gated = cond_skill.get(int(week), -1.0) < FORECAST_SKILL
        rows = []
        for j, ty in enumerate(paired):
            prev = paired[:j]
            if len(prev) < MIN_PAIRS:
                continue
            mw, mc = mse(wpred, prev), mse(cpred, prev)
            wc = 0.0 if gated else mw / (mw + mc)
            rows.append((W[ty]["truth"], W[ty]["trend"], W[ty][key], C[ty],
                         wc * C[ty] + (1 - wc) * W[ty][key]))
        if len(rows) < 6:
            continue
        a = np.array(rows)
        # Late weeks that only recent seasons reach (harvest running long)
        # have too few years to set a weight on.
        gated = gated or len(a) < MIN_SCORED

        def rmse(col):
            return float(np.sqrt(np.mean((a[:, 0] - a[:, col]) ** 2)))

        base = rmse(1)
        mw, mc = mse(wpred, paired), mse(cpred, paired)
        k, b = condition_fit(yrs, y, x)
        out[int(week)] = {
            "typical_date": (pd.Timestamp("2001-01-01")
                             + pd.Timedelta(days=doy - 1)).strftime("%m-%d"),
            "weather_at": key,
            "weight_condition": 0.0 if gated else round(mw / (mw + mc), 3),
            "gated": gated,
            "skill_weather": round(1 - rmse(2) / base, 3),
            "skill_condition": round(1 - rmse(3) / base, 3),
            "skill_blend": round(1 - rmse(4) / base, 3),
            "error_ratio": round(rmse(4) / rmse(2), 3),
            "n_test": int(len(a)),
            "test_years": [int(paired[MIN_PAIRS]), int(paired[-1])],
            "fit": {"trend": [float(v) for v in k], "cci": [float(v) for v in b]},
        }
        r = out[int(week)]
        log(f"  {crop:13} wk{week:2d} ~{r['typical_date']}  weather {r['skill_weather']:+.2f}  "
            f"cond {r['skill_condition']:+.2f}  blend {r['skill_blend']:+.2f}  "
            f"w={r['weight_condition']:.2f}{'  (gated)' if gated else ''}")
    if out and os.environ.get("GITHUB_ACTIONS"):
        live = [v for v in out.values() if not v["gated"]]
        if live:
            best = max(live, key=lambda v: v["skill_blend"])
            print(f"::notice::{crop} blend: from {min(v['typical_date'] for v in live)}, "
                  f"best {best['typical_date']} {best['skill_blend']:+.2f} "
                  f"(weather {best['skill_weather']:+.2f}, condition "
                  f"{best['skill_condition']:+.2f}, n={best['n_test']})", flush=True)
    return out


def apply(crop, season, r):
    """Fold this season's latest condition week into a weather forecast r.

    Returns r unchanged when there is nothing to blend (no ratings yet this
    season, or the week is gated). Otherwise returns a copy with the point,
    ranges and percentiles moved and rescaled, and a "condition" block that
    says what went in.
    """
    if not (os.path.exists(OUT) and os.path.exists(COND)):
        return r
    with open(OUT, encoding="utf-8") as f:
        weeks = json.load(f).get("crops", {}).get(crop) or {}
    cond = pd.read_csv(COND)
    c = cond[(cond.crop == crop) & (cond.year == season)
             & (cond.weight_reporting >= MIN_WEIGHT)]
    if c.empty:
        return r
    # The most recent usable week. Once harvest runs past the weeks with a
    # long enough record, the last of those still carries the season's
    # condition -- it is the final reading, not a stale one. Sorted by date,
    # since winter wheat's fall ratings carry high week numbers.
    row = w = None
    for _, cand in c.sort_values("week_ending", ascending=False).iterrows():
        e = weeks.get(str(int(cand.week)))
        if e and not e["gated"] and e["weight_condition"] > 0:
            row, w = cand, e
            break
    if w is None:
        return r

    k, b = np.array(w["fit"]["trend"]), np.array(w["fit"]["cci"])
    cond_point = float(np.polyval(k, season) + np.polyval(b, row.cci))
    wc = w["weight_condition"]
    weather_point = r["point"]
    point = wc * cond_point + (1 - wc) * weather_point
    # The blend's own backtested error relative to weather alone, bounded so
    # a lucky backtest cannot shrink the band to nothing.
    scale = float(np.clip(w["error_ratio"], 0.6, 1.2))

    def move(v):
        return point + (v - weather_point) * scale

    out = dict(r)
    out["point"] = point
    out["weather_effect"] = point - r["trend"]
    out["range_68"] = [move(v) for v in r["range_68"]]
    out["range_95"] = [move(v) for v in r["range_95"]]
    if r.get("percentiles"):
        out["percentiles"] = {q: move(v) for q, v in r["percentiles"].items()}
    out["sigma"] = r["sigma"] * scale
    out["condition"] = {
        "week_ending": str(row.week_ending),
        "nass_week": int(row.week),
        "cci": round(float(row.cci), 1),
        "good_excellent_pct": round(float(row.ge_pct), 1),
        "weight": wc,
        "condition_point": round(cond_point, 1),
        "weather_point": round(weather_point, 1),
        "weather_effect_only": round(weather_point - r["trend"], 1),
        "skill_blend": w["skill_blend"],
        "skill_weather": w["skill_weather"],
        "skill_condition": w["skill_condition"],
        "n_test": w["n_test"],
        "test_years": w["test_years"],
    }
    return out


def main():
    for p in (COND, COND_BT):
        if not os.path.exists(p):
            raise SystemExit(f"{p} not found -- run crop_condition.py and condition_backtest.py")
    cond = pd.read_csv(COND)
    with open(COND_BT, encoding="utf-8") as f:
        bt = json.load(f)["crops"]
    crops = sys.argv[1:] or CROPS
    result = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            result = json.load(f).get("crops", {})
    for crop in crops:
        skill = {int(wk): v["skill_vs_trend"] for wk, v in (bt.get(crop) or {}).items()}
        result[crop] = backtest_crop(crop, cond, skill)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"method": "inverse-MSE blend of the weather model and yield ~ trend + b*CCI, "
                             "weights from earlier years only when scored; condition gated "
                             f"below skill {FORECAST_SKILL}",
                   "crops": result}, f, indent=2)
    log(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
