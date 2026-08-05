"""
Argentine crop yields from MAGyP's Estimaciones Agrícolas.

The Brazilian models pull state-level yields from IBGE SIDRA one series at a
time. Argentina publishes the whole thing as a single open CSV instead --
every crop, every department, every campaign since 1969/70 -- so the ingestion
shape is different: download once, cache, and slice locally.

  https://datos.magyp.gob.ar/dataset/estimaciones-agricolas

Columns: cultivo, anio, campania, provincia, provincia_id, departamento,
departamento_id, superficie_sembrada_ha, superficie_cosechada_ha,
produccion_tm, rendimiento_kgxha.

Three things about this feed drive the code below.

**Department-level, not province-level.** Finer than SIDRA. The region configs
still aggregate to whole provinces because Buenos Aires + Córdoba + Santa Fe
*is* the Pampas, but the department column is kept so a config can name a
subset when a province straddles two climates (Salta's Anta/Orán soy frontier
against its Andean west, say).

**Yield is rebuilt from the components, never averaged.** The file carries a
per-department `rendimiento_kgxha`, and taking its mean across departments
would weight a 500 ha department the same as a 500,000 ha one. The regional
figure here is sum(produccion) / sum(superficie_cosechada), which is what a
production-weighted yield means.

**Harvest year is not `anio`.** `anio` labels the campaign start. Summer crops
sown in November of `anio` are harvested in `anio + 1`; wheat sown in June of
`anio` is harvested in December of `anio` itself. Campaign 2022/23 is the case
that makes the distinction concrete: soybeans harvested March 2023 at
1,711 kg/ha, wheat harvested December 2022 at 2,277 kg/ha -- both La Niña
casualties, one calendar year apart. Getting this backwards shifts every
weather window by twelve months.

Abandonment (sown minus harvested) is carried alongside the yield. SIDRA
offered nothing like it, and in Argentina it is a direct read on drought: a
crop written off before harvest never enters the yield figure at all, so a
severe drought partly hides itself in the target this model trains on.
"""

import os
import urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

DATASET = "https://datos.magyp.gob.ar/api/3/action/package_show?id=estimaciones-agricolas"
# Resolved from the CKAN record above; kept as a fallback so a portal outage
# does not stop a rebuild from cache-less state.
FALLBACK_CSV = ("https://datos.magyp.gob.ar/dataset/"
                "9e1e77ba-267e-4eaa-a59f-3296e86b5f36/resource/"
                "95d066e6-8a0f-4a80-b59d-6f28f88eacd5/download/"
                "estimaciones-agricolas-2026-03.csv")

LOCAL = os.path.join(CACHE, "estimaciones_agricolas.csv")

UA = {"User-Agent": "yield-model/1.0"}

# Crop labels as they appear in `cultivo`. Soy is published three ways --
# "soja 1ra", "soja 2da" and "soja total". Total is the right target: the
# first/second-crop split is a rotation decision (soy following wheat in the
# same season yields less because it is sown late), so modelling one alone
# would make an agronomic choice look like a weather effect.
CROPS = {
    "soja": "soja total",
    "maiz": "maíz",
    "trigo": "trigo total",
    "algodon": "algodón",
    "cana": "caña de azúcar",
}

# Campaign-start year to harvest year. Summer crops cross the new year;
# wheat does not.
HARVEST_OFFSET = {
    "soja": 1,
    "maiz": 1,
    "algodon": 1,
    "cana": 1,
    "trigo": 0,
}


def log(msg):
    print(f"[magyp] {msg}", flush=True)


def _resolve_url():
    """Current CSV resource URL from CKAN, falling back to the pinned one."""
    try:
        import json
        req = urllib.request.Request(DATASET, headers=UA)
        with urllib.request.urlopen(req, timeout=60) as r:
            pkg = json.loads(r.read())["result"]
        for res in pkg["resources"]:
            if res["format"].upper() == "CSV" and "estimaciones" in res["url"]:
                return res["url"]
    except Exception as e:  # noqa: BLE001 - the fallback exists for exactly this
        log(f"CKAN lookup failed ({e}); using pinned resource URL")
    return FALLBACK_CSV


def download(force=False):
    """
    Fetch the estimaciones CSV to the local cache.

    ~15 MB and served slowly -- several minutes is normal. Cached thereafter,
    because every region-crop slices the same file.
    """
    os.makedirs(CACHE, exist_ok=True)
    if os.path.exists(LOCAL) and not force:
        return LOCAL

    url = _resolve_url()
    log(f"downloading {url}")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=900) as r, \
            open(LOCAL, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    log(f"cached {os.path.getsize(LOCAL) / 1e6:.1f} MB -> {LOCAL}")
    return LOCAL


_TABLE = None


def table():
    """The whole estimaciones file, loaded once per process."""
    global _TABLE
    if _TABLE is None:
        path = download()
        df = pd.read_csv(path, low_memory=False)
        # Province and department arrive with occasional nulls (national
        # totals rows); string-cast so filters never raise on the mix.
        for c in ("cultivo", "provincia", "departamento", "campania"):
            df[c] = df[c].astype(str)
        for c in ("superficie_sembrada_ha", "superficie_cosechada_ha",
                  "produccion_tm", "rendimiento_kgxha"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        _TABLE = df
        log(f"loaded {len(df):,} rows, {df.anio.min()}-{df.anio.max()}")
    return _TABLE


def region_yield(crop, provinces, departments=None):
    """
    Production-weighted yield for a region, indexed by *harvest* year.

    `provinces` is a list of province names as MAGyP spells them.
    `departments`, when given, restricts to those departments within those
    provinces -- for a province that spans two farming climates.

    Returns a DataFrame with columns:
      year             harvest year (campaign start + HARVEST_OFFSET)
      yield_kg_ha      sum(production) / sum(harvested area)
      area_ha          harvested area, for weighting and for sanity checks
      abandonment      1 - harvested/sown, the share written off before harvest
    """
    if crop not in CROPS:
        raise KeyError(f"unknown crop {crop!r}; known: {sorted(CROPS)}")

    df = table()
    sel = df[(df.cultivo == CROPS[crop]) & (df.provincia.isin(provinces))]
    if departments:
        sel = sel[sel.departamento.isin(departments)]
    if sel.empty:
        raise ValueError(f"no rows for {crop} in {provinces}")

    # `production` rather than `prod`: DataFrame.prod is a method, and an
    # attribute-style read of a column with that name silently returns the
    # method instead of the data.
    g = sel.groupby("anio").agg(
        production=("produccion_tm", "sum"),
        harvested=("superficie_cosechada_ha", "sum"),
        sown=("superficie_sembrada_ha", "sum"),
    ).reset_index()

    # A campaign with no harvested area is a campaign the crop was not grown
    # in, not a zero-yield one.
    g = g[g.harvested > 0].copy()

    g["yield_kg_ha"] = g.production * 1000.0 / g.harvested
    g["area_ha"] = g.harvested
    g["abandonment"] = (1.0 - g.harvested / g.sown).clip(lower=0.0)
    g["year"] = g.anio + HARVEST_OFFSET[crop]

    return g[["year", "yield_kg_ha", "area_ha", "abandonment"]] \
        .sort_values("year").reset_index(drop=True)
