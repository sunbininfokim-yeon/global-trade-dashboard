"""
Planting dates and cotton area components for the US regions, from NASS.

Usage: python3 crop_progress.py

Two gaps the weather models cannot see on their own (10_미국_개선안 7장):

  - Spring wheat: when the crop went in. A late-planted crop heads into
    July heat, an early one escapes it (Lanning et al. 2010 -- the reason
    the spring wheat model needs a rolling window at all). NASS's weekly
    Crop Progress gives the share planted by week; the day the region
    reached 50% is the planting date the literature uses.

  - Cotton: the label is yield per PLANTED acre, which mixes two processes
    with different weather drivers -- how much of the crop was abandoned
    (pre-plant moisture, early summer drought on Texas dryland) and how
    much the surviving fields produced (flowering-time soil moisture, heat).
    NASS publishes planted area, harvested area and yield per harvested
    acre separately, so the two can be modelled apart and multiplied back.

Writes two committed tables:
  us_planting_dates.csv   crop, year, doy_50pct, states_reporting, weight_reporting
  us_cotton_components.csv year, planted_acres, harvested_acres, harvest_ratio,
                           yield_harvested, yield_planted  (region, production-weighted)

Raw NASS responses are cached under cache/ (not committed).
"""

import os
import sys
import time
import urllib.parse

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
OUT_PLANT = os.path.join(HERE, "us_planting_dates.csv")
OUT_COTTON = os.path.join(HERE, "us_cotton_components.csv")
START_YEAR = 1980
END_YEAR = 2026
CHUNK = 10

sys.path.insert(0, HERE)
from crop_condition import (CROPS as COND_CROPS, NASS_URL, Throttled,  # noqa: E402
                            annotate, get_json, log, nass_key)

# Planting progress is published under the same commodity / class as the
# condition ratings.
PLANTING = {c: COND_CROPS[c] for c in ("spring_wheat", "corn", "soybeans", "cotton")}


def _fetch(params, cached):
    """All rows for one NASS query across the year range, cached as CSV."""
    os.makedirs(CACHE, exist_ok=True)
    if os.path.exists(cached):
        return pd.read_csv(cached)
    rows = []
    for lo in range(START_YEAR, END_YEAR + 1, CHUNK):
        hi = min(lo + CHUNK - 1, END_YEAR)
        q = {"key": nass_key(), **params, "year__GE": str(lo), "year__LE": str(hi),
             "format": "JSON"}
        try:
            data = get_json(NASS_URL + "?" + urllib.parse.urlencode(q))
        except Throttled:
            raise
        except Exception as e:  # noqa: BLE001
            # 400 = no rows in that span (crop not reported yet); a gap.
            log(f"  {params.get('state_alpha')} {lo}-{hi}: {e}")
            continue
        rows.extend(data.get("data", []))
        time.sleep(2)
    df = pd.DataFrame(rows)
    df.to_csv(cached, index=False)
    return df


def _value(v):
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return np.nan   # (D) withheld, (NA), (Z) ...


def planting_state(crop, code):
    spec = PLANTING[crop]
    params = {"commodity_desc": spec["commodity"], "statisticcat_desc": "PROGRESS",
              "unit_desc": "PCT PLANTED", "agg_level_desc": "STATE",
              "freq_desc": "WEEKLY", "source_desc": "SURVEY", "state_alpha": code}
    if spec["class_desc"]:
        params["class_desc"] = spec["class_desc"]
    df = _fetch(params, os.path.join(CACHE, f"planted_{crop}_{code}.csv"))
    if df.empty or "week_ending" not in df:
        return pd.DataFrame(columns=["year", "doy_50pct"])
    df = df.assign(year=df.year.astype(int), pct=df.Value.map(_value),
                   date=pd.to_datetime(df.week_ending, errors="coerce"))
    df = df.dropna(subset=["pct", "date"]).drop_duplicates(["year", "date"])
    out = []
    for year, g in df.groupby("year"):
        g = g.sort_values("date")
        doy = g.date.dt.dayofyear.values.astype(float)
        pct = np.maximum.accumulate(g.pct.values)
        if pct.max() < 50 or pct.min() > 50:
            continue   # the 50% crossing is outside the published weeks
        # Linear between the two weeks either side of 50%.
        out.append({"year": int(year), "doy_50pct": float(np.interp(50, pct, doy))})
    return pd.DataFrame(out)


def planting_dates(crop):
    states = PLANTING[crop]["states"]
    total_w = sum(s["weight"] for s in states)
    parts = []
    for st in states:
        d = planting_state(crop, st["code"])
        if not d.empty:
            parts.append(d.assign(weight=st["weight"]))
    if not parts:
        return pd.DataFrame()
    df = pd.concat(parts)
    out = df.groupby("year").apply(
        lambda g: pd.Series({"doy_50pct": float(np.average(g.doy_50pct, weights=g.weight)),
                             "states_reporting": int(len(g)),
                             "weight_reporting": float(g.weight.sum() / total_w)}),
        include_groups=False).reset_index()
    out.insert(0, "crop", crop)
    return out


def cotton_components():
    """Region planted / harvested area and both yields, by year."""
    states = COND_CROPS["cotton"]["states"]
    descs = {"planted": "COTTON, UPLAND - ACRES PLANTED",
             "harvested": "COTTON, UPLAND - ACRES HARVESTED",
             "yield_harvested": "COTTON, UPLAND - YIELD, MEASURED IN LB / ACRE"}
    per_state = []
    for st in states:
        cols = {}
        for key, desc in descs.items():
            df = _fetch({"short_desc": desc, "agg_level_desc": "STATE",
                         "freq_desc": "ANNUAL", "reference_period_desc": "YEAR",
                         "source_desc": "SURVEY", "state_alpha": st["code"]},
                        os.path.join(CACHE, f"cotton_{key}_{st['code']}.csv"))
            if df.empty:
                continue
            df = df.assign(year=df.year.astype(int), v=df.Value.map(_value))
            cols[key] = df.dropna(subset=["v"]).drop_duplicates("year").set_index("year").v
        if len(cols) == 3:
            per_state.append(pd.DataFrame(cols).dropna().assign(weight=st["weight"]))
    if not per_state:
        return pd.DataFrame()
    df = pd.concat(per_state).reset_index()

    def agg(g):
        # Region yield per planted acre weighted as the training label is:
        # production weights on each state's own per-planted-acre yield.
        w = g.weight / g.weight.sum()
        ratio = g.harvested / g.planted
        return pd.Series({
            "planted_acres": float(g.planted.sum()),
            "harvested_acres": float(g.harvested.sum()),
            "harvest_ratio": float((ratio * w).sum()),
            "yield_harvested": float((g.yield_harvested * w).sum()),
            "yield_planted": float((g.yield_harvested * ratio * w).sum()),
            "states_reporting": int(len(g)),
        })

    return df.groupby("year").apply(agg, include_groups=False).reset_index()


def main():
    frames = []
    for crop in PLANTING:
        try:
            d = planting_dates(crop)
        except Exception as e:  # noqa: BLE001
            annotate("error", f"planting {crop}: {type(e).__name__}: {str(e)[:300]}")
            continue
        if d.empty:
            annotate("warning", f"planting {crop}: no data")
            continue
        annotate("notice", f"planting {crop}: {d.year.min()}-{d.year.max()}, "
                           f"median 50% date doy {d.doy_50pct.median():.0f}")
        frames.append(d)
    if frames:
        pd.concat(frames).round(3).to_csv(OUT_PLANT, index=False)
        log(f"wrote {OUT_PLANT}")

    try:
        c = cotton_components()
    except Exception as e:  # noqa: BLE001
        annotate("error", f"cotton components: {type(e).__name__}: {str(e)[:300]}")
        c = pd.DataFrame()
    if not c.empty:
        c.round(4).to_csv(OUT_COTTON, index=False)
        annotate("notice", f"cotton components: {c.year.min()}-{c.year.max()}, "
                           f"harvest ratio {c.harvest_ratio.min():.2f}-{c.harvest_ratio.max():.2f}")
        log(f"wrote {OUT_COTTON}")
    return 0 if frames or not c.empty else 1


if __name__ == "__main__":
    sys.exit(main())
