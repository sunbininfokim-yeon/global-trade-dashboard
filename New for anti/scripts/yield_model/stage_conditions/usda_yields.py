"""Provisional scoring for frozen stage calls from USDA's national yields.

A frozen call is only scored once the region's official yield reaches the
model's training table, which can take a year or more (IBGE, Rosstat, state
NASS series). USDA's PSD carries a national yield for the same season from
the first WASDE onward and revises it monthly, so it gives an early,
provisional read: the national yield against its own trend over the ten
seasons before, the yardstick the ledger uses. It is a country number for a
regional call, so it is kept apart from the final score and shown as 잠정.

Only Actions can reach PSD; the slice used is cached in psd_yields.csv so an
offline build keeps the last one.
"""

import io
import os
import urllib.request
import zipfile

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "psd_yields.csv")
PSD_ZIP = "https://apps.fas.usda.gov/psdonline/downloads/psd_alldata_csv.zip"

WHEAT, CORN, SOY = "Wheat", "Corn", "Oilseed, Soybean"
SUN, RAPE, COTTON = "Oilseed, Sunflowerseed", "Oilseed, Rapeseed", "Cotton"

# (region, crop) -> (PSD country, PSD commodity, market-year offset).
# PSD names a season by the year it starts. Southern summer crops harvested
# in the first half of year Y belong to market year Y-1 (Brazil soy harvested
# Feb 2027 is 2026/27); everything else here is harvested in its market
# year's first year. Coffee, cane, cocoa, rice and the mislabelled Australian
# barley/canola rows are left out rather than guessed.
REGION_PSD = {
    ("great_plains", "winter_wheat"): ("United States", WHEAT, 0),
    ("northern_plains", "spring_wheat"): ("United States", WHEAT, 0),
    ("corn_belt", "corn"): ("United States", CORN, 0),
    ("corn_belt", "soybeans"): ("United States", SOY, 0),
    ("cotton_belt", "cotton"): ("United States", COTTON, 0),
    ("mato_grosso_soja", "soy"): ("Brazil", SOY, -1),
    ("mato_grosso_soja", "corn_safrinha"): ("Brazil", CORN, -1),
    ("parana_soja", "soy"): ("Brazil", SOY, -1),
    ("parana_soja", "corn"): ("Brazil", CORN, -1),
    ("parana_soja", "wheat"): ("Brazil", WHEAT, 0),
    ("matopiba_soja", "soy"): ("Brazil", SOY, -1),
    ("matopiba_soja", "cotton"): ("Brazil", COTTON, -1),
    ("pampas_soja", "soy"): ("Argentina", SOY, -1),
    ("norte_soja", "soy"): ("Argentina", SOY, -1),
    ("pampas_maiz", "corn"): ("Argentina", CORN, -1),
    ("pampas_trigo", "wheat"): ("Argentina", WHEAT, 0),
    ("chaco_algodon", "cotton"): ("Argentina", COTTON, -1),
    ("southern_winter_wheat", "winter_wheat"): ("Russia", WHEAT, 0),
    ("cbe_winter_wheat", "winter_wheat"): ("Russia", WHEAT, 0),
    ("volga_winter_wheat", "winter_wheat"): ("Russia", WHEAT, 0),
    ("russia_winter_wheat", "winter_wheat"): ("Russia", WHEAT, 0),
    ("southern_sunflower", "sunflower"): ("Russia", SUN, 0),
    ("cbe_sunflower", "sunflower"): ("Russia", SUN, 0),
    ("volga_sunflower", "sunflower"): ("Russia", SUN, 0),
    ("russia_sunflower", "sunflower"): ("Russia", SUN, 0),
    ("russia_corn_cbe", "corn"): ("Russia", CORN, 0),
    ("russia_corn_south", "corn"): ("Russia", CORN, 0),
    ("russia_soy_amur", "soy"): ("Russia", SOY, 0),
    ("russia_soy_cbe", "soy"): ("Russia", SOY, 0),
    ("punjab_wheat", "wheat"): ("India", WHEAT, 0),
    ("mp_soybean", "soy"): ("India", SOY, 0),
    ("vidarbha_cotton", "cotton"): ("India", COTTON, 0),
    ("wa_wheat", "wheat"): ("Australia", WHEAT, 0),
    ("sa_wheat", "wheat"): ("Australia", WHEAT, 0),
    ("vic_wheat", "wheat"): ("Australia", WHEAT, 0),
    ("sad_sk_canola_palliser", "canola"): ("Canada", RAPE, 0),
    ("sad_ab_canola_south", "canola"): ("Canada", RAPE, 0),
    ("sad_ab_canola_central", "canola"): ("Canada", RAPE, 0),
    ("sad_ab_canola_peace", "canola"): ("Canada", RAPE, 0),
    ("sad_mb_canola_central", "canola"): ("Canada", RAPE, 0),
    ("sad_sk_wheat_palliser", "spring_wheat"): ("Canada", WHEAT, 0),
    ("sad_on_corn_southern", "corn"): ("Canada", CORN, 0),
    ("sad_on_corn_western", "corn"): ("Canada", CORN, 0),
    ("sad_mb_soy_redriver", "soy"): ("Canada", SOY, 0),
}
COUNTRY_KO = {"United States": "미국", "Brazil": "브라질", "Argentina": "아르헨티나",
              "Russia": "러시아", "India": "인도", "Australia": "호주", "Canada": "캐나다"}


def log(msg):
    print(f"[stage-usda] {msg}", flush=True)


def fetch():
    req = urllib.request.Request(PSD_ZIP, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(req, timeout=600) as r:
        z = zipfile.ZipFile(io.BytesIO(r.read()))
    name = next(n for n in z.namelist() if n.endswith(".csv"))
    df = pd.read_csv(z.open(name), encoding="latin-1", low_memory=False,
                     usecols=["Commodity_Description", "Country_Name", "Market_Year",
                              "Attribute_Description", "Value"])
    want = {(c, k) for c, k, _ in REGION_PSD.values()}
    df = df[df.Attribute_Description == "Yield"]
    df = df[[(c, k) in want for c, k in zip(df.Country_Name, df.Commodity_Description)]]
    out = (df.rename(columns={"Country_Name": "country", "Commodity_Description": "commodity",
                              "Market_Year": "year", "Value": "yield"})
           [["country", "commodity", "year", "yield"]]
           .groupby(["country", "commodity", "year"], as_index=False).last()
           .sort_values(["country", "commodity", "year"]))
    out = out[out["yield"] > 0]
    out.to_csv(CACHE, index=False)
    log(f"{len(out)} national yields, {len(want)} series -> {CACHE}")
    return out


def load(offline=False):
    if not offline:
        try:
            return fetch()
        except Exception as exc:  # noqa: BLE001 - keep the cached slice
            log(f"PSD unavailable ({exc}); using {CACHE}")
    return pd.read_csv(CACHE) if os.path.exists(CACHE) else None


def national_residual(psd, region, crop, harvest_year):
    """(log residual vs prior-10-season trend, info) or (None, None)."""
    spec = REGION_PSD.get((region, crop))
    if psd is None or spec is None:
        return None, None
    country, commodity, offset = spec
    s = psd[(psd.country == country) & (psd.commodity == commodity)].set_index("year")["yield"]
    my = int(harvest_year) + offset
    if my not in s.index:
        return None, None
    prior = s[(s.index < my) & (s.index >= my - 10)]
    if len(prior) < 8:
        return None, None
    fit = np.polyfit(prior.index.values.astype(float), np.log(prior.values.astype(float)), 1)
    res = float(np.log(s[my]) - np.polyval(fit, my))
    return res, {"country": country, "country_ko": COUNTRY_KO.get(country, country),
                 "commodity": commodity, "market_year": f"{my}/{str(my + 1)[2:]}",
                 "yield_t_ha": round(float(s[my]), 2)}
