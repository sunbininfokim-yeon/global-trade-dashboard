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
CROPS = {"winter_wheat": "C1111", "grain_maize": "C1500"}
YIELD = "YLD_HUMD_EU_T_HA"
AREA = "AR_THS_HA"
# NUTS 2 regions fetched (all of metropolitan France's arable regions).
GEOS = ["FR10", "FRB0", "FRC1", "FRC2", "FRD1", "FRD2", "FRE1", "FRE2",
        "FRF1", "FRF2", "FRF3", "FRG0", "FRH0", "FRI1", "FRI2", "FRI3",
        "FRJ1", "FRJ2", "FRK1", "FRK2", "FRL0"]
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
                 + [f"strucpro={s}" for s in (YIELD, AREA)]
                 + [f"geo={g}" for g in GEOS])
    url = f"{API}?format=JSON&lang=EN&{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        rows = _decode(json.loads(r.read()))
    if not rows:
        raise SystemExit("Eurostat returned no values")
    df = pd.DataFrame(rows).rename(columns={"time": "year"})
    df = df[["crops", "strucpro", "geo", "year", "value"]]
    df["year"] = df.year.astype(int)
    df = df.sort_values(["crops", "strucpro", "geo", "year"])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    df.to_csv(OUT, index=False)
    log(f"{len(df)} values, {df.year.min()}-{df.year.max()} -> {OUT}")
    return df


def load(path=OUT):
    return pd.read_csv(path, dtype={"geo": str})


def region_yield(crop, selector, path=OUT):
    """Area-weighted yield (kg/ha) and area (kha) by year for NUTS 2 codes."""
    d = load(path)
    d = d[(d.crops == CROPS[crop]) & d.geo.isin(selector)]
    w = d.pivot_table(index=["year", "geo"], columns="strucpro", values="value").reset_index()
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
