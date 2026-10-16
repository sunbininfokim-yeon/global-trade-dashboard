"""
MODIS NDVI at the Argentine weather points -- the in-season crop-condition
channel the weather models lack.

Usage: python3 -m argentina.ndvi            # append new composites
       python3 -m argentina.ndvi --full     # rebuild from 2000

Why satellite and not the Bolsa de Cereales weekly condition ratings: the
BCBA history files sit behind a Cloudflare browser challenge that blocks
Actions and people alike, and the pipeline has to run unattended. MOD13Q1
needs no key and the ORNL DAAC REST API answers from Actions.

Source: ORNL DAAC MODIS/VIIRS Subset REST API (modis.ornl.gov/rst), MOD13Q1,
16-day composites at 250 m, February 2000 onward.

Each point is a BOX_KM box around the station. Per composite the box is
reduced to the median and the 75th percentile of its valid pixels. The
pixel-reliability band is not requested: it doubles the calls, and MOD13Q1
is already a 16-day maximum-value composite, which keeps the greenest
cloud-free look at each pixel. There is no land-cover mask: in the
Pampas the box is overwhelmingly cropland and the median ignores the town at
its centre, while the 75th percentile leans further toward the greenest
fields. In the Chaco and NOA boxes forest and scrub share the footprint, so
there the signal is diluted -- a reason to read any measured skill there as
a floor.

Writes condition/ndvi_points.csv: one row per point per composite.
"""

import argparse
import json
import os
import time
from datetime import datetime
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from .regions import ALL

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "condition", "ndvi_points.csv")

RST = "https://modis.ornl.gov/rst/api/v1"
PRODUCT = "MOD13Q1"
BAND_NDVI = "250m_16_days_NDVI"
BOX_KM = 2            # half-width: a ~4x4 km footprint, ~17x17 pixels
MAX_DATES = 10        # API limit per request
SCALE = 1e-4
VALID_MIN = -2000     # MOD13Q1 fill is -3000; valid NDVI is -2000..10000
# Composites from May through July serve no crop window (wheat starts in
# August, the summer crops end in April), so they are not requested.
SKIP_MONTHS = (5, 6, 7)
WORKERS = 6
# Stop requesting after this many minutes and write what has arrived, so a slow
# API day costs one run's tail instead of the whole run (the job is killed at
# its timeout before the commit step). The next run picks up where this left.
BUDGET_MIN = float(os.environ.get("NDVI_BUDGET_MIN", "200"))
_T0 = time.monotonic()


def log(msg):
    print(f"[ar-ndvi] {msg}", flush=True)


def get_json(url, attempts=4, timeout=180):
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json",
                                                       "User-Agent": "yield-model/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001 -- retried, then re-raised
            if i == attempts - 1:
                raise
            log(f"retry {i + 1} after {e}")
            time.sleep(30 * 2 ** i)    # ORNL answers 502 when busy


def points():
    """Unique weather points across every region, keyed by name."""
    seen = {}
    for rc in ALL:
        for p in rc.points:
            seen.setdefault(p["name"], (p["lat"], p["lon"]))
    return seen


def dates(lat, lon):
    js = get_json(f"{RST}/{PRODUCT}/dates?latitude={lat}&longitude={lon}")
    return [d["modis_date"] for d in js["dates"]]


def subset(lat, lon, band, start, end):
    url = (f"{RST}/{PRODUCT}/subset?latitude={lat}&longitude={lon}&band={band}"
           f"&startDate={start}&endDate={end}"
           f"&kmAboveBelow={BOX_KM}&kmLeftRight={BOX_KM}")
    js = get_json(url)
    return {s["modis_date"]: (s["calendar_date"], np.asarray(s["data"], float))
            for s in js["subset"]}


def reduce(ndvi):
    ok = ndvi > VALID_MIN
    n = int(ok.sum())
    if n == 0:
        return None, None, 0, len(ndvi)
    v = ndvi[ok] * SCALE
    return float(np.median(v)), float(np.percentile(v, 75)), n, len(ndvi)


def collect_point(name, lat, lon, have, skip=SKIP_MONTHS):
    # The API takes a start and end date, not a list, so chunks are cut from
    # the full composite calendar (at most MAX_DATES per range) and then
    # trimmed to the wanted dates inside each.
    every = dates(lat, lon)
    want = {d for d in every if d not in have
            and datetime.strptime(d[1:], "%Y%j").month not in skip}
    chunks = []
    for i in range(0, len(every), MAX_DATES):
        c = [d for d in every[i:i + MAX_DATES] if d in want]
        if c:
            chunks.append(c)
    rows = []
    for i, chunk in enumerate(chunks):
        if time.monotonic() - _T0 > BUDGET_MIN * 60:
            log(f"{name}: time budget reached, {len(chunks) - i} requests left")
            break
        nd = subset(lat, lon, BAND_NDVI, chunk[0], chunk[-1])
        for md, (cal, v) in nd.items():
            if md not in want:
                continue
            med, p75, n, tot = reduce(v)
            rows.append({"point": name, "modis_date": md, "date": cal,
                         "ndvi_median": med, "ndvi_p75": p75,
                         "n_good": n, "n_pixels": tot})
    log(f"{name}: {len(rows)} new composites")
    return rows


def main(pts=None, out_path=OUT, skip=SKIP_MONTHS):
    """Also the entry point for other countries (russia.ndvi): their own
    points, output file and off-season months, the same collection."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()

    old = pd.DataFrame()
    if os.path.exists(out_path) and not args.full:
        old = pd.read_csv(out_path, dtype={"modis_date": str})
    pts = pts or points()
    log(f"{len(pts)} points, box ±{BOX_KM} km")

    def job(item):
        name, (lat, lon) = item
        have = set(old.loc[old.point == name, "modis_date"]) if len(old) else set()
        return collect_point(name, lat, lon, have, skip)

    with ThreadPoolExecutor(WORKERS) as ex:
        new = [r for rows in ex.map(job, pts.items()) for r in rows]

    out = pd.concat([old, pd.DataFrame(new)], ignore_index=True)
    out = (out.drop_duplicates(["point", "modis_date"], keep="last")
              .sort_values(["point", "modis_date"]))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    for c in ("ndvi_median", "ndvi_p75"):
        out[c] = out[c].round(4)
    out.to_csv(out_path, index=False)
    log(f"wrote {len(out)} rows ({len(new)} new) -> {out_path}")


if __name__ == "__main__":
    main()
