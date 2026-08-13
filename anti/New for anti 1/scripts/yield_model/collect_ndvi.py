"""
Collect MODIS NDVI for the Corn Belt states, to test whether satellite
greenness adds anything to the weather-only yield model.

Source: ORNL DAAC MODIS/VIIRS Subset REST API (modis.ornl.gov/rst), product
MOD13Q1 -- 16-day composites at 250 m. No authentication, no key.

Caveats worth keeping in view when reading the result:
  - Coverage starts in 2000, so adding NDVI shortens the usable record from
    34 seasons to 26. That trade has to pay for itself, which is the point of
    the experiment.
  - The API caps a request at 10 composite dates, so this walks year by year.
  - The 40x40 km box around each state centroid is not a cropland mask: it
    averages whatever is there, including pasture, woodland and towns. That
    dilutes the crop signal and is a reason any measured gain is a floor
    rather than a ceiling.

Writes cache/ndvi_<STATE>.csv with one row per composite date.
"""

import json
import os
import sys
import time
import urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

RST = "https://modis.ornl.gov/rst/api/v1"
PRODUCT = "MOD13Q1"
BAND = "250m_16_days_NDVI"
BOX_KM = 20          # half-width; 20 gives a 40x40 km footprint
MAX_DATES = 10       # hard API limit per request
FILL = -3000         # MOD13Q1 fill value; valid NDVI is scaled by 1e-4

START_YEAR = 2000
END_YEAR = 2025

# Composites overlapping the northern growing season. Anything outside this
# is irrelevant to yield and would only cost requests.
SEASON_MONTHS = (5, 6, 7, 8, 9)

sys.path.insert(0, HERE)
from collect_us_cornbelt import STATES  # noqa: E402


def log(msg):
    print(f"[ndvi] {msg}", flush=True)


def get_json(url, attempts=3, timeout=180):
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json",
                                                       "User-Agent": "yield-model/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            if i == attempts - 1:
                raise
            log(f"  retry {i + 1} after {e}")
            time.sleep(15)


def available_dates(state):
    d = get_json(f"{RST}/{PRODUCT}/dates?latitude={state['lat']}&longitude={state['lon']}")
    rows = []
    for x in d["dates"]:
        cal = pd.Timestamp(x["calendar_date"])
        if START_YEAR <= cal.year <= END_YEAR and cal.month in SEASON_MONTHS:
            rows.append((x["modis_date"], cal))
    return rows


def fetch_state(state):
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, f"ndvi_{state['code']}.csv")
    if os.path.exists(cached):
        log(f"{state['code']}: cache")
        return pd.read_csv(cached, parse_dates=["date"])

    dates = available_dates(state)
    log(f"{state['code']}: {len(dates)} season composites {START_YEAR}-{END_YEAR}")

    rows = []
    for i in range(0, len(dates), MAX_DATES):
        batch = dates[i:i + MAX_DATES]
        url = (f"{RST}/{PRODUCT}/subset?latitude={state['lat']}&longitude={state['lon']}"
               f"&startDate={batch[0][0]}&endDate={batch[-1][0]}&band={BAND}"
               f"&kmAboveBelow={BOX_KM}&kmLeftRight={BOX_KM}")
        d = get_json(url)
        if not isinstance(d, dict) or "subset" not in d:
            log(f"  {state['code']} batch {i}: unexpected response, skipped")
            continue

        for rec in d["subset"]:
            vals = [v for v in rec["data"] if v > FILL]
            if not vals:
                continue
            rows.append({
                "date": pd.Timestamp(rec["calendar_date"]),
                "ndvi": sum(vals) / len(vals) * 1e-4,
                "n_pixels": len(vals),
            })
        time.sleep(1)  # public service, keep the rate civil

    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    df.to_csv(cached, index=False)
    log(f"{state['code']}: {len(df)} composites written")
    return df


def main():
    for st in STATES:
        fetch_state(st)
    return 0


if __name__ == "__main__":
    sys.exit(main())
