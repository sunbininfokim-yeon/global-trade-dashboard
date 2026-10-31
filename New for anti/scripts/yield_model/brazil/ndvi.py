"""
MODIS NDVI for the Brazilian regions -- an in-season crop-condition channel
for the models whose weather features do not beat the trend.

Usage: python3 -m brazil.ndvi [--full] [--shard K --shards N --out FILE]
       python3 -m brazil.ndvi merge FILE [FILE ...]

Same source and pixel reduction as argentina.ndvi (ORNL DAAC MOD13Q1, 250 m,
16-day composites, median and 75th percentile of a box), reused from there.
Three differences:

  * Sampling sites. The weather points are town coordinates, which is fine
    for a 0.5-degree NASA POWER cell but not for 250 m pixels. The box is
    widened to +-4 km so a town is a small share of it, and three of the four
    MATOPIBA points are moved up onto the chapadas: Barreiras, Balsas and
    Urucui sit in river valleys below the plateaus where the soy and cotton
    are, so a box on the town would read riverside scrub. Pedro Afonso stays,
    the crop there is around the town. ndvi_backtest reports each site's
    window greenness, so a site that missed the fields shows up there. Each site keeps its weather point's name, so
    the regions' production weights carry over unchanged.
  * Months. Only the composites a region's NDVI window needs are requested
    for each site (ndvi_backtest.window), as runs of consecutive composites,
    so a four-month window costs one call a season instead of two.
  * Shards. The first backfill is ~800 calls and ORNL is slow, so the
    workflow splits the sites over parallel jobs (--shard/--shards), each
    writing only its new rows, and merges them before the backtest.

Writes condition/ndvi_points.csv: one row per site per composite.
"""

import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import numpy as np
import pandas as pd

from argentina import ndvi as A
from .ndvi_backtest import window_months
from .regions import ALL

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "condition", "ndvi_points.csv")

A.BOX_KM = 4
WORKERS = 4
COLUMNS = ["point", "modis_date", "date", "lat", "lon",
           "ndvi_median", "ndvi_p75", "n_good", "n_pixels"]

# Weather point -> NDVI site, where the town is not where the crop is.
SITES = {
    # Western Bahia plateau west of Luis Eduardo Magalhaes, the core of the
    # region's soy and cotton; Barreiras itself is in the Rio Grande valley.
    "Barreiras": (-12.30, -45.95),
    # Gerais de Balsas, the soy plateau south-west of the town.
    "Balsas": (-8.30, -46.60),
    # Serra do Urucui plateau south-west of the town (Baixa Grande do Ribeiro side).
    "Urucui": (-7.95, -45.05),
    # Cane between Dumont and Pradopolis, south-west of the city: a box on
    # Ribeirao Preto itself read 0.45 in the cane window against 0.61-0.64
    # at Piracicaba and Aracatuba, the city's 700k people filling the box.
    "Ribeirao Preto": (-21.30, -47.98),
}


def log(msg):
    print(f"[br-ndvi] {msg}", flush=True)


def sites():
    """name -> (lat, lon, months wanted), across every region using the point."""
    out = {}
    for cfg in ALL:
        months = window_months(cfg)
        for p in cfg.points:
            lat, lon = SITES.get(p["name"], (p["lat"], p["lon"]))
            entry = out.setdefault(p["name"], [lat, lon, set()])
            entry[2] |= months
    return {k: (v[0], v[1], frozenset(v[2])) for k, v in out.items()}


def runs(every, want, limit=A.MAX_DATES):
    """Split the wanted composites into runs of consecutive calendar entries."""
    chunks, cur = [], []
    for d in every:
        if d in want:
            cur.append(d)
            if len(cur) == limit:
                chunks.append(cur)
                cur = []
        elif cur:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def collect_site(name, lat, lon, months, have):
    try:
        every = A.dates(lat, lon)
    except Exception as e:  # noqa: BLE001 -- one site down should not sink the shard
        log(f"{name}: composite calendar unavailable ({e})")
        return []
    want = {d for d in every if d not in have
            and datetime.strptime(d[1:], "%Y%j").month in months}
    chunks = runs(every, want)
    rows = []
    for i, chunk in enumerate(chunks):
        if time.monotonic() - A._T0 > A.BUDGET_MIN * 60:
            log(f"{name}: time budget reached, {len(chunks) - i} requests left")
            break
        try:
            got = A.subset(lat, lon, A.BAND_NDVI, chunk[0], chunk[-1])
        except Exception as e:  # noqa: BLE001 -- keep what arrived; next run resumes
            log(f"{name}: stopped after {i} requests ({e}); {len(chunks) - i} left")
            break
        for md, (cal, v) in got.items():
            if md not in want:
                continue
            med, p75, n, tot = A.reduce(v)
            rows.append({"point": name, "modis_date": md, "date": cal,
                         "lat": lat, "lon": lon,
                         "ndvi_median": med, "ndvi_p75": p75,
                         "n_good": n, "n_pixels": tot})
    log(f"{name}: {len(rows)} new composites from {len(chunks)} requests")
    return rows


def load(path=None):
    path = path or OUT
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, dtype={"modis_date": str})


def save(frame, path=None):
    path = path or OUT
    frame = (frame.drop_duplicates(["point", "modis_date"], keep="last")
                  .sort_values(["point", "modis_date"]))
    for c in ("ndvi_median", "ndvi_p75"):
        frame[c] = frame[c].round(4)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    frame.to_csv(path, index=False)
    return frame


def collect(full=False, shard=0, shards=1, out=None):
    old = pd.DataFrame() if full else load()
    todo = sorted(sites().items())[shard::shards]
    log(f"shard {shard + 1}/{shards}: {len(todo)} sites, box ±{A.BOX_KM} km")

    def job(item):
        name, (lat, lon, months) = item
        have = set()
        if len(old):
            # A moved site is re-collected rather than mixed with the old box.
            mine = old[(old.point == name) & (old.lat.round(2) == round(lat, 2))
                       & (old.lon.round(2) == round(lon, 2))]
            have = set(mine.modis_date)
        return collect_site(name, lat, lon, months, have)

    with ThreadPoolExecutor(WORKERS) as ex:
        new = pd.DataFrame([r for rows in ex.map(job, todo) for r in rows],
                           columns=COLUMNS)
    if out:
        new.to_csv(out, index=False)
        log(f"wrote {len(new)} new rows -> {out}")
    else:
        merged = save(pd.concat([old, new], ignore_index=True))
        log(f"wrote {len(merged)} rows ({len(new)} new) -> {OUT}")


def merge(paths):
    parts = [load()] + [pd.read_csv(p, dtype={"modis_date": str}) for p in paths]
    frame = pd.concat([p for p in parts if len(p)] or [pd.DataFrame(columns=COLUMNS)],
                      ignore_index=True)
    # Rows from a site's old coordinates are dropped once it has moved.
    here = sites()
    keep = np.array([r.point in here
                     and round(r.lat, 2) == round(here[r.point][0], 2)
                     and round(r.lon, 2) == round(here[r.point][1], 2)
                     for r in frame.itertuples()], dtype=bool)
    frame = save(frame[keep])
    log(f"merged {len(paths)} shard files -> {len(frame)} rows, "
        f"{frame.point.nunique()} sites, {frame.date.min()} to {frame.date.max()}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", nargs="?", default="collect")
    ap.add_argument("files", nargs="*")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--out")
    args = ap.parse_args()
    if args.command == "merge":
        merge(args.files)
    else:
        collect(args.full, args.shard, args.shards, args.out)


if __name__ == "__main__":
    main()
