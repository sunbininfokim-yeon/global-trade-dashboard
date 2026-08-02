"""
One config per region-crop, each faithful to its own 상세분석_및_수식.md.

The nine guides do not share a methodology and deliberately so: Mato Grosso
soy is a sowing-date problem, Paraná soy is an ENSO/drought-index problem,
MATOPIBA soy is a heat problem, safrinha corn is a water-ledger problem,
coffee is an autoregressive biennial problem. Each `build` function below
implements only the derived variables its own guide specifies, which is why
they look so unalike.

Each `build` runs against one location's daily weather. collect.py calls it
once per point in the region and production-weights the resulting features --
never the other way round, because averaging the weather first would erase the
threshold exceedances (Tmax > 35, Tmin <= 1, rain > 300 mm) that most of these
guides are built on.
"""

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from . import climate as C

# Months are given as (month, year_offset_from_harvest_year).
# Offset -1 means the calendar year before the harvest year.
#
# Each point carries an elevation in metres: FAO-56 Penman-Monteith needs it
# for atmospheric pressure and clear-sky radiation, and these sites span
# 166 m on the Piaui plains to 1040 m in the coffee highlands.


@dataclass
class RegionCrop:
    key: str
    label: str
    crop: str                       # SIDRA crop key
    states: list                    # [(uf, production weight)]
    points: list                    # [{name, lat, lon, weight}]
    build: Callable                 # (daily, harvest_year) -> dict
    doc: str                        # source guide
    # NASA POWER's record opens 1981-01-01 and every crop here needs the
    # previous September (sugarcane the previous April), so 1982 is the first
    # harvest year with a complete season behind it.
    start_year: int = 1982
    # Features that can only be formed once every year is in hand (SPI needs a
    # cross-year distribution fit; coffee's biennial lags need the yield
    # series). Applied by collect.py after the per-year pass.
    panel: dict = field(default_factory=dict)
    # The guide's own headline variables, tested against the full feature set
    # so the run can show whether the extras earn their place or just fit noise.
    core: list = field(default_factory=list)
    # First season the current farming system was in place. Seasons before a
    # structural break are dropped at training time rather than detrended
    # through, because a break is a change of crop system, not of level.
    regime_start: int = 0
    # Training years required before forward chaining will make a call. Lowered
    # only where a regime restriction leaves a short record.
    min_train: int = 0
    # True for a crop sown and harvested inside one calendar year. The summer
    # crops here span the year boundary, so their season rolls over in
    # September; wheat rolls with the calendar.
    calendar_year_crop: bool = False
    # The months whose weather actually decides the yield, as (month, offset).
    # Used to report how much of the deciding window has already happened, so a
    # figure published mid-season is not read as a settled harvest number.
    critical_window: list = field(default_factory=list)
    # Known drivers of this crop's year-to-year yield that are NOT weather and
    # that no weather model can reach. Stated per config and carried through to
    # the published forecast, so a weak result is read as "weather is not what
    # moves this crop" rather than "the weather model is broken".
    non_weather_drivers: str = ""
    caveat: str = ""


# ---------------------------------------------------------------------------
# 마투그로수 -- 대두: onset of the rains is the whole story.
# ---------------------------------------------------------------------------

MT_POINTS = [
    {"name": "Sorriso",      "lat": -12.55, "lon": -55.72, "elevation": 365, "weight": 0.40},
    {"name": "Sapezal",      "lat": -13.54, "lon": -58.81, "elevation": 600, "weight": 0.30},
    {"name": "Rondonopolis", "lat": -16.47, "lon": -54.64, "elevation": 227, "weight": 0.30},
]


def _mt_soja(daily, y):
    ors, ers = C.onset_doy(daily, y)
    agro = C.onset_doy_agronomic(daily, y)

    return {
        "ors_doy": ors,
        "ors_doy_agronomic": agro,
        # max(0, ORS - 293): days the rains arrived after 20 October
        "days_late": C.days_late(ors),
        "days_late_agronomic": C.days_late(agro),
        "ers_doy": ers,
        # R_veg and R_rep from the panel regression in §3A
        "precip_veg": C.window_totals(daily, [(11, -1), (12, -1)], y),
        "precip_rep": C.window_totals(daily, [(1, 0), (2, 0)], y),
        "hotdays_rep": C.heat_days(daily, [(1, 0), (2, 0)], y, 34.0),
    }


MATO_GROSSO_SOJA = RegionCrop(
    critical_window=[(11, -1), (12, -1), (1, 0), (2, 0)],
    key="mato_grosso_soja",
    label="Mato Grosso soybeans",
    crop="soja",
    states=[("MT", 1.0)],
    points=MT_POINTS,
    build=_mt_soja,
    doc="Regions/브라질/마투그로수/대두/대두_상세분석_및_수식.md",
    caveat="NDVI_Peak_Value from §3B is omitted: MODIS starts in 2000 and "
           "would cut the record from 43 seasons to 25.",
    core=["days_late", "precip_veg", "precip_rep", "oni_season"],
)


# ---------------------------------------------------------------------------
# 마투그로수 -- 옥수수 (safrinha): the domino from a late soy harvest.
# ---------------------------------------------------------------------------

# Soybean cycle from sowing to harvest in Mato Grosso, in days. The guide
# defines safrinha planting as the soy harvest date, so the corn calendar is
# derived from the same onset that drives the soy model -- that is the
# "domino risk" the guide's reference paper describes, made explicit.
SOY_CYCLE_DAYS = 125


def _mt_milho(daily, y):
    ors, ers = C.onset_doy(daily, y)
    if ors is None:
        return {}

    plant_year = y - 1
    jan1 = pd.Timestamp(year=plant_year, month=1, day=1)
    soy_planting = jan1 + pd.Timedelta(days=int(ors) - 1)
    corn_planting = soy_planting + pd.Timedelta(days=SOY_CYCLE_DAYS)
    corn_planting_doy = (corn_planting - jan1).days + 1

    return {
        "ers_doy": ers,
        "planting_doy": corn_planting_doy,
        # Days of rain the corn actually gets: demise minus planting. Under
        # 70 the guide expects the crop to run out of water before filling.
        "time_window": (ers - corn_planting_doy) if ers is not None else None,
        # CWD accumulated over days 60-75 after planting, the silking window
        "silking_stress": C.silking_stress(daily, corn_planting),
        "vpd_peak_dry": C.vpd_peak(daily, [(4, 0), (5, 0)], y),
        "frost_days": C.frost_days(daily, [(6, 0), (7, 0)], y, 0.0),
        "precip_silking": C.window_totals(daily, [(4, 0), (5, 0)], y),
    }


MATO_GROSSO_MILHO = RegionCrop(
    critical_window=[(3, 0), (4, 0), (5, 0), (6, 0)],
    key="mato_grosso_milho",
    label="Mato Grosso corn (safrinha)",
    crop="milho",
    states=[("MT", 1.0)],
    points=MT_POINTS,
    build=_mt_milho,
    doc="Regions/브라질/마투그로수/옥수수/옥수수_상세분석_및_수식.md",
    caveat="Planting date is derived from the modelled soy onset plus a fixed "
           "125-day soy cycle, not observed. SIDRA reports one combined corn "
           "figure, but in Mato Grosso safrinha is the great majority of it.",
    core=["time_window", "silking_stress", "ers_doy", "vpd_peak_dry"],
)


# ---------------------------------------------------------------------------
# 남부지방 (Paraná & RS) -- soybeans: SPI and ENSO.
# ---------------------------------------------------------------------------

SOUTH_POINTS = [
    {"name": "Cascavel",     "lat": -24.96, "lon": -53.46, "elevation": 781, "weight": 0.30},
    {"name": "Ponta Grossa", "lat": -25.09, "lon": -50.16, "elevation": 975, "weight": 0.20},
    {"name": "Passo Fundo",  "lat": -28.26, "lon": -52.41, "elevation": 687, "weight": 0.25},
    {"name": "Cruz Alta",    "lat": -28.64, "lon": -53.61, "elevation": 452, "weight": 0.25},
]


def _south_soja(daily, y):
    ors, _ = C.onset_doy(daily, y)
    return {
        # Raw total; spi() converts it across years in the panel step
        "precip_dec_feb": C.window_totals(daily, [(12, -1), (1, 0), (2, 0)], y),
        # Ideal sowing opens 20 October here too (DOY 293)
        "planting_delay": C.days_late(ors),
        "tmax_jan": float(daily[(daily.date.dt.year == y)
                                & (daily.date.dt.month == 1)].tmax.mean()),
        # IF(Rain_Feb > 300, Rain_Feb - 300, 0), extended to March
        "waterlogging": C.waterlogging_penalty(daily, [(2, 0), (3, 0)], y, 300.0),
        "precip_planting": C.window_totals(daily, [(10, -1), (11, -1)], y),
    }


SOUTH_SOJA = RegionCrop(
    critical_window=[(12, -1), (1, 0), (2, 0)],
    key="parana_soja",
    label="Paraná + Rio Grande do Sul soybeans",
    crop="soja",
    states=[("PR", 0.50), ("RS", 0.50)],
    points=SOUTH_POINTS,
    build=_south_soja,
    doc="Regions/브라질/남부지방_파라나/대두/대두_상세분석_및_수식.md",
    panel={"spi3_dec_feb": "precip_dec_feb"},
    core=["spi3_dec_feb", "oni_season", "planting_delay", "waterlogging",
          "tmax_jan"],
)


# ---------------------------------------------------------------------------
# 남부지방 -- 옥수수: silking water balance.
# ---------------------------------------------------------------------------


def _south_milho(daily, y):
    # Summer corn here is sown Sep-Nov; 1 October is the centre of that window
    planting = pd.Timestamp(year=y - 1, month=10, day=1)
    return {
        "silking_cwd": C.silking_stress(daily, planting),
        "vpd_peak": C.vpd_peak(daily, [(12, -1), (1, 0)], y),
        "precip_nov_jan": C.window_totals(daily, [(11, -1), (12, -1), (1, 0)], y),
        "hotdays_silking": C.heat_days(daily, [(12, -1), (1, 0)], y, 35.0),
        "frost_days": C.frost_days(daily, [(9, -1), (10, -1)], y, 0.0),
    }


SOUTH_MILHO = RegionCrop(
    critical_window=[(11, -1), (12, -1), (1, 0)],
    key="parana_milho",
    label="Paraná + Rio Grande do Sul corn",
    crop="milho",
    states=[("PR", 0.70), ("RS", 0.30)],
    points=SOUTH_POINTS,
    build=_south_milho,
    doc="Regions/브라질/남부지방_파라나/옥수수/옥수수_상세분석_및_수식.md",
    panel={"spi3_jan": "precip_nov_jan"},
    caveat="The SIDRA target mixes first-season and safrinha corn, which in "
           "Paraná are both large. The guide's methodology addresses the "
           "summer crop only, so the signal is diluted by construction.",
    core=["silking_cwd", "vpd_peak", "spi3_jan"],
    non_weather_drivers=(
        "SIDRA publishes one combined corn figure per state. In Paraná the "
        "first-season and safrinha crops are both large and their area split "
        "shifts with soybean and corn prices, so part of the year-to-year "
        "movement in this target is an acreage-mix decision rather than "
        "anything the weather did."),
)


# ---------------------------------------------------------------------------
# 남부지방 -- 밀: Fusarium head blight at anthesis.
# ---------------------------------------------------------------------------


def _south_trigo(daily, y):
    # Wheat is a winter crop here: sown June, anthesis September, harvested
    # October-November, all inside one calendar year.
    anthesis_start = pd.Timestamp(year=y, month=9, day=1)
    anthesis_end = pd.Timestamp(year=y, month=9, day=30)

    feats = dict(C.fhb_features(daily, anthesis_start, anthesis_end))
    feats.update({
        "frost_days": C.frost_days(daily, [(6, 0), (7, 0), (8, 0)], y, 0.0),
        # max(0, harvest rain - 200): pre-harvest sprouting
        "harvest_rain_penalty": C.harvest_rain(
            daily, [(10, 0), (11, 0)], y, 200.0),
        "precip_anthesis": C.window_totals(daily, [(9, 0)], y),
    })
    return feats


SOUTH_TRIGO = RegionCrop(
    calendar_year_crop=True,
    critical_window=[(8, 0), (9, 0), (10, 0), (11, 0)],
    key="parana_trigo",
    label="Paraná + Rio Grande do Sul wheat",
    crop="trigo",
    states=[("PR", 0.55), ("RS", 0.45)],
    points=SOUTH_POINTS,
    build=_south_trigo,
    doc="Regions/브라질/남부지방_파라나/밀/밀_상세분석_및_수식.md",
    caveat="Del Ponte's logistic coefficients are not given in the guide, so "
           "the FHB weather features are fed to the yield model directly "
           "instead of through a calibrated P(Epidemic). Anthesis is fixed at "
           "September rather than tracked per season.",
    core=["fhb_rh_days", "fhb_rain_events", "fhb_warm_days", "frost_days",
          "harvest_rain_penalty"],
)


# ---------------------------------------------------------------------------
# MATOPIBA -- 대두: heat stress on sandy soil.
# ---------------------------------------------------------------------------

MATOPIBA_POINTS = [
    {"name": "Barreiras",    "lat": -12.15, "lon": -45.00, "elevation": 452, "weight": 0.40},
    {"name": "Balsas",       "lat": -7.53,  "lon": -46.04, "elevation": 247, "weight": 0.22},
    {"name": "Urucui",       "lat": -7.23,  "lon": -44.56, "elevation": 166, "weight": 0.18},
    {"name": "Pedro Afonso", "lat": -8.97,  "lon": -48.17, "elevation": 200, "weight": 0.20},
]

# Cerrado soils under MATOPIBA soy are predominantly sandy Latosols; 0.65 is
# the mid-range sand fraction reported for the region's arenosols.
MATOPIBA_SAND = 0.65


def _matopiba_soja(daily, y):
    ors, _ = C.onset_doy(daily, y)
    rep = [(1, 0), (2, 0)]          # flowering and pod fill
    return {
        # CWSI proxy -- see climate.py module docstring
        "heat_vpd_stress": C.vpd_heat_stress(daily, rep, y, 35.0),
        "heat_days_35": C.heat_days(daily, rep, y, 35.0),
        # sum of max(0, Tmax - 35), the guide's heat-penalty node
        "heat_excess": C.heat_excess(daily, rep, y, 35.0),
        # Rainfall * (1 - sand_fraction)
        "effective_water": C.effective_water_capacity(
            daily, [(12, -1), (1, 0), (2, 0)], y, MATOPIBA_SAND),
        "days_late": C.days_late(ors),
        "precip_rep": C.window_totals(daily, rep, y),
    }


MATOPIBA_SOJA = RegionCrop(
    critical_window=[(12, -1), (1, 0), (2, 0)],
    key="matopiba_soja",
    label="MATOPIBA soybeans",
    crop="soja",
    states=[("BA", 0.40), ("MA", 0.20), ("PI", 0.17), ("TO", 0.23)],
    points=MATOPIBA_POINTS,
    build=_matopiba_soja,
    doc="Regions/브라질/MATOPIBA/대두/대두_상세분석_및_수식.md",
    caveat="CWSI is replaced by a Tmax/VPD stress proxy -- satellite canopy "
           "temperature needs a thermal-infrared feed. Sand fraction is one "
           "regional constant rather than a joined soil map, so "
           "Effective_Water_Capacity rescales rainfall uniformly here.",
    core=["heat_vpd_stress", "heat_days_35", "heat_excess",
          "effective_water"],
)


# ---------------------------------------------------------------------------
# MATOPIBA -- 면화: degree-day phenology, then heat x VPD.
# ---------------------------------------------------------------------------


def _matopiba_algodao(daily, y):
    # Cotton follows the rains in, sown from December
    planting = pd.Timestamp(year=y - 1, month=12, day=1)
    add = C.accumulated_degree_days(daily, planting, tbase=15.6)

    # ADD 800 opens flowering, 1200 opens boll filling (guide §2A)
    flower_start, flower_end = C.stage_window(add, 800, 1200)
    boll_start, boll_end = C.stage_window(add, 1200, 1800)

    feats = {
        "flowering_heat_penalty": C.cotton_heat_stress(
            daily, flower_start, flower_end, 32.0),
        "boll_heat_penalty": C.cotton_heat_stress(
            daily, boll_start, boll_end, 32.0),
        # Any rain on open bolls discolours the lint: raw total, threshold 0
        "harvest_rainfall": C.harvest_rain(daily, [(7, 0), (8, 0)], y, 0.0),
        "heat_days_32": C.heat_days(daily, [(3, 0), (4, 0)], y, 32.0),
    }
    if flower_start is not None:
        feats["flowering_doy"] = float(flower_start.dayofyear)
        feats["flowering_precip"] = float(
            daily[(daily.date >= flower_start)
                  & (daily.date <= flower_end)].precip.sum())
    return feats


MATOPIBA_ALGODAO = RegionCrop(
    critical_window=[(2, 0), (3, 0), (4, 0), (7, 0), (8, 0)],
    key="matopiba_algodao",
    label="MATOPIBA cotton",
    crop="algodao",
    states=[("BA", 0.75), ("MA", 0.15), ("PI", 0.08), ("TO", 0.02)],
    points=MATOPIBA_POINTS,
    build=_matopiba_algodao,
    doc="Regions/브라질/MATOPIBA/면화/면화_상세분석_및_수식.md",
    # MATOPIBA cotton is two different crops in one series. Through the 1990s
    # it averaged 741 kg/ha with 30% year-to-year scatter -- rainfed smallholder
    # cotton. Yield jumps 82% between 1999 and 2000 and then runs at
    # 3,100-4,500 kg/ha with 8-10% scatter: irrigated, high-input Cerrado
    # cotton on a different calendar with different weather sensitivities.
    # Fitting one trend and one set of coefficients across that break corrupts
    # the trend, the feature scaling and the regression at once.
    regime_start=2000,
    min_train=15,
    non_weather_drivers=(
        "The 1999-2000 jump is a change of production system -- relocation to "
        "the Cerrado, new cultivars, scale and management -- not a good "
        "weather year. Note it is not irrigation: about 92% of Brazil's cotton "
        "area is rainfed, and Brazil leads the world in rainfed lint yield. "
        "The largest single non-weather driver inside the modern era is the "
        "boll weevil, which can take up to 70% of a crop and whose pressure "
        "depends on planting-date coordination and control programmes rather "
        "than on climate. Published work also finds MODIS NDVI adds little to "
        "upland cotton yield models over a trend baseline (Johnson, ORNL), so "
        "satellite greenness is unlikely to recover what is missing here."),
    caveat="Yield only. The guide's second target -- fibre quality/Micronaire "
           "-- has no open data series, so the two-output structure collapses "
           "to one. The NDVI classifier that would date flowering is replaced "
           "by the degree-day threshold from the same guide. Training starts "
           "in 2000: the pre-2000 smallholder crop is a different system.",
    core=["flowering_heat_penalty", "boll_heat_penalty",
          "harvest_rainfall"],
)


# ---------------------------------------------------------------------------
# 상파울루 -- 사탕수수: long-horizon water stress.
# ---------------------------------------------------------------------------

CANA_POINTS = [
    {"name": "Ribeirao Preto", "lat": -21.17, "lon": -47.81, "elevation": 546, "weight": 0.40},
    {"name": "Piracicaba",     "lat": -22.72, "lon": -47.65, "elevation": 547, "weight": 0.30},
    {"name": "Aracatuba",      "lat": -21.21, "lon": -50.43, "elevation": 390, "weight": 0.30},
]


def _sp_cana(daily, y):
    # The guide gives the cycle as 12-18 months and says the damaging quantity
    # is "수개월간 누적된 토양 수분 고갈" -- accumulated depletion over months,
    # not any single dry month. So both horizons are built: the 12-month cycle
    # (April of the previous year to March of this one) and an 18-month window
    # reaching back into the cycle before, which is what a ratoon stand
    # actually carries.
    defs = C.monthly_water_deficit(daily, awc=120.0)
    cycle = [(m, -1) for m in range(4, 13)] + [(m, 0) for m in range(1, 4)]
    long_cycle = [(m, -2) for m in range(10, 13)] + \
                 [(m, -1) for m in range(1, 13)] + [(m, 0) for m in range(1, 4)]

    # WS_photo = T_actual / T_potential. In a bucket balance the unmet demand
    # is exactly the deficit, so AET/ETp = 1 - DEF/ETp; summing the shortfall
    # over the cycle is the guide's Sum_WS_photo, sign-flipped to "stress".
    total_def, total_etp, months_seen = 0.0, 0.0, 0
    for month, offset in cycle:
        yr = y + offset
        row = defs[(defs.year == yr) & (defs.month == month)]
        if row.empty:
            continue
        total_def += float(row.def_mm.iloc[0])
        w = daily[(daily.date.dt.year == yr) & (daily.date.dt.month == month)]
        total_etp += float(w.et0.sum())
        months_seen += 1

    # A cycle with no months on record is missing, not stress-free. Returning
    # zero here would make every pre-1981 season look like a perfect year.
    if months_seen < len(cycle):
        return {}

    long_def = 0.0
    for month, offset in long_cycle:
        row = defs[(defs.year == y + offset) & (defs.month == month)]
        if not row.empty:
            long_def += float(row.def_mm.iloc[0])

    return {
        "cycle_deficit": total_def,
        "cycle_deficit_18mo": long_def,
        "water_stress_fraction": (total_def / total_etp) if total_etp else None,
        # SPI-6 input: the dry half of the cycle, named in guide §3B
        "precip_6mo": C.window_totals(
            daily, [(10, -1), (11, -1), (12, -1), (1, 0), (2, 0), (3, 0)], y),
        # SPI-12 input: the whole cycle, for the long-horizon depletion the
        # guide puts ahead of any single month
        "precip_12mo": C.window_totals(daily, cycle, y),
        "frost_days": C.frost_days(daily, [(6, -1), (7, -1)], y, 1.0),
        "heat_days": C.heat_days(daily, [(1, 0), (2, 0)], y, 35.0),
    }


SP_CANA = RegionCrop(
    critical_window=[(10, -1), (11, -1), (12, -1), (1, 0), (2, 0), (3, 0)],
    key="sp_cana",
    label="São Paulo sugarcane",
    crop="cana",
    states=[("SP", 1.0)],
    points=CANA_POINTS,
    build=_sp_cana,
    doc="Regions/브라질/상파울루/사탕수수/사탕수수_상세분석_및_수식.md",
    panel={"spi6": "precip_6mo", "spi12": "precip_12mo", "lag1": "__yield__"},
    caveat="Stage 1 of the guide is DSSAT-CANEGRO, which is not runnable "
           "without the simulator and its calibrated genetic coefficients. "
           "Y_sim is therefore absent and the technology trend carries the "
           "baseline instead; WS_photo is a bucket-balance surrogate. The "
           "guide's NDVI_Max is also absent (MODIS starts in 2000). This is "
           "the largest departure from any guide in the set.",
    core=["water_stress_fraction", "spi6", "spi12", "cycle_deficit_18mo",
          "lag1"],
    non_weather_drivers=(
        "Sugarcane is a ratoon crop, replanted only every five to seven "
        "years, so much of any season's yield is the age profile of the "
        "standing crop -- how much of São Paulo's area is first-cut versus "
        "fifth-cut. That is set by replanting investment, variety turnover "
        "and mill economics, none of which appears in any weather feed. "
        "Detrended yield moves only about 3% a year across the whole record "
        "(2.7% in 1985-99, 3.1% in 2013-24). "
        "This is the published finding, not a shortcoming of this model: "
        "Dias & Sentelhas (Field Crops Research, 2017) ran all three standard "
        "simulators -- FAO-AZM, DSSAT/CANEGRO and APSIM-Sugarcane, including "
        "the CANEGRO this guide asks for -- against commercial Brazilian "
        "fields and got MAE above 29 t/ha with R2 below 0.54, attributing the "
        "failure to 'the lack of coefficients accounting for crop "
        "management'. Adding a ratoon-decline management factor (kdec) moved "
        "them to MAE 13-15 t/ha and R2 0.58-0.72. Climate alone does not "
        "forecast this crop for anyone. lag1 is carried here to represent "
        "stand persistence, but it is a proxy for management, not a climate "
        "signal."),
)


# ---------------------------------------------------------------------------
# 상파울루 & 미나스제라이스 -- 커피: biennial bearing.
# ---------------------------------------------------------------------------

CAFE_POINTS = [
    {"name": "Patrocinio", "lat": -18.94, "lon": -46.99, "elevation": 965, "weight": 0.30},
    {"name": "Varginha",   "lat": -21.55, "lon": -45.43, "elevation": 940, "weight": 0.30},
    {"name": "Manhuacu",   "lat": -20.26, "lon": -42.03, "elevation": 630, "weight": 0.20},
    {"name": "Franca",     "lat": -20.54, "lon": -47.40, "elevation": 1040, "weight": 0.20},
]


def _sp_cafe(daily, y):
    defs = C.monthly_water_deficit(daily, awc=125.0)

    # FAO yield-response factors by stage (guide §2B)
    flowering = [(y - 1, 9, 1.2), (y - 1, 10, 1.2)]
    filling = [(y, 1, 0.8), (y, 2, 0.8)]
    harvest = [(y, 5, 0.2), (y, 6, 0.2), (y, 7, 0.2)]

    return {
        "def_flowering": C.weighted_deficit(defs, flowering),
        "def_filling": C.weighted_deficit(defs, filling),
        "def_harvest": C.weighted_deficit(defs, harvest),
        # Tmin <= 1 C in the winter before flowering kills leaves and branches
        "frost_count": C.frost_days(daily, [(6, -1), (7, -1), (8, -1)], y, 1.0),
        "precip_flowering": C.window_totals(daily, [(9, -1), (10, -1)], y),
        "heat_days": C.heat_days(daily, [(1, 0), (2, 0)], y, 34.0),
    }


SP_CAFE = RegionCrop(
    critical_window=[(9, -1), (10, -1), (1, 0), (2, 0)],
    key="sp_cafe",
    label="Minas Gerais + São Paulo coffee (Arabica)",
    crop="cafe",
    states=[("MG", 0.75), ("SP", 0.25)],
    points=CAFE_POINTS,
    build=_sp_cafe,
    doc="Regions/브라질/상파울루/커피/커피_상세분석_및_수식.md",
    # Y_{t-1} and Y_{t-2} carry the biennial cycle; both are known at forecast
    # time, so using them is honest rather than leakage.
    panel={"lag1": "__yield__", "lag2": "__yield2__"},
    caveat="The guide's stratified high-/low-yield split is replaced by the "
           "autoregressive form from the same guide (§3A). With ~43 seasons, "
           "training two stratified models on ~21 rows each would fit noise.",
    core=["lag1", "lag2", "def_flowering", "frost_count"],
    non_weather_drivers=(
        "Biennial bearing is physiological, not meteorological: a heavy crop "
        "exhausts the tree and the next year is light regardless of weather. "
        "lag1 and lag2 carry that cycle, and they are the model's strongest "
        "features -- so much of this model's skill is biological memory, not "
        "climate. Replanting rates and the arabica/robusta area mix are also "
        "outside any weather feed."),
)


ALL = [
    MATO_GROSSO_SOJA,
    MATO_GROSSO_MILHO,
    SOUTH_SOJA,
    SOUTH_MILHO,
    SOUTH_TRIGO,
    MATOPIBA_SOJA,
    MATOPIBA_ALGODAO,
    SP_CANA,
    SP_CAFE,
]

BY_KEY = {r.key: r for r in ALL}
