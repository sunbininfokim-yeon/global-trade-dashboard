"""
One config per Thailand region-crop.

Literature-backed T1 (see SOURCES.md):
  · central_ne_sugarcane — rainfed cane, SPI/SM/ENSO (Pipitpukdee et al. 2020;
    Pattanapanchai et al. 2022; OCSB drought years)
  · chao_phraya_rice_wet — monsoon rice ENSO/onset (Prabnakorn et al. 2018)
  · chao_phraya_rice_off — dry-season irrigated rice; dam storage is PROXY only
    (TDRI Chaiyasit; RID Bhumibol/Sirikit mechanism)
  · thailand_rubber — rainy/tapping days (Makkaew & Sdoodee 2015, PSU Hat Yai)

T2 stub:
  · isan_cassava — CMD disease dominates weather; schema only
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from . import climate as C


@dataclass
class RegionCrop:
    key: str
    label: str
    label_ko: str
    crop: str
    faostat_item: str
    points: list
    build: Callable
    doc: str
    yield_base_kg_ha: float = 0.0
    yield_growth: float = 0.012
    calendar_year_crop: bool = True
    start_year: int = 1985
    panel: dict = field(default_factory=dict)
    core: list = field(default_factory=list)
    critical_window: list = field(default_factory=list)
    oni_window: tuple = field(
        default_factory=lambda: ({"OND", "NDJ"}, {"DJF", "JFM"}))
    min_train: int = 0
    regime_start: int = 0
    tier: str = "T1"
    stub: bool = False
    non_weather_drivers: str = ""
    caveat: str = ""
    sources: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Central + Northeast sugarcane (calendar crop year ≈ crushing year)
# ---------------------------------------------------------------------------

SUGAR_POINTS = [
    # Northeast (Isan) belt
    {"name": "Nakhon_Ratchasima", "lat": 14.97, "lon": 102.10, "elevation": 180,
     "weight": 0.22},
    {"name": "Khon_Kaen", "lat": 16.44, "lon": 102.83, "elevation": 165,
     "weight": 0.16},
    {"name": "Udon_Thani", "lat": 17.41, "lon": 102.79, "elevation": 170,
     "weight": 0.12},
    {"name": "Chaiyaphum", "lat": 15.81, "lon": 102.03, "elevation": 200,
     "weight": 0.10},
    # Central belt
    {"name": "Suphan_Buri", "lat": 14.47, "lon": 100.12, "elevation": 10,
     "weight": 0.14},
    {"name": "Kanchanaburi", "lat": 14.02, "lon": 99.53, "elevation": 30,
     "weight": 0.14},
    {"name": "Lopburi", "lat": 14.80, "lon": 100.65, "elevation": 20,
     "weight": 0.12},
]

# Early tillering / establishment (dry) and grand growth (wet) per work note §C
SUGAR_EARLY = [(1, 0), (2, 0), (3, 0), (4, 0)]
SUGAR_GRAND = [(5, 0), (6, 0), (7, 0), (8, 0), (9, 0), (10, 0)]
SUGAR_SPI3 = [(3, 0), (4, 0), (5, 0)]  # SPI-like 3-month precip for tillering


def _sugarcane(daily, y, point):
    return {
        "sm_early": C.window_mean(daily, "gwetroot", SUGAR_EARLY, y),
        "sm_grand": C.window_mean(daily, "gwetroot", SUGAR_GRAND, y),
        "precip_early": C.window_sum(daily, "precip", SUGAR_EARLY, y),
        "precip_grand": C.window_sum(daily, "precip", SUGAR_GRAND, y),
        "precip_spi3": C.window_sum(daily, "precip", SUGAR_SPI3, y),
        "wd_early": C.water_deficit(daily, SUGAR_EARLY, y),
        "heat_x_drought_early": C.heat_x_drought_days(
            daily, SUGAR_EARLY, y, sm_thresh=0.30, tmax_thresh=35.0),
        "edd_35_early": C.edd(daily, SUGAR_EARLY, y, 35.0),
        "tmax_early": C.window_mean(daily, "tmax", SUGAR_EARLY, y),
        "dry_spell_early": C.max_dry_spell(daily, SUGAR_EARLY, y),
    }


SUGARCANE = RegionCrop(
    key="central_ne_sugarcane",
    label="Central–NE Thailand sugarcane",
    label_ko="중부·북동 사탕수수",
    crop="sugarcane",
    faostat_item="Sugar cane",
    points=SUGAR_POINTS,
    build=_sugarcane,
    doc="Regions/태국/중부_북동부/설탕_고무 + Pipitpukdee et al. 2020",
    yield_base_kg_ha=65000.0,
    yield_growth=0.008,
    calendar_year_crop=True,
    start_year=1985,
    critical_window=SUGAR_EARLY + SUGAR_GRAND,
    oni_window=({"OND", "NDJ"}, {"DJF", "JFM", "FMA"}),
    core=["sm_early", "sm_grand", "precip_spi3", "heat_x_drought_early",
          "oni_djf", "wd_early"],
    panel={"spi3_z": "precip_spi3"},
    caveat=(
        "FAOSTAT national sugar-cane yield (not OCSB province×mill). "
        "No live CCS sweetness. GWETROOT stands in for SMAP/ETa drought "
        "indices (SEaI12) used in Thai drought-cane papers."),
    non_weather_drivers=(
        "OCSB cane price, mill capacity, ratoon age, and labour; 2019/20 "
        "COVID + drought compound shock (Chula 2022 thesis)."),
    sources=[
        "Pipitpukdee et al. (2020) Atmosphere — Kasetsart/spatial ENSO cane",
        "Pattanapanchai et al. (2022) Agronomy 12:2005 — sat+weather cane",
        "Promping et al. EASR — SEaI12 drought × cane yield / Nino3.4",
        "Kapetch et al. (2014) Thai Agric. Res. J. — DSSAT-CANEGRO N/NE",
        "OCSB / Office of the Cane and Sugar Board production stats",
    ],
)


# ---------------------------------------------------------------------------
# Chao Phraya — wet-season (main) rice
# ---------------------------------------------------------------------------

CP_RICE_POINTS = [
    {"name": "Ayutthaya", "lat": 14.35, "lon": 100.55, "elevation": 5,
     "weight": 0.20},
    {"name": "Suphan_Buri_Rice", "lat": 14.47, "lon": 100.12, "elevation": 10,
     "weight": 0.18},
    {"name": "Nakhon_Sawan", "lat": 15.70, "lon": 100.12, "elevation": 30,
     "weight": 0.16},
    {"name": "Chainat", "lat": 15.18, "lon": 100.13, "elevation": 15,
     "weight": 0.14},
    {"name": "Sing_Buri", "lat": 14.89, "lon": 100.40, "elevation": 10,
     "weight": 0.12},
    {"name": "Pathum_Thani", "lat": 14.02, "lon": 100.53, "elevation": 5,
     "weight": 0.10},
    {"name": "Ang_Thong", "lat": 14.59, "lon": 100.45, "elevation": 8,
     "weight": 0.10},
]

WET_MAIN = [(5, 0), (6, 0), (7, 0), (8, 0), (9, 0), (10, 0)]
WET_MID = [(7, 0), (8, 0)]
WET_HARVEST = [(10, 0), (11, 0)]


def _rice_wet(daily, y, point):
    return {
        "onset_doy": C.monsoon_onset_doy(daily, y),
        "precip_wet": C.window_sum(daily, "precip", WET_MAIN, y),
        "sm_mid": C.window_mean(daily, "gwetroot", WET_MID, y),
        "wd_mid": C.water_deficit(daily, WET_MID, y),
        "dry_spell_mid": C.max_dry_spell(daily, WET_MID, y),
        "flood_days_harvest": C.rainy_days(daily, WET_HARVEST, y, mm=20.0),
        "edd_33_wet": C.edd(daily, WET_MAIN, y, 33.0),
        "heat_days_35_wet": C.heat_days(daily, WET_MAIN, y, 35.0),
    }


RICE_WET = RegionCrop(
    key="chao_phraya_rice_wet",
    label="Chao Phraya wet-season rice",
    label_ko="짜오프라야 우기 쌀",
    crop="rice",
    faostat_item="Rice",
    points=CP_RICE_POINTS,
    build=_rice_wet,
    doc="Regions/태국/중부_짜오프라야/쌀 + Prabnakorn et al. 2018",
    yield_base_kg_ha=2800.0,
    yield_growth=0.010,
    calendar_year_crop=True,
    start_year=1985,
    critical_window=WET_MAIN,
    oni_window=({"MAM", "AMJ"}, {"JJA", "JAS"}),
    core=["onset_delay", "sm_mid", "dry_spell_mid", "oni_season",
          "flood_days_harvest", "precip_wet"],
    caveat=(
        "FAOSTAT national rice mixes wet+dry seasons and basins outside "
        "Chao Phraya. Onset/flood features follow Prabnakorn/Limsakul ENSO "
        "rainfall literature, not OAE wet-only provincial yields."),
    non_weather_drivers=(
        "Variety turnover, fertiliser, and irrigation expansion outside the "
        "strict rainfed Isan share."),
    sources=[
        "Prabnakorn et al. (2018) Climatic Change — rice × ENSO Thailand",
        "Limsakul et al. (2014) J. Earth Sci. — ENSO–rainfall maps",
        "OAE Agricultural Statistics of Thailand",
    ],
)


# ---------------------------------------------------------------------------
# Chao Phraya — off-season (dry) irrigated rice
# Harvest year y; sown ~Dec(y-1)–Jan(y); critical Nov storage decision.
# ---------------------------------------------------------------------------

# Upstream catchment proxies near Bhumibol (Ping) and Sirikit (Nan)
DAM_CATCHMENT_POINTS = [
    {"name": "Bhumibol_catchment", "lat": 17.24, "lon": 99.00, "elevation": 200,
     "weight": 0.55, "role": "upstream"},
    {"name": "Sirikit_catchment", "lat": 17.76, "lon": 100.56, "elevation": 180,
     "weight": 0.45, "role": "upstream"},
]

# Irrigated plain points (same as wet, reweighted) + catchment for dam proxy
OFF_POINTS = [
    {"name": "Ayutthaya", "lat": 14.35, "lon": 100.55, "elevation": 5,
     "weight": 0.18, "role": "plain"},
    {"name": "Suphan_Buri_Rice", "lat": 14.47, "lon": 100.12, "elevation": 10,
     "weight": 0.16, "role": "plain"},
    {"name": "Nakhon_Sawan", "lat": 15.70, "lon": 100.12, "elevation": 30,
     "weight": 0.14, "role": "plain"},
    {"name": "Chainat", "lat": 15.18, "lon": 100.13, "elevation": 15,
     "weight": 0.12, "role": "plain"},
    {"name": "Bhumibol_catchment", "lat": 17.24, "lon": 99.00, "elevation": 200,
     "weight": 0.22, "role": "upstream"},
    {"name": "Sirikit_catchment", "lat": 17.76, "lon": 100.56, "elevation": 180,
     "weight": 0.18, "role": "upstream"},
]

WET_PRIOR = [(5, -1), (6, -1), (7, -1), (8, -1), (9, -1), (10, -1)]
OFF_DRY = [(11, -1), (12, -1), (1, 0), (2, 0), (3, 0), (4, 0)]
OFF_HEAT = [(2, 0), (3, 0)]


def _rice_off(daily, y, point):
    wet_p = C.window_sum(daily, "precip", WET_PRIOR, y)
    role = point.get("role", "plain")
    out = {
        "precip_wet_prior": wet_p,
        "heat_days_35_off": C.heat_days(daily, OFF_HEAT, y, 35.0),
        "edd_35_off": C.edd(daily, OFF_HEAT, y, 35.0),
        "tmax_off_peak": C.window_mean(daily, "tmax", OFF_HEAT, y),
        "precip_off": C.window_sum(daily, "precip", OFF_DRY, y),
        "role_upstream": 1.0 if role == "upstream" else 0.0,
    }
    # Dam proxy filled later at region level with ONI; local wet still stored.
    if role == "upstream":
        out["upstream_wet_precip"] = wet_p
    else:
        out["upstream_wet_precip"] = 0.0
    return out


RICE_OFF = RegionCrop(
    key="chao_phraya_rice_off",
    label="Chao Phraya off-season rice",
    label_ko="짜오프라야 건기 쌀",
    crop="rice",
    faostat_item="Rice",
    points=OFF_POINTS,
    build=_rice_off,
    doc="Regions/태국/중부_짜오프라야/쌀 + TDRI dam-irrigation mechanism",
    yield_base_kg_ha=3200.0,
    yield_growth=0.010,
    calendar_year_crop=False,  # season rolls with Nov storage decision
    start_year=1985,
    critical_window=OFF_DRY,
    oni_window=({"SON", "OND", "NDJ"}, {"DJF", "JFM"}),
    core=["dam_recharge_proxy", "oni_djf", "heat_days_35_off",
          "upstream_wet_precip"],
    caveat=(
        "CRITICAL: dam_recharge_proxy ≠ RID Nov-1 Bhumibol+Sirikit storage. "
        "Policy planting bans act on AREA more than yield; FAOSTAT national "
        "rice mixes seasons. Do not claim irrigation-allocation skill until "
        "Thaiwater/RID series is wired."),
    non_weather_drivers=(
        "RID/ONWR dry-season planting permits, municipal/industrial water "
        "priority, and farm-gate rice price."),
    sources=[
        "TDRI Chaiyasit technical report — Chao Phraya water & dry-season rice",
        "Kyaw / Chulalongkorn AER 2024 — Bhumibol–Sirikit operations",
        "Ekasingh et al. (2007) World Bank/SEI — irrigated CP rice mechanism",
        "RID Daily Reservoir Water Situation; Thaiwater HAII",
    ],
)


# ---------------------------------------------------------------------------
# Natural rubber — South + expanding NE
# ---------------------------------------------------------------------------

RUBBER_POINTS = [
    {"name": "Songkhla_Hat_Yai", "lat": 7.00, "lon": 100.47, "elevation": 20,
     "weight": 0.22},
    {"name": "Surat_Thani", "lat": 9.14, "lon": 99.33, "elevation": 10,
     "weight": 0.18},
    {"name": "Nakhon_Si_Thammarat", "lat": 8.43, "lon": 99.96, "elevation": 15,
     "weight": 0.16},
    {"name": "Trang", "lat": 7.56, "lon": 99.61, "elevation": 20,
     "weight": 0.12},
    {"name": "Phatthalung", "lat": 7.62, "lon": 100.07, "elevation": 15,
     "weight": 0.10},
    {"name": "Chumphon", "lat": 10.49, "lon": 99.18, "elevation": 10,
     "weight": 0.10},
    # Northeast expansion belt
    {"name": "Bueng_Kan", "lat": 18.36, "lon": 103.65, "elevation": 160,
     "weight": 0.06},
    {"name": "Nong_Khai", "lat": 17.88, "lon": 102.74, "elevation": 160,
     "weight": 0.06},
]

# Main tapping window (south): avoid heaviest SW monsoon peak for loss days
TAP_MAIN = [(1, 0), (2, 0), (3, 0), (4, 0), (5, 0), (11, -1), (12, -1)]
TAP_WET = [(5, 0), (6, 0), (7, 0), (8, 0), (9, 0), (10, 0)]


def _rubber(daily, y, point):
    return {
        "rainy_days_1mm": C.rainy_days(daily, TAP_MAIN, y, mm=1.0),
        "rainy_days_5mm": C.rainy_days_tapping(daily, TAP_MAIN, y, mm=5.0),
        "rainy_days_wet_season": C.rainy_days(daily, TAP_WET, y, mm=1.0),
        "precip_tapping": C.window_sum(daily, "precip", TAP_MAIN, y),
        "precip_wet": C.window_sum(daily, "precip", TAP_WET, y),
        "sm_tapping": C.window_mean(daily, "gwetroot", TAP_MAIN, y),
        "tmax_tapping": C.window_mean(daily, "tmax", TAP_MAIN, y),
    }


RUBBER = RegionCrop(
    key="thailand_rubber",
    label="Thailand natural rubber",
    label_ko="태국 천연고무",
    crop="rubber",
    faostat_item="Natural rubber in primary forms",
    points=RUBBER_POINTS,
    build=_rubber,
    doc="Regions/태국/중부_북동부/설탕_고무 + Makkaew & Sdoodee 2015",
    yield_base_kg_ha=1600.0,
    yield_growth=0.006,
    calendar_year_crop=True,
    start_year=1985,
    critical_window=TAP_MAIN + TAP_WET,
    oni_window=({"AMJ", "MJJ", "JJA"}, {"JAS", "ASO"}),
    core=["rainy_days_5mm", "rainy_days_1mm", "oni_season", "precip_wet"],
    caveat=(
        "FAOSTAT national rubber; rainy-day loss is a tapping-opportunity "
        "proxy, not measured latex kg/tree. NE vs South rainfall signs can "
        "oppose (Thaiburi 2025 JAM)."),
    non_weather_drivers=(
        "Farm-gate rubber price, tapping frequency, labour, clone RRIM600 "
        "share, and Pestalotiopsis / leaf disease."),
    sources=[
        "Makkaew & Sdoodee (2015) IJAT — Songkhla rainy days × tapping yield",
        "Thaiburi et al. (2025) J. Agrometeorology — climate × rubber TH",
        "FAO WPP/MPP rubber production potential (East/NE Thailand)",
    ],
)


# ---------------------------------------------------------------------------
# Isan cassava — T2 stub (CMD, not weather-primary)
# ---------------------------------------------------------------------------

CASSAVA_POINTS = [
    {"name": "Nakhon_Ratchasima_Cassava", "lat": 14.97, "lon": 102.10,
     "elevation": 180, "weight": 0.40},
    {"name": "Kalasin", "lat": 16.43, "lon": 103.51, "elevation": 150,
     "weight": 0.30},
    {"name": "Roi_Et", "lat": 16.05, "lon": 103.65, "elevation": 140,
     "weight": 0.30},
]


def _cassava(daily, y, point):
    grow = [(5, 0), (6, 0), (7, 0), (8, 0), (9, 0), (10, 0)]
    return {
        "precip_grow": C.window_sum(daily, "precip", grow, y),
        "sm_grow": C.window_mean(daily, "gwetroot", grow, y),
        "wd_grow": C.water_deficit(daily, grow, y),
    }


CASSAVA = RegionCrop(
    key="isan_cassava",
    label="Isan cassava (T2 stub — CMD)",
    label_ko="이산 카사바",
    crop="cassava",
    faostat_item="Cassava, fresh",
    points=CASSAVA_POINTS,
    build=_cassava,
    doc="Regions/태국/북동부_이산/카사바",
    yield_base_kg_ha=22000.0,
    calendar_year_crop=True,
    tier="T2",
    stub=True,
    core=["sm_grow", "wd_grow", "oni_djf"],
    critical_window=[(5, 0), (6, 0), (7, 0), (8, 0), (9, 0), (10, 0)],
    caveat=(
        "Cassava Mosaic Disease (CMD) / whitefly dominates recent supply "
        "risk — weather-only ridge is not an honest production forecast. "
        "Use reference panel until disease incidence is wired."),
    sources=[
        "Regions/태국 cassava guide — CMD / whitefly mechanism",
        "OAE cassava statistics (labels only if promoted from stub)",
    ],
)


ALL = [SUGARCANE, RICE_WET, RICE_OFF, RUBBER]
ALL_WITH_STUBS = ALL + [CASSAVA]
BY_KEY = {c.key: c for c in ALL_WITH_STUBS}
