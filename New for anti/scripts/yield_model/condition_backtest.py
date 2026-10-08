"""
How much the NASS condition index says about yield, week by week.

Usage: python3 condition_backtest.py [crop ...]

For each crop and NASS week, regress the yield deviation from trend on the
region's crop condition index (CCI) that week -- the K-State / farmdoc form,
one variable -- and score it out of sample by forward chaining (train on
years before Y, predict Y, trend refit inside the fold), against trend-only.
The result says from which week the condition index earns a place in the
forecast, crop by crop; it is the evidence the blend with the weather model
will be built on, so nothing here is used for a forecast yet.

Reads us_crop_condition.csv (crop_condition.py) and us_{crop}_training.csv.
Writes us_condition_backtest.json.
"""

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
COND = os.path.join(HERE, "us_crop_condition.csv")
OUT = os.path.join(HERE, "us_condition_backtest.json")
MIN_TRAIN = 15        # condition starts in 1986; keeps the test span 2001-
MIN_WEIGHT = 0.8      # skip weeks where states covering <80% of the region report


def _annotate_crash(kind, value, tb):
    """Surface an uncaught error as an Actions annotation, then fail as usual."""
    import traceback
    if os.environ.get("GITHUB_ACTIONS"):
        last = traceback.extract_tb(tb)[-1] if tb else None
        where = f" at {os.path.basename(last.filename)}:{last.lineno}" if last else ""
        print(f"::error::{kind.__name__}{where}: {str(value)[:300]}", flush=True)
    sys.__excepthook__(kind, value, tb)


sys.excepthook = _annotate_crash


def log(msg):
    print(f"[cond-bt] {msg}", flush=True)


def backtest_week(df):
    """Forward-chained skill of yield ~ trend + b * CCI for one week."""
    years, y, x = df.year.values, df["yield"].values, df.cci.values
    truth, pred, base = [], [], []
    for i, ty in enumerate(years):
        tr = years < ty
        if tr.sum() < MIN_TRAIN:
            continue
        c = np.polyfit(years[tr], y[tr], 1)
        resid = y[tr] - np.polyval(c, years[tr])
        b = np.polyfit(x[tr], resid, 1)
        t = np.polyval(c, ty)
        truth.append(y[i])
        base.append(t)
        pred.append(t + np.polyval(b, x[i]))
    if len(truth) < 8:
        return None
    truth, pred, base = map(np.array, (truth, pred, base))
    rmse = float(np.sqrt(np.mean((truth - pred) ** 2)))
    brmse = float(np.sqrt(np.mean((truth - base) ** 2)))
    return {"skill_vs_trend": 1 - rmse / brmse, "rmse": rmse,
            "baseline_rmse": brmse, "n_test": int(len(truth))}


def run(crop, cond):
    lab = pd.read_csv(os.path.join(HERE, f"us_{crop}_training.csv"))
    lab = lab.dropna(subset=["yield"])[["year", "yield"]]
    c = cond[(cond.crop == crop) & (cond.weight_reporting >= MIN_WEIGHT)]
    out = {}
    for week, g in c.groupby("week"):
        df = g.merge(lab, on="year").sort_values("year")
        r = backtest_week(df)
        if r is None:
            continue
        # A typical calendar date for the week, so the table reads as dates.
        doy = int(pd.to_datetime(g.week_ending).dt.dayofyear.median())
        r["typical_date"] = (pd.Timestamp("2001-01-01") + pd.Timedelta(days=doy - 1)).strftime("%m-%d")
        out[int(week)] = r
        log(f"  {crop:13} week {week:2d} (~{r['typical_date']}): "
            f"skill={r['skill_vs_trend']:+6.1%}  n={r['n_test']}")
    if out and os.environ.get("GITHUB_ACTIONS"):
        # One annotation per crop so the result is readable from the check run.
        cells = " ".join(f"{v['typical_date']}:{v['skill_vs_trend']:+.2f}"
                         for _, v in sorted(out.items()))
        print(f"::notice::{crop} skill by week (n={next(iter(out.values()))['n_test']}): {cells}",
              flush=True)
    return out


def main():
    if not os.path.exists(COND):
        raise SystemExit(f"{COND} not found -- run crop_condition.py first")
    cond = pd.read_csv(COND)
    crops = sys.argv[1:] or sorted(cond.crop.unique())
    result = {crop: run(crop, cond) for crop in crops}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"method": "forward chaining, yield ~ trend + b*CCI per NASS week, "
                             f"min {MIN_TRAIN} training years",
                   "crops": result}, f, indent=2)
    log(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
