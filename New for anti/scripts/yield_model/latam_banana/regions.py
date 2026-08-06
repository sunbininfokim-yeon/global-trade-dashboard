"""Pre-registered LatAm banana zone configurations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from . import climate as C
from . import labels as L


@dataclass
class RegionCrop:
    key: str
    label: str
    label_ko: str
    country: str
    points: list
    build: Callable
    doc: str
    target: Callable
    target_label: str = "banana"
    target_unit: str = "kg/ha"
    label_source: str = "province"
    start_year: int = 1990
    min_train: int = 16
    core: list = field(default_factory=list)
    feature_sets: dict = field(default_factory=dict)
    caveat: str = ""
    label_resolution: str = "blocked"
    hurricane_prone: bool = False


def z(names: list[str]) -> list[str]:
    return [name + "_z20" for name in names]


SIGATOKA_CORE = [
    "sigatoka_rh_days", "humid_spell_max", "rain_wet", "wet_days",
]
STORM_CORE = ["wind_storm_days", "wind_max_daily"]
THERMAL = ["tmean_year", "heat_days_34", "heat_excess_34"]
MOISTURE = ["rain_year", "rain_dry", "sm_year", "vpd_year"]

WEATHER = z(SIGATOKA_CORE + THERMAL + ["rain_year"])
WEATHER_STORM = z(SIGATOKA_CORE + STORM_CORE + THERMAL + ["rain_year"])
ECUADOR_SET = z(SIGATOKA_CORE + THERMAL + MOISTURE + ["oni_amj"])

LIT = (
    "Jiménez et al. 2022 RF (Panama) — YLWS/YLS lead, farm weekly. "
    "Garcés-Fiallos et al. 2025 RF (Ecuador) — NDVI+soil+phenology, farm. "
    "Rojas-Briones et al. 2011 Bayesian net (Ecuador). "
    "Phase-1 is province+POWER ridge proxies, not farm RF."
)

ECUADOR_POINTS = [
    {"name": "Quevedo", "lat": -1.03, "lon": -79.45, "elevation": 74,
     "weight": 0.40, "province": "Los Rios"},
    {"name": "Guayaquil", "lat": -2.17, "lon": -79.90, "elevation": 4,
     "weight": 0.30, "province": "Guayas"},
    {"name": "Machala", "lat": -3.26, "lon": -79.96, "elevation": 6,
     "weight": 0.30, "province": "El Oro"},
]

GUATEMALA_POINTS = [
    {"name": "Puerto Barrios", "lat": 15.73, "lon": -88.59, "elevation": 2,
     "weight": 0.55, "province": "Izabal"},
    {"name": "Escuintla", "lat": 14.30, "lon": -90.79, "elevation": 347,
     "weight": 0.45, "province": "Escuintla"},
]

COSTA_RICA_POINTS = [
    {"name": "Limon", "lat": 9.99, "lon": -83.04, "elevation": 3,
     "weight": 0.70, "province": "Limon"},
    {"name": "Sixaola", "lat": 9.51, "lon": -82.63, "elevation": 10,
     "weight": 0.30, "province": "Limon"},
]

HONDURAS_POINTS = [
    {"name": "La Lima", "lat": 15.43, "lon": -87.92, "elevation": 30,
     "weight": 0.55, "province": "Cortes"},
    {"name": "El Progreso", "lat": 15.40, "lon": -87.80, "elevation": 48,
     "weight": 0.45, "province": "Yoro"},
]


def _ecuador(daily, y):
    return C.ecuador_features(daily, y)


def _guatemala(daily, y):
    return C.caribbean_features(daily, y)


def _costa_rica(daily, y):
    return C.caribbean_features(daily, y)


def _honduras(daily, y):
    return C.caribbean_features(daily, y)


DOC = "Regions/중남미/바나나공화국_에콰도르/바나나/바나나_상세분석_및_수식.md"

ECUADOR = RegionCrop(
    key="ecuador_coast_banana",
    label="Ecuador coastal banana",
    label_ko="에콰도르 연안 바나나",
    country="ecuador",
    points=ECUADOR_POINTS,
    build=_ecuador,
    doc=DOC,
    target=L.ecuador_yield_kg_ha,
    core=list(ECUADOR_SET),
    feature_sets={
        "weather": z(SIGATOKA_CORE + THERMAL + ["rain_year"]),
        "weather_enso": ECUADOR_SET,
        "weather_moisture": z(SIGATOKA_CORE + THERMAL + MOISTURE),
    },
    caveat=LIT + " ENSO drought on Pacific coast; TR4 area layer separate.",
    label_resolution="blocked",
    hurricane_prone=False,
)

GUATEMALA = RegionCrop(
    key="guatemala_banana",
    label="Guatemala banana",
    label_ko="과테말라 바나나",
    country="guatemala",
    points=GUATEMALA_POINTS,
    build=_guatemala,
    doc=DOC,
    target=L.guatemala_yield_kg_ha,
    core=list(WEATHER_STORM),
    feature_sets={
        "weather": WEATHER,
        "weather_storm": WEATHER_STORM,
    },
    caveat=LIT + " Hurricane blowdown hard-cut via IBTrACS when available.",
    label_resolution="blocked",
    hurricane_prone=True,
)

COSTA_RICA = RegionCrop(
    key="costa_rica_banana",
    label="Costa Rica banana",
    label_ko="코스타리카 바나나",
    country="costa_rica",
    points=COSTA_RICA_POINTS,
    build=_costa_rica,
    doc=DOC,
    target=L.costa_rica_yield_kg_ha,
    core=list(WEATHER_STORM),
    feature_sets={
        "weather": WEATHER,
        "weather_storm": WEATHER_STORM,
    },
    caveat=LIT + " CORBANA weekly Sigatoka is Phase-2 gold standard.",
    label_resolution="blocked",
    hurricane_prone=True,
)

HONDURAS = RegionCrop(
    key="honduras_banana",
    label="Honduras banana",
    label_ko="온두라스 바나나",
    country="honduras",
    points=HONDURAS_POINTS,
    build=_honduras,
    doc=DOC,
    target=L.honduras_yield_kg_ha,
    core=list(WEATHER_STORM),
    feature_sets={
        "weather": WEATHER,
        "weather_storm": WEATHER_STORM,
    },
    caveat=LIT + " Highest hurricane blowdown exposure among the four.",
    label_resolution="blocked",
    hurricane_prone=True,
)

ALL = [ECUADOR, GUATEMALA, COSTA_RICA, HONDURAS]
BY_KEY = {cfg.key: cfg for cfg in ALL}
