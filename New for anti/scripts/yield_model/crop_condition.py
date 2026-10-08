"""
Weekly crop condition for the US regions, from USDA NASS Crop Progress.

Usage: python3 crop_condition.py [crop ...]

Every week from spring to harvest NASS asks county extension staff and
farmers to rate each state's crop as very poor / poor / fair / good /
excellent. Those ratings see what weather alone cannot -- disease, hail,
stand problems, management -- and they are what the established in-season
models run on:

  - K-State's Kansas winter wheat model: a crop condition index (CCI) with
    weights excellent 1.0, good 0.75, fair 0.5, poor 0.25, very poor 0,
    regressed against the yield deviation from trend.
  - farmdoc (Irwin & Good): the same kind of index for corn and soybeans,
    about 5-6% RMSPE from late July; simple index models did as well as
    elaborate ones.

This module only collects. It writes one committed table,
us_crop_condition.csv, with one row per crop, year and NASS week:
the production-weighted CCI across the region's states, the good+excellent
share, and how many of the states reported that week. The weights are the
ones the weather models already use, so the condition index describes the
same region as the yield it is compared with.

Raw NASS responses are cached under cache/ (not committed).
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
OUT = os.path.join(HERE, "us_crop_condition.csv")
NASS_URL = "https://quickstats.nass.usda.gov/api/api_GET/"
CHUNK = 10
START_YEAR = 1986   # first year NASS publishes weekly condition by state
END_YEAR = 2026

sys.path.insert(0, HERE)
from collect_us_cornbelt import STATES as CORN_BELT  # noqa: E402
from collect_us_south import CROPS as SOUTH  # noqa: E402
from collect_us_wheat import CROPS as WHEAT  # noqa: E402

CROPS = {
    "corn": {"commodity": "CORN", "class_desc": None, "states": CORN_BELT},
    "soybeans": {"commodity": "SOYBEANS", "class_desc": None, "states": CORN_BELT},
    "winter_wheat": {"commodity": "WHEAT", "class_desc": "WINTER",
                     "states": WHEAT["winter_wheat"]["states"]},
    "spring_wheat": {"commodity": "WHEAT", "class_desc": "SPRING, (EXCL DURUM)",
                     "states": WHEAT["spring_wheat"]["states"]},
    "cotton": {"commodity": "COTTON", "class_desc": "UPLAND",
               "states": SOUTH["cotton"]["states"]},
}

# K-State weights. Good + excellent is carried as well because farmdoc and
# the trade quote that share.
RATINGS = {"PCT EXCELLENT": 1.0, "PCT GOOD": 0.75, "PCT FAIR": 0.5,
           "PCT POOR": 0.25, "PCT VERY POOR": 0.0}


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
    print(f"[condition] {msg}", flush=True)


def annotate(level, msg):
    """GitHub Actions annotation: readable from the check run even when the
    raw job log is not (the log store sits behind a different host)."""
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::{level}::{msg}", flush=True)


def get_json(url, attempts=3, timeout=120):
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


def fetch_state(crop, code):
    """Weekly rating percentages for one crop and state, cached."""
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, f"condition_{crop}_{code}.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached, parse_dates=["week_ending"])

    key = os.environ.get("USDA_NASS_API_KEY")
    if not key:
        raise SystemExit("USDA_NASS_API_KEY is not set")

    spec = CROPS[crop]
    rows = []
    for lo in range(START_YEAR, END_YEAR + 1, CHUNK):
        hi = min(lo + CHUNK - 1, END_YEAR)
        params = {"key": key, "commodity_desc": spec["commodity"],
                  "statisticcat_desc": "CONDITION", "agg_level_desc": "STATE",
                  "freq_desc": "WEEKLY", "source_desc": "SURVEY",
                  "state_alpha": code, "year__GE": str(lo), "year__LE": str(hi),
                  "format": "JSON"}
        if spec["class_desc"]:
            params["class_desc"] = spec["class_desc"]
        try:
            data = get_json(NASS_URL + "?" + urllib.parse.urlencode(params))
        except Exception as e:  # noqa: BLE001
            # NASS answers 400 when a chunk has no rows (e.g. a state that
            # stopped growing the crop); that is a gap, not a failure.
            log(f"  {crop}/{code} {lo}-{hi}: {e}")
            annotate("warning", f"{crop}/{code} {lo}-{hi}: {str(e)[:200]}")
            continue
        for r in data.get("data", []):
            unit = r.get("unit_desc")
            if unit not in RATINGS or not r.get("week_ending"):
                continue
            try:
                rows.append({"year": int(r["year"]),
                             "week": int(r["reference_period_desc"].split("#")[1]),
                             "week_ending": pd.Timestamp(r["week_ending"]),
                             "rating": unit,
                             "pct": float(r["Value"].replace(",", ""))})
            except (ValueError, KeyError, IndexError):
                continue
        time.sleep(1)

    df = pd.DataFrame(rows, columns=["year", "week", "week_ending", "rating", "pct"])
    df = df.drop_duplicates(["year", "week", "rating"]).sort_values(["year", "week"])
    df.to_csv(cached, index=False)
    log(f"{crop}/{code}: {df[['year', 'week']].drop_duplicates().shape[0]} state-weeks")
    return df


def state_index(df):
    """CCI and good+excellent share per week from the five rating rows."""
    wide = df.pivot_table(index=["year", "week", "week_ending"], columns="rating",
                          values="pct", aggfunc="first").reset_index()
    have = [c for c in RATINGS if c in wide.columns]
    total = wide[have].sum(axis=1)
    # A week whose shares don't add to ~100 is a partial release; skip it.
    wide = wide[(total > 95) & (total < 105)].copy()
    total = wide[have].sum(axis=1)
    wide["cci"] = sum(wide[c] * RATINGS[c] for c in have) / total * 100
    ge = [c for c in ("PCT EXCELLENT", "PCT GOOD") if c in wide.columns]
    wide["ge_pct"] = wide[ge].sum(axis=1) / total * 100
    return wide[["year", "week", "week_ending", "cci", "ge_pct"]]


def region_index(crop):
    """Production-weighted CCI across the region's states, per NASS week."""
    parts = []
    for st in CROPS[crop]["states"]:
        raw = fetch_state(crop, st["code"])
        if raw.empty:
            continue
        s = state_index(raw)
        s["weight"] = st["weight"]
        parts.append(s)
    if not parts:
        return pd.DataFrame()
    df = pd.concat(parts, ignore_index=True)
    total_w = sum(st["weight"] for st in CROPS[crop]["states"])

    def agg(g):
        w = g.weight / g.weight.sum()
        return pd.Series({"week_ending": g.week_ending.max(),
                          "cci": float((g.cci * w).sum()),
                          "ge_pct": float((g.ge_pct * w).sum()),
                          "weight_reporting": float(g.weight.sum() / total_w),
                          "states_reporting": int(len(g))})

    out = df.groupby(["year", "week"]).apply(agg, include_groups=False).reset_index()
    out.insert(0, "crop", crop)
    return out


def main():
    crops = sys.argv[1:] or list(CROPS)
    frames = []
    for crop in crops:
        try:
            r = region_index(crop)
        except Exception as e:  # noqa: BLE001
            # One crop failing must not cost the others their data.
            annotate("error", f"{crop}: {type(e).__name__}: {str(e)[:300]}")
            log(f"{crop}: failed: {e}")
            continue
        if r.empty:
            log(f"{crop}: no condition data")
            continue
        log(f"{crop}: {r.year.min()}-{r.year.max()}, {len(r)} region-weeks")
        annotate("notice", f"{crop}: {r.year.min()}-{r.year.max()}, {len(r)} region-weeks")
        frames.append(r)
    if not frames:
        return 1

    new = pd.concat(frames, ignore_index=True)
    if os.path.exists(OUT):
        # Keep crops that were not refreshed this run.
        old = pd.read_csv(OUT)
        new = pd.concat([old[~old.crop.isin(new.crop.unique())], new], ignore_index=True)
    new = new.sort_values(["crop", "year", "week"])
    new["week_ending"] = pd.to_datetime(new.week_ending).dt.date
    new.round(2).to_csv(OUT, index=False)
    log(f"wrote {OUT} ({len(new)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
