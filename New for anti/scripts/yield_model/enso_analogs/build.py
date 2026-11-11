"""How did each country's main crops do in past strong El Nino years?

The yield models answer "what does this season's weather say". For a
country with no usable model (China) or one whose model ignores the ocean,
the plainest evidence of what a strong El Nino means is the record: the
national yield in the years of past strong events, measured against its own
trend so that technology gains do not hide the dip.

Fixed before looking at any result (2026-11-11):
  events     NOAA CPC ONI episodes (>= +0.5 for 5+ overlapping seasons)
             whose peak reached +1.5 ("strong"); year Y = the year of the
             peak (a DJF-FMA peak counts for the year before). Crops harvested in Y and in Y+1 are both shown,
             because the same event hits a September rice crop in Y and an
             April palm or southern-hemisphere maize crop in Y+1.
  labels     FAOSTAT national yield (QCL, Element "Yield"), 1961 onward.
  trend      linear fit on the 15 years centred on the target year,
             excluding the target year; at the ends of the record the
             window shifts inward. At least 8 years or the year is skipped.
  output     deviation % from that trend per event year, the mean, how many
             of the events were below trend, and the spread of all years
             (so a -3% can be read against a normal +-4%).

Nothing here feeds a forecast. It is a reference table.

Run from scripts/yield_model:  python3 -m enso_analogs.build
"""
from __future__ import annotations

import io
import json
import os
import statistics
import urllib.request
import zipfile
from datetime import datetime, timezone

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "..", "..", "public", "data", "enso_analogs_v1.json"))
FAO_URL = ("https://bulks-faostat.fao.org/production/"
           "Production_Crops_Livestock_E_All_Data_(Normalized).zip")
FAO_MEMBER = "Production_Crops_Livestock_E_All_Data_(Normalized).csv"
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
STRONG = 1.5
HALF_WINDOW = 7
MIN_YEARS = 8

# FAOSTAT area name per dashboard country (CLIMATE_COUNTRIES key).
AREAS = {
    "China": "China, mainland", "United States": "United States of America",
    "Canada": "Canada", "Australia": "Australia", "Indonesia": "Indonesia",
    "Malaysia": "Malaysia", "Thailand": "Thailand", "Vietnam": "Viet Nam",
    "Colombia": "Colombia", "Argentina": "Argentina", "Brazil": "Brazil",
    "India": "India", "South Africa": "South Africa", "Ethiopia": "Ethiopia",
    "Uganda": "Uganda", "Nigeria": "Nigeria", "Russia": "Russian Federation",
    "Ukraine": "Ukraine", "Kazakhstan": "Kazakhstan", "France": "France",
    "Ivory Coast": "Côte d'Ivoire", "Ghana": "Ghana",
}
# Countries on the Pacific rim, flagged so the screen can say so.
PACIFIC_RIM = {"China", "United States", "Canada", "Australia", "Indonesia", "Malaysia",
               "Thailand", "Vietnam", "Colombia", "Russia"}

# (FAOSTAT item aliases, label_ko). FAOSTAT renamed several items in 2021.
ITEMS = {
    "rice": (["Rice", "Rice, paddy"], "쌀"),
    "wheat": (["Wheat"], "밀"),
    "maize": (["Maize (corn)", "Maize"], "옥수수"),
    "soy": (["Soya beans", "Soybeans"], "대두"),
    "palm": (["Oil palm fruit"], "팜 열매"),
    "coffee": (["Coffee, green"], "커피"),
    "cocoa": (["Cocoa beans"], "코코아"),
    "sugarcane": (["Sugar cane"], "사탕수수"),
    "rapeseed": (["Rape or colza seed", "Rapeseed"], "유채·카놀라"),
    "barley": (["Barley"], "보리"),
}
CROPS = {
    "China": ["rice", "wheat", "maize", "soy"],
    "United States": ["maize", "soy", "wheat"],
    "Canada": ["wheat", "rapeseed"],
    "Australia": ["wheat", "barley", "sugarcane"],
    "Indonesia": ["palm", "rice"],
    "Malaysia": ["palm"],
    "Thailand": ["rice", "sugarcane"],
    "Vietnam": ["rice", "coffee"],
    "Colombia": ["coffee", "palm"],
    "Argentina": ["soy", "maize", "wheat"],
    "Brazil": ["soy", "maize", "coffee", "sugarcane"],
    "India": ["rice", "wheat", "soy"],
    "South Africa": ["maize"],
    "Ethiopia": ["coffee"],
    "Uganda": ["coffee"],
    "Nigeria": ["maize", "palm"],
    "Russia": ["wheat"],
    "Ukraine": ["wheat", "maize"],
    "Kazakhstan": ["wheat"],
    "France": ["wheat"],
    "Ivory Coast": ["cocoa"],
    "Ghana": ["cocoa"],
}


def log(msg):
    print(f"[enso-analogs] {msg}", flush=True)


def fetch(url, timeout=900):
    req = urllib.request.Request(url, headers={"User-Agent": "global-trade-dashboard"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def strong_events(text):
    """[(start_year, peak, peak_season)] for ONI episodes peaking >= STRONG."""
    rows = []
    for line in text.splitlines()[1:]:
        p = line.split()
        if len(p) >= 4:
            try:
                rows.append((p[0], int(p[1]), float(p[3])))
            except ValueError:
                pass
    events, run = [], []
    for row in rows + [("END", 0, -9.0)]:
        if row[2] >= 0.5:
            run.append(row)
            continue
        if len(run) >= 5:
            s, y, v = max(run, key=lambda r: r[2])
            # The event year is the one it peaked in; a DJF-FMA peak belongs
            # to the winter that began the year before (1991-92 -> 1991).
            start = y - 1 if s in ("DJF", "JFM", "FMA") else y
            if v >= STRONG:
                events.append({"year": start, "peak": round(v, 2), "peak_season": f"{s} {y}"})
        run = []
    ongoing = rows and rows[-1][2] >= 0.5
    return events, rows, ongoing


def load_fao():
    names = {a for a in AREAS.values()}
    items = {alias for aliases, _ in ITEMS.values() for alias in aliases}
    blob = fetch(FAO_URL)
    parts = []
    with zipfile.ZipFile(io.BytesIO(blob)) as z, z.open(FAO_MEMBER) as f:
        for chunk in pd.read_csv(f, encoding="latin-1", chunksize=300000,
                                 usecols=["Area", "Item", "Element", "Year", "Unit", "Value"]):
            keep = chunk.Area.isin(names) & chunk.Item.isin(items) & chunk.Element.eq("Yield")
            if keep.any():
                parts.append(chunk[keep])
    d = pd.concat(parts)
    log(f"FAOSTAT rows {len(d)}, years {int(d.Year.min())}-{int(d.Year.max())}, units {set(d.Unit)}")
    return d


def deviation(series: pd.Series, year: int):
    """Percent deviation of series[year] from a linear trend that excludes it."""
    if year not in series.index or pd.isna(series[year]):
        return None
    years = series.dropna().index.values
    lo, hi = year - HALF_WINDOW, year + HALF_WINDOW
    if lo < years.min():
        hi += years.min() - lo
        lo = years.min()
    if hi > years.max():
        lo -= hi - years.max()
        hi = years.max()
    w = series[(series.index >= lo) & (series.index <= hi) & (series.index != year)].dropna()
    if len(w) < MIN_YEARS:
        return None
    b = np.polyfit(w.index.values, np.log(w.values), 1)
    return float(100 * (np.exp(np.log(series[year]) - np.polyval(b, year)) - 1))


def main():
    events, oni_rows, ongoing = strong_events(fetch(ONI_URL, 60).decode("utf-8", "replace"))
    log(f"strong El Nino years: {[e['year'] for e in events]}; ongoing episode: {ongoing}")
    fao = load_fao()
    out = {}
    for country, crops in CROPS.items():
        area = AREAS[country]
        entries = []
        for crop in crops:
            aliases, label_ko = ITEMS[crop]
            d = fao[(fao.Area == area) & fao.Item.isin(aliases)]
            if d.empty:
                continue
            s = d.groupby("Year").Value.mean()
            s.index = s.index.astype(int)
            # all-year spread, for "is -3% unusual here?"
            spread = [deviation(s, y) for y in s.index]
            spread = [v for v in spread if v is not None]
            rows = []
            for e in events:
                y = e["year"]
                rows.append({"event": y, "peak": e["peak"],
                             "dev_y0": _r(deviation(s, y)), "dev_y1": _r(deviation(s, y + 1))})
            y0 = [r["dev_y0"] for r in rows if r["dev_y0"] is not None]
            y1 = [r["dev_y1"] for r in rows if r["dev_y1"] is not None]
            entries.append({
                "crop": crop, "label_ko": label_ko, "fao_item": d.Item.iloc[0],
                "last_year": int(s.dropna().index.max()),
                "normal_sd_pct": _r(statistics.pstdev(spread)) if len(spread) > 5 else None,
                "y0": _summary(y0), "y1": _summary(y1),
                "events": rows,
            })
        if entries:
            out[country] = {"fao_area": area, "pacific_rim": country in PACIFIC_RIM, "crops": entries}
        log(f"{country}: " + ", ".join(
            f"{c['label_ko']} Y {c['y0']['mean']}/{c['y0']['below']}of{c['y0']['n']} "
            f"Y+1 {c['y1']['mean']}/{c['y1']['below']}of{c['y1']['n']}" for c in entries))
    doc = {
        "schema_version": "enso-analogs-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "spec": __doc__.split("Run from")[0].strip(),
        "source": "FAOSTAT QCL (national yield) · NOAA CPC ONI",
        "events": events,
        "current_episode": ({"year": oni_rows[-1][1], "latest": oni_rows[-1][2],
                             "season": oni_rows[-1][0]} if ongoing else None),
        "countries": out,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    log(f"wrote {OUT}")


def _r(v):
    return None if v is None else round(v, 1)


def _summary(vals):
    if not vals:
        return {"n": 0, "mean": None, "below": 0}
    return {"n": len(vals), "mean": _r(statistics.fmean(vals)), "below": sum(v < 0 for v in vals)}


if __name__ == "__main__":
    main()
