"""
State-level Brazilian crop yields from IBGE SIDRA.

The national FAOSTAT series the existing brazil_soy model uses cannot support
the region-specific methodologies in Regions/브라질 -- those are written for
Mato Grosso, Paraná, MATOPIBA and São Paulo separately, and a national average
blends the very contrasts they are built to exploit (a Paraná drought and a
Mato Grosso sowing delay cancel each other out in the national number).

SIDRA is IBGE's open statistics API: no key, no rate limit published, and
"Rendimento médio da produção" (variable 112) runs from 1974 to 2024 for every
state and crop used here.

  Table 1612 -- Produção Agrícola Municipal, temporary crops
                (soja, milho, trigo, algodão herbáceo, cana-de-açúcar)
  Table 1613 -- Produção Agrícola Municipal, permanent crops (café)

One caveat that matters for how the corn models are read: PAM reports a single
"Milho (em grão)" figure per state, first and second season combined. In Mato
Grosso that is close to harmless -- safrinha is the overwhelming majority of
the crop -- but in Paraná the two seasons are both large and the target is a
genuine blend. That limitation is recorded on the affected configs in
regions.py rather than hidden here.
"""

import json
import os
import time
import urllib.request
from datetime import datetime, timedelta

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

SIDRA = "https://apisidra.ibge.gov.br/values"

# How long a cached yield series is trusted. IBGE publishes PAM once a year, so
# a permanent cache would mean the models never see a newly released season --
# the pipeline would keep forecasting against a record that stopped growing.
CACHE_MAX_AGE = timedelta(days=30)

# variable 112 = Rendimento médio da produção (kg/ha)
YIELD_VAR = "112"

# Crop code and its SIDRA table. Temporary crops live in 1612 under
# classification c81; permanent crops in 1613 under c82.
CROPS = {
    "soja":     {"table": "1612", "cls": "c81", "code": "2713"},
    "milho":    {"table": "1612", "cls": "c81", "code": "2711"},
    "trigo":    {"table": "1612", "cls": "c81", "code": "2716"},
    "algodao":  {"table": "1612", "cls": "c81", "code": "2689"},
    "cana":     {"table": "1612", "cls": "c81", "code": "2696"},
    "cafe":     {"table": "1613", "cls": "c82", "code": "2723"},
}

# IBGE state (UF) codes.
UF = {
    "MA": 21, "PI": 22, "BA": 29, "MG": 31, "SP": 35,
    "PR": 41, "RS": 43, "MS": 50, "MT": 51, "GO": 52, "TO": 17,
}

# SIDRA's placeholders for "no data" / "not applicable" / "suppressed".
MISSING = {"...", "..", "-", "X", "*"}


def log(msg):
    print(f"[sidra] {msg}", flush=True)


def _get(url, attempts=3, timeout=240):
    for i in range(attempts):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "yield-model/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001 - retry any transport failure
            if i == attempts - 1:
                raise
            log(f"  retry {i + 1} after {e}")
            time.sleep(10)


def state_yield(crop, uf):
    """
    Yield in kg/ha for one crop in one state, indexed by harvest year.

    Returns a DataFrame with columns year, yield_kg_ha.
    """
    if crop not in CROPS:
        raise KeyError(f"unknown crop {crop!r}; known: {sorted(CROPS)}")
    if uf not in UF:
        raise KeyError(f"unknown state {uf!r}; known: {sorted(UF)}")

    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, f"sidra_{crop}_{uf}.csv")
    if os.path.exists(cached):
        age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(cached))
        if age < CACHE_MAX_AGE:
            return pd.read_csv(cached)
        log(f"{crop}/{uf}: cache {age.days}d old, refreshing")

    spec = CROPS[crop]
    url = (f"{SIDRA}/t/{spec['table']}/n3/{UF[uf]}/v/{YIELD_VAR}"
           f"/p/all/{spec['cls']}/{spec['code']}")
    log(f"{crop}/{uf}: downloading")
    raw = _get(url)

    rows = []
    for rec in raw[1:]:  # row 0 is the header description, not data
        v = rec.get("V")
        if v in MISSING or v is None:
            continue
        try:
            rows.append({"year": int(rec["D3N"]), "yield_kg_ha": float(v)})
        except (ValueError, KeyError):
            continue

    df = pd.DataFrame(rows).sort_values("year").reset_index(drop=True)
    df.to_csv(cached, index=False)
    log(f"{crop}/{uf}: {len(df)} years "
        f"({df.year.min()}-{df.year.max()})" if len(df) else f"{crop}/{uf}: empty")
    return df


def region_yield(crop, states):
    """
    Production-weighted yield for a multi-state region.

    `states` is a list of (uf, weight). Weights are the states' shares of the
    region's output; they are renormalised over whichever states report in a
    given year, so one state's missing year does not drag the region's yield
    down towards zero.
    """
    frames = []
    for uf, w in states:
        df = state_yield(crop, uf).copy()
        df["w"] = w
        df["uf"] = uf
        frames.append(df)

    allst = pd.concat(frames, ignore_index=True)
    allst["wy"] = allst.yield_kg_ha * allst.w

    g = allst.groupby("year").agg(wy=("wy", "sum"), w=("w", "sum")).reset_index()
    g["yield_kg_ha"] = g.wy / g.w
    return g[["year", "yield_kg_ha"]]
