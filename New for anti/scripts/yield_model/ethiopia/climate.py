"""GEE seasonal climate features for Ethiopia's coffee regions."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import ee
import pandas as pd

from .regions import POINTS

PROJECT = "climate-project-504313"
HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"


def initialize_ee() -> None:
    ee.Initialize(project=PROJECT)


def latest_source_dates() -> dict:
    """Return source coverage dates so partial current windows are not drought."""
    initialize_ee()
    out = {}
    for key, dataset in {
        "chirps": "UCSB-CHG/CHIRPS/DAILY",
        "era5_land": "ECMWF/ERA5_LAND/DAILY_AGGR",
    }.items():
        image = ee.ImageCollection(dataset).sort("system:time_start", False).first()
        out[key] = ee.Date(image.get("system:time_start")).format("YYYY-MM-dd").getInfo()
    return out


def _zones() -> ee.FeatureCollection:
    return ee.FeatureCollection([
        ee.Feature(ee.Geometry.Point([p["lon"], p["lat"]]).buffer(25000), {"name": p["name"], "region": p["region"], "weight": p["weight"]})
        for p in POINTS
    ])


def _weighted(fc: ee.FeatureCollection, name: str) -> ee.Number:
    weighted = fc.map(lambda f: f.set("wv", ee.Number(f.get(name)).multiply(f.get("weight"))))
    return ee.Number(weighted.aggregate_sum("wv")).divide(weighted.aggregate_sum("weight"))


def _era_derived(image: ee.Image) -> ee.Image:
    tmax = image.select("temperature_2m_max").subtract(273.15)
    dew = image.select("dewpoint_temperature_2m").subtract(273.15)
    hot30 = tmax.subtract(30).max(0).rename("hot30")
    es = tmax.expression("0.6108*exp(17.27*t/(t+237.3))", {"t": tmax})
    ea = dew.expression("0.6108*exp(17.27*t/(t+237.3))", {"t": dew})
    vpd = es.subtract(ea).max(0).rename("vpd")
    root_sm = image.expression("0.07*l1 + 0.21*l2 + 0.72*l3", {
        "l1": image.select("volumetric_soil_water_layer_1"),
        "l2": image.select("volumetric_soil_water_layer_2"),
        "l3": image.select("volumetric_soil_water_layer_3"),
    }).rename("root_sm")
    return ee.Image.cat([hot30, vpd, root_sm]).copyProperties(image, ["system:time_start"])


def _season_feature(year: int, zones: ee.FeatureCollection) -> dict:
    chirps = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
    era = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR").map(_era_derived)
    prev_start, prev_end = ee.Date.fromYMD(year - 1, 8, 1), ee.Date.fromYMD(year, 1, 1)
    flower_start, flower_end = ee.Date.fromYMD(year, 3, 1), ee.Date.fromYMD(year, 6, 1)
    fill_start, fill_end = ee.Date.fromYMD(year, 6, 1), ee.Date.fromYMD(year, 8, 1)
    season_start, season_end = flower_start, fill_end
    stack = ee.Image.cat([
        chirps.filterDate(prev_start, prev_end).sum().rename("rain_prev_aug_dec_mm"),
        chirps.filterDate(flower_start, flower_end).sum().rename("rain_flowering_mar_may_mm"),
        chirps.filterDate(fill_start, fill_end).sum().rename("rain_filling_jun_jul_mm"),
        era.filterDate(season_start, season_end).select("hot30").sum().rename("hot30_mar_jul_c_days"),
        era.filterDate(season_start, season_end).select("root_sm").mean().rename("root_sm_mar_jul"),
        era.filterDate(season_start, season_end).select("vpd").mean().rename("vpd_mar_jul_kpa"),
    ])
    reduced = stack.reduceRegions(collection=zones, reducer=ee.Reducer.mean(), scale=10000, tileScale=2)
    names = ["rain_prev_aug_dec_mm", "rain_flowering_mar_may_mm", "rain_filling_jun_jul_mm", "hot30_mar_jul_c_days", "root_sm_mar_jul", "vpd_mar_jul_kpa"]
    return ee.Feature(None, {"year": year, **{name: _weighted(reduced, name) for name in names}}).getInfo()["properties"]


def collect_seasonal(start_year: int = 1993, end_year: int = None, refresh: bool = False) -> pd.DataFrame:
    end_year = end_year or date.today().year
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / f"gee_ethiopia_coffee_v1_{start_year}_{end_year}.csv"
    if target.exists() and not refresh:
        return pd.read_csv(target)
    initialize_ee(); zones = _zones()
    checkpoint = CACHE / f"gee_ethiopia_coffee_v1_{start_year}_{end_year}.partial.csv"
    records = [] if refresh or not checkpoint.exists() else pd.read_csv(checkpoint).to_dict("records")
    completed = {int(record["year"]) for record in records}
    for year in range(start_year, end_year + 1):
        if year not in completed:
            records.append(_season_feature(year, zones))
            pd.DataFrame(records).sort_values("year").to_csv(checkpoint, index=False)
        if (year - start_year + 1) % 5 == 0 or year == end_year:
            print(f"[climate] Earth Engine seasons through {year}", flush=True)
    frame = pd.DataFrame(records).sort_values("year").reset_index(drop=True)
    frame.to_csv(target, index=False); checkpoint.unlink(missing_ok=True)
    return frame


if __name__ == "__main__":
    print(collect_seasonal().tail().to_string(index=False))
