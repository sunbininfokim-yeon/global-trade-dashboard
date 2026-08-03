"""Transparent climate summaries for cocoa-year data feasibility tests."""

from datetime import datetime
import math


def _vpd(tmax, tdew):
    saturation = 0.6108 * math.exp(17.27 * tmax / (tmax + 237.3))
    actual = 0.6108 * math.exp(17.27 * tdew / (tdew + 237.3))
    return max(0.0, saturation - actual)


def _mean(values):
    return sum(values) / len(values) if values else None


def _longest_dry_spell(rows, threshold=1.0):
    longest = current = 0
    for row in sorted(rows, key=lambda item: item["date"]):
        if row["PRECTOTCORR"] < threshold:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def cocoa_year_features(daily_rows, harvest_year):
    """Summarize Oct(Y-1)-Sep(Y) without claiming a calibrated disease loss."""
    parsed = []
    for row in daily_rows:
        day = datetime.strptime(row["date"], "%Y%m%d").date()
        copy = dict(row)
        copy["date"] = day
        parsed.append(copy)
    season = [row for row in parsed if (
        (row["date"].year == harvest_year - 1 and row["date"].month >= 10) or
        (row["date"].year == harvest_year and row["date"].month <= 9))]
    harmattan = [row for row in season if row["date"].month in {12, 1, 2, 3}]
    wet = [row for row in season if row["date"].month in {4, 5, 6, 7}]
    if len(season) < 330 or len(harmattan) < 100 or len(wet) < 100:
        return None
    return {
        "year": harvest_year,
        "cocoa_year_rain_mm": sum(row["PRECTOTCORR"] for row in season),
        "cocoa_year_root_wetness": _mean([row["GWETROOT"] for row in season]),
        "cocoa_year_solar": _mean([row["ALLSKY_SFC_SW_DWN"] for row in season]),
        "max_dry_spell_days": _longest_dry_spell(season),
        "harmattan_rain_mm": sum(row["PRECTOTCORR"] for row in harmattan),
        "harmattan_rh_mean": _mean([row["RH2M"] for row in harmattan]),
        "harmattan_vpd_mean": _mean([_vpd(row["T2M_MAX"], row["T2MDEW"])
                                      for row in harmattan]),
        "harmattan_wind_mean": _mean([row["WS10M"] for row in harmattan]),
        "harmattan_root_wetness": _mean([row["GWETROOT"] for row in harmattan]),
        "wet_season_rain_mm": sum(row["PRECTOTCORR"] for row in wet),
        "wet_days_ge_10mm": sum(row["PRECTOTCORR"] >= 10 for row in wet),
        "humid_wet_days_proxy": sum(
            row["PRECTOTCORR"] >= 1 and row["RH2M"] >= 80 for row in wet),
        "wet_season_root_wetness": _mean([row["GWETROOT"] for row in wet]),
    }


def weighted_country_features(point_frames, points):
    """Aggregate already-derived point features using recent production weights."""
    point_by_region = {point["region"]: point for point in points}
    years = sorted(set.intersection(*(
        {row["year"] for row in rows} for rows in point_frames.values())))
    output = []
    for year in years:
        rows = {region: next(row for row in values if row["year"] == year)
                for region, values in point_frames.items()}
        total_weight = sum(point_by_region[region]["weight"] for region in rows)
        combined = {"country": points[0]["country"], "year": year,
                    "weight_basis": "recent official regional cocoa volume"}
        feature_names = [name for name in next(iter(rows.values())) if name != "year"]
        for name in feature_names:
            combined[name] = sum(
                rows[region][name] * point_by_region[region]["weight"]
                for region in rows) / total_weight
        output.append(combined)
    return output
