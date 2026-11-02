"""
Regional yield labels from Eurostat (apro_cpshr: crop production in EU
standard humidity by NUTS 2 region, 2000 onward).

Usage: python3 -m france.eurostat     # refresh data/eurostat_apro.csv

The extract is committed, so collect/train run offline; CI refreshes it
weekly. A region-crop's label is the area-weighted yield of its NUTS 2
regions: sum(yield x area) / sum(area), over the regions reporting both that
year. A year missing more than a fifth of the region's usual area is dropped
rather than published as a partial average.
"""

import json
import os
import sys
import urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "eurostat_apro.csv")
API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/apro_cpshr"

# Crop key -> Eurostat crop code.
CROPS = {"winter_wheat": "C1110", "grain_maize": "C1500"}
# Common winter wheat (C1111) carries area but no regional yield or
# production in this table, so the label is common wheat (C1110); in
# northern France spring wheat is a rounding error next to winter wheat.
YIELD = "YLD_HUMD_EU_T_HA"
AREA = "AR_THS_HA"
PROD = "HPRD_HUMD_EU_THS_T"
# NUTS 2 regions fetched (all of metropolitan France's arable regions).
GEOS = ["FR10", "FRB0", "FRC1", "FRC2", "FRD1", "FRD2", "FRE1", "FRE2",
        "FRF1", "FRF2", "FRF3", "FRG0", "FRH0", "FRI1", "FRI2", "FRI3",
        "FRJ1", "FRJ2", "FRK1", "FRK2", "FRL0"]
# NUTS 2013 codes, which Eurostat keeps for the years before the 2016
# recoding (same boundaries in every pair below, only the code changed).
OLD_CODES = {"FR24": "FRB0", "FR30": "FRE1", "FR22": "FRE2", "FR21": "FRF2",
             "FR25": "FRD1", "FR23": "FRD2", "FR26": "FRC1", "FR43": "FRC2",
             "FR61": "FRI1", "FR62": "FRJ2", "FR63": "FRI2", "FR53": "FRI3",
             "FR51": "FRG0", "FR52": "FRH0", "FR42": "FRF1", "FR41": "FRF3",
             "FR81": "FRJ1", "FR71": "FRK2", "FR72": "FRK1", "FR82": "FRL0"}
MIN_AREA_SHARE = 0.8


def log(msg):
    print(f"[eurostat] {msg}", flush=True)


def _decode(d):
    """JSON-stat 2.0 -> long rows of every dimension plus value."""
    dims, size = d["id"], d["size"]
    inv = {k: {v: c for c, v in d["dimension"][k]["category"]["index"].items()}
           for k in dims}
    stride = [1] * len(size)
    for i in range(len(size) - 2, -1, -1):
        stride[i] = stride[i + 1] * size[i + 1]
    rows = []
    for k, v in d.get("value", {}).items():
        k = int(k)
        row = {dim: inv[dim][(k // stride[i]) % size[i]] for i, dim in enumerate(dims)}
        row["value"] = v
        rows.append(row)
    return rows


def fetch():
    q = "&".join([f"crops={c}" for c in CROPS.values()]
                 + [f"strucpro={s}" for s in (YIELD, AREA, PROD)]
                 + [f"geo={g}" for g in GEOS + list(OLD_CODES)])
    url = f"{API}?format=JSON&lang=EN&{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        rows = _decode(json.loads(r.read()))
    if not rows:
        raise SystemExit("Eurostat returned no values")
    df = pd.DataFrame(rows).rename(columns={"time": "year"})
    df = df[["crops", "strucpro", "geo", "year", "value"]]
    df["year"] = df.year.astype(int)
    # Old-code rows fill only the years the new code does not cover.
    old = df[df.geo.isin(OLD_CODES)].assign(geo=lambda x: x.geo.map(OLD_CODES))
    new = df[~df.geo.isin(OLD_CODES)]
    have = set(zip(new.crops, new.strucpro, new.geo, new.year))
    old = old[[k not in have for k in zip(old.crops, old.strucpro, old.geo, old.year)]]
    if len(old):
        log(f"{len(old)} values from NUTS 2013 codes, {old.year.min()}-{old.year.max()}")
    df = pd.concat([new, old], ignore_index=True)
    df = df.sort_values(["crops", "strucpro", "geo", "year"])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    df.to_csv(OUT, index=False)
    log(f"{len(df)} values, {df.year.min()}-{df.year.max()} -> {OUT}")
    for (c, s), g in df.groupby(["crops", "strucpro"]):
        log(f"  {c} {s}: {len(g)} values, {g.year.min()}-{g.year.max()}, {g.geo.nunique()} regions")
    return df


def load(path=OUT):
    return pd.read_csv(path, dtype={"geo": str})


def region_yield(crop, selector, path=OUT):
    """Area-weighted yield (kg/ha) and area (kha) by year for NUTS 2 codes."""
    d = load(path)
    d = d[(d.crops == CROPS[crop]) & d.geo.isin(selector)]
    w = d.pivot_table(index=["year", "geo"], columns="strucpro", values="value").reset_index()
    for col in (YIELD, AREA, PROD):
        if col not in w:
            w[col] = float("nan")
    # Yield where published, else production / area (both in EU humidity).
    w[YIELD] = w[YIELD].fillna(w[PROD] / w[AREA])
    w = w.dropna(subset=[YIELD, AREA])
    w = w[(w[YIELD] > 0) & (w[AREA] > 0)]
    usual = w.groupby("geo")[AREA].median()
    out = []
    for year, g in w.groupby("year"):
        if g[AREA].sum() < MIN_AREA_SHARE * usual.sum():
            continue
        area = g[AREA].sum()
        out.append({"year": int(year),
                    "yield_kg_ha": float((g[YIELD] * g[AREA]).sum() / area * 1000),
                    "area_kha": float(area)})
    return pd.DataFrame(out, columns=["year", "yield_kg_ha", "area_kha"])


def area_shares(crop, selector, since=2015, path=OUT):
    d = load(path)
    d = d[(d.crops == CROPS[crop]) & d.geo.isin(selector) & (d.strucpro == AREA) & (d.year >= since)]
    s = d.groupby("geo").value.mean()
    return (s / s.sum()).round(3).to_dict()


if __name__ == "__main__":
    fetch()
    from .regions import ALL
    for cfg in ALL:
        log(f"{cfg.key}: shares {area_shares(cfg.crop, cfg.selector)}")
        log(region_yield(cfg.crop, cfg.selector).tail(8).to_string())
    sys.exit(0)
