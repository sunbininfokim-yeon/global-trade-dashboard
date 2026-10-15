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
reduced to the median and the 75th percentile of pixels flagged good or
marginal by the pixel-reliability band. There is no land-cover mask: in the
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
BAND_REL = "250m_16_days_pixel_reliability"
BOX_KM = 3            # half-width: a ~6x6 km footprint, ~27x27 pixels
MAX_DATES = 10        # API limit per request
SCALE = 1e-4
GOOD = (0, 1)         # reliability: 0 good, 1 marginal; 2 snow, 3 cloud, -1 fill
WORKERS = 4


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
            time.sleep(5 * (i + 1))


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


def reduce(ndvi, rel):
    ok = np.isin(rel, GOOD) & (ndvi > -2000)
    n = int(ok.sum())
    if n == 0:
        return None, None, 0, len(ndvi)
    v = ndvi[ok] * SCALE
    return float(np.median(v)), float(np.percentile(v, 75)), n, len(ndvi)


def collect_point(name, lat, lon, have):
    todo = [d for d in dates(lat, lon) if d not in have]
    rows = []
    for i in range(0, len(todo), MAX_DATES):
        chunk = todo[i:i + MAX_DATES]
        nd = subset(lat, lon, BAND_NDVI, chunk[0], chunk[-1])
        rl = subset(lat, lon, BAND_REL, chunk[0], chunk[-1])
        for md, (cal, v) in nd.items():
            if md in have or md not in rl:
                continue
            med, p75, n, tot = reduce(v, rl[md][1])
            rows.append({"point": name, "modis_date": md, "date": cal,
                         "ndvi_median": med, "ndvi_p75": p75,
                         "n_good": n, "n_pixels": tot})
    log(f"{name}: {len(rows)} new composites")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()

    old = pd.DataFrame()
    if os.path.exists(OUT) and not args.full:
        old = pd.read_csv(OUT, dtype={"modis_date": str})
    pts = points()
    log(f"{len(pts)} points, box ±{BOX_KM} km")

    def job(item):
        name, (lat, lon) = item
        have = set(old.loc[old.point == name, "modis_date"]) if len(old) else set()
        return collect_point(name, lat, lon, have)

    with ThreadPoolExecutor(WORKERS) as ex:
        new = [r for rows in ex.map(job, pts.items()) for r in rows]

    out = pd.concat([old, pd.DataFrame(new)], ignore_index=True)
    out = (out.drop_duplicates(["point", "modis_date"], keep="last")
              .sort_values(["point", "modis_date"]))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    for c in ("ndvi_median", "ndvi_p75"):
        out[c] = out[c].round(4)
    out.to_csv(OUT, index=False)
    log(f"wrote {len(out)} rows ({len(new)} new) -> {OUT}")


if __name__ == "__main__":
    main()
