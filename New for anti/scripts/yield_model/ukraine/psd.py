"""
USDA PSD national figures for Ukraine wheat, corn and sunflower.

Usage: python3 -m ukraine.psd

Writes
  training/<region key>.csv   year, yield_kg_ha, production_kt, area_kha
      National yields from 1992, so stage_conditions can check its past
      stage calls against how the harvest landed (year = USDA market year,
      which for all three crops is the harvest year).
  public/data/ukraine_yield_forecast.json   government_outlooks refreshed
      with USDA's current and previous market-year production and yield.

There is no yield model: regional labels are too short (see model.yaml).
National yields since 2022 also reflect the occupied south dropping out.
"""

import io
import json
import os
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training")
REF = os.path.normpath(os.path.join(HERE, "..", "..", "..", "public", "data",
                                    "ukraine_yield_forecast.json"))
ZIPS = {
    "grains": "https://apps.fas.usda.gov/psdonline/downloads/psd_grains_pulses_csv.zip",
    "oilseeds": "https://apps.fas.usda.gov/psdonline/downloads/psd_oilseeds_csv.zip",
}
CROPS = {  # PSD commodity -> (region key, Korean label)
    "Wheat": ("ukraine_winter_wheat", "밀"),
    "Corn": ("ukraine_corn", "옥수수"),
    "Oilseed, Sunflowerseed": ("ukraine_sunflower", "해바라기씨"),
}
ATTRS = ["Production", "Yield", "Area Harvested", "Exports"]
PSD_URL = "https://apps.fas.usda.gov/psdonline/app/index.html#/app/advQuery"
FIRST_YEAR = 1992


def log(msg):
    print(f"[ukraine:psd] {msg}", flush=True)


def fetch():
    parts = []
    for url in ZIPS.values():
        req = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
        with urllib.request.urlopen(req, timeout=600) as r:
            z = zipfile.ZipFile(io.BytesIO(r.read()))
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        df = pd.read_csv(z.open(name), encoding="latin-1", low_memory=False)
        parts.append(df[(df.Country_Name == "Ukraine")
                        & df.Commodity_Description.isin(CROPS)
                        & df.Attribute_Description.isin(ATTRS)])
    return pd.concat(parts, ignore_index=True)


def tables(df):
    """Commodity -> frame indexed by market year with the four attributes."""
    out = {}
    for c, g in df.groupby("Commodity_Description"):
        out[c] = g.pivot_table(index="Market_Year", columns="Attribute_Description",
                               values="Value").sort_index()
    return out


def write_training(tabs):
    os.makedirs(TRAINING, exist_ok=True)
    for c, t in tabs.items():
        key = CROPS[c][0]
        t = t[t.index >= FIRST_YEAR]
        frame = pd.DataFrame({
            "year": t.index.astype(int),
            "yield_kg_ha": (t["Yield"] * 1000).round(0),
            "production_kt": t["Production"],
            "area_kha": t["Area Harvested"],
        }).dropna(subset=["yield_kg_ha"])
        frame.to_csv(os.path.join(TRAINING, f"{key}.csv"), index=False)
        log(f"{key}: {len(frame)} seasons {frame.year.min()}-{frame.year.max()}")


def outlooks(tabs, release):
    rows = []
    for c, t in tabs.items():
        label = CROPS[c][1]
        cur_y, prev_y = int(t.index.max()), int(t.index.max()) - 1
        cur, prev = t.loc[cur_y], t.loc[prev_y]
        pct = (cur["Production"] / prev["Production"] - 1) * 100
        rows.append({
            "agency": "USDA", "agency_ko": "USDA (PSD·WASDE)",
            "season": f"{cur_y}/{str(cur_y + 1)[-2:]}",
            "metric_ko": f"{label} 생산 전망",
            "value": int(cur["Production"] * 1000), "unit": "tonnes",
            "status_ko": f"{release} 기준 · 전년 대비 {pct:+.0f}%",
            "note_ko": (f"단수 {cur['Yield']:.2f} t/ha (전년 {prev['Yield']:.2f}), "
                        f"수확면적 {cur['Area Harvested'] / 1000:.2f}백만 ha, "
                        f"수출 {cur['Exports'] / 1000:.1f}백만 t. "
                        "2022년 이후는 점령지 일부가 빠진 정부 통제 지역 기준."),
            "url": PSD_URL, "url_label": "USDA PSD Online",
        })
    return rows


def update_reference(tabs, release):
    with open(REF, encoding="utf-8") as f:
        ref = json.load(f)
    ref["government_outlooks"] = outlooks(tabs, release)
    ref["generated_at"] = datetime.now(timezone.utc).isoformat()
    with open(REF, "w", encoding="utf-8") as f:
        json.dump(ref, f, ensure_ascii=False, indent=2)
        f.write("\n")
    log(f"reference outlooks -> {REF}")


def main(argv):
    df = fetch()
    if df.empty:
        log("PSD returned no Ukraine rows")
        return 1
    last = df.sort_values(["Calendar_Year", "Month"]).iloc[-1]
    release = f"{int(last.Calendar_Year)}년 {int(last.Month)}월 USDA"
    tabs = tables(df)
    write_training(tabs)
    update_reference(tabs, release)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
