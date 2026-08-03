"""Machine-readable catalogue of data sources relevant to West African cocoa."""

from dataclasses import asdict, dataclass
import csv
import json
from pathlib import Path


@dataclass(frozen=True)
class Source:
    key: str
    layer: str
    provider_region: str
    provider: str
    geography: str
    variables: str
    coverage: str
    resolution: str
    access: str
    auth: str
    pipeline_status: str
    url: str
    limitation: str


SOURCES = [
    Source(
        "civ_ccc_regional", "production", "Africa", "Conseil Café-Cacao / data.gouv.ci",
        "Côte d'Ivoire administrative regions", "cocoa and coffee production tonnes",
        "2022-2023", "region-year", "open Data Fair JSON API", "none", "implemented",
        "https://data.gouv.ci/data-fair/api/v1/datasets/"
        "repartition-de-la-production-de-cafe-et-cacao-par-region-administrative-en-tonnes/lines",
        "Only two regional seasons; useful for current spatial weights, not regional training."),
    Source(
        "ghana_cocobod_purchases", "purchases", "Africa", "Ghana Cocoa Board",
        "Ghana cocoa-growing regions", "graded and sealed cocoa purchases tonnes",
        "historical crop years shown on live table", "region-crop-year", "public HTML table",
        "none", "implemented", "https://cocobod.gh/cocoa-purchases",
        "Purchases are a market-receipt label, not farm biological yield; region definitions change."),
    Source(
        "ghana_mofa_facts", "production", "Africa", "Ghana MoFA SRID",
        "Ghana country, region and district", "crop area, production, yield, rain, soils, prices",
        "annual series begun in 1991; latest report 2024", "mixed", "annual PDF", "none",
        "catalogued", "https://srid.mofa.gov.gh/node/49",
        "Tables mix survey and secondary sources; cocoa details often come from COCOBOD."),
    Source(
        "faostat_cocoa", "production", "Global/UN", "FAOSTAT",
        "Côte d'Ivoire and Ghana", "harvested area, yield, production, quality flags",
        "1961-present", "country-year", "bulk CSV", "none", "implemented",
        "https://bulks-faostat.fao.org/production/",
        "National annual series smooths regional shocks and recent values may be estimated."),
    Source(
        "usda_fas", "production_trade", "United States", "USDA Foreign Agricultural Service",
        "Côte d'Ivoire and Ghana", "marketing-year production, exports, policy and crop reports",
        "report-dependent", "country-marketing-year", "PSD/GAIN reports", "none or optional key",
        "catalogued", "https://www.fas.usda.gov/data",
        "Forecasts and analyst estimates must be kept separate from final observations."),
    Source(
        "icco", "market_balance", "International", "International Cocoa Organization",
        "major producing and consuming countries", "production, grindings, stocks, prices, trade",
        "public last three cocoa years; detailed history from 1960 is subscription",
        "country-cocoa-year/quarter", "web tables and paid QBCS", "none/payment", "catalogued",
        "https://www.icco.org/app/statistics/",
        "The public page is insufficient as a long historical training label."),
    Source(
        "nasa_power", "climate", "United States", "NASA POWER",
        "global points", "rain, temperature, humidity, dewpoint, wind, radiation, root wetness",
        "1981-present", "daily, about 0.5 degree", "JSON API", "none", "implemented",
        "https://power.larc.nasa.gov/api/temporal/daily/point",
        "Coarse reanalysis grid; use as a reproducible screen rather than a farm measurement."),
    Source(
        "chirps", "rainfall", "United States", "UCSB Climate Hazards Center / USGS",
        "global land, strong Africa use", "precipitation", "1981-present", "0.05 degree daily",
        "download or Earth Engine", "Earth Engine for EE route", "earth_engine_optional",
        "https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY",
        "Rainfall only; compare with gauges or ERA5 rather than treating it as truth."),
    Source(
        "era5_land", "climate_soil_water", "Europe", "ECMWF / Copernicus C3S",
        "global land", "rain, temperature, radiation, evaporation, four-layer soil water",
        "1950-present", "hourly, 0.1 degree", "CDS API or Earth Engine", "CDS credentials or EE",
        "earth_engine_optional",
        "https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land",
        "Modelled land state; uncertainty grows in earlier decades and sparse-observation regions."),
    Source(
        "cams_eac4", "dust", "Europe", "Copernicus Atmosphere Monitoring Service",
        "global", "dust aerosol optical depth, dust mass, humidity, wind",
        "2003-2025", "3-hourly, 0.75 degree", "Atmosphere Data Store API", "ADS credentials",
        "catalogued", "https://ads.atmosphere.copernicus.eu/datasets/cams-global-reanalysis-eac4",
        "Four-to-six-month latency; use CAMS, not ERA5, for explicit dust variables."),
    Source(
        "fao_wapor", "water_vegetation", "Europe/UN", "FAO WaPOR",
        "Africa", "ET, precipitation, relative soil moisture, biomass, phenology, land cover",
        "product-dependent", "300 m global and 100 m Africa; dekadal to annual",
        "WaPOR v3 API", "none", "catalogued",
        "https://www.fao.org/in-action/remote-sensing-for-water-productivity/wapor-data/en",
        "Satellite-derived layers require a cocoa mask and cannot by themselves identify yield."),
    Source(
        "sentinel_2", "land_vegetation", "Europe", "EU/ESA Copernicus",
        "global", "surface reflectance, red edge, NDVI/EVI and canopy condition",
        "2017-present SR", "10-20 m, 5-day revisit", "Earth Engine/CDSE", "EE/CDSE account",
        "earth_engine_optional",
        "https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED",
        "Cloud cover is severe; cocoa classification needs labelled polygons and uncertainty."),
    Source(
        "sentinel_1", "land_structure", "Europe", "EU/ESA Copernicus",
        "global", "C-band SAR VV/VH backscatter and canopy structure proxy",
        "2014-present", "10-40 m, 6-day revisit", "Earth Engine/CDSE", "EE/CDSE account",
        "earth_engine_optional",
        "https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S1_GRD",
        "SAR reduces cloud limitations but does not uniquely distinguish cocoa from other tree crops."),
    Source(
        "smap_l4", "soil_water", "United States", "NASA/NSIDC",
        "global", "surface and 0-100 cm root-zone soil moisture, ET, net radiation",
        "2015-present", "3-hourly, 9 km", "Earth Engine", "EE account",
        "earth_engine_optional",
        "https://developers.google.com/earth-engine/datasets/catalog/NASA_SMAP_SPL4SMGP_008",
        "Short satellite-era record; outages include model-only periods."),
    Source(
        "cocoa_map_2020", "cocoa_area", "Africa/Europe", "PANGAEA / JRC-led research",
        "Côte d'Ivoire and Ghana", "10 m cocoa presence map",
        "single published map vintage", "10 m", "public GeoTIFF download", "none", "catalogued",
        "https://doi.pangaea.de/10.1594/PANGAEA.917473",
        "Producer accuracy exceeded user accuracy; a single vintage cannot measure annual area change."),
    Source(
        "hansen_gfc", "forest_change", "United States", "University of Maryland / Google",
        "global", "tree cover 2000 and annual tree-cover loss",
        "2000-2025", "30 m annual loss", "Earth Engine", "EE account",
        "earth_engine_optional",
        "https://developers.google.com/earth-engine/datasets/catalog/"
        "UMD_hansen_global_forest_change_2025_v1_13",
        "Tree-cover loss is not automatically EUDR deforestation or cocoa causation."),
]


def write_catalog(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    rows = [asdict(source) for source in SOURCES]
    (directory / "source_catalog.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (directory / "source_catalog.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return rows
