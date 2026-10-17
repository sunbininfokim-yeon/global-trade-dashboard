"""
MODIS NDVI at the Thai weather points -- an in-season crop-condition channel
for models whose weather features have not beaten the trend.

Usage: python3 -m thailand.ndvi            # append new composites
       python3 -m thailand.ndvi --full     # rebuild from 2000

Same source and reduction as argentina.ndvi (ORNL DAAC MOD13Q1, 250 m, 16-day
composites, median and 75th percentile of a ±2 km box), reused from there.
Two differences: every month is requested, because Thai crops are in the
field all year (off-season rice January to April, the wet-season crop and
cane through the monsoon), and the output goes to thailand/condition/.

MOD13Q1 is a 16-day maximum-value composite, which keeps the clearest look at
each pixel; over the monsoon that still leaves some cloud-contaminated
composites, so a weak signal in the wet-season windows is a floor, not a
verdict on the crop.

Writes condition/ndvi_points.csv: one row per point per composite.
"""

import argparse
import os
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from argentina import ndvi as A
from .regions import ALL

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "condition", "ndvi_points.csv")


def log(msg):
    print(f"[th-ndvi] {msg}", flush=True)


def points():
    seen = {}
    for rc in ALL:
        if rc.stub:
            continue
        for p in rc.points:
            seen.setdefault(p["name"], (p["lat"], p["lon"]))
    return seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()

    A.SKIP_MONTHS = ()          # tropical: every month serves some crop
    old = pd.DataFrame()
    if os.path.exists(OUT) and not args.full:
        old = pd.read_csv(OUT, dtype={"modis_date": str})
    pts = points()
    log(f"{len(pts)} points, box ±{A.BOX_KM} km")

    def job(item):
        name, (lat, lon) = item
        have = set(old.loc[old.point == name, "modis_date"]) if len(old) else set()
        return A.collect_point(name, lat, lon, have)

    with ThreadPoolExecutor(A.WORKERS) as ex:
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
