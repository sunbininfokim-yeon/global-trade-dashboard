"""Collect province climate windows with the existing Earth Engine login.

This module never creates credentials and never starts an authentication flow.
The caller must use the machine's existing Earth Engine authentication.
"""

import csv
import concurrent.futures
import datetime as dt
import os
import sys

import ee


PROJECT_ID = "climate-project-504313"
GAUL = "FAO/GAUL/2015/level1"
ERA5 = "ECMWF/ERA5_LAND/DAILY_AGGR"
CHIRPS = "UCSB-CHG/CHIRPS/DAILY"
SCALE_M = 11_132

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "province_climate.csv")

GAUL_TO_BPS = {
    "Nangroe Aceh Darussalam": "Aceh",
    "Kepulauan-riau": "Kepulauan Riau",
    "Daerah Istimewa Yogyakarta": "DI Yogyakarta",
    "Dki Jakarta": "DKI Jakarta",
    "Nusatenggara Barat": "Nusa Tenggara Barat",
    "Nusatenggara Timur": "Nusa Tenggara Timur",
}

YEARS = {
    # Labels currently end in 2024.  Keep 2025/2026 lag windows as inference
    # inputs only; they must never be counted as additional training seasons.
    "oil_palm": range(2001, 2027),
    "coffee": range(2016, 2024),
    "rubber": range(2007, 2024),
}


def log(message):
    print("[indonesia:gee] " + message, flush=True)


def initialize():
    """Use only the pre-existing local credentials and named cloud project."""
    ee.Initialize(project="climate-project-504313")


def provinces():
    collection = (ee.FeatureCollection(GAUL)
                  .filter(ee.Filter.eq("ADM0_NAME", "Indonesia")))
    return collection.map(lambda feature: feature.simplify(1_000))


def window_specs(crop, year):
    if crop == "oil_palm":
        return [
            ("dry_lag2", "%d-06-01" % (year - 2), "%d-11-01" % (year - 2)),
            ("dry_lag1", "%d-06-01" % (year - 1), "%d-11-01" % (year - 1)),
        ]
    if crop == "coffee":
        return [
            ("preflower", "%d-07-01" % (year - 1), "%d-10-01" % (year - 1)),
            ("flowering", "%d-10-01" % (year - 1), "%d-01-01" % year),
            ("wet_season", "%d-11-01" % (year - 1), "%d-04-01" % year),
        ]
    if crop == "rubber":
        return [
            ("dry_lag", "%d-07-01" % (year - 1), "%d-11-01" % (year - 1)),
            ("tapping", "%d-01-01" % year, "%d-05-01" % year),
        ]
    raise KeyError(crop)


def _era_daily(image):
    tmean = image.select("temperature_2m").subtract(273.15)
    tmax = image.select("temperature_2m_max").subtract(273.15)
    dew = image.select("dewpoint_temperature_2m").subtract(273.15)
    vpd = tmax.expression(
        "max(0, 0.6108 * exp(17.27 * tx / (tx + 237.3)) - "
        "0.6108 * exp(17.27 * td / (td + 237.3)))",
        {"tx": tmax, "td": dew},
    ).rename("vpd_max_kpa")
    soil = (image.select("volumetric_soil_water_layer_1").multiply(0.07)
            .add(image.select("volumetric_soil_water_layer_2").multiply(0.21))
            .add(image.select("volumetric_soil_water_layer_3").multiply(0.72))
            .rename("soil_root_m3m3"))
    solar = (image.select("surface_solar_radiation_downwards_sum")
             .divide(1_000_000).rename("solar_mj_m2_day"))
    precip = image.select("total_precipitation_sum").max(0).multiply(1_000)
    fungal = (precip.gte(1).And(tmean.gte(18)).And(tmean.lte(30))
              .rename("fungal_risk_days"))
    return (soil.addBands(vpd).addBands(tmax.rename("tmax_c"))
            .addBands(solar).addBands(fungal)
            .copyProperties(image, ["system:time_start"]))


def climate_image(start, end):
    era = ee.ImageCollection(ERA5).filterDate(start, end).map(_era_daily)
    continuous = era.select([
        "soil_root_m3m3", "vpd_max_kpa", "tmax_c", "solar_mj_m2_day",
    ]).mean()
    fungal = era.select("fungal_risk_days").sum()
    chirps = ee.ImageCollection(CHIRPS).filterDate(start, end)
    rain = chirps.select("precipitation").sum().rename("precip_mm")
    wet = (chirps.map(lambda image: image.select("precipitation").gte(1))
           .sum().rename("wet_days"))
    return continuous.addBands(fungal).addBands(rain).addBands(wet)


def collect_window(boundaries, crop, year, window, start, end, extracted_at):
    image = climate_image(start, end)
    reduced = image.reduceRegions(
        collection=boundaries,
        reducer=ee.Reducer.mean(),
        scale=SCALE_M,
        tileScale=4,
    ).getInfo()
    rows = []
    for feature in reduced["features"]:
        properties = feature["properties"]
        gaul_name = properties["ADM1_NAME"]
        province = GAUL_TO_BPS.get(gaul_name, gaul_name)
        for metric in [
                "soil_root_m3m3", "vpd_max_kpa", "tmax_c",
                "solar_mj_m2_day", "fungal_risk_days", "precip_mm",
                "wet_days"]:
            value = properties.get(metric)
            if value is None:
                raise RuntimeError(
                    "%s %s %s %s is null" % (crop, year, province, metric))
            rows.append({
                "crop": crop,
                "year": year,
                "province": province,
                "window": window,
                "window_start": start,
                "window_end_exclusive": end,
                "metric": metric,
                "value": value,
                "source": ERA5 + ";" + CHIRPS,
                "scale_m": SCALE_M,
                "extracted_at": extracted_at,
            })
    if len({row["province"] for row in rows}) != 33:
        raise RuntimeError("Expected 33 stable GAUL provinces")
    return rows


def existing_rows(refresh=False):
    if refresh or not os.path.exists(OUT):
        return [], set()
    with open(OUT, encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["year"] = int(row["year"])
        row["value"] = float(row["value"])
        row["scale_m"] = int(row["scale_m"])
    counts = {}
    for row in rows:
        key = (row["crop"], row["year"], row["window"])
        counts[key] = counts.get(key, 0) + 1
    complete = {key for key, count in counts.items() if count == 33 * 7}
    retained = [row for row in rows
                if (row["crop"], row["year"], row["window"]) in complete]
    return retained, complete


def main():
    initialize()
    boundaries = provinces()
    extracted_at = dt.datetime.now(dt.timezone.utc).isoformat()
    refresh = "--refresh" in sys.argv[1:]
    rows, complete = existing_rows(refresh=refresh)
    tasks = []
    for crop, years in YEARS.items():
        for year in years:
            for window, start, end in window_specs(crop, year):
                if (crop, year, window) not in complete:
                    tasks.append((crop, year, window, start, end))
    log("reusing %s complete rows; extracting %s windows" %
        (len(rows), len(tasks)))

    def run(task):
        crop, year, window, start, end = task
        log("start %s %s %s %s..%s" % (crop, year, window, start, end))
        result = collect_window(
            boundaries, crop, year, window, start, end, extracted_at)
        log("done %s %s %s" % (crop, year, window))
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        for result in executor.map(run, tasks):
            rows.extend(result)
    rows.sort(key=lambda row: (
        row["crop"], row["year"], row["province"], row["window"], row["metric"]))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fields = [
        "crop", "year", "province", "window", "window_start",
        "window_end_exclusive", "metric", "value", "source", "scale_m",
        "extracted_at",
    ]
    with open(OUT, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    log("wrote %s rows to %s" % (len(rows), OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
