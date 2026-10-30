"""
Real yield labels for Central Highlands robusta from FAOSTAT.

Usage: python3 -m vietnam.faostat

The coffee model had only synthetic placeholder labels, so it was never
trained. FAOSTAT "Coffee, green" for Viet Nam is a national series, but the
Central Highlands (Dak Lak, Lam Dong, Gia Lai, Dak Nong, Kon Tum) hold roughly
nine tenths of Vietnam's coffee area, so the national yield is close to the
region's. That is the reason this crop can use a national label while Red
River rice (a small share of national rice) cannot.

Writes training/labels_official/central_highlands_coffee.csv, which
labels.load_official picks up ahead of the synthetic fallback.
"""

import io
import os
import urllib.request
import zipfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "training", "labels_official",
                   "central_highlands_coffee.csv")
URL = ("https://bulks-faostat.fao.org/production/"
       "Production_Crops_Livestock_E_All_Data_(Normalized).zip")
MEMBER = "Production_Crops_Livestock_E_All_Data_(Normalized).csv"
SOURCE = "faostat_vietnam_national_coffee_green"


def log(msg):
    print(f"[vn-faostat] {msg}", flush=True)


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(req, timeout=900) as r:
        blob = r.read()
    rows = []
    with zipfile.ZipFile(io.BytesIO(blob)) as z, z.open(MEMBER) as f:
        for chunk in pd.read_csv(f, encoding="latin-1", chunksize=250000,
                                 usecols=["Area", "Item", "Element", "Year",
                                          "Unit", "Value"]):
            keep = (chunk.Area.eq("Viet Nam") & chunk.Item.eq("Coffee, green")
                    & chunk.Element.eq("Yield"))
            if keep.any():
                rows.append(chunk[keep])
    if not rows:
        raise RuntimeError("no FAOSTAT Viet Nam coffee yield rows")
    d = pd.concat(rows).groupby("Year", as_index=False).first()
    units = set(d.Unit)
    log(f"units {units}")
    scale = 0.1 if units & {"hg/ha", "100 g/ha"} else 1.0
    out = pd.DataFrame({"year": d.Year.astype(int),
                        "yield_kg_ha": (d.Value * scale).round(1),
                        "label_source": SOURCE})
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    out.to_csv(OUT, index=False)
    log(f"wrote {len(out)} years {out.year.min()}-{out.year.max()} -> {OUT}")


if __name__ == "__main__":
    main()
