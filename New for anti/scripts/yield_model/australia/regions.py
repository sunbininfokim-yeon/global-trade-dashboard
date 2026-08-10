"""Pre-registered Australian state-crop configurations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .climate import barley_features, canola_features, cotton_features, wheat_features


@dataclass(frozen=True)
class RegionCrop:
    key: str
    label: str
    label_ko: str
    crop: str
    state_sheet: str
    crop_label: str
    harvest_rule: str
    points: list[dict]
    build: Callable
    feature_sets: dict[str, list[str]]
    doc: str
    caveat: str
    start_year: int = 1982
    min_train: int = 20


def z(names: list[str]) -> list[str]:
    return [name + "_z20" for name in names]


WHEAT_WEATHER = z(["rain_growing", "heat_excess_spring", "frost_days"])
WHEAT_SOIL = WHEAT_WEATHER + z(["sm_preseason", "sm_spring"])
COTTON_WEATHER = z(["rain_flowering", "heat_excess_flowering", "harvest_rain"])
COTTON_SOIL = COTTON_WEATHER + z(["sm_preseason", "sm_flowering",
                                  "heat_dry_stress"])
BARLEY_WEATHER = z(["rain_growing", "heat_excess_reproductive",
                    "frost_exposure_reproductive"])
BARLEY_SOIL = BARLEY_WEATHER + z(["sm_preseason", "sm_reproductive"])
CANOLA_WEATHER = z(["rain_growing", "rain_flowering_pod",
                    "heat_excess_flowering_pod", "frost_exposure_flowering_pod"])
CANOLA_SOIL = CANOLA_WEATHER + z(["sm_preseason", "sm_flowering_pod"])

# Point weights are deliberately equal in phase 1.  They are sampling weights,
# not invented claims about production shares.  The next spatial-data step will
# replace them with annual crop-area weights from an Australian crop mask.
WA_POINTS = [
    {"name": "Morawa", "lat": -29.21, "lon": 116.00, "weight": 0.25},
    {"name": "Merredin", "lat": -31.48, "lon": 118.28, "weight": 0.25},
    {"name": "Katanning", "lat": -33.69, "lon": 117.56, "weight": 0.25},
    {"name": "Esperance", "lat": -33.86, "lon": 121.89, "weight": 0.25},
]
SA_POINTS = [
    {"name": "Wudinna", "lat": -33.05, "lon": 135.46, "weight": 0.25},
    {"name": "Maitland", "lat": -34.37, "lon": 137.67, "weight": 0.25},
    {"name": "Loxton", "lat": -34.45, "lon": 140.57, "weight": 0.25},
    {"name": "Bordertown", "lat": -36.31, "lon": 140.77, "weight": 0.25},
]
VIC_POINTS = [
    {"name": "Birchip", "lat": -35.98, "lon": 142.92, "weight": 1 / 3},
    {"name": "Horsham", "lat": -36.71, "lon": 142.20, "weight": 1 / 3},
    {"name": "Echuca", "lat": -36.13, "lon": 144.75, "weight": 1 / 3},
]
NSW_COTTON_POINTS = [
    {"name": "Moree", "lat": -29.46, "lon": 149.84, "weight": 0.25},
    {"name": "Narrabri", "lat": -30.33, "lon": 149.78, "weight": 0.25},
    {"name": "Warren", "lat": -31.70, "lon": 147.84, "weight": 0.25},
    {"name": "Hillston", "lat": -33.48, "lon": 145.53, "weight": 0.25},
]
QLD_COTTON_POINTS = [
    {"name": "St George", "lat": -28.04, "lon": 148.58, "weight": 0.25},
    {"name": "Dalby", "lat": -27.18, "lon": 151.26, "weight": 0.25},
    {"name": "Emerald", "lat": -23.53, "lon": 148.16, "weight": 0.25},
    {"name": "Goondiwindi", "lat": -28.55, "lon": 150.31, "weight": 0.25},
]


def wheat_sets(include_sam: bool) -> dict[str, list[str]]:
    drivers = ["iod_winter_spring_z20", "oni_winter_spring_z20"]
    if include_sam:
        drivers.append("sam_winter_spring_z20")
    return {
        "weather": WHEAT_WEATHER,
        "weather_soil": WHEAT_SOIL,
        "weather_soil_drivers": WHEAT_SOIL + drivers,
    }


def cotton_sets() -> dict[str, list[str]]:
    return {
        "weather": COTTON_WEATHER,
        "weather_soil": COTTON_SOIL,
        "weather_soil_drivers": COTTON_SOIL + ["oni_flowering_z20"],
    }


def winter_crop_sets(weather: list[str], soil: list[str], include_sam: bool) -> dict[str, list[str]]:
    drivers = ["iod_winter_spring_z20", "oni_winter_spring_z20"]
    if include_sam:
        drivers.append("sam_winter_spring_z20")
    return {"weather": weather, "weather_soil": soil,
            "weather_soil_drivers": soil + drivers}


WA_WHEAT = RegionCrop(
    key="wa_wheat", label="Western Australia wheat", label_ko="서호주 밀",
    crop="wheat", state_sheet="Western Australia", crop_label="Wheat",
    harvest_rule="winter", points=WA_POINTS, build=wheat_features,
    feature_sets=wheat_sets(include_sam=False),
    doc="Regions/호주/서호주_WA/밀/밀_상세분석_및_수식.md",
    caveat=("Phase-1 NASA POWER benchmark; PAWC/APSIM, AWRA-L, crop masks and "
            "NDVI are not yet integrated. Point weights are equal sampling weights."),
)
SA_WHEAT = RegionCrop(
    key="sa_wheat", label="South Australia wheat", label_ko="남호주 밀",
    crop="wheat", state_sheet="South Australia", crop_label="Wheat",
    harvest_rule="winter", points=SA_POINTS, build=wheat_features,
    feature_sets=wheat_sets(include_sam=True),
    doc="Regions/호주/남부_SA_VIC/밀/밀_상세분석_및_수식.md",
    caveat=("South Australia is kept separate from Victoria. SAM is an ablation "
            "feature, not assigned a forced sign or importance."),
)
VIC_WHEAT = RegionCrop(
    key="vic_wheat", label="Victoria wheat", label_ko="빅토리아 밀",
    crop="wheat", state_sheet="Victoria", crop_label="Wheat",
    harvest_rule="winter", points=VIC_POINTS, build=wheat_features,
    feature_sets=wheat_sets(include_sam=True),
    doc="Regions/호주/남부_SA_VIC/밀/밀_상세분석_및_수식.md",
    caveat=("Victoria is kept separate from South Australia. SAM effects vary "
            "by season and location and are accepted only if forward skill improves."),
)

# Barley and canola share the broad winter-crop footprint with wheat, but use
# separate reproductive-stage stress windows and validation artifacts.
WA_BARLEY = RegionCrop(
    key="wa_barley", label="Western Australia barley", label_ko="서호주 보리",
    crop="barley", state_sheet="Western Australia", crop_label="Barley",
    harvest_rule="winter", points=WA_POINTS, build=barley_features,
    feature_sets=winter_crop_sets(BARLEY_WEATHER, BARLEY_SOIL, include_sam=False),
    doc="ABARES state crop report; winter-crop climate diagnostic",
    caveat=("Crop-specific barley climate window; equal point weights and no "
            "annual crop mask. State yield labels include management effects."),
)
SA_BARLEY = RegionCrop(
    key="sa_barley", label="South Australia barley", label_ko="남호주 보리",
    crop="barley", state_sheet="South Australia", crop_label="Barley",
    harvest_rule="winter", points=SA_POINTS, build=barley_features,
    feature_sets=winter_crop_sets(BARLEY_WEATHER, BARLEY_SOIL, include_sam=True),
    doc="ABARES state crop report; winter-crop climate diagnostic",
    caveat=("Crop-specific barley climate window; equal point weights and no "
            "annual crop mask. State yield labels include management effects."),
)
VIC_BARLEY = RegionCrop(
    key="vic_barley", label="Victoria barley", label_ko="빅토리아 보리",
    crop="barley", state_sheet="Victoria", crop_label="Barley",
    harvest_rule="winter", points=VIC_POINTS, build=barley_features,
    feature_sets=winter_crop_sets(BARLEY_WEATHER, BARLEY_SOIL, include_sam=True),
    doc="ABARES state crop report; winter-crop climate diagnostic",
    caveat=("Crop-specific barley climate window; equal point weights and no "
            "annual crop mask. State yield labels include management effects."),
)
WA_CANOLA = RegionCrop(
    key="wa_canola", label="Western Australia canola", label_ko="서호주 카놀라",
    crop="canola", state_sheet="Western Australia", crop_label="Canola",
    harvest_rule="winter", points=WA_POINTS, build=canola_features,
    feature_sets=winter_crop_sets(CANOLA_WEATHER, CANOLA_SOIL, include_sam=False),
    doc="ABARES state crop report; winter-oilseed climate diagnostic",
    caveat=("Broad July-October canola flowering/pod-set window; actual flowering "
            "dates and cultivar phenology are not observed. No annual crop mask."),
)
SA_CANOLA = RegionCrop(
    key="sa_canola", label="South Australia canola", label_ko="남호주 카놀라",
    crop="canola", state_sheet="South Australia", crop_label="Canola",
    harvest_rule="winter", points=SA_POINTS, build=canola_features,
    feature_sets=winter_crop_sets(CANOLA_WEATHER, CANOLA_SOIL, include_sam=True),
    doc="ABARES state crop report; winter-oilseed climate diagnostic",
    caveat=("Broad July-October canola flowering/pod-set window; actual flowering "
            "dates and cultivar phenology are not observed. No annual crop mask."),
)
VIC_CANOLA = RegionCrop(
    key="vic_canola", label="Victoria canola", label_ko="빅토리아 카놀라",
    crop="canola", state_sheet="Victoria", crop_label="Canola",
    harvest_rule="winter", points=VIC_POINTS, build=canola_features,
    feature_sets=winter_crop_sets(CANOLA_WEATHER, CANOLA_SOIL, include_sam=True),
    doc="ABARES state crop report; winter-oilseed climate diagnostic",
    caveat=("Broad July-October canola flowering/pod-set window; actual flowering "
            "dates and cultivar phenology are not observed. No annual crop mask."),
)
NSW_COTTON = RegionCrop(
    key="nsw_cotton", label="New South Wales cotton lint", label_ko="NSW 면화",
    crop="cotton_lint", state_sheet="New South Wales", crop_label="Cotton lint a",
    harvest_rule="summer", points=NSW_COTTON_POINTS, build=cotton_features,
    feature_sets=cotton_sets(),
    doc="Regions/호주/동부_QLD_NSW/면화/면화_상세분석_및_수식.md",
    caveat=("ABARES yield is based on harvested area and mixes irrigated and "
            "dryland systems. This is a screening model until water allocations "
            "and planted area are modelled separately."),
)
QLD_COTTON = RegionCrop(
    key="qld_cotton", label="Queensland cotton lint", label_ko="QLD 면화",
    crop="cotton_lint", state_sheet="Queensland", crop_label="Cotton lint a",
    harvest_rule="summer", points=QLD_COTTON_POINTS, build=cotton_features,
    feature_sets=cotton_sets(),
    doc="Regions/호주/동부_QLD_NSW/면화/면화_상세분석_및_수식.md",
    caveat=("ABARES yield is based on harvested area and mixes irrigated and "
            "dryland systems. This is a screening model until water allocations "
            "and planted area are modelled separately."),
)

ALL = [
    WA_WHEAT, SA_WHEAT, VIC_WHEAT,
    WA_BARLEY, SA_BARLEY, VIC_BARLEY, WA_CANOLA, SA_CANOLA, VIC_CANOLA,
]
COTTON_ARCHIVE = [NSW_COTTON, QLD_COTTON]
BY_KEY = {cfg.key: cfg for cfg in ALL + COTTON_ARCHIVE}
