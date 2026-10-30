"""
Refresh the oblast label CSVs from tochno.st's Rosstat "Regions of Russia"
collection.

Usage: python3 -m russia.tochno

Why this source: rosstat.gov.ru, fedstat.ru and showdata.gks.ru all answer
403 Forbidden outside Russia, from GitHub Actions as from here. Tochno.st
republishes the "Regions of Russia" yearbook as open data (CC BY 4.0) on
Yandex Object Storage, which is reachable. The current release covers
2001-2024 for every indicator used here. On the overlapping 2001-2021 years
it matches the CSVs this package already had to within 0.1 c/ha (cereal
yield) and 1.4 thousand ha (sown area), which is yearbook-edition rounding.

Indicators (all "in farms of all categories"):

    Y477110424  cereal + legume yield, c/ha of harvested area -> oblast_yields.csv
    Y477110300  cereal + legume sown area, 1000 ha           -> oblast_sown_area.csv
    Y477110428  sunflower yield, c/ha                        -> oblast_sunflower_yields.csv
    Y477110304  sunflower sown area, 1000 ha                 -> oblast_sunflower_sown_area.csv

Rows already in a CSV for years tochno.st does not cover (2000, and the 2024
mojgorod patch where tochno.st lacks an oblast) are kept; every year tochno.st
does cover is taken from it, so a later yearbook's revisions win.

The release folder is versioned (v20260313). When tochno.st publishes a new
one, bump RELEASE; the module fails loudly rather than silently reading a
stale or missing file.
"""

import io
import os
import urllib.request
import zipfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training")

RELEASE = "v20260313"
URL = ("https://storage.yandexcloud.net/tochno-st-catalog/Rosstat/"
       f"data_regions_collection_102_{RELEASE}/"
       f"data_13_socio_economic_102_{RELEASE}.zip")

OBLASTS = {
    "Белгородская область": "Belgorod",
    "Волгоградская область": "Volgograd",
    "Воронежская область": "Voronezh",
    "Краснодарский край": "Krasnodar",
    "Курская область": "Kursk",
    "Ростовская область": "Rostov",
    "Самарская область": "Samara",
    "Саратовская область": "Saratov",
    "Ставропольский край": "Stavropol",
    "Тамбовская область": "Tambov",
}

# indicator -> (csv, value column, source label)
TARGETS = {
    "Y477110424": ("oblast_yields.csv", "yield_c_ha",
                   "cereals+legumes yield"),
    "Y477110300": ("oblast_sown_area.csv", "sown_1000ha",
                   "cereals+legumes sown area"),
    "Y477110428": ("oblast_sunflower_yields.csv", "yield_c_ha",
                   "sunflower yield"),
    "Y477110304": ("oblast_sunflower_sown_area.csv", "sown_1000ha",
                   "sunflower sown area"),
}


def log(msg):
    print(f"[tochno] {msg}", flush=True)


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(req, timeout=600) as r:
        blob = r.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(name) as f:
            return pd.read_csv(f, sep=None, engine="python")


def main():
    raw = fetch()
    raw = raw[raw.object_name.isin(OBLASTS)
              & raw.indicator_code.isin(TARGETS)].copy()
    raw["oblast"] = raw.object_name.map(OBLASTS)
    raw["value"] = pd.to_numeric(raw.indicator_value, errors="coerce")
    raw = raw.dropna(subset=["value"])

    for code, (fname, col, what) in TARGETS.items():
        new = (raw[raw.indicator_code == code]
               .groupby(["year", "oblast"]).value.last().reset_index()
               .rename(columns={"value": col}))
        if new.empty:
            raise RuntimeError(f"{code} ({what}) missing from {URL}")
        new["year"] = new.year.astype(int)
        new[col] = new[col].round(2)
        if col == "yield_c_ha":
            new["yield_kg_ha"] = new[col] * 100.0
        new["source"] = f"Rosstat Regions of Russia via tochno.st {RELEASE} {code} {what}"

        path = os.path.join(TRAINING, fname)
        old = pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()
        if len(old):
            covered = set(zip(new.year, new.oblast))
            old = old[[k not in covered for k in zip(old.year, old.oblast)]]
        out = (pd.concat([old, new[old.columns if len(old) else new.columns]],
                         ignore_index=True)
                 .sort_values(["oblast", "year"]))
        out.to_csv(path, index=False)
        log(f"{fname}: {len(new)} rows from tochno.st, "
            f"{int(new.year.min())}-{int(new.year.max())}, total {len(out)}")


if __name__ == "__main__":
    main()
