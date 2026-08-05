"""
One config per Vietnam region-crop, faithful to Regions/베트남 methodology.

T1: Mekong Delta WS rice (salinity/ENSO), Central Highlands robusta (WD +
irrigation buffer + Kath temp), Red River Delta rice (typhoon/flood/coast).
T2 stubs: Central Coast rice, black pepper — schema only / optional collect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

import pandas as pd

from . import climate as C


@dataclass
class RegionCrop:
    key: str
    label: str
    label_ko: str
    crop: str
    points: list
    build: Callable                      # (daily, harvest_year, point) -> dict
    doc: str
    # Yield label keys for labels.py provisional series
    yield_base_kg_ha: float
    yield_growth: float = 0.012          # annual log-linear tech growth
    calendar_year_crop: bool = False
    start_year: int = 1985
    panel: dict = field(default_factory=dict)
    core: list = field(default_factory=list)
    critical_window: list = field(default_factory=list)
    # ONI window: (prev-year seasons set, harvest-year seasons set)
    oni_window: tuple = field(
        default_factory=lambda: ({"OND", "NDJ"}, {"DJF", "JFM"}))
    min_train: int = 0
    regime_start: int = 0
    tier: str = "T1"
    stub: bool = False
    non_weather_drivers: str = ""
    caveat: str = ""


# ---------------------------------------------------------------------------
# Mekong Delta — Winter–Spring (Đông Xuân) rice
# Harvest ~Mar–Apr of year y; critical dry salinity window Dec(y-1)–Apr(y).
# Coastal vs inland stratification via coast_km on each point.
# ---------------------------------------------------------------------------

MEKONG_POINTS = [
    # Coastal / salinity-exposed
    {"name": "Ben Tre", "lat": 10.24, "lon": 106.38, "elevation": 2,
     "weight": 0.14, "coast_km": 12},
    {"name": "Tra Vinh", "lat": 9.93, "lon": 106.34, "elevation": 2,
     "weight": 0.12, "coast_km": 18},
    {"name": "Soc Trang", "lat": 9.60, "lon": 105.97, "elevation": 2,
     "weight": 0.13, "coast_km": 22},
    {"name": "Bac Lieu", "lat": 9.29, "lon": 105.72, "elevation": 2,
     "weight": 0.10, "coast_km": 8},
    {"name": "Ca Mau", "lat": 9.18, "lon": 105.15, "elevation": 1,
     "weight": 0.09, "coast_km": 15},
    # Inland / upper delta (freshwater, flood rather than salt)
    {"name": "An Giang", "lat": 10.52, "lon": 105.13, "elevation": 5,
     "weight": 0.16, "coast_km": 120},
    {"name": "Dong Thap", "lat": 10.46, "lon": 105.63, "elevation": 4,
     "weight": 0.14, "coast_km": 95},
    {"name": "Can Tho", "lat": 10.05, "lon": 105.75, "elevation": 3,
     "weight": 0.12, "coast_km": 70},
]

# Dry-season salinity peak window for WS rice (master §1.1, §1.5)
WS_DRY = [(12, -1), (1, 0), (2, 0), (3, 0), (4, 0)]
WS_PEAK = [(2, 0), (3, 0), (4, 0)]
# Preceding wet-season recharge (May–Oct of y-1) as Q_river memory proxy
WS_WET_PRIOR = [(5, -1), (6, -1), (7, -1), (8, -1), (9, -1), (10, -1)]
# Monsoon flood window for dual risk (upper delta, AW calendar remnant)
WS_FLOOD = [(8, -1), (9, -1), (10, -1), (11, -1)]


def _mekong_rice(daily, y, point):
    dry_p = C.window_sum(daily, "precip", WS_DRY, y)
    wet_p = C.window_sum(daily, "precip", WS_WET_PRIOR, y)
    dry_et0 = C.window_sum(daily, "et0", WS_DRY, y)
    # Flow / tidal contrast proxy without MRC discharge: dry moisture + wet memory.
    dry_flow = dry_p
    # ONI is injected later by collect; builders use 0.0 here, then salt is
    # recomputed at region level with ONI. Local water parts still filled.
    salt = C.salinity_proxy(
        point.get("coast_km", 50.0), dry_flow, 0.0, wet_p)
    return {
        "precip_dry_ws": dry_p,
        "precip_wet_prior": wet_p,
        "et0_dry_ws": dry_et0,
        "wd_dry_ws": C.water_deficit(daily, WS_DRY, y),
        "heat_days_35_ws": C.heat_days(daily, WS_PEAK, y, 35.0),
        "tmax_peak": C.window_mean(daily, "tmax", WS_PEAK, y),
        "sm_dry": C.window_mean(daily, "gwetroot", WS_PEAK, y),
        "flood_wet_days": C.extreme_rain_days(daily, WS_FLOOD, y, 40.0),
        "flood_spell": C.consecutive_wet_spell(daily, WS_FLOOD, y, 25.0),
        "coast_km": float(point.get("coast_km", 50.0)),
        # salt_proxy / ec_proxy without ONI — region blend overwrites with ONI
        "salt_water_index": salt["salt_proxy"],
        "ec_proxy_hydro": salt["ec_proxy"],
        "y_rel_salt_hydro": salt["y_rel_salt"],
    }


MEKONG_RICE = RegionCrop(
    key="mekong_rice_ws",
    label="Mekong Delta Winter–Spring rice",
    label_ko="메콩 삼각주 동춘(건기) 쌀",
    crop="rice",
    points=MEKONG_POINTS,
    build=_mekong_rice,
    doc="Regions/베트남/베트남_쌀_커피_상세수식.md §1 + 메콩삼각주",
    yield_base_kg_ha=5200.0,
    yield_growth=0.011,
    calendar_year_crop=False,
    start_year=1985,
    # WS harvest Mar–Apr; season under way from prior November sowing
    critical_window=[(12, -1), (1, 0), (2, 0), (3, 0), (4, 0)],
    oni_window=({"OND", "NDJ"}, {"DJF", "JFM"}),
    core=["salt_proxy", "oni_djf", "precip_dry_ws", "heat_days_35_ws",
          "wd_dry_ws", "y_rel_salt"],
    caveat=(
        "Labels: GSO Yearbook Mekong-region spring paddy (2018–2023) + MTN "
        "GSO-style provincial Đông Xuân (2017/2024); pre-2017 is FAOSTAT "
        "national rice scaled to WS overlap — not true province×WS. "
        "salt_proxy is not measured EC; no MRC discharge, no Sentinel-1 area."),
    non_weather_drivers=(
        "Early planting adaptation, canal sluice management, shrimp–rice "
        "conversion, and export market prices move Mekong WS area and intensity "
        "independently of weather."),
)


# ---------------------------------------------------------------------------
# Central Highlands — Robusta coffee
# Critical moisture stress: Feb–Apr flowering; harvest year = calendar year of
# the main bean crop (often Oct–Dec bagging).
# ---------------------------------------------------------------------------

COFFEE_POINTS = [
    {"name": "Buon Ma Thuot", "lat": 12.67, "lon": 108.04, "elevation": 470,
     "weight": 0.32, "irrig_fraction": 0.75},
    {"name": "Dak Nong", "lat": 12.00, "lon": 107.69, "elevation": 620,
     "weight": 0.18, "irrig_fraction": 0.70},
    {"name": "Pleiku", "lat": 13.98, "lon": 108.00, "elevation": 780,
     "weight": 0.22, "irrig_fraction": 0.65},
    {"name": "Di Linh", "lat": 11.58, "lon": 108.07, "elevation": 990,
     "weight": 0.18, "irrig_fraction": 0.55},
    {"name": "Kon Tum", "lat": 14.35, "lon": 108.00, "elevation": 530,
     "weight": 0.10, "irrig_fraction": 0.50},
]

COFFEE_WD = [(2, 0), (3, 0), (4, 0)]
COFFEE_GS = [(3, 0), (4, 0), (5, 0), (6, 0), (7, 0), (8, 0), (9, 0)]
COFFEE_WET_PRIOR = [(5, -1), (6, -1), (7, -1), (8, -1), (9, -1), (10, -1)]


def _coffee_robusta(daily, y, point):
    wd = C.water_deficit(daily, COFFEE_WD, y)
    # Irrigation buffer: SM retention days + static irrig_fraction γ (§2.2).
    i_sm = C.irrigation_buffer_proxy(daily, COFFEE_WD, y)
    gamma = float(point.get("irrig_fraction", 0.6))
    # Convert SM day counts (~0–90) and irrig fraction into mm-equivalent buffer.
    i_proxy = gamma * (40.0 + 1.5 * (i_sm if not pd.isna(i_sm) else 0.0))
    wd_eff = max(0.0, (wd if not pd.isna(wd) else 0.0) - i_proxy)
    tpen, tmin_gs, tmax_gs = C.kath_temp_penalty(daily, COFFEE_GS, y)
    return {
        "wd_feb_apr": wd,
        "irrigation_buffer_mm": float(i_proxy),
        "irrig_fraction": gamma,
        "wd_eff": float(wd_eff),
        "sm_flowering_days_above": i_sm,
        "sm_flowering": C.window_mean(daily, "gwetroot", COFFEE_WD, y),
        "t_penalty_kath": tpen,
        "tmin_gs": tmin_gs,
        "tmax_gs": tmax_gs,
        "precip_feb_apr": C.window_sum(daily, "precip", COFFEE_WD, y),
        "precip_wet_prior": C.window_sum(daily, "precip", COFFEE_WET_PRIOR, y),
        "et0_feb_apr": C.window_sum(daily, "et0", COFFEE_WD, y),
    }


COFFEE_ROBUSTA = RegionCrop(
    key="central_highlands_coffee",
    label="Central Highlands robusta coffee",
    label_ko="중부 고원 로부스타 커피",
    crop="coffee",
    points=COFFEE_POINTS,
    build=_coffee_robusta,
    doc="Regions/베트남/베트남_쌀_커피_상세수식.md §2 + 중부고원/커피",
    yield_base_kg_ha=2100.0,   # kg green bean / ha provisional order
    yield_growth=0.008,
    calendar_year_crop=True,
    start_year=1985,
    critical_window=[(2, 0), (3, 0), (4, 0)],
    oni_window=(set(), {"DJF", "JFM", "FMA"}),
    core=["wd_eff", "t_penalty_kath", "sm_flowering", "oni_djf",
          "precip_wet_prior"],
    caveat=(
        "Labels provisional. irrigation_buffer is POWER GWETROOT retention × "
        "literature irrig_fraction dummies — not metered irrigation. "
        "Never interpret WD alone as yield without this buffer."),
    non_weather_drivers=(
        "Fertiliser, biennial bearing, farm-gate price, and tree age dominate "
        "robusta production; irrigation expansion changed the moisture surface "
        "after 2000."),
)


# ---------------------------------------------------------------------------
# Red River Delta — rice (double crop system; spring focus)
# ---------------------------------------------------------------------------

RRD_POINTS = [
    {"name": "Thai Binh", "lat": 20.45, "lon": 106.34, "elevation": 3,
     "weight": 0.22, "coast_km": 15},
    {"name": "Nam Dinh", "lat": 20.42, "lon": 106.17, "elevation": 3,
     "weight": 0.20, "coast_km": 18},
    {"name": "Hai Phong", "lat": 20.86, "lon": 106.68, "elevation": 5,
     "weight": 0.16, "coast_km": 8},
    {"name": "Hung Yen", "lat": 20.65, "lon": 106.05, "elevation": 5,
     "weight": 0.16, "coast_km": 45},
    {"name": "Ninh Binh", "lat": 20.25, "lon": 105.97, "elevation": 10,
     "weight": 0.14, "coast_km": 35},
    {"name": "Ha Nam", "lat": 20.54, "lon": 105.92, "elevation": 8,
     "weight": 0.12, "coast_km": 55},
]

RRD_SPRING = [(2, 0), (3, 0), (4, 0), (5, 0)]
RRD_DRY_SALT = [(12, -1), (1, 0), (2, 0), (3, 0)]
RRD_TYPHOON = [(6, 0), (7, 0), (8, 0), (9, 0), (10, 0), (11, 0)]


def _rrd_rice(daily, y, point):
    dry_p = C.window_sum(daily, "precip", RRD_DRY_SALT, y)
    wet_p = C.window_sum(daily, "precip", RRD_TYPHOON, y)
    salt = C.salinity_proxy(
        point.get("coast_km", 40.0), dry_p, 0.0, wet_p)
    return {
        "precip_spring": C.window_sum(daily, "precip", RRD_SPRING, y),
        "precip_dry_coast": dry_p,
        "precip_typhoon_window": wet_p,
        "extreme_rain_days": C.extreme_rain_days(daily, RRD_TYPHOON, y, 80.0),
        "flood_spell": C.consecutive_wet_spell(daily, RRD_TYPHOON, y, 30.0),
        "heat_days_35": C.heat_days(daily, RRD_SPRING, y, 35.0),
        "tmax_spring": C.window_mean(daily, "tmax", RRD_SPRING, y),
        "coast_km": float(point.get("coast_km", 40.0)),
        "salt_water_index": salt["salt_proxy"],
        "ec_proxy_hydro": salt["ec_proxy"],
        # IBTrACS not wired: extreme rain day count is the cyclone exposure proxy
        "cyclone_rain_proxy": C.extreme_rain_days(daily, RRD_TYPHOON, y, 100.0),
    }


RRD_RICE = RegionCrop(
    key="red_river_rice",
    label="Red River Delta rice",
    label_ko="홍강 삼각주 쌀",
    crop="rice",
    points=RRD_POINTS,
    build=_rrd_rice,
    doc="Regions/베트남/베트남_쌀_커피_상세수식.md §3 + 홍강삼각주",
    yield_base_kg_ha=5600.0,
    yield_growth=0.010,
    calendar_year_crop=True,
    start_year=1985,
    critical_window=[(2, 0), (3, 0), (4, 0), (5, 0)],
    oni_window=({"OND", "NDJ"}, {"DJF", "JFM"}),
    core=["flood_spell", "cyclone_rain_proxy", "salt_proxy", "oni_djf",
          "heat_days_35"],
    caveat=(
        "Labels provisional. No IBTrACS distance product yet — cyclone exposure "
        "is extreme rainfall day counts in the monsoon window only."),
    non_weather_drivers=(
        "Dike systems, urbanisation of peri-delta farmland, and seed variety "
        "turnover (IRRI/AGI lineages) dominate RRD yield levels."),
)


# ---------------------------------------------------------------------------
# T2 stubs — collect/train skip unless explicitly requested
# ---------------------------------------------------------------------------

COAST_POINTS = [
    {"name": "Hue", "lat": 16.46, "lon": 107.59, "elevation": 8,
     "weight": 0.35, "coast_km": 10},
    {"name": "Da Nang", "lat": 16.05, "lon": 108.20, "elevation": 10,
     "weight": 0.30, "coast_km": 5},
    {"name": "Quy Nhon", "lat": 13.78, "lon": 109.22, "elevation": 8,
     "weight": 0.35, "coast_km": 5},
]


def _coast_rice(daily, y, point):
    dry = [(1, 0), (2, 0), (3, 0), (4, 0)]
    storm = [(8, 0), (9, 0), (10, 0), (11, 0)]
    dry_p = C.window_sum(daily, "precip", dry, y)
    salt = C.salinity_proxy(point.get("coast_km", 10.0), dry_p, 0.0,
                            C.window_sum(daily, "precip", storm, y))
    return {
        "precip_dry": dry_p,
        "cyclone_rain_proxy": C.extreme_rain_days(daily, storm, y, 80.0),
        "salt_water_index": salt["salt_proxy"],
        "heat_days_35": C.heat_days(daily, dry, y, 35.0),
    }


CENTRAL_COAST_RICE = RegionCrop(
    key="central_coast_rice",
    label="Central Coast rice (T2 stub)",
    label_ko="중부 연안 쌀",
    crop="rice",
    points=COAST_POINTS,
    build=_coast_rice,
    doc="Regions/베트남/베트남_쌀_커피_상세수식.md §4",
    yield_base_kg_ha=4800.0,
    calendar_year_crop=True,
    tier="T2",
    stub=True,
    core=["salt_proxy", "cyclone_rain_proxy", "oni_djf"],
    critical_window=[(1, 0), (2, 0), (3, 0), (8, 0), (9, 0), (10, 0)],
    caveat="T2 optional stub — lower national supply share; sparse labels.",
)


def _pepper(daily, y, point):
    dry = [(11, -1), (12, -1), (1, 0), (2, 0), (3, 0), (4, 0)]
    return {
        "wd_dry": C.water_deficit(daily, dry, y),
        "sm_dry": C.window_mean(daily, "gwetroot", dry, y),
        "precip_dry": C.window_sum(daily, "precip", dry, y),
        "t_penalty_kath": C.kath_temp_penalty(daily, dry, y)[0],
    }


PEPPER = RegionCrop(
    key="central_highlands_pepper",
    label="Central Highlands black pepper (T2 stub)",
    label_ko="중부 고원 흑후추",
    crop="pepper",
    points=COFFEE_POINTS[:3],
    build=_pepper,
    doc="Regions/베트남/베트남_쌀_커피_상세수식.md §5",
    yield_base_kg_ha=2800.0,
    calendar_year_crop=True,
    tier="T2",
    stub=True,
    core=["wd_dry", "sm_dry", "oni_djf"],
    critical_window=[(12, -1), (1, 0), (2, 0), (3, 0), (4, 0)],
    caveat="T2 stub — export risk indicator priority; thin farm yield panels.",
)


ALL = [MEKONG_RICE, COFFEE_ROBUSTA, RRD_RICE]
ALL_WITH_STUBS = ALL + [CENTRAL_COAST_RICE, PEPPER]
BY_KEY = {c.key: c for c in ALL_WITH_STUBS}
