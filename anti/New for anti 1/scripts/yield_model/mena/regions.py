"""
One config per MENA region-crop, faithful to Regions/중동_북아프리카_MENA.

T1: Nile irrigated wheat, Atlantic Morocco rainfed, Hauts Plateaux Algeria.
T2 stub: Tunisia — schema only unless --stubs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from . import climate as C

# Growing-season rainfall (Nov–Apr) for Maghreb rainfed wheat
GSR_NOV_APR = [(11, -1), (12, -1), (1, 0), (2, 0), (3, 0), (4, 0)]
TILLERING = [(2, 0), (3, 0)]
HEADING = [(3, 0), (4, 0)]
PRESEASON_OCT = [(10, -1)]
GS_WD = GSR_NOV_APR

# Nile wet / Blue Nile JJAS inflow memory (harvest year y → summer y−1)
NILE_WET = [(6, -1), (7, -1), (8, -1), (9, -1)]

BLUE_NILE_POINTS = [
    {"name": "Bahir Dar", "lat": 11.60, "lon": 37.39, "elevation": 1800,
     "weight": 0.40},
    {"name": "Gonder", "lat": 12.60, "lon": 37.47, "elevation": 2200,
     "weight": 0.30},
    {"name": "Debre Markos", "lat": 10.35, "lon": 37.74, "elevation": 2500,
     "weight": 0.30},
]


@dataclass
class RegionCrop:
    key: str
    label: str
    label_ko: str
    crop: str
    points: list
    build: Callable                      # (daily, harvest_year, point) -> dict
    doc: str
    yield_base_kg_ha: float
    yield_growth: float = 0.010
    calendar_year_crop: bool = False
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
    faostat_area: str = ""
    non_weather_drivers: str = ""
    caveat: str = ""


# ---------------------------------------------------------------------------
# Egypt — Nile Delta / Middle Egypt irrigated wheat
# ---------------------------------------------------------------------------

EGYPT_POINTS = [
    {"name": "Kafr El-Sheikh", "lat": 31.11, "lon": 30.94, "elevation": 5,
     "weight": 0.20, "coast_km": 25, "irrig_fraction": 0.98,
     "sand_fraction": 0.42, "awc_mm": 120},
    {"name": "Beheira", "lat": 30.85, "lon": 30.60, "elevation": 8,
     "weight": 0.18, "coast_km": 35, "irrig_fraction": 0.97,
     "sand_fraction": 0.45, "awc_mm": 115},
    {"name": "Dakahlia", "lat": 31.05, "lon": 31.38, "elevation": 10,
     "weight": 0.18, "coast_km": 40, "irrig_fraction": 0.96,
     "sand_fraction": 0.40, "awc_mm": 118},
    {"name": "Sharqia", "lat": 30.58, "lon": 31.50, "elevation": 12,
     "weight": 0.16, "coast_km": 55, "irrig_fraction": 0.95,
     "sand_fraction": 0.38, "awc_mm": 120},
    {"name": "Minya", "lat": 28.09, "lon": 30.75, "elevation": 25,
     "weight": 0.14, "coast_km": 180, "irrig_fraction": 0.94,
     "sand_fraction": 0.35, "awc_mm": 125},
    {"name": "Asyut", "lat": 27.18, "lon": 31.18, "elevation": 60,
     "weight": 0.14, "coast_km": 250, "irrig_fraction": 0.92,
     "sand_fraction": 0.33, "awc_mm": 128},
]

EGYPT_WD = [(2, 0), (3, 0), (4, 0)]
EGYPT_GS = [(12, -1), (1, 0), (2, 0), (3, 0), (4, 0)]
EGYPT_DRY = [(12, -1), (1, 0), (2, 0)]


def _egypt_nile_wheat(daily, y, point):
    wd = C.water_deficit(daily, EGYPT_WD, y)
    i_sm = C.irrigation_buffer_proxy(daily, EGYPT_WD, y)
    gamma = float(point.get("irrig_fraction", 0.95))
    awc_eff = C.effective_awc_mm(point.get("awc_mm", 120),
                                 point.get("sand_fraction", 0.40))
    i_proxy = gamma * (45.0 + 1.4 * (i_sm if not pd.isna(i_sm) else 0.0))
    wd_eff = max(0.0, (wd if not pd.isna(wd) else 0.0) - i_proxy)
    dry_p = C.window_sum(daily, "precip", EGYPT_DRY, y)
    salt = C.delta_salt_proxy(point.get("coast_km", 80.0), dry_p, 0.0)
    return {
        "wd_gs": wd,
        "wd_eff": float(wd_eff),
        "irrigation_buffer_mm": float(i_proxy),
        "irrig_fraction": gamma,
        "awc_eff_mm": awc_eff,
        "sand_fraction": float(point.get("sand_fraction", 0.40)),
        "coast_km": float(point.get("coast_km", 80.0)),
        "salt_proxy": salt["salt_proxy"],
        "delta_salt": salt["delta_salt"],
        "sm_grainfill": C.window_mean(daily, "gwetroot", EGYPT_WD, y),
        "edd_heading": C.edd(daily, HEADING, y, 32.0),
        "heat_days_32": C.heat_days(daily, HEADING, y, 32.0),
        "vpd_heading": C.window_mean(daily, "vpd_max", HEADING, y),
        "tmax_heading": C.window_mean(daily, "tmax", HEADING, y),
        "et0_gs": C.window_sum(daily, "et0", EGYPT_GS, y),
        "nile_inflow_proxy": 0.0,  # region blend overwrites from Blue Nile
    }


EGYPT_NILE_WHEAT = RegionCrop(
    key="egypt_nile_wheat",
    label="Egypt Nile irrigated wheat",
    label_ko="이집트 나일 관개 밀",
    crop="wheat",
    points=EGYPT_POINTS,
    build=_egypt_nile_wheat,
    doc="Regions/중동_북아프리카_MENA/MENA_밀_작황_방법론.md §3 이집트",
    yield_base_kg_ha=6800.0,
    yield_growth=0.008,
    calendar_year_crop=False,
    start_year=1985,
    critical_window=[(2, 0), (3, 0), (4, 0)],
    oni_window=({"OND", "NDJ"}, {"DJF", "JFM"}),
    faostat_area="Egypt",
    core=["wd_eff", "salt_proxy", "nile_inflow_proxy", "oni_ndj",
          "edd_heading", "sm_grainfill"],
    caveat=(
        "Labels: FAOSTAT national wheat — not governorate×season. "
        "salt_proxy and nile_inflow_proxy are hydrologic stand-ins, not EC "
        "or G-REALM stage. WD alone is never yield without irrigation_buffer."),
    non_weather_drivers=(
        "Subsidised fertiliser, area policy, FX, and GASC import strategy "
        "move Nile wheat independently of weather."),
)


# ---------------------------------------------------------------------------
# Morocco — Atlantic rainfed wheat
# ---------------------------------------------------------------------------

MOROCCO_POINTS = [
    {"name": "Chaouia", "lat": 33.00, "lon": -7.60, "elevation": 280,
     "weight": 0.22, "sand_fraction": 0.35, "awc_mm": 145,
     "irrig_fraction": 0.12},
    {"name": "Doukkala", "lat": 32.80, "lon": -8.50, "elevation": 120,
     "weight": 0.20, "sand_fraction": 0.38, "awc_mm": 130,
     "irrig_fraction": 0.10},
    {"name": "Gharb", "lat": 34.40, "lon": -6.30, "elevation": 15,
     "weight": 0.22, "sand_fraction": 0.32, "awc_mm": 150,
     "irrig_fraction": 0.18},
    {"name": "Meknes", "lat": 33.89, "lon": -5.55, "elevation": 520,
     "weight": 0.20, "sand_fraction": 0.30, "awc_mm": 155,
     "irrig_fraction": 0.08},
    {"name": "Sidi El Aidi", "lat": 33.12, "lon": -7.63, "elevation": 450,
     "weight": 0.16, "sand_fraction": 0.33, "awc_mm": 148,
     "irrig_fraction": 0.06},
]


def _rainfed_wheat_builder(daily, y, point):
    awc_eff = C.effective_awc_mm(point.get("awc_mm", 140),
                                 point.get("sand_fraction", 0.35))
    sm_oct = C.window_mean(daily, "gwetroot", PRESEASON_OCT, y)
    stored = (sm_oct if not pd.isna(sm_oct) else 0.0) * awc_eff
    gsr = C.window_sum(daily, "precip", GSR_NOV_APR, y)
    return {
        "gsr_mm": gsr,
        "stored_mm": float(stored),
        "awc_eff_mm": awc_eff,
        "sand_fraction": float(point.get("sand_fraction", 0.35)),
        "irrig_fraction": float(point.get("irrig_fraction", 0.10)),
        "y_w_proxy": C.french_schultz_yw(gsr, stored),
        "spei_like_6": C.spei_like_min(daily, y),
        "spi_gs": C.spi_like_window(daily, GSR_NOV_APR, y),
        "sm_tillering": C.window_mean(daily, "gwetroot", TILLERING, y),
        "wd_gs": C.water_deficit(daily, GS_WD, y),
        "edd_heading": C.edd(daily, HEADING, y, 32.0),
        "heat_days_32": C.heat_days(daily, HEADING, y, 32.0),
        "vpd_heading": C.window_mean(daily, "vpd_max", HEADING, y),
        "tmax_heading": C.window_mean(daily, "tmax", HEADING, y),
        "et0_gs": C.window_sum(daily, "et0", GSR_NOV_APR, y),
    }


MOROCCO_ATLANTIC_WHEAT = RegionCrop(
    key="morocco_atlantic_wheat",
    label="Morocco Atlantic rainfed wheat",
    label_ko="모로코 대서양 천수답 밀",
    crop="wheat",
    points=MOROCCO_POINTS,
    build=_rainfed_wheat_builder,
    doc="Regions/중동_북아프리카_MENA/MENA_밀_작황_방법론.md §3 마그레브",
    yield_base_kg_ha=2200.0,
    yield_growth=0.009,
    calendar_year_crop=False,
    start_year=1985,
    critical_window=[(2, 0), (3, 0), (4, 0)],
    oni_window=({"OND", "NDJ"}, {"DJF", "JFM"}),
    faostat_area="Morocco",
    core=["y_w_proxy", "spei_like_6", "spi_gs", "edd_heading",
          "oni_ndj", "iod_ond"],
    caveat=(
        "Labels: FAOSTAT national wheat — Chaouia ≠ Oriental. "
        "French–Schultz y_w_proxy is a rainfall scaffold, not APSIM potential."),
    non_weather_drivers=(
        "MAPMDREF input subsidies, fallow area swings, and EU import parity "
        "reshape Moroccan wheat area beyond weather."),
)


# ---------------------------------------------------------------------------
# Algeria — Hauts Plateaux rainfed wheat
# ---------------------------------------------------------------------------

ALGERIA_POINTS = [
    {"name": "Setif", "lat": 36.19, "lon": 5.41, "elevation": 1100,
     "weight": 0.28, "sand_fraction": 0.36, "awc_mm": 135,
     "irrig_fraction": 0.07},
    {"name": "Constantine", "lat": 36.36, "lon": 6.61, "elevation": 650,
     "weight": 0.24, "sand_fraction": 0.34, "awc_mm": 140,
     "irrig_fraction": 0.08},
    {"name": "Tiaret", "lat": 35.37, "lon": 1.32, "elevation": 980,
     "weight": 0.24, "sand_fraction": 0.38, "awc_mm": 128,
     "irrig_fraction": 0.05},
    {"name": "Guelma", "lat": 36.46, "lon": 7.43, "elevation": 280,
     "weight": 0.24, "sand_fraction": 0.33, "awc_mm": 142,
     "irrig_fraction": 0.09},
]

ALGERIA_HAUTS_WHEAT = RegionCrop(
    key="algeria_hauts_wheat",
    label="Algeria Hauts Plateaux rainfed wheat",
    label_ko="알제리 고원 천수답 밀",
    crop="wheat",
    points=ALGERIA_POINTS,
    build=_rainfed_wheat_builder,
    doc="Regions/중동_북아프리카_MENA/MENA_밀_작황_방법론.md §3 마그레브",
    yield_base_kg_ha=1800.0,
    yield_growth=0.007,
    calendar_year_crop=False,
    start_year=1985,
    critical_window=[(2, 0), (3, 0), (4, 0)],
    oni_window=({"OND", "NDJ"}, {"DJF", "JFM"}),
    faostat_area="Algeria",
    core=["y_w_proxy", "spei_like_6", "spi_gs", "wd_gs",
          "oni_ndj", "iod_ond"],
    caveat=(
        "Labels: FAOSTAT national wheat/barley mix at country scale. "
        "Setif high-plateau frost risk not separately labelled."),
    non_weather_drivers=(
        "Input access, land fragmentation, and bread-subsidy policy dominate "
        "Algerian plateau yields beyond seasonal rainfall."),
)


# ---------------------------------------------------------------------------
# Tunisia — T2 stub
# ---------------------------------------------------------------------------

TUNISIA_POINTS = [
    {"name": "Beja", "lat": 36.73, "lon": 9.18, "elevation": 120,
     "weight": 0.35, "sand_fraction": 0.36, "awc_mm": 130,
     "irrig_fraction": 0.12},
    {"name": "Kairouan", "lat": 35.68, "lon": 10.10, "elevation": 70,
     "weight": 0.35, "sand_fraction": 0.40, "awc_mm": 125,
     "irrig_fraction": 0.10},
    {"name": "Siliana", "lat": 36.08, "lon": 9.37, "elevation": 450,
     "weight": 0.30, "sand_fraction": 0.34, "awc_mm": 132,
     "irrig_fraction": 0.08},
]


TUNISIA_WHEAT = RegionCrop(
    key="tunisia_wheat",
    label="Tunisia rainfed wheat (T2 stub)",
    label_ko="튀니지 천수답 밀",
    crop="wheat",
    points=TUNISIA_POINTS,
    build=_rainfed_wheat_builder,
    doc="Regions/중동_북아프리카_MENA/MENA_밀_작황_방법론.md §1",
    yield_base_kg_ha=1600.0,
    calendar_year_crop=False,
    tier="T2",
    stub=True,
    faostat_area="Tunisia",
    core=["y_w_proxy", "spei_like_6", "spi_gs", "oni_ndj"],
    critical_window=[(2, 0), (3, 0), (4, 0)],
    caveat="T2 optional stub — lower national supply share; sparse labels.",
)


ALL = [EGYPT_NILE_WHEAT, MOROCCO_ATLANTIC_WHEAT, ALGERIA_HAUTS_WHEAT]
ALL_WITH_STUBS = ALL + [TUNISIA_WHEAT]
BY_KEY = {c.key: c for c in ALL_WITH_STUBS}
