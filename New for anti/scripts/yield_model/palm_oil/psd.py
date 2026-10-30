"""
USDA FAS PSD crude palm oil for every producer in producers.ALL.

Usage: python3 -m palm_oil.psd     # -> training/psd_palm.csv

One download covers all countries. Year mapping follows indonesia/palm_psd.py:
PSD market year M for palm oil runs October M to September M+1 and is
labelled M+1 here, the year most of it is harvested in.
"""

import io
import os
import urllib.request
import zipfile

import pandas as pd

from .producers import ALL

HERE = os.path.dirname(os.path.abspath(__file__))
PSD_CSV = os.path.join(HERE, "training", "psd_palm.csv")
URL = "https://apps.fas.usda.gov/psdonline/downloads/psd_oilseeds_csv.zip"


def log(msg):
    print(f"[palm-oil:psd] {msg}", flush=True)


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(req, timeout=600) as r:
        blob = r.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(name) as f:
            d = pd.read_csv(f, low_memory=False)
    names = [p.psd_name for p in ALL]
    d = d[d.Country_Name.isin(names) & (d.Commodity_Description == "Oil, Palm")]
    d = d[d.Attribute_Description.isin(["Production", "Area Harvested"])]
    keep = ["Country_Name", "Market_Year", "Calendar_Year", "Month",
            "Attribute_Description", "Unit_Description", "Value"]
    d = d[keep].sort_values(["Country_Name", "Attribute_Description", "Market_Year"])
    missing = sorted(set(names) - set(d.Country_Name))
    if missing:
        raise SystemExit(f"PSD has no palm oil for: {', '.join(missing)}")
    os.makedirs(os.path.dirname(PSD_CSV), exist_ok=True)
    d.to_csv(PSD_CSV, index=False)
    for country, g in d.groupby("Country_Name"):
        log(f"{country}: market years {g.Market_Year.min()}-{g.Market_Year.max()}")


def labels(producer, path=None):
    """year, psd_production_kt for one producer (label year = market year + 1)."""
    d = pd.read_csv(path or PSD_CSV)
    d = d[(d.Country_Name == producer.psd_name)
          & (d.Attribute_Description == "Production")]
    out = (d.groupby("Market_Year").Value.last().rename("psd_production_kt")
           .reset_index())
    out["year"] = out.Market_Year + 1
    out = out[out.psd_production_kt > 0]
    return out[["year", "psd_production_kt"]].sort_values("year").reset_index(drop=True)


if __name__ == "__main__":
    fetch()
