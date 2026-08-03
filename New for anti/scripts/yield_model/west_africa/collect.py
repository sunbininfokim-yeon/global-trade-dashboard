"""Collect and normalize West Africa cocoa labels and climate screening data."""

import argparse
import csv
from pathlib import Path

from .catalog import write_catalog
from .data import (
    civ_regional_cocoa,
    faostat_cocoa,
    ghana_regional_purchases,
    power_daily,
    write_rows,
)
from .features import cocoa_year_features, weighted_country_features
from .regions import POINTS, points_for


HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
TRAINING = HERE / "training"


def log(message):
    print("[west-africa:collect] " + message, flush=True)


def wide_faostat(rows):
    records = {}
    names = {
        "Area harvested": ("area_ha", "area_flag"),
        "Yield": ("yield_kg_ha", "yield_flag"),
        "Production": ("production_tonnes", "production_flag"),
    }
    for row in rows:
        record = records.setdefault(
            (row["country"], row["year"]),
            {"country": row["country"], "year": row["year"], "source": "FAOSTAT"})
        value_name, flag_name = names[row["element"]]
        record[value_name] = row["value"]
        record[flag_name] = row["flag"]
    return [records[key] for key in sorted(records)]


def country_purchase_totals(rows):
    totals = {}
    for row in rows:
        key = (row["country"], row["crop_year"], row["year"])
        totals[key] = totals.get(key, 0.0) + row["value_tonnes"]
    return [{
        "country": country, "crop_year": crop_year, "year": year,
        "purchases_tonnes": value, "source": "Ghana Cocoa Board regional sum",
    } for (country, crop_year, year), value in sorted(totals.items())]


def merge_by_country_year(labels, climate, label_name):
    indexed = {(row["country"], int(row["year"])): row for row in labels}
    output = []
    for feature in climate:
        row = dict(feature)
        label = indexed.get((row["country"], int(row["year"])), {})
        for name, value in label.items():
            if name not in {"country", "year"}:
                row[name] = value
        row["label_alignment"] = label_name
        output.append(row)
    return output


def collect_labels(refresh=False):
    write_catalog(DATA)
    fao_long = faostat_cocoa(refresh=refresh)
    fao_wide = wide_faostat(fao_long)
    civ = civ_regional_cocoa(refresh=refresh)
    ghana = ghana_regional_purchases(refresh=refresh)
    write_rows(DATA / "faostat_cocoa_long.csv", fao_long)
    write_rows(DATA / "faostat_cocoa_country_year.csv", fao_wide)
    write_rows(DATA / "civ_regional_cocoa.csv", civ)
    write_rows(DATA / "ghana_regional_purchases.csv", ghana)
    write_rows(DATA / "ghana_country_purchases.csv", country_purchase_totals(ghana))
    log("labels: {} FAOSTAT country-years, {} CIV region-years, {} Ghana region-years".format(
        len(fao_wide), len(civ), len(ghana)))
    return fao_wide, civ, ghana


def collect_climate(refresh=False):
    all_country_features = []
    for country in {point["country"] for point in POINTS}:
        point_frames = {}
        for point in points_for(country):
            log("POWER {} / {}".format(country, point["region"]))
            daily = power_daily(point, refresh=refresh)
            features = []
            for year in range(1982, 2027):
                row = cocoa_year_features(daily, year)
                if row:
                    features.append(row)
            point_frames[point["region"]] = features
            output = [dict({"country": country, "region": point["region"]}, **row)
                      for row in features]
            write_rows(DATA / "climate_points" / (country + "_" + point["region"] + ".csv"), output)
        combined = weighted_country_features(point_frames, points_for(country))
        all_country_features.extend(combined)
    write_rows(DATA / "cocoa_country_climate.csv", all_country_features)
    return all_country_features


def build_training(fao_wide, ghana_rows, climate):
    fao_training = merge_by_country_year(
        fao_wide, climate,
        "provisional: FAOSTAT calendar year joined to cocoa year ending September")
    write_rows(TRAINING / "cocoa_faostat_country.csv", fao_training)
    ghana_totals = country_purchase_totals(ghana_rows)
    ghana_climate = [row for row in climate if row["country"] == "Ghana"]
    purchases_training = merge_by_country_year(
        ghana_totals, ghana_climate,
        "COCOBOD crop year joined to its ending year; purchases are not biological yield")
    write_rows(TRAINING / "ghana_cocoa_purchases.csv", purchases_training)
    purchases_index = {(row["region"], int(row["year"])): row for row in ghana_rows}
    regional_training = []
    for point in points_for("Ghana"):
        path = DATA / "climate_points" / ("Ghana_" + point["region"] + ".csv")
        for feature in read_csv(path):
            key = (point["region"], int(feature["year"]))
            label = purchases_index.get(key)
            if not label:
                continue
            row = dict(feature)
            row["purchases_tonnes"] = label["value_tonnes"]
            row["crop_year"] = label["crop_year"]
            row["label_source"] = label["source"]
            row["label_alignment"] = (
                "COCOBOD region/crop-year joined to the ending year; purchases are not yield")
            regional_training.append(row)
    write_rows(TRAINING / "ghana_cocoa_regional_purchases.csv", regional_training)


def read_csv(path):
    with Path(path).open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--climate", action="store_true",
                        help="also download NASA POWER at all cocoa sampling points")
    args = parser.parse_args(argv)
    fao_wide, _, ghana = collect_labels(refresh=args.refresh)
    if args.climate:
        climate = collect_climate(refresh=args.refresh)
        build_training(fao_wide, ghana, climate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
