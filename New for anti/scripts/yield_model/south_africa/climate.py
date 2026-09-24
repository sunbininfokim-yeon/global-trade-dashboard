"""Google Earth Engine seasonal climate features for the maize belt.

All Earth Engine runs use the existing local authentication and the project
specified by the repository owner. CHIRPS supplies rainfall; ERA5-Land supplies
daily maximum temperature, VPD and depth-weighted 0-100 cm soil moisture.
"""

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
    features = []
    for point in POINTS:
        geometry = ee.Geometry.Point([point["lon"], point["lat"]]).buffer(40000)
        features.append(
            ee.Feature(
                geometry,
                {
                    "name": point["name"],
                    "province": point["province"],
                    "weight": point["weight"],
                },
            )
        )
    return ee.FeatureCollection(features)


def _weighted(fc: ee.FeatureCollection, property_name: str) -> ee.Number:
    def apply(feature):
        value = ee.Number(feature.get(property_name))
        return feature.set("weighted_value", value.multiply(feature.get("weight")))

    return ee.Number(fc.map(apply).aggregate_sum("weighted_value"))


def _era_derived(image: ee.Image) -> ee.Image:
    tmax_c = image.select("temperature_2m_max").subtract(273.15)
    dew_c = image.select("dewpoint_temperature_2m").subtract(273.15)
    edd = tmax_c.subtract(29.0).max(0).rename("edd29")
    es = tmax_c.expression(
        "0.6108 * exp(17.27 * t / (t + 237.3))", {"t": tmax_c}
    )
    ea = dew_c.expression(
        "0.6108 * exp(17.27 * t / (t + 237.3))", {"t": dew_c}
    )
    vpd = es.subtract(ea).max(0).rename("vpd")
    root_sm = image.expression(
        "0.07*l1 + 0.21*l2 + 0.72*l3",
        {
            "l1": image.select("volumetric_soil_water_layer_1"),
            "l2": image.select("volumetric_soil_water_layer_2"),
            "l3": image.select("volumetric_soil_water_layer_3"),
        },
    ).rename("root_sm")
    return ee.Image.cat([edd, vpd, root_sm]).copyProperties(
        image, ["system:time_start"]
    )


def _season_feature(year: ee.Number, zones: ee.FeatureCollection) -> ee.Feature:
    year = ee.Number(year).toInt()
    chirps = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
    era = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR").map(_era_derived)

    planting_start = ee.Date.fromYMD(year.subtract(1), 10, 1)
    planting_end = ee.Date.fromYMD(year, 1, 1)
    critical_start = ee.Date.fromYMD(year, 1, 1)
    critical_end = ee.Date.fromYMD(year, 3, 1)

    stack = ee.Image.cat(
        [
            chirps.filterDate(planting_start, planting_end)
            .sum()
            .rename("rain_planting_mm"),
            chirps.filterDate(critical_start, critical_end)
            .sum()
            .rename("rain_critical_mm"),
            era.filterDate(critical_start, critical_end)
            .select("edd29")
            .sum()
            .rename("edd29_critical_c_days"),
            era.filterDate(critical_start, critical_end)
            .select("root_sm")
            .mean()
            .rename("root_sm_critical"),
            era.filterDate(critical_start, critical_end)
            .select("vpd")
            .mean()
            .rename("vpd_critical_kpa"),
        ]
    )
    reduced = stack.reduceRegions(
        collection=zones, reducer=ee.Reducer.mean(), scale=10000, tileScale=2
    )
    properties = {"year": year}
    for name in (
        "rain_planting_mm",
        "rain_critical_mm",
        "edd29_critical_c_days",
        "root_sm_critical",
        "vpd_critical_kpa",
    ):
        properties[name] = _weighted(reduced, name)
    return ee.Feature(None, properties)


def collect_seasonal(
    start_year: int = 1982,
    end_year: int = None,
    refresh: bool = False,
) -> pd.DataFrame:
    end_year = end_year or date.today().year
    CACHE.mkdir(parents=True, exist_ok=True)
    # Dated so a same-day rerun is free but the next run re-reads the current
    # season (the old undated name returned August's partial season forever).
    target = CACHE / f"gee_maize_belt_v2_{start_year}_{end_year}_{date.today().isoformat()}.csv"
    if target.exists() and not refresh:
        return pd.read_csv(target)
    initialize_ee()
    zones = _zones()
    frame = gee_live.collect_incremental(
        lambda year: _season_feature(ee.Number(year), zones).getInfo()["properties"],
        start_year,
        end_year,
        HERE / "training" / "commercial_maize_belt.csv",
        refresh=refresh,
    )
    frame.to_csv(target, index=False)
    return frame


if __name__ == "__main__":
    print(collect_seasonal().tail().to_string(index=False))
