"""
Crop phenology from USDA NASS Crop Progress.

Two things come out of this:

1. Planting-delay anomaly. Thompson's Midwest work ties excess spring wetness
   to delayed planting and lower yield; the delay itself is the mechanism, so
   it is worth carrying as its own feature rather than inferring it from rain.

2. Phenology-aligned weather windows. The model currently reads heat over
   fixed calendar months, but what matters is heat *during pollination*, and
   pollination does not fall on the same date every year. In Iowa 2012, corn
   was 50% planted by 29 April -- weeks early -- so a fixed July window is
   looking at a different growth stage than it would in a late year.
   NASS reports PCT SILKING weekly, which dates pollination directly.

Progress is a percentage series by week; the date a stage "happens" is taken
as the week the series crosses 50%, linearly interpolated between the
bracketing weeks so the estimate isn't quantised to whole weeks.

Coverage is 1992- for all eight states and both stages, so unlike NDVI this
costs no training years.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
NASS_URL = "https://quickstats.nass.usda.gov/api/api_GET/"
CHUNK = 10  # NASS is fast only when the year range is bounded both sides

sys.path.insert(0, HERE)
from collect_us_cornbelt import STATES, START_YEAR, END_YEAR  # noqa: E402

# Stages worth dating, per crop. Silking is corn's pollination window and the
# single most yield-critical moment; soybeans have no directly comparable
# NASS stage, so only planting is used there.
STAGES = {
    "corn": {"commodity": "CORN", "planted": "PCT PLANTED", "critical": "PCT SILKING"},
    "soybeans": {"commodity": "SOYBEANS", "planted": "PCT PLANTED", "critical": None},
}


def log(msg):
    print(f"[pheno] {msg}", flush=True)


def get_json(url, attempts=3, timeout=300):
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            if i == attempts - 1:
                raise
            log(f"  retry {i + 1} after {e}")
            time.sleep(10)


def fetch_progress(crop, state):
    """Weekly progress percentages for one state, cached."""
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, f"progress_{crop}_{state['code']}.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached, parse_dates=["week_ending"])

    key = os.environ.get("USDA_NASS_API_KEY")
    if not key:
        raise SystemExit("USDA_NASS_API_KEY is not set")

    spec = STAGES[crop]
    wanted = {spec["planted"], spec["critical"]} - {None}

    rows = []
    for lo in range(START_YEAR, END_YEAR + 1, CHUNK):
        hi = min(lo + CHUNK - 1, END_YEAR)
        q = urllib.parse.urlencode({
            "key": key, "commodity_desc": spec["commodity"],
            "statisticcat_desc": "PROGRESS", "agg_level_desc": "STATE",
            "state_alpha": state["code"], "year__GE": str(lo), "year__LE": str(hi),
            "format": "JSON",
        })
        for r in get_json(NASS_URL + "?" + q).get("data", []):
            if r.get("unit_desc") not in wanted or not r.get("week_ending"):
                continue
            try:
                rows.append({
                    "week_ending": pd.Timestamp(r["week_ending"]),
                    "year": int(r["year"]),
                    "stage": r["unit_desc"],
                    "pct": float(r["Value"].replace(",", "")),
                })
            except (ValueError, KeyError):
                continue
        time.sleep(1)

    df = (pd.DataFrame(rows)
          .drop_duplicates(["year", "stage", "week_ending"])
          .sort_values(["stage", "week_ending"])
          .reset_index(drop=True))
    df.to_csv(cached, index=False)
    log(f"{crop}/{state['code']}: {len(df)} weekly records")
    return df


def crossing_doy(sub, threshold=50.0):
    """
    Day-of-year at which the progress series crosses `threshold`.

    Interpolates between the two bracketing weeks, so a stage that is 30% one
    week and 70% the next is dated mid-week rather than snapped to either end.
    """
    sub = sub.sort_values("week_ending")
    prev = None
    for _, row in sub.iterrows():
        if row.pct >= threshold:
            doy = row.week_ending.dayofyear
            if prev is not None and row.pct > prev[1]:
                frac = (threshold - prev[1]) / (row.pct - prev[1])
                doy = prev[0] + frac * (doy - prev[0])
            return float(doy)
        prev = (row.week_ending.dayofyear, row.pct)
    return np.nan


def stage_dates(crop, state):
    """Per-year day-of-year for 50% planted and 50% of the critical stage."""
    df = fetch_progress(crop, state)
    spec = STAGES[crop]

    out = {}
    for year in sorted(df.year.unique()):
        y = df[df.year == year]
        rec = {}
        p = y[y.stage == spec["planted"]]
        if not p.empty:
            rec["planted_doy"] = crossing_doy(p)
        if spec["critical"]:
            c = y[y.stage == spec["critical"]]
            if not c.empty:
                rec["critical_doy"] = crossing_doy(c)
        if rec:
            out[int(year)] = rec
    return out


def critical_window(crop, state, year, half_width_days=14):
    """
    Dates bracketing the yield-critical stage, for aligning weather windows.

    Corn: +/- half_width around 50% silking. Soybeans have no equivalent NASS
    stage, so the window is anchored to planting plus a typical interval to
    pod set.
    """
    dates = stage_dates(crop, state)
    rec = dates.get(year)
    if not rec:
        return None

    if crop == "corn" and not pd.isna(rec.get("critical_doy", np.nan)):
        centre = rec["critical_doy"]
    elif not pd.isna(rec.get("planted_doy", np.nan)):
        # Soybeans reach pod fill roughly 90 days after planting.
        centre = rec["planted_doy"] + 90
    else:
        return None

    start = pd.Timestamp(f"{year}-01-01") + pd.Timedelta(days=centre - half_width_days - 1)
    end = pd.Timestamp(f"{year}-01-01") + pd.Timedelta(days=centre + half_width_days - 1)
    return start, end, centre


def main():
    for crop in ("corn", "soybeans"):
        log(f"=== {crop} ===")
        for st in STATES:
            d = stage_dates(crop, st)
            yrs = sorted(d)
            if not yrs:
                log(f"  {st['code']}: none")
                continue
            planted = [d[y]["planted_doy"] for y in yrs if not pd.isna(d[y].get("planted_doy", np.nan))]
            crit = [d[y]["critical_doy"] for y in yrs if not pd.isna(d[y].get("critical_doy", np.nan))]
            msg = (f"  {st['code']}: {len(yrs)} years, "
                   f"50% planted doy {np.mean(planted):.0f}+/-{np.std(planted):.0f}")
            if crit:
                msg += f", 50% silking doy {np.mean(crit):.0f}+/-{np.std(crit):.0f}"
            log(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
