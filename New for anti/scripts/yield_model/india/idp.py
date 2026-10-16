"""
District crop statistics after 2019, from India Data Portal.

Usage: python3 -m india.idp

ICRISAT's District Level Database stops at 2019, which froze all three
Indian models. The official successor series is the Ministry of
Agriculture's Area-Production-Yield (DES, data.desagri.gov.in), and
data.gov.in needs an Indian mobile number to register. India Data Portal
(ISB) republishes it on an open CKAN with direct CSV downloads:

  crop-wise-area-production-yield.csv          DES APY, 1997-98 to 2022-23
  cropwise-area-production-yield-upag.csv      UPAg,    2013-14 to 2024-25

Both are district-level and both are refreshed upstream; the UPAg file was
last updated 2026-10-12. This module downloads them, keeps the states and
crops the Indian models use, and writes one tidy table:

  data/idp_apy.csv   source, year_label, state, district, crop, season,
                     area_ha, production_t

Where both sources report a district-crop-year, both rows are kept with
their source tag; india.labels decides which wins.
"""

import io
import os
import urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "idp_apy.csv")

BASE = ("https://ckan.indiadataportal.com/dataset/"
        "5b8f4660-52d2-4edf-824b-1af41d290498/resource")
SOURCES = {
    "des_apy": f"{BASE}/a000ce51-a257-42e3-8ab7-3cd212966f88/download/"
               "crop-wise-area-production-yield.csv",
    "upag": f"{BASE}/9668b3f8-8e23-45a5-b290-4193cbacc670/download/"
            "cropwise-area-production-yield-upag.csv",
}

STATES = {"Punjab", "Haryana", "Madhya Pradesh", "Maharashtra", "Gujarat"}
# Source crop name (lower-cased, prefix match) -> model crop key
CROPS = {"wheat": "wheat", "soyabean": "soybean", "soybean": "soybean",
         "cotton": "cotton"}


def log(msg):
    print(f"[idp] {msg}", flush=True)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return pd.read_csv(io.BytesIO(r.read()), low_memory=False)


def crop_key(name):
    n = str(name).strip().lower()
    for prefix, key in CROPS.items():
        if n.startswith(prefix):
            return key
    return None


def tidy(df, source):
    df = df[df.state_name.str.strip().isin(STATES)].copy()
    df["crop"] = df.crop_name.map(crop_key)
    df = df.dropna(subset=["crop"])
    out = pd.DataFrame({
        "source": source,
        "year_label": df.year.astype(str).str.strip(),
        "state": df.state_name.str.strip(),
        "district": df.district_name.astype(str).str.strip(),
        "crop": df.crop,
        "crop_name": df.crop_name.astype(str).str.strip(),
        "season": df.season.astype(str).str.strip(),
        "area": pd.to_numeric(df.area, errors="coerce"),
        "production": pd.to_numeric(df.production, errors="coerce"),
        "area_unit": df.get("area_unit", pd.Series("Hectare", index=df.index)),
        "production_unit": df.get("production_unit",
                                  pd.Series("", index=df.index)),
    })
    return out


def main():
    frames = []
    for source, url in SOURCES.items():
        raw = fetch(url)
        log(f"{source}: {len(raw)} rows, columns {raw.columns.tolist()}")
        t = tidy(raw, source)
        log(f"{source}: kept {len(t)} rows; units "
            f"{t.groupby('crop').production_unit.unique().to_dict()}")
        frames.append(t)
    out = pd.concat(frames, ignore_index=True).sort_values(
        ["crop", "state", "district", "year_label", "source"])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    out.to_csv(OUT, index=False)
    log(f"wrote {len(out)} rows -> {OUT}")


if __name__ == "__main__":
    main()
