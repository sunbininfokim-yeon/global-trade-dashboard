"""Sea ice concentration on the Northern Sea Route line, day by day.

Source: NSIDC Sea Ice Index (G02135) daily concentration GeoTIFFs, 25 km
polar stereographic grid, open HTTPS (no login), 1978-11 onward (every other
day before 1987-08). One file per day:

  .../G02135/north/daily/geotiff/<YYYY>/<MM_Mon>/N_<YYYYMMDD>_concentration_v<ver>.tif

The route is drawn as waypoints along the usual coastal NSR track, split in
six legs whose ice decides passage: Kara Sea, Vilkitsky Strait, Laptev Sea,
Sannikov Strait, East Siberian Sea, Long Strait/Chukchi. Each leg is sampled
every 10 km; the grid cells it crosses (land, coast and missing cells left
out) give the leg's p90 concentration for the day -- the "worst stretch"
of that leg without letting a single coastal cell decide. The route's value
for the day is the worst leg.

Output: one CSV per year under scripts/data/nsr_route_ice/, columns
date, <leg p90 %> ..., n_cells. Backfill runs once per year range
(--years 1979-1990); the daily run fills only the dates still missing.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import io
import math
import os
import re
import sys
import urllib.request
from datetime import date, timedelta

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "data", "nsr_route_ice")
BASE = "https://noaadata.apps.nsidc.org/NOAA/G02135/north/daily/geotiff/"
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# (lon, lat) waypoints, west to east.
LEGS = [
    ("kara", "카라해", [(59.0, 70.5), (65.0, 72.0), (72.0, 73.5), (80.0, 75.0), (90.0, 76.0), (98.0, 76.8)]),
    ("vilkitsky", "빌키츠키 해협", [(98.0, 76.8), (101.5, 77.7), (104.5, 77.9), (107.0, 77.6)]),
    ("laptev", "랍테프해", [(107.0, 77.6), (112.0, 77.0), (120.0, 76.0), (128.0, 75.0), (135.0, 74.4)]),
    ("sannikov", "산니코프 해협", [(135.0, 74.4), (138.5, 74.7), (141.0, 74.6), (144.5, 74.2)]),
    ("east_siberian", "동시베리아해", [(144.5, 74.2), (150.0, 73.0), (157.0, 72.0), (165.0, 71.0), (172.0, 70.3)]),
    ("long_chukchi", "롱 해협·추코트해", [(172.0, 70.3), (176.0, 70.0), (180.0, 69.9), (-176.0, 69.0), (-172.0, 67.5), (-169.5, 66.2)]),
]

# NSIDC polar stereographic north (Hughes 1980 ellipsoid, true at 70N, -45E).
A, E, LAT_TS, LON0 = 6378273.0, 0.081816153, 70.0, -45.0


def ps_xy(lon, lat):
    phi, phic = math.radians(lat), math.radians(LAT_TS)
    t = lambda p: math.tan(math.pi / 4 - p / 2) / ((1 - E * math.sin(p)) / (1 + E * math.sin(p))) ** (E / 2)
    mc = math.cos(phic) / math.sqrt(1 - E * E * math.sin(phic) ** 2)
    rho = A * mc * t(phi) / t(phic)
    lam = math.radians(lon - LON0)
    return rho * math.sin(lam), -rho * math.cos(lam)


def densify(points, step_km=10.0):
    """Points every ~step_km along great circles between waypoints."""
    out = []
    for (lo1, la1), (lo2, la2) in zip(points, points[1:]):
        p1, p2 = [np.radians([lo, la]) for lo, la in ((lo1, la1), (lo2, la2))]
        v1 = np.array([math.cos(p1[1]) * math.cos(p1[0]), math.cos(p1[1]) * math.sin(p1[0]), math.sin(p1[1])])
        v2 = np.array([math.cos(p2[1]) * math.cos(p2[0]), math.cos(p2[1]) * math.sin(p2[0]), math.sin(p2[1])])
        ang = math.acos(max(-1.0, min(1.0, float(v1 @ v2))))
        n = max(1, int(ang * 6371 / step_km))
        for k in range(n):
            f = k / n
            v = (math.sin((1 - f) * ang) * v1 + math.sin(f * ang) * v2) / math.sin(ang) if ang > 0 else v1
            out.append((math.degrees(math.atan2(v[1], v[0])), math.degrees(math.asin(v[2]))))
    out.append(points[-1])
    return out


# Grid of the Sea Ice Index north GeoTIFFs: 304 x 448 cells of 25 km,
# upper-left corner (-3 850 000, 5 850 000). Checked against the file's own
# tie point and pixel scale on every read.
GRID = {"x0": -3850000.0, "y0": 5850000.0, "dx": 25000.0, "dy": 25000.0, "w": 304, "h": 448}


def leg_cells(grid=GRID):
    cells = {}
    for key, _, pts in LEGS:
        seen = []
        for lon, lat in densify(pts):
            x, y = ps_xy(lon, lat)
            c = int((x - grid["x0"]) // grid["dx"])
            r = int((grid["y0"] - y) // grid["dy"])
            if 0 <= c < grid["w"] and 0 <= r < grid["h"] and (r, c) not in seen:
                seen.append((r, c))
        cells[key] = seen
    return cells


def url_for(d, ver):
    return f"{BASE}{d.year}/{d.month:02d}_{MON[d.month - 1]}/N_{d:%Y%m%d}_concentration_v{ver}.tif"


def fetch(url, tries=3):
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "global-trade-dashboard"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            last = e
        except OSError as e:
            last = e
    raise OSError(f"{url}: {last}")


def read_tif(blob):
    """(array of concentration in %, NaN where not ocean, grid dict)."""
    from PIL import Image
    im = Image.open(io.BytesIO(blob))
    arr = np.array(im)
    tags = im.tag_v2
    grid = dict(GRID)
    try:
        tp, sc = tags.get(33922), tags.get(33550)
        if tp and sc:
            grid.update(x0=float(tp[3]), y0=float(tp[4]), dx=float(sc[0]), dy=float(sc[1]))
    except (TypeError, IndexError):
        pass
    grid.update(h=arr.shape[0], w=arr.shape[1])
    a = arr.astype(float)
    if arr.dtype == np.uint8 or a.max() <= 255:
        conc = np.where(a <= 100, a, np.nan)                 # 251+ = pole hole, coast, land, missing
    else:
        conc = np.where(a <= 1000, a / 10.0, np.nan)        # tenths of a percent; 2510+ flags
    return conc, grid, arr


def leg_values(conc, cells):
    out, n = {}, 0
    for key, cs in cells.items():
        v = [conc[r, c] for r, c in cs if not math.isnan(conc[r, c])]
        n += len(v)
        out[key] = round(float(np.percentile(v, 90)), 1) if len(v) >= 2 else None
    return out, n


def version(d):
    """File version for a day: read the month's directory listing once."""
    key = (d.year, d.month)
    if key not in _ver:
        try:
            listing = fetch(f"{BASE}{d.year}/{d.month:02d}_{MON[d.month - 1]}/").decode("utf-8", "replace")
            vs = sorted(set(re.findall(r"_concentration_v([\d.]+)\.tif", listing)), reverse=True)
            _ver[key] = vs[0] if vs else "4.0"
        except (OSError, AttributeError):
            _ver[key] = "4.0"
    return _ver[key]


_ver = {}


def one_day(d, cells):
    blob = fetch(url_for(d, version(d)))
    if blob is None:
        return d, None, 0
    conc, grid, _ = read_tif(blob)
    if (grid["x0"], grid["y0"], grid["dx"]) != (GRID["x0"], GRID["y0"], GRID["dx"]):
        cells = leg_cells(grid)
    vals, n = leg_values(conc, cells)
    return d, vals, n


def year_file(y):
    return os.path.join(OUT_DIR, f"{y}.csv")


def load_year(y):
    rows = {}
    p = year_file(y)
    if os.path.exists(p):
        with open(p, newline="") as f:
            for r in csv.DictReader(f):
                rows[r["date"]] = r
    return rows


def save_year(y, rows):
    os.makedirs(OUT_DIR, exist_ok=True)
    cols = ["date"] + [k for k, _, _ in LEGS] + ["n_cells"]
    with open(year_file(y), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for k in sorted(rows):
            w.writerow({c: rows[k].get(c, "") for c in cols})


def run(days, workers=12):
    cells = leg_cells()
    by_year = {}
    for d in days:
        by_year.setdefault(d.year, []).append(d)
    for y, ds in sorted(by_year.items()):
        rows = load_year(y)
        todo = [d for d in ds if d.isoformat() not in rows]
        if not todo:
            continue
        got = 0
        with cf.ThreadPoolExecutor(workers) as ex:
            for d, vals, n in ex.map(lambda d: one_day(d, cells), todo):
                if vals is None:
                    continue
                rows[d.isoformat()] = {"date": d.isoformat(), "n_cells": n,
                                       **{k: ("" if v is None else v) for k, v in vals.items()}}
                got += 1
        save_year(y, rows)
        print(f"{y}: +{got} days ({len(rows)} total)")


def probe():
    cells = leg_cells()
    print({k: len(v) for k, v in cells.items()})
    print("listing", BASE, re.findall(r'href="([^"]+)"', fetch(BASE).decode())[:8])
    for d in (date(2020, 9, 15), date(2014, 9, 15), date(2025, 3, 1), date(1985, 9, 14)):
        blob = fetch(url_for(d, version(d)))
        if blob is None:
            print(d, "없음", url_for(d, version(d)))
            continue
        conc, grid, raw = read_tif(blob)
        u = np.unique(raw)
        print(d, len(blob), raw.dtype, raw.shape, grid, "values", u[:5], u[-6:])
        for key, cs in cells.items():
            v = [conc[r, c] for r, c in cs]
            print("  ", key, len(cs), "valid", sum(1 for x in v if not math.isnan(x)),
                  "p90", leg_values(conc, {key: cs})[0][key], "raw", [int(raw[r, c]) for r, c in cs][:14])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--years", help="backfill, e.g. 1979-1990")
    ap.add_argument("--days", type=int, default=45, help="daily mode: look back this many days")
    a = ap.parse_args()
    if a.probe:
        return probe()
    if a.years:
        y0, y1 = (int(x) for x in a.years.split("-"))
        days = [date(y0, 1, 1) + timedelta(days=k) for k in range((date(y1, 12, 31) - date(y0, 1, 1)).days + 1)]
        days = [d for d in days if d <= date.today()]
    else:
        days = [date.today() - timedelta(days=k) for k in range(a.days, 0, -1)]
    run(days)


if __name__ == "__main__":
    sys.exit(main())
