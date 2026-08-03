"""Earth Engine inventory and reusable cocoa-monitoring inputs.

Authentication is intentionally external. This module only uses the existing
local credentials and always initializes the user-specified Cloud project.
"""

import json
from pathlib import Path

import ee


PROJECT = "climate-project-504313"
AOIS = {
    "Côte d'Ivoire": [-8.7, 4.2, -2.4, 10.8],
    "Ghana": [-3.4, 4.6, 1.3, 11.3],
}
COLLECTIONS = {
    "sentinel_2_sr": "COPERNICUS/S2_SR_HARMONIZED",
    "sentinel_1_grd": "COPERNICUS/S1_GRD",
    "smap_l4": "NASA/SMAP/SPL4SMGP/008",
    "chirps_daily": "UCSB-CHG/CHIRPS/DAILY",
    "era5_land_daily": "ECMWF/ERA5_LAND/DAILY_AGGR",
}
HANSEN = "UMD/hansen/global_forest_change_2025_v1_13"


def initialize():
    ee.Initialize(project="climate-project-504313")


def _geometry(country):
    return ee.Geometry.Rectangle(AOIS[country], proj=None, geodesic=False)


def probe(output_path=None):
    """Verify collection access over both countries with one server request."""
    initialize()
    checks = {}
    for country in AOIS:
        aoi = _geometry(country)
        for name, asset in COLLECTIONS.items():
            collection = ee.ImageCollection(asset).filterBounds(aoi)
            if name in {"sentinel_2_sr", "sentinel_1_grd"}:
                collection = collection.filterDate("2024-01-01", "2025-01-01")
            elif name == "smap_l4":
                collection = collection.filterDate("2024-01-01", "2024-02-01")
            elif name in {"chirps_daily", "era5_land_daily"}:
                collection = collection.filterDate("2024-01-01", "2024-02-01")
            checks["{}:{}".format(country, name)] = collection.size()
    checks["hansen_band_count"] = ee.Image(HANSEN).bandNames().size()
    result = ee.Dictionary(checks).getInfo()
    result = {
        "project": PROJECT,
        "initialized": True,
        "checks": result,
        "interpretation": (
            "Positive counts prove catalogue access only. Cocoa mapping still requires "
            "a validated cocoa mask or labelled farm polygons."
        ),
    }
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def monitoring_stack(country, start, end, cocoa_mask_asset=None):
    """Return complementary land, vegetation and water layers for one period.

    The result is not a cocoa classifier. If cocoa_mask_asset is omitted, the
    image covers the whole national AOI and must not be interpreted as cocoa.
    """
    initialize()
    aoi = _geometry(country)

    def mask_s2(image):
        scl = image.select("SCL")
        clear = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
        return image.updateMask(clear).divide(10000)

    s2 = (ee.ImageCollection(COLLECTIONS["sentinel_2_sr"])
          .filterBounds(aoi).filterDate(start, end).map(mask_s2))
    optical = s2.median()
    ndvi = optical.normalizedDifference(["B8", "B4"]).rename("s2_ndvi")
    ndmi = optical.normalizedDifference(["B8", "B11"]).rename("s2_ndmi")

    s1 = (ee.ImageCollection(COLLECTIONS["sentinel_1_grd"])
          .filterBounds(aoi).filterDate(start, end)
          .filter(ee.Filter.eq("instrumentMode", "IW"))
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH")))
    radar = s1.select(["VV", "VH"]).median().rename(["s1_vv", "s1_vh"])

    smap = (ee.ImageCollection(COLLECTIONS["smap_l4"])
            .filterBounds(aoi).filterDate(start, end)
            .select("sm_rootzone").mean().rename("smap_rootzone"))
    rain = (ee.ImageCollection(COLLECTIONS["chirps_daily"])
            .filterBounds(aoi).filterDate(start, end)
            .select("precipitation").sum().rename("chirps_rain"))
    stack = ee.Image.cat([ndvi, ndmi, radar, smap, rain]).clip(aoi)
    if cocoa_mask_asset:
        stack = stack.updateMask(ee.Image(cocoa_mask_asset).gt(0))
    return stack


if __name__ == "__main__":
    output = Path(__file__).resolve().parent / "data" / "earth_engine_status.json"
    print(json.dumps(probe(output), ensure_ascii=False, indent=2))
