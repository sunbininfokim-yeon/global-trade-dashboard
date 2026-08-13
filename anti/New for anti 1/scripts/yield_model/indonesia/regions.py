"""Indonesia crop configurations and crop-specific climate mechanisms."""

from dataclasses import dataclass, field
from typing import Callable, List

from . import climate as C


@dataclass
class CropConfig:
    key: str
    label: str
    label_ko: str
    faostat_item: str
    points: list
    build: Callable
    core: List[str]
    area_core: List[str] = field(default_factory=list)
    critical_window: list = field(default_factory=list)
    doc: str = ""
    caveat: str = ""
    non_weather_drivers: str = ""


RICE_POINTS = [
    {"name": "Indramayu_West_Java", "lat": -6.33, "lon": 108.32, "weight": 0.24},
    {"name": "Grobogan_Central_Java", "lat": -7.02, "lon": 110.92, "weight": 0.23},
    {"name": "Ngawi_East_Java", "lat": -7.40, "lon": 111.45, "weight": 0.25},
    {"name": "Sidrap_South_Sulawesi", "lat": -3.93, "lon": 119.78, "weight": 0.16},
    {"name": "Banyuasin_South_Sumatra", "lat": -2.88, "lon": 104.38, "weight": 0.12},
]

PALM_POINTS = [
    {"name": "Riau", "lat": 0.50, "lon": 101.45, "weight": 0.25},
    {"name": "North_Sumatra", "lat": 3.10, "lon": 99.50, "weight": 0.18},
    {"name": "South_Sumatra", "lat": -3.00, "lon": 104.70, "weight": 0.17},
    {"name": "Jambi", "lat": -1.60, "lon": 103.60, "weight": 0.13},
    {"name": "West_Kalimantan", "lat": -0.20, "lon": 110.20, "weight": 0.12},
    {"name": "Central_Kalimantan", "lat": -1.70, "lon": 113.40, "weight": 0.15},
]

COFFEE_POINTS = [
    {"name": "Lampung", "lat": -5.10, "lon": 104.30, "weight": 0.27},
    {"name": "South_Sumatra_Coffee", "lat": -4.00, "lon": 103.20, "weight": 0.23},
    {"name": "Aceh_Gayo", "lat": 4.60, "lon": 96.85, "weight": 0.14},
    {"name": "North_Sumatra_Coffee", "lat": 2.60, "lon": 98.70, "weight": 0.14},
    {"name": "East_Java_Coffee", "lat": -7.95, "lon": 113.85, "weight": 0.12},
    {"name": "South_Sulawesi_Coffee", "lat": -3.10, "lon": 119.85, "weight": 0.10},
]

RUBBER_POINTS = [
    {"name": "South_Sumatra_Rubber", "lat": -3.10, "lon": 104.20, "weight": 0.31},
    {"name": "North_Sumatra_Rubber", "lat": 2.90, "lon": 99.20, "weight": 0.18},
    {"name": "Riau_Rubber", "lat": 0.20, "lon": 101.30, "weight": 0.14},
    {"name": "Jambi_Rubber", "lat": -1.70, "lon": 103.30, "weight": 0.14},
    {"name": "West_Kalimantan_Rubber", "lat": 0.10, "lon": 110.00, "weight": 0.13},
    {"name": "South_Kalimantan_Rubber", "lat": -2.70, "lon": 115.30, "weight": 0.10},
]


def build_rice(daily, year):
    main = [(10, -1), (11, -1), (12, -1), (1, 0), (2, 0), (3, 0)]
    growth = [(1, 0), (2, 0), (3, 0)]
    return {
        "onset_delay": C.wet_season_delay(daily, year),
        "precip_main": C.sum_value(daily, year, main, "precip"),
        "soil_growth": C.mean_value(daily, year, growth, "soil"),
        "edd_growth": C.edd(daily, year, growth, 33.0),
        "solar_growth": C.mean_value(daily, year, growth, "solar"),
        "dry_spell_growth": C.max_dry_spell(daily, year, growth),
    }


def build_palm(daily, year):
    dry1 = [(6, -1), (7, -1), (8, -1), (9, -1), (10, -1)]
    dry2 = [(6, -2), (7, -2), (8, -2), (9, -2), (10, -2)]
    haze = [(8, -1), (9, -1), (10, -1)]
    return {
        "soil_dry_lag1": C.mean_value(daily, year, dry1, "soil"),
        "soil_dry_lag2": C.mean_value(daily, year, dry2, "soil"),
        "precip_dry_lag1": C.sum_value(daily, year, dry1, "precip"),
        "vpd_dry_lag1": C.mean_value(daily, year, dry1, "vpd_max"),
        "solar_haze_lag1": C.mean_value(daily, year, haze, "solar"),
        "dry_spell_lag1": C.max_dry_spell(daily, year, dry1),
    }


def build_coffee(daily, year):
    dry = [(7, -1), (8, -1), (9, -1)]
    flower = [(10, -1), (11, -1), (12, -1)]
    wet = [(11, -1), (12, -1), (1, 0), (2, 0), (3, 0)]
    return {
        "soil_flower_lag": C.mean_value(daily, year, dry, "soil"),
        "vpd_flower_lag": C.mean_value(daily, year, dry, "vpd_max"),
        "precip_flower": C.sum_value(daily, year, flower, "precip"),
        "fungal_risk": C.fungal_risk_days(daily, year, wet),
        "wet_days": C.wet_days(daily, year, wet),
        "solar_wet": C.mean_value(daily, year, wet, "solar"),
    }


def build_rubber(daily, year):
    tapping = [(1, 0), (2, 0), (3, 0), (4, 0)]
    lag_dry = [(7, -1), (8, -1), (9, -1), (10, -1)]
    return {
        "wet_tapping_days": C.wet_days(daily, year, tapping),
        "fungal_risk": C.fungal_risk_days(daily, year, tapping),
        "soil_dry_lag": C.mean_value(daily, year, lag_dry, "soil"),
        "vpd_dry_lag": C.mean_value(daily, year, lag_dry, "vpd_max"),
        "precip_tapping": C.sum_value(daily, year, tapping, "precip"),
    }


RICE = CropConfig(
    key="indonesia_rice", label="Indonesia rice", label_ko="인도네시아 쌀",
    faostat_item="Rice", points=RICE_POINTS, build=build_rice,
    core=["onset_delay", "soil_growth", "edd_growth", "precip_main"],
    area_core=["onset_delay", "soil_growth", "precip_main"],
    critical_window=[(10, -1), (11, -1), (12, -1), (1, 0), (2, 0), (3, 0)],
    doc="Regions/인도네시아/자바/쌀/쌀_상세분석_및_수식.md",
    caveat=("FAOSTAT national yield mixes irrigated and rainfed rice and several crop cycles. "
            "Weather is production-weighted across five major belts, not a Java-only label."),
    non_weather_drivers="Irrigation releases, fertilizer, varietal change, KSA area revisions and policy.",
)

PALM = CropConfig(
    key="indonesia_oil_palm", label="Indonesia oil palm fruit", label_ko="인도네시아 팜유 과실",
    faostat_item="Oil palm fruit", points=PALM_POINTS, build=build_palm,
    core=["soil_dry_lag1", "soil_dry_lag2", "vpd_dry_lag1"],
    critical_window=[(6, -2), (7, -2), (8, -2), (9, -2), (10, -2),
                     (6, -1), (7, -1), (8, -1), (9, -1), (10, -1)],
    doc="Regions/인도네시아/수마트라_칼리만탄/팜유/팜유_상세분석_및_수식.md",
    caveat=("The FAOSTAT oil-palm series is national and recent production/yield values are "
            "flagged estimated; solar anomaly is a haze proxy, not an AOD observation."),
    non_weather_drivers="Mature-tree share, replanting, fertilizer, labour and milling capacity.",
)

COFFEE = CropConfig(
    key="indonesia_coffee", label="Indonesia green coffee", label_ko="인도네시아 커피",
    faostat_item="Coffee, green", points=COFFEE_POINTS, build=build_coffee,
    core=["soil_flower_lag", "vpd_flower_lag", "precip_flower", "fungal_risk"],
    critical_window=[(7, -1), (8, -1), (9, -1), (10, -1), (11, -1), (12, -1),
                     (1, 0), (2, 0), (3, 0)],
    doc="Regions/인도네시아/수마트라/고무_커피/고무_커피_상세분석_및_수식.md",
    caveat="The national label mixes Arabica and Robusta and cannot identify local disease outbreaks.",
    non_weather_drivers="Biennial bearing, tree age, pruning, farm-gate price and harvest labour.",
)

RUBBER = CropConfig(
    key="indonesia_rubber", label="Indonesia natural rubber", label_ko="인도네시아 천연고무",
    faostat_item="Natural rubber in primary forms", points=RUBBER_POINTS, build=build_rubber,
    core=["wet_tapping_days", "fungal_risk", "soil_dry_lag", "vpd_dry_lag"],
    critical_window=[(7, -1), (8, -1), (9, -1), (10, -1),
                     (1, 0), (2, 0), (3, 0), (4, 0)],
    doc="Regions/인도네시아/수마트라/고무_커피/고무_커피_상세분석_및_수식.md",
    caveat="Fungal-risk days are a weather proxy and are not observed Pestalotiopsis incidence.",
    non_weather_drivers="Rubber price, tapping intensity, labour, mature area and disease control.",
)

ALL = [RICE, PALM, COFFEE, RUBBER]
BY_KEY = {cfg.key: cfg for cfg in ALL}

