"""
District-level Indian crop yields from the ICRISAT District Level Database.

Why this source and not the obvious ones:

  - FAOSTAT and USDA PSD publish India as one national number. That cannot
    support these three guides at all. Madhya Pradesh alone is over half of
    India's soybean and Maharashtra plus Gujarat about half its cotton, so a
    national average blends a Punjab heatwave, a Malwa monsoon failure and a
    Vidarbha dry spell into a single figure in which all three cancel. This is
    the same argument brazil/sidra.py makes against FAOSTAT for Brazil, only
    sharper -- India spans more agro-climatic zones.
  - data.gov.in carries the official DES series but registration requires an
    Indian mobile number, so it is not obtainable from outside India.
  - ICRISAT DLD needs no key and no registration, and it is *district* level
    rather than state level -- finer than SIDRA. That matters most for cotton,
    where the guide names Vidarbha and Marathwada specifically rather than
    Maharashtra as a whole, and where the state average would fold in the
    irrigated sugar belt around Kolhapur and Pune.

The API serves one 13 MB JSON blob containing every crop, district and year;
there is no server-side filter, so it is fetched once and cached as a tidy CSV
per crop. The upstream server is slow and drops long transfers, hence the
resume-free retry loop with a completeness check against Content-Length --
a truncated JSON body would otherwise parse as far as it got and silently
produce a training table missing its recent years.

Aggregation is by real area, not by fixed weights:

    yield_region(y) = sum_d production_d(y) / sum_d area_d(y)

Both columns are published, so the region's yield is the actual harvest
divided by the actual hectares rather than an average of district yields
weighted by a guess. A district that did not grow the crop in a given year
contributes zero to both sums and drops out on its own.
"""

import json
import os
import time
import urllib.error
import urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

# A committed snapshot, distinct from cache/ (which is gitignored as
# reproducible-by-refetch). This one is not reliably reproducible: the
# upstream server has a hard per-request timeout of roughly 90 seconds and
# throttles the transfer to ~60-70 KB/s, so any client on an ordinary
# connection is cut off partway through the 13 MB response no matter how many
# times it retries -- four separate attempts from a home connection all failed
# at the identical byte offset. A datacentre link (a GitHub Actions runner)
# gets there before the same 90-second wall, so the fetch is done once from
# CI and the tidy table is committed here rather than re-attempted by every
# contributor and every run.
VENDORED_CSV = os.path.join(HERE, "data", "icrisat_apy.csv")

API = "http://data.icrisat.org/dldAPI"
DATASET = "unapportioned/area-production-yield"

# "unapportioned" reports each district on its boundaries as they were in the
# year of record; "apportioned" back-projects every year onto 2015 boundaries
# but only starts in 1990. India redrew a great many district boundaries after
# 1966 -- Madhya Pradesh alone shed Chhattisgarh in 2000 -- but because
# everything here is aggregated up to a multi-district region before use, the
# splits happen *inside* the aggregate and cancel. The extra 24 years of record
# are worth more than boundary-stable district identifiers we do not use.

CROPS = {
    "wheat": "WHEAT",
    "soybean": "SOYABEAN",
    "cotton": "COTTON",
}

# ICRISAT writes -1 for "not reported" rather than leaving the cell empty.
# Treating it as a number would put negative hectares into the denominator.
MISSING = -0.5

TIMEOUT = 1800


def log(msg):
    print(f"[icrisat] {msg}", flush=True)


def _raw_path():
    return os.path.join(CACHE, "icrisat_apy_raw.json")


def _download(attempts=6):
    """
    Fetch the blob, verifying the body arrived whole.

    The server sends Content-Length and then frequently closes early. urllib
    will happily hand back the short body, so the length is checked explicitly
    and a short read is retried rather than parsed.
    """
    url = f"{API}/{DATASET}"
    delay = 20

    for i in range(attempts):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "yield-model/1.0"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                declared = r.headers.get("Content-Length")
                body = r.read()

            if declared and len(body) != int(declared):
                raise IOError(
                    f"short read: {len(body):,} of {int(declared):,} bytes")

            # Parsing is itself the completeness test when no length is sent.
            return json.loads(body.decode("utf-8"))

        except Exception as e:  # noqa: BLE001 - retry any transport or parse failure
            if i == attempts - 1:
                raise
            log(f"  attempt {i + 1} failed ({e}); retrying in {delay}s")
            time.sleep(delay)
            delay = min(delay * 2, 300)


def load_raw():
    """
    The full district-year table as a DataFrame.

    Checked in this order:

      1. The committed snapshot at VENDORED_CSV, if present. This is the
         normal path for every contributor and every CI run once the snapshot
         exists: no network call at all.
      2. The local cache, if a previous run in this environment fetched it.
      3. A fresh download, retried with exponential backoff -- which a home
         connection has not been observed to complete (see VENDORED_CSV's
         module-level comment).

    Columns are renamed from the API's display headers to the compact names
    used below; everything else is passed through so the cache can serve crops
    beyond the three modelled here without a refetch.
    """
    if os.path.exists(VENDORED_CSV):
        return pd.read_csv(VENDORED_CSV)

    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, "icrisat_apy.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached)

    raw_file = _raw_path()
    if os.path.exists(raw_file):
        log("using cached raw JSON")
        with open(raw_file, encoding="utf-8") as f:
            payload = json.load(f)
    else:
        log(f"downloading {DATASET} (~13 MB, the server is slow)")
        payload = _download()
        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    headers = [h["header"] for h in payload["headers"]]
    df = pd.DataFrame(payload["data"], columns=headers)

    df = df.rename(columns={
        "Year": "year",
        "State Code": "state_code",
        "State Name": "state",
        "Dist Code": "dist_code",
        "Dist Name": "district",
        "Region Name": "division",
        "LATITUDE": "lat",
        "LONGITUDE": "lon",
    })

    for c in ("year", "state_code", "dist_code", "lat", "lon"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    for crop in CROPS.values():
        for kind in ("AREA", "PRODUCTION", "YIELD"):
            col = f"{crop} {kind}"
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
                df.loc[df[col] < MISSING, col] = pd.NA

    df = df.dropna(subset=["year"])
    df["year"] = df.year.astype(int)

    df.to_csv(cached, index=False)
    log(f"{len(df):,} district-years, {df.year.min()}-{df.year.max()}, "
        f"{df.district.nunique()} districts")
    return df


def select(df, selector):
    """
    Rows for a region.

    `selector` is a list of (state_code, divisions) where divisions is either
    None for the whole state or a list of ICRISAT "Region Name" values --
    Maharashtra's Amravati/Nagpur/Aurangabad/Latur divisions are Vidarbha and
    Marathwada, which is the area the cotton guide is actually written about.
    """
    frames = []
    for state_code, divisions in selector:
        rows = df[df.state_code == state_code]
        if divisions:
            rows = rows[rows.division.isin(divisions)]
        frames.append(rows)
    return pd.concat(frames, ignore_index=True)


def region_yield(crop, selector):
    """
    Area-weighted yield in kg/ha for a region, indexed by harvest year.

    Returns a DataFrame with columns year, yield_kg_ha, area_kha.

    Production is published in 1000 t and area in 1000 ha, so
    production/area * 1000 is kg/ha and the thousands cancel.

    Years where the region reports no area at all are dropped rather than
    returned as zero: a crop that was not grown has no yield, and a zero would
    be detrended as a catastrophic harvest.
    """
    if crop not in CROPS:
        raise KeyError(f"unknown crop {crop!r}; known: {sorted(CROPS)}")

    name = CROPS[crop]
    rows = select(load_raw(), selector)

    area, prod = f"{name} AREA", f"{name} PRODUCTION"
    g = rows.groupby("year").agg(
        area_kha=(area, "sum"), prod_kt=(prod, "sum")).reset_index()

    g = g[g.area_kha > 0].copy()
    g["yield_kg_ha"] = g.prod_kt / g.area_kha * 1000.0

    return g[["year", "yield_kg_ha", "area_kha"]].sort_values("year")


def rank_districts(crop, selector, since=2000, top=None):
    """
    Districts ranked by mean planted area, with coordinates.

    Used offline to choose which locations to pull weather for and what to
    weight them by -- the same job the hand-listed points do in
    brazil/regions.py, except the shares here are measured rather than
    estimated. Not called by the pipeline at run time; the chosen points are
    written into regions.py so a run is reproducible and reviewable.
    """
    name = CROPS[crop]
    rows = select(load_raw(), selector)
    rows = rows[rows.year >= since]

    g = rows.groupby(["district", "state"]).agg(
        area_kha=(f"{name} AREA", "mean"),
        lat=("lat", "first"),
        lon=("lon", "first"),
    ).reset_index()

    g = g[g.area_kha > 0].sort_values("area_kha", ascending=False)
    g["share"] = g.area_kha / g.area_kha.sum()
    return g.head(top) if top else g


def main():
    """
    Fetch the ICRISAT blob and write the committed snapshot at VENDORED_CSV.

    Usage: python3 -m india.icrisat

    Meant to run once, from an environment with more bandwidth than a home
    connection can sustain inside the upstream server's ~90-second per-request
    window (see VENDORED_CSV's comment) -- in practice, a GitHub Actions
    runner. Once VENDORED_CSV exists and is committed, load_raw() never
    downloads again.
    """
    if os.path.exists(VENDORED_CSV):
        log(f"already have a snapshot at {VENDORED_CSV}; delete it to refetch")
        return 0

    df = load_raw()
    os.makedirs(os.path.dirname(VENDORED_CSV), exist_ok=True)
    df.to_csv(VENDORED_CSV, index=False)
    log(f"wrote {VENDORED_CSV}: {len(df):,} district-years, "
        f"{df.year.min()}-{df.year.max()}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
