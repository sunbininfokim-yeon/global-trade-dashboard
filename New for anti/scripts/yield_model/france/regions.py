"""
France region-crops: northern winter wheat belt and south-west grain maize.

Each `build` runs against one location's daily weather; collect.py calls it
once per point and area-weights the results (same rule as india/brazil: a
threshold crossing does not survive averaging the weather first).

Point weights are each NUTS 2 region's share of the crop's area over
2015-2024 from the same Eurostat table the labels come from
(eurostat.area_shares), split evenly where a region has two points.
"""

from dataclasses import dataclass, field
from typing import Callable

from . import climate as C


@dataclass
class RegionCrop:
    key: str
    label: str
    crop: str                       # eurostat.CROPS key
    selector: list                  # NUTS 2 codes
    points: list                    # [{name, lat, lon, elevation, weight}]
    build: Callable                 # (daily, harvest_year) -> dict
    doc: str
    start_year: int = 1985
    calendar_year_crop: bool = False
    panel: dict = field(default_factory=dict)
    core: list = field(default_factory=list)
    regime_start: int = 0
    min_train: int = 0
    critical_window: list = field(default_factory=list)
    non_weather_drivers: str = ""
    caveat: str = ""


def _count(daily, months, y, test):
    w = C._window(daily, months, y)
    return None if w.empty else float(test(w).sum())


def _mean(daily, months, y, col):
    w = C._window(daily, months, y)
    return None if w.empty else float(w[col].mean())


# ---------------------------------------------------------------------------
# Northern winter wheat (Centre, Hauts-de-France, Champagne, Ile-de-France,
# Normandy, Burgundy) -- about two thirds of French soft wheat.
#
# French wheat losses come from two directions, and both are recent:
#   - too wet: 2016, the worst harvest in decades, was a cool, sunless,
#     waterlogged May-June that brought fusarium and septoria and killed grain
#     set; 2024 repeated it after a soaked autumn sowing.
#   - too hot/dry: 2003 and 2022, heat and drought during grain fill.
# So the features carry both arms: autumn sowing rain, spring water balance,
# wet days and rain in May-June, and June heat.
# ---------------------------------------------------------------------------

WHEAT_POINTS = [
    {"name": "Chartres",    "lat": 48.45, "lon": 1.49, "elevation": 150, "weight": 0.11},
    {"name": "Chateauroux", "lat": 46.81, "lon": 1.69, "elevation": 155, "weight": 0.11},
    {"name": "Amiens",      "lat": 49.89, "lon": 2.30, "elevation": 40,  "weight": 0.13},
    {"name": "Arras",       "lat": 50.29, "lon": 2.78, "elevation": 70,  "weight": 0.10},
    {"name": "Chalons",     "lat": 48.96, "lon": 4.36, "elevation": 85,  "weight": 0.13},
    {"name": "Melun",       "lat": 48.54, "lon": 2.66, "elevation": 60,  "weight": 0.09},
    {"name": "Evreux",      "lat": 49.03, "lon": 1.15, "elevation": 140, "weight": 0.09},
    {"name": "Caen",        "lat": 49.18, "lon": -0.37, "elevation": 30, "weight": 0.08},
    {"name": "Auxerre",     "lat": 47.80, "lon": 3.57, "elevation": 120, "weight": 0.16},
]


def _wheat(daily, y):
    return {
        "precip_oct_nov": C.window_totals(daily, [(10, -1), (11, -1)], y),
        "frost_days_dec_feb": _count(daily, [(12, -1), (1, 0), (2, 0)], y,
                                     lambda w: w.tmin < -10),
        "tmean_feb_mar": _mean(daily, [(2, 0), (3, 0)], y, "tmean"),
        "deficit_mar_may": C.moisture_deficit(daily, [(3, 0), (4, 0), (5, 0)], y),
        "precip_may_jun": C.window_totals(daily, [(5, 0), (6, 0)], y),
        "wet_days_may_jun": _count(daily, [(5, 0), (6, 0)], y,
                                   lambda w: w.precip >= 1.0),
        "heat_days_28_jun": C.heat_days(daily, [(6, 0)], y, threshold=28.0),
    }


NORTH_WHEAT = RegionCrop(
    key="north_wheat",
    label="Northern France winter wheat",
    crop="winter_wheat",
    selector=["FRB0", "FRE1", "FRE2", "FRF2", "FR10", "FRD1", "FRD2", "FRC1"],
    points=WHEAT_POINTS,
    build=_wheat,
    doc="No guide file: winter wheat agronomy for the Paris Basin (wet May-June "
        "disease years 2016/2024, grain-fill heat 2003/2022); features fixed before training.",
    critical_window=[(3, 0), (4, 0), (5, 0), (6, 0), (7, 0)],
    panel={"spi_spring": "precip_may_jun"},
    core=["wet_days_may_jun", "precip_may_jun", "deficit_mar_may",
          "heat_days_28_jun", "precip_oct_nov", "nao_season"],
    min_train=14,
    caveat="Labels are Eurostat NUTS 2 yields from 2000 only (25 seasons), so "
           "the out-of-sample record is short; 2016 alone dominates the wet arm.",
    non_weather_drivers="French wheat yields have been flat since the late 1990s "
        "(nitrogen limits, the end of breeding gains, climate); the trend is "
        "taken out before reading weather.",
)


# ---------------------------------------------------------------------------
# South-west and western grain maize (Aquitaine, Midi-Pyrenees,
# Poitou-Charentes, Pays de la Loire, Centre, Alsace).
#
# A summer crop: July-August water and flowering heat decide it. A large
# share is irrigated (Landes, Alsace), which dampens drought years but
# exposes the crop to irrigation bans in the worst ones (2022).
# ---------------------------------------------------------------------------

MAIZE_POINTS = [
    {"name": "Pau",           "lat": 43.30, "lon": -0.37, "elevation": 190, "weight": 0.13},
    {"name": "Mont-de-Marsan", "lat": 43.89, "lon": -0.50, "elevation": 60, "weight": 0.13},
    {"name": "Auch",          "lat": 43.65, "lon": 0.59, "elevation": 150, "weight": 0.15},
    {"name": "Niort",         "lat": 46.32, "lon": -0.46, "elevation": 30,  "weight": 0.12},
    {"name": "Angers",        "lat": 47.47, "lon": -0.55, "elevation": 40,  "weight": 0.14},
    {"name": "Orleans",       "lat": 47.90, "lon": 1.90, "elevation": 110,  "weight": 0.14},
    {"name": "Colmar",        "lat": 48.08, "lon": 7.36, "elevation": 190,  "weight": 0.19},
]


def _maize(daily, y):
    return {
        "precip_may_jun": C.window_totals(daily, [(5, 0), (6, 0)], y),
        "precip_jul_aug": C.window_totals(daily, [(7, 0), (8, 0)], y),
        "deficit_jul_aug": C.moisture_deficit(daily, [(7, 0), (8, 0)], y),
        "heat_days_32_jul_aug": C.heat_days(daily, [(7, 0), (8, 0)], y, threshold=32.0),
        "tmean_jun_aug": _mean(daily, [(6, 0), (7, 0), (8, 0)], y, "tmean"),
        "wet_days_oct": _count(daily, [(10, 0)], y, lambda w: w.precip >= 1.0),
    }


WEST_MAIZE = RegionCrop(
    key="west_maize",
    label="South-west and western France grain maize",
    crop="grain_maize",
    selector=["FRI1", "FRJ2", "FRI3", "FRG0", "FRB0", "FRF1"],
    points=MAIZE_POINTS,
    build=_maize,
    doc="No guide file: grain maize agronomy (July-August water balance and "
        "flowering heat; irrigation bans in 2022); features fixed before training.",
    calendar_year_crop=True,
    critical_window=[(6, 0), (7, 0), (8, 0), (9, 0)],
    panel={"spi_summer": "precip_jul_aug"},
    core=["deficit_jul_aug", "heat_days_32_jul_aug", "precip_jul_aug", "oni_season"],
    min_train=12,
    caveat="Eurostat publishes regional grain maize only from 2007 (18 seasons). "
           "Irrigated and rainfed maize are not split, so drought shows up "
           "damped.",
    non_weather_drivers="Irrigation share and irrigation bans, and the "
        "area moving out of maize since 2010, move yields independently of weather.",
)


ALL = [NORTH_WHEAT, WEST_MAIZE]
BY_KEY = {c.key: c for c in ALL}
