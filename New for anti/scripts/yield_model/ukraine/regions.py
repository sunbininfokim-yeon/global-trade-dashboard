"""
Phase-2 Ukraine zones: winter wheat first, sunflower stubs.

Central forest-steppe, Southern steppe, Western rear. Crimea / Donetsk /
Luhansk excluded. Point weights are production priors until sown-area CSV lands.
"""

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
    points: list
    build: Callable
    doc: str
    target: Callable
    target_label: str
    target_unit: str
    label_source: str
    region_share: str
    start_year: int = 1982
    panel: dict = field(default_factory=dict)
    core: list = field(default_factory=list)
    critical_window: list = field(default_factory=list)
    regime_start: int = 0
    min_train: int = 0
    non_weather_drivers: str = ""
    caveat: str = ""
    # "oblast" | "blocked" | ""
    label_resolution: str = ""


CENTRAL_POINTS = [
    {"name": "Poltava", "lat": 49.59, "lon": 34.55, "elevation": 132,
     "weight": 0.40},
    {"name": "Vinnytsia", "lat": 49.23, "lon": 28.48, "elevation": 260,
     "weight": 0.35},
    {"name": "Cherkasy", "lat": 49.44, "lon": 32.06, "elevation": 110,
     "weight": 0.25},
]

SOUTH_POINTS = [
    {"name": "Odesa", "lat": 46.48, "lon": 30.73, "elevation": 50,
     "weight": 0.40},
    {"name": "Mykolaiv", "lat": 46.97, "lon": 31.99, "elevation": 50,
     "weight": 0.35},
    {"name": "Kherson", "lat": 46.64, "lon": 32.62, "elevation": 45,
     "weight": 0.25},
]

WEST_POINTS = [
    {"name": "Ternopil", "lat": 49.55, "lon": 25.59, "elevation": 320,
     "weight": 0.35},
    {"name": "Khmelnytskyi", "lat": 49.42, "lon": 27.00, "elevation": 290,
     "weight": 0.35},
    {"name": "Rivne", "lat": 50.62, "lon": 26.25, "elevation": 200,
     "weight": 0.30},
]

# Central : South : West ≈ 40 : 35 : 25 until sown-area weights land.
BELT_POINTS = (
    [{**p, "weight": p["weight"] * 0.40} for p in CENTRAL_POINTS]
    + [{**p, "weight": p["weight"] * 0.35} for p in SOUTH_POINTS]
    + [{**p, "weight": p["weight"] * 0.25} for p in WEST_POINTS]
)


def _central_wheat(daily, y):
    return C.winter_wheat_features(
        daily, y,
        grainfill_months=[(5, 0), (6, 0), (7, 0)],
        heat_thr=28.0,
        winterkill_tmin=-15.0,
    )


def _south_wheat(daily, y):
    return C.winter_wheat_features(
        daily, y,
        grainfill_months=[(5, 0), (6, 0)],
        heat_thr=28.0,
        winterkill_tmin=-12.0,  # milder winters; drought dominates
    )


def _west_wheat(daily, y):
    return C.winter_wheat_features(
        daily, y,
        grainfill_months=[(6, 0), (7, 0)],
        heat_thr=27.0,
        winterkill_tmin=-18.0,
    )


def _sunflower(daily, y):
    return C.sunflower_features(
        daily, y,
        flower_months=[(6, 0), (7, 0), (8, 0)],
        heat_thr=30.0,
    )


CORE_FEATURES = [
    "winterkill_bare_frost", "winterkill_edd", "sm_april",
    "edd_grainfill", "precip_spring", "precip_autumn",
]

SUNFLOWER_CORE = [
    "precip_april", "sm_april", "edd_flower", "sm_flower",
    "precip_may_aug", "radiation_season",
]

DOC = "Regions/흑해_통합/방법론_우크라이나_yield_kickoff.md"

WHEAT_CAVEAT = (
    "Target: SSSU/Ukrstat oblast wheat yield (c/ha→kg/ha), sown-area-weighted. "
    "Train years ≤2021. Crimea/Donetsk/Luhansk excluded. War-year area/"
    "abandonment is a separate layer — not absorbed into weather residuals. "
    "PSD national is cross-check only. No Open-Meteo soil."
)

SUNFLOWER_CAVEAT = (
    "Stub until oblast sunflower CSV lands. Same war/area separation as wheat. "
    "Flowering Jun–Aug heat–drought + April establishment moisture."
)

NON_WEATHER = (
    "UA wheat carries variety and fertilizer trends plus a hard break after "
    "2022 (input access, occupied land). Log trend uses pre-war years only; "
    "do not fit war technical shock into weather coefficients."
)

SUNFLOWER_NON_WEATHER = (
    "Sunflower area and crush economics shifted sharply in wartime; keep "
    "planted-area RS separate from this yield residual model."
)

_WHEAT_OK = L.wheat_oblast_available()
_SUN_OK = L.sunflower_oblast_available()
_WHEAT_RES = "oblast" if _WHEAT_OK else "blocked"
_SUN_RES = "oblast" if _SUN_OK else "blocked"

_WHEAT_SRC = (
    "SSSU/Ukrstat / data.gov.ua oblast wheat yield + sown area (≤2021)"
    if _WHEAT_OK else
    "BLOCKED: drop oblast_wheat_yields.csv + oblast_wheat_sown_area.csv "
    "(see labels.md). PSD national must not be used as zone target."
)
_SUN_SRC = (
    "SSSU/Ukrstat oblast sunflower yield + sown area (≤2021)"
    if _SUN_OK else
    "BLOCKED: drop oblast_sunflower_*.csv before sunflower train."
)


CENTRAL = RegionCrop(
    key="central_winter_wheat",
    label="Central forest-steppe winter wheat (Poltava, Vinnytsia, Cherkasy)",
    label_ko="중부 삼림스텝 겨울밀",
    points=CENTRAL_POINTS,
    build=_central_wheat,
    doc=DOC,
    target=L.central_wheat_yield_kg_ha,
    target_label="zone wheat yield (SSSU oblast, area-weighted)",
    target_unit="kg/ha",
    label_source=_WHEAT_SRC,
    region_share="Core UA winter-wheat / black-soil belt; relative rear vs South front.",
    panel={"spi3_spring": "precip_spring"},
    core=CORE_FEATURES,
    critical_window=[(5, 0), (6, 0), (7, 0)],
    regime_start=2000,
    min_train=16,
    caveat=WHEAT_CAVEAT,
    non_weather_drivers=NON_WEATHER,
    label_resolution=_WHEAT_RES,
)

SOUTH = RegionCrop(
    key="southern_winter_wheat",
    label="Southern steppe winter wheat (Odesa, Mykolaiv, Kherson)",
    label_ko="남부 스텝 겨울밀",
    points=SOUTH_POINTS,
    build=_south_wheat,
    doc=DOC,
    target=L.southern_wheat_yield_kg_ha,
    target_label="zone wheat yield (SSSU oblast, area-weighted)",
    target_unit="kg/ha",
    label_source=_WHEAT_SRC,
    region_share=(
        "Drought-prone export steppe; 2022+ occupation/frontline → area mask "
        "required before interpreting production."),
    panel={"spi3_spring": "precip_spring"},
    core=CORE_FEATURES,
    critical_window=[(5, 0), (6, 0)],
    regime_start=2000,
    min_train=16,
    caveat=WHEAT_CAVEAT,
    non_weather_drivers=NON_WEATHER,
    label_resolution=_WHEAT_RES,
)

WEST = RegionCrop(
    key="western_winter_wheat",
    label="Western winter wheat (Ternopil, Khmelnytskyi, Rivne)",
    label_ko="서부 겨울밀",
    points=WEST_POINTS,
    build=_west_wheat,
    doc=DOC,
    target=L.western_wheat_yield_kg_ha,
    target_label="zone wheat yield (SSSU oblast, area-weighted)",
    target_unit="kg/ha",
    label_source=_WHEAT_SRC,
    region_share="Western rear belt; more stable area, milder drought signal.",
    panel={"spi3_spring": "precip_spring"},
    core=CORE_FEATURES,
    critical_window=[(6, 0), (7, 0)],
    regime_start=2000,
    min_train=16,
    caveat=WHEAT_CAVEAT,
    non_weather_drivers=NON_WEATHER,
    label_resolution=_WHEAT_RES,
)

BELT = RegionCrop(
    key="ukraine_winter_wheat",
    label="Ukraine winter-wheat belt (Central + South + West)",
    label_ko="우크라이나 겨울밀 벨트",
    points=BELT_POINTS,
    build=_central_wheat,
    doc=DOC,
    target=L.belt_wheat_yield_kg_ha,
    target_label="belt wheat yield (SSSU oblast, area-weighted)",
    target_unit="kg/ha",
    label_source=_WHEAT_SRC,
    region_share="Production-prior mix of three zones; replace weights with sown area.",
    panel={"spi3_spring": "precip_spring"},
    core=CORE_FEATURES,
    critical_window=[(5, 0), (6, 0)],
    regime_start=2000,
    min_train=16,
    caveat=WHEAT_CAVEAT,
    non_weather_drivers=NON_WEATHER,
    label_resolution=_WHEAT_RES,
)

CENTRAL_SUN = RegionCrop(
    key="central_sunflower",
    label="Central sunflower (Poltava, Vinnytsia, Cherkasy) — stub",
    label_ko="중부 해바라기",
    points=CENTRAL_POINTS,
    build=_sunflower,
    doc=DOC,
    target=L.central_sunflower_yield_kg_ha,
    target_label="zone sunflower yield (SSSU oblast, area-weighted)",
    target_unit="kg/ha",
    label_source=_SUN_SRC,
    region_share="Central oilseed / rotation after cereals.",
    panel={"spi3_flower": "precip_flower"},
    core=SUNFLOWER_CORE,
    critical_window=[(6, 0), (7, 0), (8, 0)],
    regime_start=2000,
    min_train=16,
    caveat=SUNFLOWER_CAVEAT,
    non_weather_drivers=SUNFLOWER_NON_WEATHER,
    label_resolution=_SUN_RES,
)

SOUTH_SUN = RegionCrop(
    key="southern_sunflower",
    label="Southern sunflower (Odesa, Mykolaiv, Kherson) — stub",
    label_ko="남부 해바라기",
    points=SOUTH_POINTS,
    build=_sunflower,
    doc=DOC,
    target=L.southern_sunflower_yield_kg_ha,
    target_label="zone sunflower yield (SSSU oblast, area-weighted)",
    target_unit="kg/ha",
    label_source=_SUN_SRC,
    region_share="Classic UA sunflower steppe; wartime planted-area RS literature.",
    panel={"spi3_flower": "precip_flower"},
    core=SUNFLOWER_CORE,
    critical_window=[(6, 0), (7, 0), (8, 0)],
    regime_start=2000,
    min_train=16,
    caveat=SUNFLOWER_CAVEAT,
    non_weather_drivers=SUNFLOWER_NON_WEATHER,
    label_resolution=_SUN_RES,
)

WEST_SUN = RegionCrop(
    key="western_sunflower",
    label="Western sunflower (Ternopil, Khmelnytskyi, Rivne) — stub",
    label_ko="서부 해바라기",
    points=WEST_POINTS,
    build=_sunflower,
    doc=DOC,
    target=L.western_sunflower_yield_kg_ha,
    target_label="zone sunflower yield (SSSU oblast, area-weighted)",
    target_unit="kg/ha",
    label_source=_SUN_SRC,
    region_share="Expanding western sunflower; lower drought stress than South.",
    panel={"spi3_flower": "precip_flower"},
    core=SUNFLOWER_CORE,
    critical_window=[(6, 0), (7, 0), (8, 0)],
    regime_start=2000,
    min_train=16,
    caveat=SUNFLOWER_CAVEAT,
    non_weather_drivers=SUNFLOWER_NON_WEATHER,
    label_resolution=_SUN_RES,
)

BELT_SUN = RegionCrop(
    key="ukraine_sunflower",
    label="Ukraine sunflower belt — stub",
    label_ko="우크라이나 해바라기 벨트",
    points=BELT_POINTS,
    build=_sunflower,
    doc=DOC,
    target=L.belt_sunflower_yield_kg_ha,
    target_label="belt sunflower yield (SSSU oblast, area-weighted)",
    target_unit="kg/ha",
    label_source=_SUN_SRC,
    region_share="Belt mix pending sown-area weights.",
    panel={"spi3_flower": "precip_flower"},
    core=SUNFLOWER_CORE,
    critical_window=[(6, 0), (7, 0), (8, 0)],
    regime_start=2000,
    min_train=16,
    caveat=SUNFLOWER_CAVEAT,
    non_weather_drivers=SUNFLOWER_NON_WEATHER,
    label_resolution=_SUN_RES,
)

# Wheat first in ALL; sunflower stubs included so keys exist but train blocks.
ALL = [CENTRAL, SOUTH, WEST, BELT,
       CENTRAL_SUN, SOUTH_SUN, WEST_SUN, BELT_SUN]
BY_KEY = {r.key: r for r in ALL}
