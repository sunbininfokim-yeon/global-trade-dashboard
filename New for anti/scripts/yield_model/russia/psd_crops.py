"""
Russian corn and soybeans: USDA PSD national outlook and yield history, and
the stage-call points for them (no yield model).

Usage: python3 -m russia.psd_crops          # fetch PSD, write, patch the JSON
       python3 -m russia.psd_crops apply    # rebuild from the committed slice

Why no model: Rosstat's crop-by-crop oblast yields are only on rosstat.gov.ru
and fedstat.ru (403 outside Russia, Actions included), and tochno.st
republishes the yearbook's cereals+legumes total only, not corn or soy. So
corn and soy get what Ukraine and Kazakhstan get: stage-by-stage weather
calls at representative points (stage_conditions), checked against the
USDA national yield since 1992, plus USDA's current outlook.

Writes
  training/psd_russia_crops.csv      the PSD slice (committed; `apply` reads it)
  training/<point key>.csv           national yield per point, for the check
  training/psd_regions.json          the panel entries; run_forecast merges them
  public/data/russia_yield_forecast.json   patched in place with those entries
"""

import io
import json
import os
import sys
import urllib.request
import zipfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training")
SLICE = os.path.join(TRAINING, "psd_russia_crops.csv")
REGIONS_JSON = os.path.join(TRAINING, "psd_regions.json")
OUT = os.path.normpath(os.path.join(HERE, "..", "..", "..", "public", "data",
                                    "russia_yield_forecast.json"))
ZIPS = {
    "grains": "https://apps.fas.usda.gov/psdonline/downloads/psd_grains_pulses_csv.zip",
    "oilseeds": "https://apps.fas.usda.gov/psdonline/downloads/psd_oilseeds_csv.zip",
}
ATTRS = ["Production", "Yield", "Area Harvested", "Exports"]
PSD_URL = "https://apps.fas.usda.gov/psdonline/app/index.html#/app/advQuery"
FIRST_YEAR = 1992

# PSD commodity -> (Korean label, crop, [(point key, label_ko, area)]).
CROPS = {
    "Corn": ("옥수수", "corn", [
        ("russia_corn_south", "남부 옥수수", "크라스노다르"),
        ("russia_corn_cbe", "흑토대 옥수수", "쿠르스크·벨고로드·보로네시"),
    ]),
    "Oilseed, Soybean": ("대두", "soy", [
        ("russia_soy_amur", "극동 대두", "아무르"),
        ("russia_soy_cbe", "흑토대 대두", "벨고로드·쿠르스크"),
    ]),
}


def log(msg):
    print(f"[russia:psd-crops] {msg}", flush=True)


def fetch():
    parts = []
    for url in ZIPS.values():
        req = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
        with urllib.request.urlopen(req, timeout=600) as r:
            z = zipfile.ZipFile(io.BytesIO(r.read()))
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        df = pd.read_csv(z.open(name), encoding="latin-1", low_memory=False)
        parts.append(df[(df.Country_Name == "Russia")
                        & df.Commodity_Description.isin(CROPS)
                        & df.Attribute_Description.isin(ATTRS)])
    out = pd.concat(parts, ignore_index=True)[
        ["Commodity_Description", "Market_Year", "Calendar_Year", "Month",
         "Attribute_Description", "Value"]]
    if out.empty:
        raise SystemExit("PSD returned no Russia corn/soy rows")
    os.makedirs(TRAINING, exist_ok=True)
    out.to_csv(SLICE, index=False)
    log(f"{len(out)} rows -> {SLICE}")
    return out


def tables(df):
    return {c: g.pivot_table(index="Market_Year", columns="Attribute_Description",
                             values="Value").sort_index()
            for c, g in df.groupby("Commodity_Description")}


def release_of(df):
    last = df.sort_values(["Calendar_Year", "Month"]).iloc[-1]
    return f"{int(last.Calendar_Year)}년 {int(last.Month)}월 USDA"


def write_training(tabs):
    for c, t in tabs.items():
        t = t[t.index >= FIRST_YEAR]
        frame = pd.DataFrame({
            "year": t.index.astype(int),
            "yield_kg_ha": (t["Yield"] * 1000).round(0),
            "production_kt": t["Production"],
            "area_kha": t["Area Harvested"],
        }).dropna(subset=["yield_kg_ha"])
        for key, _, _ in CROPS[c][2]:
            frame.to_csv(os.path.join(TRAINING, f"{key}.csv"), index=False)
        log(f"{c}: {len(frame)} seasons {frame.year.min()}-{frame.year.max()}")


def entries(tabs, release):
    out = {}
    for c, t in tabs.items():
        label, crop, points = CROPS[c]
        cur_y = int(t.index.max())
        cur, prev = t.loc[cur_y], t.loc[cur_y - 1]
        pct = (cur["Production"] / prev["Production"] - 1) * 100
        # Last finished season: the one before the current USDA marketing year.
        reason = (f"지역별 {label} 단수 공개 자료가 없어(Rosstat 작물별 지역 통계는 해외 접속 차단) "
                  f"예측하지 않습니다. {release} 국가 전망 {cur_y}/{str(cur_y + 1)[-2:]}: "
                  f"생산 {cur['Production'] / 1000:.1f}백만 t(전년 대비 {pct:+.0f}%), "
                  f"단수 {cur['Yield']:.2f} t/ha(전년 {prev['Yield']:.2f}). "
                  "생육 단계 판정은 이 지점의 날씨만 봅니다.")
        for key, label_ko, area in points:
            out[key] = {
                "label": f"{label_ko} ({area})",
                "label_ko": label_ko,
                "crop": crop,
                "forecast_available": False,
                "reason_ko": reason,
                "season": cur_y,
                "unit": "kg/ha",
                "last_actual": {"year": cur_y - 1, "yield": round(float(prev["Yield"]) * 1000, 1),
                                "basis": "USDA 국가 단수"},
                "usda_outlook": {"season": cur_y, "production_t": int(cur["Production"] * 1000),
                                 "yield_kg_ha": round(float(cur["Yield"]) * 1000, 1),
                                 "change_pct": round(float(pct), 1), "release": release,
                                 "url": PSD_URL},
            }
    return out


def merge_into(path, regions):
    """Add the entries to a forecast JSON already written by run_forecast."""
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    payload.setdefault("regions", {}).update(regions)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return True


def main(argv):
    if argv[:1] == ["apply"]:
        df = pd.read_csv(SLICE)
    else:
        try:
            df = fetch()
        except Exception as exc:  # keep the committed slice
            log(f"PSD fetch failed ({exc}); using {SLICE}")
            df = pd.read_csv(SLICE)
    tabs = tables(df)
    write_training(tabs)
    regions = entries(tabs, release_of(df))
    with open(REGIONS_JSON, "w", encoding="utf-8") as f:
        json.dump(regions, f, indent=1, ensure_ascii=False)
        f.write("\n")
    if merge_into(OUT, regions):
        log(f"{len(regions)} corn/soy entries -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
