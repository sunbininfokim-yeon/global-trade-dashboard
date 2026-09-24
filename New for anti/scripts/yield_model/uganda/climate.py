"""Earth Engine climate features for Uganda's Robusta and Arabica belts."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import ee
import pandas as pd

import gee_live

from .regions import POINTS

PROJECT = "climate-project-504313"
HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"


def initialize_ee() -> None:
    gee_live.initialize(ee, PROJECT)


def _zones() -> ee.FeatureCollection:
    return ee.FeatureCollection(
        [
            ee.Feature(
                ee.Geometry.Point([point["lon"], point["lat"]]).buffer(30000),
                {
                    "name": point["name"],
                    "zone": point["zone"],
                    "species": point["species"],
                    "weight": point["weight"],
                },
            )
            for point in POINTS
        ]
    )


def _weighted(fc: ee.FeatureCollection, property_name: str) -> ee.Number:
    def apply(feature):
        return feature.set(
            "weighted_value",
            ee.Number(feature.get(property_name)).multiply(feature.get("weight")),
        )

    return ee.Number(fc.map(apply).aggregate_sum("weighted_value"))


def _era_derived(image: ee.Image) -> ee.Image:
    tmax = image.select("temperature_2m_max").subtract(273.15)
    dew = image.select("dewpoint_temperature_2m").subtract(273.15)
    hot28 = tmax.subtract(28.0).max(0).rename("hot28")
    es = tmax.expression("0.6108 * exp(17.27*t/(t+237.3))", {"t": tmax})
    ea = dew.expression("0.6108 * exp(17.27*t/(t+237.3))", {"t": dew})
    vpd = es.subtract(ea).max(0).rename("vpd")
    root_sm = image.expression(
        "0.07*l1 + 0.21*l2 + 0.72*l3",
        {
            "l1": image.select("volumetric_soil_water_layer_1"),
            "l2": image.select("volumetric_soil_water_layer_2"),
            "l3": image.select("volumetric_soil_water_layer_3"),
        },
    ).rename("root_sm")
    return ee.Image.cat([hot28, vpd, root_sm]).copyProperties(
        image, ["system:time_start"]
    )


def _season_feature(year: int, zones: ee.FeatureCollection) -> dict:
    chirps = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
    era = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR").map(_era_derived)
    short_start = ee.Date.fromYMD(year - 1, 10, 1)
    short_end = ee.Date.fromYMD(year, 1, 1)
    long_start = ee.Date.fromYMD(year, 3, 1)
    long_end = ee.Date.fromYMD(year, 6, 1)
    dry_start = ee.Date.fromYMD(year, 6, 1)
    dry_end = ee.Date.fromYMD(year, 8, 1)
    cycle_end = dry_end
    stack = ee.Image.cat(
        [
            chirps.filterDate(short_start, short_end).sum().rename("rain_short_rains_mm"),
            chirps.filterDate(long_start, long_end).sum().rename("rain_long_rains_mm"),
            chirps.filterDate(dry_start, dry_end).sum().rename("rain_jun_jul_mm"),
            era.filterDate(short_start, cycle_end).select("hot28").sum().rename("hot28_edd_c_days"),
            era.filterDate(long_start, long_end).select("root_sm").mean().rename("root_sm_long_rains"),
            era.filterDate(long_start, long_end).select("vpd").mean().rename("vpd_long_rains_kpa"),
        ]
    )
    reduced = stack.reduceRegions(
        collection=zones, reducer=ee.Reducer.mean(), scale=10000, tileScale=2
    )
    names = [
        "rain_short_rains_mm",
        "rain_long_rains_mm",
        "rain_jun_jul_mm",
        "hot28_edd_c_days",
        "root_sm_long_rains",
        "vpd_long_rains_kpa",
    ]
    feature = ee.Feature(
        None,
        {"year": year, **{name: _weighted(reduced, name) for name in names}},
    )
    return feature.getInfo()["properties"]


def collect_seasonal(
    start_year: int = 1982, end_year: int = None, refresh: bool = False
) -> pd.DataFrame:
    end_year = end_year or date.today().year
    CACHE.mkdir(parents=True, exist_ok=True)
    # Dated so a same-day rerun is free but the next run re-reads the current
    # season (the old undated name returned August's partial season forever).
    target = CACHE / f"gee_uganda_coffee_v1_{start_year}_{end_year}_{date.today().isoformat()}.csv"
    if target.exists() and not refresh:
        return pd.read_csv(target)
    initialize_ee()
    zones = _zones()
    frame = gee_live.collect_incremental(
        lambda year: _season_feature(year, zones),
        start_year,
        end_year,
        HERE / "training" / "national_coffee_belt.csv",
        refresh=refresh,
    )
    frame.to_csv(target, index=False)
    return frame


if __name__ == "__main__":
    print(collect_seasonal().tail().to_string(index=False))
