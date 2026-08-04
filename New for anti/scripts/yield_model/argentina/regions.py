"""
One config per region-crop, each faithful to its own 상세분석_및_수식.md.

Six guides, six methodologies, and as in Brazil they deliberately do not share
one: Pampas soy is an FAO Ky water-deficit problem, Pampas corn an ENSO x IOD
problem with an unobserved sowing date, Pampas wheat a frost problem, northern
soy a heat-count problem on a planting-relative window, Chaco cotton a
heat x dryness product masked by degree-day phenology, Tucumán cane a
simulator-baseline problem. Each `build` implements only its own guide.

`build` runs against one location's daily weather; collect.py calls it once per
point and production-weights the results, never the reverse -- averaging the
weather first would erase the threshold exceedances (Tmax > 35, Tmin < 0)
almost every one of these guides is built on.
"""

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from brazil import climate as C
from . import climate_ar as A


@dataclass
class RegionCrop:
    key: str
    label: str
    crop: str                       # magyp.CROPS key
    provinces: list                 # MAGyP province names
    points: list                    # [{name, lat, lon, elevation, weight}]
    build: Callable                 # (daily, harvest_year) -> dict
    doc: str                        # source guide
    departments: list = None        # optional department restriction
    # NASA POWER opens 1981-01-01. Summer crops need the previous September, so
    # 1982 is the first harvest year with a full season behind it. Wheat is
    # sown and harvested inside one calendar year and could start at 1981, but
    # is held at 1982 for comparability.
    start_year: int = 1982
    # Features needing a cross-year view (SPI's Gamma fit, the ENSO x IOD
    # switch, lagged yield). Applied by collect.py after the per-year pass.
    panel: dict = field(default_factory=dict)
    # The guide's own headline variables, tested against the full feature set
    # so the run shows whether the extras earn their place or fit noise.
    core: list = field(default_factory=list)
    # ONI seasons to average, as ({previous-year seasons}, {harvest-year ones}).
    oni_window: tuple = None
    # The months that decide the yield, as (month, year_offset). Used at
    # forecast time to report how much of the deciding window has actually
    # happened, so a figure published while the critical months are still
    # ahead reads as the climatological projection it is.
    critical_window: list = field(default_factory=list)
    # True for a crop sown and harvested inside one calendar year (wheat), so
    # its season does not roll over in September with the summer crops.
    calendar_year_crop: bool = False
    regime_start: int = 0
    min_train: int = 0
    non_weather_drivers: str = ""
    caveat: str = ""


# ---------------------------------------------------------------------------
# Weather points.
#
# The Pampas set is the classic INTA experimental-station transect across the
# three core provinces. Wheat gets its own set because the wheat belt is not
# the soy belt: 57% of Argentine wheat is Buenos Aires and its centre of
# gravity is the cool south (Tres Arroyos, Coronel Suárez), four degrees of
# latitude from the soy core and on a completely different frost calendar.
# ---------------------------------------------------------------------------

PAMPAS_POINTS = [
    {"name": "Pergamino",     "lat": -33.89, "lon": -60.57, "elevation": 65,  "weight": 0.18},
    {"name": "Junin",         "lat": -34.59, "lon": -60.94, "elevation": 81,  "weight": 0.17},
    {"name": "Marcos Juarez", "lat": -32.70, "lon": -62.11, "elevation": 110, "weight": 0.19},
    {"name": "Rio Cuarto",    "lat": -33.12, "lon": -64.35, "elevation": 421, "weight": 0.15},
    {"name": "Venado Tuerto", "lat": -33.75, "lon": -61.97, "elevation": 112, "weight": 0.17},
    {"name": "Rafaela",       "lat": -31.25, "lon": -61.49, "elevation": 99,  "weight": 0.14},
]

# Corn leans harder on Buenos Aires and Córdoba than soy does (33% / 30% / 14%
# of national output against 29% / 28% / 25%), so the same stations carry
# different weights.
PAMPAS_CORN_POINTS = [
    {**p, "weight": w} for p, w in zip(
        PAMPAS_POINTS, [0.22, 0.21, 0.21, 0.18, 0.10, 0.08])
]

WHEAT_POINTS = [
    {"name": "Tres Arroyos",   "lat": -38.38, "lon": -60.28, "elevation": 115, "weight": 0.25},
    {"name": "Coronel Suarez", "lat": -37.46, "lon": -61.93, "elevation": 233, "weight": 0.20},
    {"name": "Pergamino",      "lat": -33.89, "lon": -60.57, "elevation": 65,  "weight": 0.20},
    {"name": "Marcos Juarez",  "lat": -32.70, "lon": -62.11, "elevation": 110, "weight": 0.15},
    {"name": "Venado Tuerto",  "lat": -33.75, "lon": -61.97, "elevation": 112, "weight": 0.20},
]

NORTE_POINTS = [
    {"name": "Quimili",      "lat": -27.64, "lon": -62.42, "elevation": 130, "weight": 0.25},
    {"name": "Bandera",      "lat": -28.69, "lon": -62.24, "elevation": 90,  "weight": 0.18},
    {"name": "Saenz Pena",   "lat": -26.79, "lon": -60.44, "elevation": 92,  "weight": 0.22},
    {"name": "Las Lajitas",  "lat": -24.71, "lon": -64.19, "elevation": 400, "weight": 0.21},
    {"name": "Burruyacu",    "lat": -26.50, "lon": -64.74, "elevation": 340, "weight": 0.14},
]

COTTON_POINTS = [
    {"name": "Saenz Pena",  "lat": -26.79, "lon": -60.44, "elevation": 92, "weight": 0.35},
    {"name": "Las Brenas",  "lat": -27.09, "lon": -61.08, "elevation": 102, "weight": 0.20},
    {"name": "Anatuya",     "lat": -28.46, "lon": -62.83, "elevation": 95, "weight": 0.25},
    {"name": "Formosa",     "lat": -26.18, "lon": -58.18, "elevation": 60, "weight": 0.10},
    {"name": "Reconquista", "lat": -29.15, "lon": -59.65, "elevation": 53, "weight": 0.10},
]

CANE_POINTS = [
    {"name": "Famailla",   "lat": -27.05, "lon": -65.40, "elevation": 363, "weight": 0.40},
    {"name": "Simoca",     "lat": -27.26, "lon": -65.36, "elevation": 340, "weight": 0.30},
    {"name": "Cruz Alta",  "lat": -26.83, "lon": -65.14, "elevation": 430, "weight": 0.30},
]


# ---------------------------------------------------------------------------
# 팜파스 -- 대두: the FAO Ky water-deficit equation.
# ---------------------------------------------------------------------------

def _pampas_soja(daily, y):
    # Sown mid-November, ~145 days to harvest in early April. R1-R5 -- the
    # window the guide calls the year's most critical -- runs mid-January to
    # end of February.
    planting = pd.Timestamp(year=y - 1, month=11, day=15)
    wb = A.water_balance(daily, planting, 145, A.AWC_PAMPAS, A.KC_SOYBEAN)

    veg = (planting, pd.Timestamp(year=y, month=1, day=9), 0.3)
    rep = (pd.Timestamp(year=y, month=1, day=10),
           pd.Timestamp(year=y, month=2, day=28), 1.5)
    late = (pd.Timestamp(year=y, month=3, day=1),
            pd.Timestamp(year=y, month=3, day=31), 0.5)

    return {
        # Sum of Ky * (1 - ETa/ETc): the guide's predicted fractional loss
        "ky_penalty": A.ky_penalty(wb, [veg, rep, late]),
        # The single most-named variable in the guide
        "water_deficit_feb": A.deficit_ratio(
            wb, pd.Timestamp(year=y, month=2, day=1),
            pd.Timestamp(year=y, month=2, day=28)),
        "water_deficit_rep": A.deficit_ratio(wb, rep[0], rep[1]),
        "smi_flowering": A.mean_smi(wb, rep[0], rep[1]),
        # Run length, not a count -- 팜파스/대두 §3A
        "heat_wave_duration": A.heatwave_duration(
            daily, [(1, 0), (2, 0)], y, 35.0),
        "heat_days_35": C.heat_days(daily, [(1, 0), (2, 0)], y, 35.0),
        "precip_dec_feb": C.window_totals(
            daily, [(12, -1), (1, 0), (2, 0)], y),
        # --- 0803 작업지시서 §A: observed root-zone water, not the bucket's
        # guess at it. Carried alongside smi_flowering so the training run can
        # say which of the two the yield actually follows.
        "sm_summer": A.mean_soil_percentile(
            daily, pd.Timestamp(year=y, month=1, day=1),
            pd.Timestamp(year=y, month=3, day=31)),
        "heat_x_drought": A.heat_x_drought(
            daily, [(1, 0), (2, 0), (3, 0)], y, 35.0, 0.2),
        # El Nino autumns drown the harvest: beans rot standing and the
        # combines cannot enter a saturated field.
        "harvest_wet_days": A.wet_days(daily, [(4, 0), (5, 0)], y, 0.9),
    }


PAMPAS_SOJA = RegionCrop(
    key="pampas_soja",
    label="Pampas soybeans (BA + Córdoba + Santa Fe)",
    crop="soja",
    provinces=["Buenos Aires", "Córdoba", "Santa Fe"],
    points=PAMPAS_POINTS,
    build=_pampas_soja,
    doc="Regions/아르헨티나/팜파스/대두/대두_상세분석_및_수식.md",
    panel={"spi3_dec_feb": "precip_dec_feb"},
    core=["ky_penalty", "water_deficit_feb", "oni_lag", "heat_wave_duration"],
    # ONI lagged to the pre-sowing spring the guide asks for (Sep-Nov), not the
    # concurrent summer: the point of §3A's `ONI_3M_Lag` is that the index is
    # known *before* the season it forecasts.
    oni_window=({"ASO", "SON", "OND"}, set()),
    # R1-R5: the guide calls January-February the season's decisive window.
    critical_window=[(1, 0), (2, 0)],
    caveat="Sowing is fixed at 15 November rather than observed; MAGyP "
           "publishes area and production but not planting progress by "
           "department. The spatial fixed-effects/embedding structure in §3B "
           "is replaced by production-weighting six stations, which captures "
           "between-province contrast but not within-province soil variation.",
)


# ---------------------------------------------------------------------------
# 팜파스 -- 옥수수: ENSO x IOD, and a sowing date nobody publishes.
# ---------------------------------------------------------------------------

def _pampas_maiz(daily, y):
    # The guide's central claim: early and late corn are two different crops
    # on two different risk calendars, and without the sowing date the weather
    # alone cannot say which one you are looking at. Both calendars are
    # therefore built and both are offered to the model.
    early = pd.Timestamp(year=y - 1, month=10, day=1)
    late = pd.Timestamp(year=y - 1, month=12, day=10)

    wb_e = A.water_balance(daily, early, 150, A.AWC_PAMPAS, C.KC_MAIZE)
    wb_l = A.water_balance(daily, late, 150, A.AWC_PAMPAS, C.KC_MAIZE)

    # Silking: days 75-95 after sowing for the early crop (late December, the
    # hottest and driest fortnight of the Pampas year), days 65-85 for the late
    # one (mid-February to early March, when rain is more reliable).
    e_sil = (early + pd.Timedelta(days=75), early + pd.Timedelta(days=95))
    l_sil = (late + pd.Timedelta(days=65), late + pd.Timedelta(days=85))

    tmax_dec_jan = daily[((daily.date.dt.year == y - 1) & (daily.date.dt.month == 12))
                         | ((daily.date.dt.year == y) & (daily.date.dt.month == 1))]

    return {
        # WDEF, DSSAT's water-stress factor, from the bucket (see climate_ar)
        "wdef_silking_early": A.wdef(wb_e, *e_sil),
        "wdef_silking_late": A.wdef(wb_l, *l_sil),
        "silking_cwd_early": C.silking_stress(daily, early, 75, 95, 150),
        "heat_days_silking_early": C.heat_days(
            daily, [(12, -1), (1, 0)], y, 35.0),
        "tmax_dec_jan": (float(tmax_dec_jan.tmax.mean())
                         if not tmax_dec_jan.empty else None),
        "heat_wave_duration": A.heatwave_duration(
            daily, [(12, -1), (1, 0)], y, 35.0),
        "precip_spring": C.window_totals(daily, [(9, -1), (10, -1), (11, -1)], y),
        "precip_silking": C.window_totals(daily, [(12, -1), (1, 0)], y),
        # --- 0803 작업지시서 §A
        "sm_summer": A.mean_soil_percentile(
            daily, pd.Timestamp(year=y, month=1, day=1),
            pd.Timestamp(year=y, month=3, day=31)),
        "sm_silking": A.mean_soil_percentile(daily, *e_sil),
        "heat_x_drought": A.heat_x_drought(
            daily, [(12, -1), (1, 0), (2, 0)], y, 35.0, 0.2),
    }


PAMPAS_MAIZ = RegionCrop(
    key="pampas_maiz",
    label="Pampas corn (BA + Córdoba + Santa Fe)",
    crop="maiz",
    provinces=["Buenos Aires", "Córdoba", "Santa Fe"],
    points=PAMPAS_CORN_POINTS,
    build=_pampas_maiz,
    doc="Regions/아르헨티나/팜파스/옥수수/옥수수_상세분석_및_수식.md",
    panel={"spi3_silking": "precip_silking",
           "climate_shock": "__shock__"},
    core=["wdef_silking_early", "wdef_silking_late", "climate_shock",
          "oni_lag", "iod_spring"],
    oni_window=({"ASO", "SON", "OND"}, {"DJF"}),
    # Early-corn silking (late December) through late-corn silking (February).
    critical_window=[(12, -1), (1, 0), (2, 0)],
    caveat="The guide's Climate_Shock_Index never fires: across 42 seasons "
           "no year has both ONI < -0.5 in the pre-sowing spring and DMI > "
           "0.4, so the switch is constant at 1.0 and the training run drops "
           "it. That is a property of the climate rather than of the data -- "
           "a strongly positive dipole and a La Nina are themselves "
           "negatively associated, so the guide's worst case is close to "
           "mutually exclusive at these thresholds. ONI and DMI are carried "
           "separately instead. SAWHC is one constant per region here, so it "
           "rescales every season identically. DSSAT/APSIM is not runnable, "
           "so WDEF is the same ratio (ETa/ETc over silking) taken from a "
           "bucket balance instead of a process model.",
    non_weather_drivers=(
        "The early/late sowing split is the guide's own headline variable and "
        "it is not published: MAGyP reports one combined corn figure per "
        "department. The split moves year to year with December rainfall and "
        "with the corn/soy price ratio, so part of this target is a sowing "
        "decision the weather cannot see. Both calendars are modelled and "
        "offered, but their mix is unobserved."),
)


# ---------------------------------------------------------------------------
# 팜파스 -- 밀: late spring frost at anthesis.
# ---------------------------------------------------------------------------

def _pampas_trigo(daily, y):
    # Wheat is sown June and harvested December of the *same* calendar year,
    # which is why magyp.HARVEST_OFFSET is 0 for this crop alone.
    planting = pd.Timestamp(year=y, month=6, day=15)
    anthesis = pd.Timestamp(year=y, month=10, day=15)
    wb = A.water_balance(daily, planting, 175, A.AWC_PAMPAS, A.KC_WHEAT)

    fill = (anthesis, pd.Timestamp(year=y, month=11, day=30))

    return {
        # FII: degrees of frost accumulated over anthesis -5 to +10 days.
        # The guide's own 0 C threshold, and a raised-threshold canopy-frost
        # proxy over a wider window -- see climate_ar.frost_intensity_index for
        # why the first one is near-empty on a gridded 2 m feed.
        "fii": A.frost_intensity_index(daily, anthesis),
        "fii_proxy": A.frost_intensity_index(
            daily, anthesis, before=30, after=21, threshold=3.0),
        "frost_days_spring": C.frost_days(daily, [(9, 0), (10, 0)], y, 0.0),
        "cold_days_spring": C.frost_days(daily, [(9, 0), (10, 0)], y, 3.0),
        # Stage 1 of the guide's delta model is DSSAT CERES-Wheat; without it
        # the growth-potential side is carried by the water balance directly.
        "water_deficit_fill": A.deficit_ratio(wb, *fill),
        "water_deficit_season": A.deficit_ratio(wb, planting, fill[1]),
        "smi_anthesis": A.mean_smi(
            wb, anthesis - pd.Timedelta(days=15), anthesis + pd.Timedelta(days=15)),
        # Warm nights and wet spells at anthesis are the disease side the
        # guide names alongside frost ("비가 너무 오면 곰팡이가 핍니다")
        "precip_anthesis": C.window_totals(daily, [(10, 0), (11, 0)], y),
        "heat_days_fill": C.heat_days(daily, [(11, 0)], y, 30.0),
        "harvest_rain_penalty": C.harvest_rain(daily, [(12, 0)], y, 100.0),
        "precip_sowing": C.window_totals(daily, [(4, 0), (5, 0), (6, 0)], y),
        # --- 0803 작업지시서 §B. Pampas wheat is sown into whatever water the
        # autumn left in the profile and then gets almost no winter rain, so
        # the March-May soil state is a stock the whole season draws down.
        # Spennemann (2015) is why this is treated as a persistent state rather
        # than as lagged rainfall: Pampas soil-moisture anomalies survive
        # months, which is what lets an autumn number reach an October outcome.
        "autumn_recharge": A.autumn_recharge(daily, y),
        "sm_spring": A.mean_soil_percentile(
            daily, pd.Timestamp(year=y, month=10, day=1),
            pd.Timestamp(year=y, month=11, day=30)),
        # Satorre & Slafer (1999): wheat senesces sharply above 30 C
        "spring_heat_days": C.heat_days(daily, [(10, 0), (11, 0)], y, 30.0),
    }


PAMPAS_TRIGO = RegionCrop(
    key="pampas_trigo",
    label="Pampas wheat (BA + Córdoba + Santa Fe + La Pampa)",
    crop="trigo",
    provinces=["Buenos Aires", "Córdoba", "Santa Fe", "La Pampa"],
    points=WHEAT_POINTS,
    build=_pampas_trigo,
    doc="Regions/아르헨티나/팜파스/밀/밀_상세분석_및_수식.md",
    core=["fii_proxy", "water_deficit_fill", "cold_days_spring", "precip_sowing"],
    # A winter crop takes the austral winter ONI, not the summer one.
    oni_window=(set(), {"JJA", "JAS", "ASO"}),
    # Anthesis and grain fill, both inside the harvest year.
    critical_window=[(10, 0), (11, 0)],
    calendar_year_crop=True,
    caveat="The guide's FII cannot be computed as written from this weather "
           "feed: over the fixed 10-25 October anthesis window, POWER's "
           "gridded 2 m minimum falls below 0 C on 4 days in 42 years across "
           "five stations, because damaging spring frost in the Pampas is a "
           "radiative canopy-level event below the resolution of a reanalysis "
           "2 m field. `fii` is kept at the guide's 0 C and is near-constant; "
           "`fii_proxy` raises the threshold to 3 C over a wider window as a "
           "frost-risk proxy. This variable needs station minima (INTA SIGA, "
           "SMN) to be modelled properly. Anthesis is also fixed at 15 October "
           "rather than tracked, and DSSAT CERES-Wheat is not runnable, so the "
           "guide's two-stage delta model collapses to one regression.",
)


# ---------------------------------------------------------------------------
# 북부 NOA/NEA -- 대두: heat, counted on a planting-relative window.
# ---------------------------------------------------------------------------

def _norte_soja(daily, y):
    # The Chaco crop follows the summer rains in: sown mid-December, so the
    # guide's decisive days 50-100 window lands in February and early March.
    planting = pd.Timestamp(year=y - 1, month=12, day=15)
    wb = A.water_balance(daily, planting, 140, A.AWC_CHACO, A.KC_SOYBEAN)

    rep = (planting + pd.Timedelta(days=50), planting + pd.Timedelta(days=100))

    return {
        # The guide's headline: count of Tmax > 35 C on days 50-100
        "heat_penalty_50_100": A.heat_days_window(daily, planting, 50, 100, 35.0),
        "heat_excess_50_100": A.heat_excess_window(daily, planting, 50, 100, 35.0),
        "water_deficit_rep": A.deficit_ratio(wb, *rep),
        "smi_rep": A.mean_smi(wb, *rep),
        "heat_wave_duration": A.heatwave_duration(
            daily, [(1, 0), (2, 0)], y, 35.0),
        # Raw total; the panel step turns it into a deviation from climatology
        "precip_dec_jan": C.window_totals(daily, [(12, -1), (1, 0)], y),
        "precip_rep": C.window_totals(daily, [(2, 0), (3, 0)], y),
        # --- 0803 작업지시서. The sheet has no section for northern soy, but
        # its premise -- rainfed, so what is in the soil is what the crop gets
        # -- applies here more sharply than anywhere: the Chaco is hotter than
        # the Pampas and its soils hold a third less water, which is why the
        # same rainfall shortfall bites harder. The Pampas soy feature set is
        # reused, on this crop's own days-50-to-100 window.
        "sm_rep_obs": A.mean_soil_percentile(daily, *rep),
        "sm_summer": A.mean_soil_percentile(
            daily, pd.Timestamp(year=y, month=1, day=1),
            pd.Timestamp(year=y, month=3, day=31)),
        "heat_x_drought": A.heat_x_drought(
            daily, [(1, 0), (2, 0), (3, 0)], y, 35.0, 0.2),
        "dry_spell": A.dry_spell(daily, *rep, 0.2),
    }


NORTE_SOJA = RegionCrop(
    key="norte_soja",
    label="NOA/NEA soybeans (Santiago del Estero, Chaco, Salta, Tucumán)",
    crop="soja",
    provinces=["Santiago del Estero", "Chaco", "Salta", "Tucumán"],
    points=NORTE_POINTS,
    build=_norte_soja,
    doc="Regions/아르헨티나/북부지역_NOA_NEA/대두/대두_상세분석_및_수식.md",
    panel={"spi_dec_jan": "precip_dec_jan"},
    core=["heat_penalty_50_100", "spi_dec_jan", "oni_lag", "water_deficit_rep"],
    oni_window=({"ASO", "SON", "OND"}, {"DJF"}),
    # Days 50-100 after a mid-December sowing.
    critical_window=[(2, 0), (3, 0)],
    # The Chaco soy frontier is a cleared-land expansion story. Through the
    # 1980s this was a marginal crop on a few thousand hectares; the area has
    # grown roughly twentyfold since, onto progressively more marginal land.
    regime_start=1995,
    min_train=18,
    caveat="Sowing fixed at 15 December. The spatial error model in §3 is "
           "replaced by production-weighting five stations across four "
           "provinces -- between-province contrast survives, department-level "
           "soil and management fixed effects do not.",
    non_weather_drivers=(
        "This is a frontier crop: area has expanded roughly twentyfold since "
        "the 1980s onto newly cleared and progressively more marginal Chaco "
        "land. Average yield therefore moves with *where* the crop is grown, "
        "not only with the weather over it, and no climate feed sees that."),
)


# ---------------------------------------------------------------------------
# 차코 -- 면화: degree-day phenology, then heat x dryness.
# ---------------------------------------------------------------------------

def _chaco_algodon(daily, y):
    planting = pd.Timestamp(year=y - 1, month=11, day=1)
    wb = A.water_balance(daily, planting, 180, A.AWC_CHACO, A.KC_COTTON)
    add = C.accumulated_degree_days(daily, planting, tbase=15.6)

    # ADD 800 opens flowering and 1200 opens peak bloom, the same thresholds
    # the guide points at ("브라질 면화 모델과 동일하게")
    flower_start, flower_end = C.stage_window(add, 800, 1200)
    boll_start, boll_end = C.stage_window(add, 1200, 1800)

    feats = {
        # sum of max(0, Tmax - 32) * (1 - SMI) over flowering..peak bloom
        "combined_stress": A.combined_heat_water_stress(
            daily, wb, flower_start, flower_end, 32.0),
        "combined_stress_boll": A.combined_heat_water_stress(
            daily, wb, boll_start, boll_end, 32.0),
        "smi_flowering": A.mean_smi(wb, flower_start, flower_end),
        "heat_days_32": C.heat_days(daily, [(1, 0), (2, 0)], y, 32.0),
        # Any rain on open bolls discolours the lint: threshold 0
        "harvest_rainfall": C.harvest_rain(daily, [(4, 0), (5, 0), (6, 0)], y, 0.0),
        "precip_season": C.window_totals(
            daily, [(11, -1), (12, -1), (1, 0), (2, 0), (3, 0)], y),
    }
    # --- 0803 작업지시서 §C
    feats["sm_summer"] = A.mean_soil_percentile(
        daily, pd.Timestamp(year=y, month=1, day=1),
        pd.Timestamp(year=y, month=3, day=31))
    feats["dry_spell"] = A.dry_spell(
        daily, pd.Timestamp(year=y - 1, month=12, day=1),
        pd.Timestamp(year=y, month=3, day=31), 0.2)
    if flower_start is not None:
        feats["add_flowering_doy"] = float(flower_start.dayofyear)
        feats["sm_flowering_obs"] = A.mean_soil_percentile(
            daily, flower_start, flower_end)
    return feats


CHACO_ALGODON = RegionCrop(
    key="chaco_algodon",
    label="Chaco cotton (Chaco, Santiago del Estero, Formosa, Santa Fe)",
    crop="algodon",
    provinces=["Chaco", "Santiago del Estero", "Formosa", "Santa Fe"],
    points=COTTON_POINTS,
    build=_chaco_algodon,
    doc="Regions/아르헨티나/북부지역_NOA_NEA/면화/면화_상세분석_및_수식.md",
    core=["combined_stress", "smi_flowering", "harvest_rainfall",
          "add_flowering_doy"],
    oni_window=({"SON", "OND"}, {"DJF", "JFM"}),
    # Flowering to peak bloom, located by degree days but landing here.
    critical_window=[(1, 0), (2, 0)],
    caveat="Soil_Moisture_Index is a modelled bucket store, not a satellite "
           "product. Sowing fixed at 1 November. Fibre quality has no open "
           "series, so the target is lint yield alone.",
    non_weather_drivers=(
        "Argentine cotton area collapsed from ~700k ha in the late 1990s to "
        "~150k ha in the mid-2000s and has swung with the cotton/soy price "
        "ratio ever since, while the crop simultaneously shifted from "
        "smallholder rainfed to mechanised narrow-row production. Both moves "
        "change average yield without any weather doing anything."),
)


# ---------------------------------------------------------------------------
# 투쿠만 -- 사탕수수: the simulator that is not here.
# ---------------------------------------------------------------------------

def _tucuman_cana(daily, y):
    # Summer growth November-March, then a dry winter ripening and a May-
    # September zafra. The guide wants CANEGRO's daily biomass accumulation
    # and WS_photo; without the simulator the water balance carries both.
    growth = pd.Timestamp(year=y - 1, month=11, day=1)
    wb = A.water_balance(daily, growth, 150, A.AWC_TUCUMAN, A.KC_CANE)

    return {
        "water_stress_summer": A.deficit_ratio(
            wb, growth, pd.Timestamp(year=y, month=3, day=31)),
        "smi_summer": A.mean_smi(
            wb, growth, pd.Timestamp(year=y, month=3, day=31)),
        "precip_summer": C.window_totals(
            daily, [(11, -1), (12, -1), (1, 0), (2, 0), (3, 0)], y),
        # Rain during the zafra stops the harvesters and dilutes sucrose
        "harvest_rain_penalty": C.harvest_rain(
            daily, [(5, 0), (6, 0), (7, 0), (8, 0), (9, 0)], y, 150.0),
        "frost_days_winter": C.frost_days(daily, [(6, 0), (7, 0)], y, 0.0),
        "heat_days_summer": C.heat_days(daily, [(1, 0), (2, 0)], y, 35.0),
        "sm_summer": A.mean_soil_percentile(
            daily, growth, pd.Timestamp(year=y, month=3, day=31)),
    }


TUCUMAN_CANA = RegionCrop(
    key="tucuman_cana",
    label="Tucumán sugarcane",
    crop="cana",
    provinces=["Tucumán"],
    points=CANE_POINTS,
    build=_tucuman_cana,
    doc="Regions/아르헨티나/북부지역_NOA_NEA/사탕수수/사탕수수_상세분석_및_수식.md",
    panel={"lag1": "__yield__"},
    core=["water_stress_summer", "harvest_rain_penalty", "precip_summer"],
    oni_window=({"OND"}, {"DJF", "JFM"}),
    # Summer biomass accumulation, then the zafra.
    critical_window=[(12, -1), (1, 0), (2, 0), (3, 0)],
    caveat="MAGyP's estimaciones series stops at campaign 2004/05 for "
           "sugarcane and has a 1998-2002 hole, leaving too few post-1981 "
           "seasons to validate against. FAOSTAT's national series was "
           "checked as a substitute and rejected: its 2015-2024 stretch is a "
           "monotonic 46->28 t/ha decline with no year-to-year structure, and "
           "it correlates only 0.46 with the MAGyP Tucumán figures on their "
           "overlap. DSSAT-CANEGRO is not runnable either, so Y_sim is absent "
           "and the trend carries the baseline. Point EEAOC's series at "
           "magyp.region_yield to revive this config.",
    non_weather_drivers=(
        "Cane is a ratoon crop cut for five to seven years before replanting, "
        "so much of a season's yield is the age profile of the standing crop "
        "-- set by replanting investment and mill economics, not weather."),
)


ALL = [
    PAMPAS_SOJA,
    PAMPAS_MAIZ,
    PAMPAS_TRIGO,
    NORTE_SOJA,
    CHACO_ALGODON,
    TUCUMAN_CANA,
]

BY_KEY = {r.key: r for r in ALL}
