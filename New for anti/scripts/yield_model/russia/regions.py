"""
Phase-1 Russia winter-wheat zones.

Southern grain export belt (Krasnodar, Rostov, Stavropol) and Central Black
Earth (Belgorod, Voronezh, Kursk, Tambov). Crimea and wartime "new regions"
are excluded from points and from any future oblast label join.

Coordinates follow the Phase-1 deep-dive sample points; weights are rough
export-/production-share priors, not invented farm census claims — replace
with Rosstat sown-area shares when oblast labels land.
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


# Production-prior weights (South export belt ≈ larger share of RU wheat
# export story; still only ~1/3 of national production combined with CBE).
SOUTH_POINTS = [
    {"name": "Krasnodar", "lat": 45.05, "lon": 38.98, "elevation": 34,
     "weight": 0.40},
    {"name": "Rostov", "lat": 47.23, "lon": 39.72, "elevation": 50,
     "weight": 0.35},
    {"name": "Stavropol", "lat": 45.04, "lon": 41.97, "elevation": 547,
     "weight": 0.25},
]

CBE_POINTS = [
    {"name": "Belgorod", "lat": 50.60, "lon": 36.59, "elevation": 170,
     "weight": 0.25},
    {"name": "Voronezh", "lat": 51.67, "lon": 39.18, "elevation": 140,
     "weight": 0.30},
    {"name": "Kursk", "lat": 51.73, "lon": 36.19, "elevation": 200,
     "weight": 0.25},
    {"name": "Tambov", "lat": 52.72, "lon": 41.44, "elevation": 130,
     "weight": 0.20},
]

VOLGA_POINTS = [
    {"name": "Saratov", "lat": 51.53, "lon": 46.03, "elevation": 80,
     "weight": 0.40},
    {"name": "Samara", "lat": 53.20, "lon": 50.15, "elevation": 100,
     "weight": 0.30},
    {"name": "Volgograd", "lat": 48.71, "lon": 44.52, "elevation": 50,
     "weight": 0.30},
]

# All Phase-1 points, reweighted so South : CBE ≈ 55 : 45 of the model mix.
NATIONAL_POINTS = [
    {**p, "weight": p["weight"] * 0.55} for p in SOUTH_POINTS
] + [
    {**p, "weight": p["weight"] * 0.45} for p in CBE_POINTS
]

SUNFLOWER_BELT_POINTS = (
    [{**p, "weight": p["weight"] * 0.40} for p in SOUTH_POINTS]
    + [{**p, "weight": p["weight"] * 0.30} for p in CBE_POINTS]
    + [{**p, "weight": p["weight"] * 0.30} for p in VOLGA_POINTS]
)


def _south(daily, y):
    return C.winter_wheat_features(
        daily, y,
        grainfill_months=[(5, 0), (6, 0)],
        heat_thr=28.0,
        winterkill_tmin=-15.0,
    )


def _cbe(daily, y):
    # CBE: slightly longer fill window and colder winterkill threshold proxy.
    return C.winter_wheat_features(
        daily, y,
        grainfill_months=[(5, 0), (6, 0), (7, 0)],
        heat_thr=28.0,
        winterkill_tmin=-18.0,
    )


def _volga_wheat(daily, y):
    # Drier continental Volga: colder winterkill, May–Jun fill, stronger drought.
    return C.winter_wheat_features(
        daily, y,
        grainfill_months=[(5, 0), (6, 0)],
        heat_thr=29.0,
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

CAVEAT = (
    "Target: Rosstat oblast grain yield (урожайность зерновых, c/ha→kg/ha), "
    "sown-area-weighted within the zone. Indicator is cereals+legumes (not "
    "winter-wheat-only); in South/CBE winter wheat dominates that basket. "
    "Crimea/new regions excluded. ERA5-Land snow optional; without it "
    "winterkill uses POWER Tmin bare-frost. No Open-Meteo soil (project rule)."
)

SUNFLOWER_CAVEAT = (
    "Target: Rosstat oblast sunflower yield (13160000), sown-area-weighted "
    "(13070000). Features follow North Caucasus / CFO agromet literature "
    "(April precip, flowering heat–drought, May–Aug moisture, radiation). "
    "WOFOST is a process benchmark only — this package stays ridge+trend."
)

NON_WEATHER = (
    "Russian wheat yields carry a strong post-Soviet recovery and variety "
    "trend, plus fertilizer and policy shocks (export duty regime). Those are "
    "not weather; the log technology trend absorbs the smooth part, not the "
    "policy steps."
)

SUNFLOWER_NON_WEATHER = (
    "Sunflower carries hybrid turnover, rotation (often after cereals), and "
    "crush/export economics; weather models explain residual after trend."
)


SOUTH = RegionCrop(
    key="southern_winter_wheat",
    label="Southern grain belt winter wheat (Krasnodar, Rostov, Stavropol)",
    label_ko="남부 수출축 겨울밀",
    points=SOUTH_POINTS,
    build=_south,
    doc="Regions/흑해_통합/파이프라인_딥다이브_RU_UA_Phase1.md §D–E",
    target=L.southern_yield_kg_ha,
    target_label="zone grain yield (Rosstat oblast, area-weighted)",
    target_unit="kg/ha",
    label_source=(
        "Rosstat Regions of Russia (tochno-st 13120000) Krasnodar+Rostov+"
        "Stavropol; sown-area weights 13050000; 2024 from mojgorod yearbook table"),
    region_share=(
        "Southern Federal District + Stavropol export winter-wheat belt; "
        "oblast labels exclude Volga/Siberia spring wheat dilution."),
    panel={"spi3_spring": "precip_spring"},
    core=CORE_FEATURES,
    critical_window=[(5, 0), (6, 0)],
    # Soft regime after post-Soviet floor; oblast series starts 2000.
    regime_start=2000,
    min_train=18,
    caveat=CAVEAT,
    non_weather_drivers=NON_WEATHER,
)

CBE = RegionCrop(
    key="cbe_winter_wheat",
    label="Central Black Earth winter wheat (Belgorod, Voronezh, Kursk, Tambov)",
    label_ko="중앙 흑토 겨울밀",
    points=CBE_POINTS,
    build=_cbe,
    doc="Regions/흑해_통합/파이프라인_딥다이브_RU_UA_Phase1.md §D–E",
    target=L.cbe_yield_kg_ha,
    target_label="zone grain yield (Rosstat oblast, area-weighted)",
    target_unit="kg/ha",
    label_source=(
        "Rosstat Regions of Russia (tochno-st 13120000) Belgorod+Voronezh+"
        "Kursk+Tambov; sown-area weights 13050000; 2024 from mojgorod yearbook table"),
    region_share=(
        "Central Black Earth winter-wheat core; oblast labels match zone weather."),
    panel={"spi3_spring": "precip_spring"},
    core=CORE_FEATURES,
    critical_window=[(5, 0), (6, 0), (7, 0)],
    regime_start=2000,
    min_train=18,
    caveat=CAVEAT,
    non_weather_drivers=NON_WEATHER,
)

NATIONAL = RegionCrop(
    key="russia_winter_wheat",
    label="Russia winter-wheat belt (South + CBE production-weighted)",
    label_ko="러시아 겨울밀 (남부·흑토 가중)",
    points=NATIONAL_POINTS,
    build=_south,  # grainfill May–Jun; CBE still contributes via points
    doc="Regions/흑해_통합/파이프라인_딥다이브_RU_UA_Phase1.md §D–E",
    target=L.belt_yield_kg_ha,
    target_label="belt grain yield (Rosstat oblast, area-weighted)",
    target_unit="kg/ha",
    label_source=(
        "Rosstat Regions of Russia (tochno-st 13120000) South+CBE seven oblasts; "
        "sown-area weights 13050000; 2024 from mojgorod yearbook table"),
    region_share=(
        "South+CBE winter-wheat export weather; Siberia/Volga outside labels."),
    panel={"spi3_spring": "precip_spring"},
    core=CORE_FEATURES,
    critical_window=[(5, 0), (6, 0)],
    regime_start=2000,
    min_train=18,
    caveat=CAVEAT,
    non_weather_drivers=NON_WEATHER,
)

VOLGA = RegionCrop(
    key="volga_winter_wheat",
    label="Volga winter wheat (Saratov, Samara, Volgograd)",
    label_ko="볼가 겨울밀",
    points=VOLGA_POINTS,
    build=_volga_wheat,
    doc="russia/METHODOLOGY_sunflower_wheat.md",
    target=L.volga_yield_kg_ha,
    target_label="zone grain yield (Rosstat oblast, area-weighted)",
    target_unit="kg/ha",
    label_source=(
        "Rosstat Regions of Russia (tochno-st 13120000) Saratov+Samara+Volgograd; "
        "sown-area weights 13050000"),
    region_share=(
        "Volga steppe — drier continental winter wheat / mixed cereals; "
        "export path differs from Black Sea South but climate signal is sharp."),
    panel={"spi3_spring": "precip_spring"},
    core=CORE_FEATURES,
    critical_window=[(5, 0), (6, 0)],
    regime_start=2000,
    min_train=16,
    caveat=CAVEAT,
    non_weather_drivers=NON_WEATHER,
)

SOUTH_SUN = RegionCrop(
    key="southern_sunflower",
    label="Southern sunflower (Krasnodar, Rostov, Stavropol)",
    label_ko="남부 해바라기",
    points=SOUTH_POINTS,
    build=_sunflower,
    doc="russia/METHODOLOGY_sunflower_wheat.md",
    target=L.southern_sunflower_yield_kg_ha,
    target_label="zone sunflower yield (Rosstat oblast, area-weighted)",
    target_unit="kg/ha",
    label_source=(
        "Rosstat 13160000 sunflower yield; sown-area weights 13070000 "
        "(Krasnodar+Rostov+Stavropol)"),
    region_share="Core Black Sea sunflower / oilseed export belt.",
    panel={"spi3_flower": "precip_flower"},
    core=SUNFLOWER_CORE,
    critical_window=[(6, 0), (7, 0), (8, 0)],
    regime_start=2000,
    min_train=16,
    caveat=SUNFLOWER_CAVEAT,
    non_weather_drivers=SUNFLOWER_NON_WEATHER,
)

CBE_SUN = RegionCrop(
    key="cbe_sunflower",
    label="Central Black Earth sunflower (Belgorod, Voronezh, Kursk, Tambov)",
    label_ko="중앙 흑토 해바라기",
    points=CBE_POINTS,
    build=_sunflower,
    doc="russia/METHODOLOGY_sunflower_wheat.md",
    target=L.cbe_sunflower_yield_kg_ha,
    target_label="zone sunflower yield (Rosstat oblast, area-weighted)",
    target_unit="kg/ha",
    label_source=(
        "Rosstat 13160000; sown-area weights 13070000 "
        "(Belgorod+Voronezh+Kursk+Tambov)"),
    region_share="CBE expanding sunflower; Hydrometcenter CFO forecast literature.",
    panel={"spi3_flower": "precip_flower"},
    core=SUNFLOWER_CORE,
    critical_window=[(6, 0), (7, 0), (8, 0)],
    regime_start=2000,
    min_train=16,
    caveat=SUNFLOWER_CAVEAT,
    non_weather_drivers=SUNFLOWER_NON_WEATHER,
)

VOLGA_SUN = RegionCrop(
    key="volga_sunflower",
    label="Volga sunflower (Saratov, Samara, Volgograd)",
    label_ko="볼가 해바라기",
    points=VOLGA_POINTS,
    build=_sunflower,
    doc="russia/METHODOLOGY_sunflower_wheat.md",
    target=L.volga_sunflower_yield_kg_ha,
    target_label="zone sunflower yield (Rosstat oblast, area-weighted)",
    target_unit="kg/ha",
    label_source=(
        "Rosstat 13160000; sown-area weights 13070000 "
        "(Saratov+Samara+Volgograd)"),
    region_share="Volga is a top RF sunflower production share (Saratov especially).",
    panel={"spi3_flower": "precip_flower"},
    core=SUNFLOWER_CORE,
    critical_window=[(6, 0), (7, 0), (8, 0)],
    regime_start=2000,
    min_train=16,
    caveat=SUNFLOWER_CAVEAT,
    non_weather_drivers=SUNFLOWER_NON_WEATHER,
)

BELT_SUN = RegionCrop(
    key="russia_sunflower",
    label="Russia sunflower belt (South + CBE + Volga)",
    label_ko="러시아 해바라기 벨트",
    points=SUNFLOWER_BELT_POINTS,
    build=_sunflower,
    doc="russia/METHODOLOGY_sunflower_wheat.md",
    target=L.belt_sunflower_yield_kg_ha,
    target_label="belt sunflower yield (Rosstat oblast, area-weighted)",
    target_unit="kg/ha",
    label_source="Rosstat 13160000 / 13070000 across 10 oblasts",
    region_share="Main RF sunflower production geography for oilseed markets.",
    panel={"spi3_flower": "precip_flower"},
    core=SUNFLOWER_CORE,
    critical_window=[(6, 0), (7, 0), (8, 0)],
    regime_start=2000,
    min_train=16,
    caveat=SUNFLOWER_CAVEAT,
    non_weather_drivers=SUNFLOWER_NON_WEATHER,
)

ALL = [SOUTH, CBE, NATIONAL, VOLGA,
       SOUTH_SUN, CBE_SUN, VOLGA_SUN, BELT_SUN]
BY_KEY = {r.key: r for r in ALL}
