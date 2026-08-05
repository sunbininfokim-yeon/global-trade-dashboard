"""
One config per region-crop, each faithful to its own 상세분석_및_수식.md.

The three Indian guides share even less methodology than the nine Brazilian
ones. Punjab wheat is a pure temperature problem on an irrigated crop and its
guide says in as many words to cut the weight on rainfall. Madhya Pradesh
soybean is the opposite -- a rainfed crop where the guide discards monthly
rainfall entirely and asks for the *timing* of daily rain. Maharashtra cotton
is a two-sided problem where both too little and too much water lose the crop,
the second through pest pressure rather than through water directly.

So each `build` implements only its own guide's variables. Where a formula
already exists in the shared physics it is called; where the guide asks for
something no Brazilian config needed, it is in india/climate.py.

Each `build` runs against one location's daily weather. collect.py calls it
once per point and area-weights the results -- never the other way round.

Point weights are measured, not estimated: each district's share of the
region's planted area for that crop over 2005-2019, from the same ICRISAT
tables the yields come from (icrisat.rank_districts), renormalised over the
points actually sampled.

Coordinates are *not* ICRISAT's. Its district centroids are unreliable in
places -- it puts Bhatinda at 31.60N/75.30E, about 150 km from the real town,
and Sangrur three quarters of a degree north of where it is -- and a
mislocated point silently samples the wrong weather. The coordinates here are
checked by hand. Elevations are hand-entered too, since ICRISAT publishes no
altitude and FAO-56 needs it for atmospheric pressure.

These points sample 24-36% of each region's planted area. That is lower than
it sounds: no district dominates any of these regions (the largest single
share anywhere is Ujjain's 8% of MP soybean), so the shares are close to flat
and coverage climbs slowly with each added point. Whether the sample is
*representative* matters more than the fraction it covers, and the open
question there is Marathwada -- Aurangabad, Bid, Jalna and Parbhani together
are about 20% of the cotton region and are drier than the Vidarbha districts
standing in for them. See README.
"""

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from . import climate as C

# Months are given as (month, year_offset_from_harvest_year), the same
# convention as the Brazilian package. Kharif crops never use a negative
# offset -- they are sown and harvested inside one calendar year.


@dataclass
class RegionCrop:
    key: str
    label: str
    crop: str                       # ICRISAT crop key
    selector: list                  # [(state_code, [divisions] or None)]
    points: list                    # [{name, lat, lon, elevation, weight}]
    build: Callable                 # (daily, harvest_year) -> dict
    doc: str                        # source guide
    # NASA POWER's *meteorology* opens in 1981, but its shortwave radiation
    # record starts 1984-01-01, and ET0 needs radiation. Every point pulled
    # here returns 1984-01-01 onward, so a Kharif season -- which lives inside
    # one calendar year -- is complete from 1984. Rabi wheat needs the previous
    # November and so starts a year later.
    start_year: int = 1984
    # True for a crop sown and harvested inside one calendar year. Both Kharif
    # crops are; Rabi wheat is not.
    calendar_year_crop: bool = True
    panel: dict = field(default_factory=dict)
    core: list = field(default_factory=list)
    regime_start: int = 0
    min_train: int = 0
    # The months whose weather actually decides the yield, as (month, offset).
    critical_window: list = field(default_factory=list)
    non_weather_drivers: str = ""
    caveat: str = ""


# ---------------------------------------------------------------------------
# 북서부_펀자브 -- 밀: terminal heat, and almost nothing else.
#
# The guide's instruction is unusual and worth restating because it shapes the
# whole config: "강수량 데이터의 가중치를 대폭 낮추는 대신(관개 인프라가 워낙 잘
# 되어 있으므로), 3월 특정 주간의 누적 온도 피처에 모델의 운명을 걸도록".
# Punjab and Haryana wheat sits under the Indus-Gangetic canal network and is
# close to fully irrigated, so rainfall is not the binding constraint --
# March heat during grain filling is. Every feature below is temperature.
# ---------------------------------------------------------------------------

PUNJAB_POINTS = [
    {"name": "Ludhiana", "lat": 30.90, "lon": 75.85, "elevation": 247, "weight": 0.171},
    {"name": "Sangrur",  "lat": 30.25, "lon": 75.84, "elevation": 232, "weight": 0.198},
    {"name": "Bhatinda", "lat": 30.21, "lon": 74.95, "elevation": 210, "weight": 0.169},
    {"name": "Karnal",   "lat": 29.69, "lon": 76.99, "elevation": 245, "weight": 0.117},
    {"name": "Hissar",   "lat": 29.15, "lon": 75.72, "elevation": 215, "weight": 0.151},
    {"name": "Sirsa",    "lat": 29.53, "lon": 75.03, "elevation": 205, "weight": 0.193},
]


def _punjab_wheat(daily, y):
    return {
        # THSDD: sum of max(0, Tmax - 30) over grain filling (§2A)
        "thsdd": C.thsdd(daily, y),
        # The same window counted as days rather than degrees, so the run can
        # show whether the overshoot magnitude the guide insists on actually
        # beats a plain day count.
        "heat_days_30": C.heat_days(daily, [(3, 0)], y, 30.0),
        "heat_days_35": C.heat_days(daily, [(3, 0), (4, 0)], y, 35.0),
        # Nights that never fall below 18 C during grain filling (§2B)
        "warm_nights": C.warm_night_days(daily, y),
        # Mean March Tmax -- the plain-average control the guide argues is
        # inadequate. Carried so that argument is tested rather than assumed.
        "tmax_march": float(daily[(daily.date.dt.year == y)
                                  & (daily.date.dt.month == 3)].tmax.mean()),
        # Rainfall is carried but deliberately not in `core`. The guide expects
        # it to earn little; leaving it out of the model entirely would prevent
        # the run from ever showing that.
        "precip_season": C.window_totals(
            daily, [(11, -1), (12, -1), (1, 0), (2, 0), (3, 0)], y),
        # A cold, long grain-fill is the good case: degree days below the
        # stress threshold accumulated over February, when the crop is still
        # laying down biomass.
        "tmin_feb": float(daily[(daily.date.dt.year == y)
                                & (daily.date.dt.month == 2)].tmin.mean()),
    }


PUNJAB_WHEAT = RegionCrop(
    key="punjab_wheat",
    label="Punjab + Haryana wheat",
    crop="wheat",
    selector=[(9, None), (4, None)],        # Punjab, Haryana
    points=PUNJAB_POINTS,
    build=_punjab_wheat,
    doc="Regions/인도/북서부_펀자브/밀/밀_상세분석_및_수식.md",
    start_year=1985,                        # needs the previous November
    calendar_year_crop=False,
    critical_window=[(2, 0), (3, 0)],
    core=["thsdd", "warm_nights", "heat_days_30", "oni_season"],
    caveat="The guide's Hybrid LASSO-Random Forest is replaced by the same "
           "ridge-on-log-yield used across this repo. With ~40 seasons, LASSO "
           "variable selection over daily weather would select on noise; the "
           "weekly-resolution heat tensor it is meant to search is collapsed "
           "to the guide's own named windows instead. MODIS LST and NDVI from "
           "§3 are omitted -- MODIS starts in 2000 and would halve the record.",
    non_weather_drivers=(
        "Punjab and Haryana wheat yields are shaped by the procurement system "
        "as much as by weather: assured MSP purchase, subsidised power for "
        "tubewells and canal rotation schedules set both the input intensity "
        "and the sowing window, and none of it is visible in a weather feed. "
        "Groundwater depletion is a slow constraint moving underneath the "
        "whole series, and it enters the technology trend rather than any "
        "seasonal feature."),
)


# ---------------------------------------------------------------------------
# 중부_마디아프라데시 -- 대두: the shape of the monsoon, not its size.
#
# "단순 누적 강수량은 수확량과 상관관계가 낮았으며, 오히려 '6월 파종 지연 일수'와
# '8월 개화기 10일 연속 가뭄(Dry Spell)' 텐서가 수확량 변동성의 핵심 키".
# Total rainfall is carried anyway, as the control that claim is measured
# against.
# ---------------------------------------------------------------------------

MP_POINTS = [
    {"name": "Ujjain",    "lat": 23.18, "lon": 75.78, "elevation": 491, "weight": 0.251},
    {"name": "Dewas",     "lat": 22.96, "lon": 76.06, "elevation": 555, "weight": 0.179},
    {"name": "Sehore",    "lat": 23.20, "lon": 77.09, "elevation": 502, "weight": 0.158},
    {"name": "Mandsaur",  "lat": 24.07, "lon": 75.07, "elevation": 435, "weight": 0.146},
    {"name": "Vidisha",   "lat": 23.52, "lon": 77.81, "elevation": 424, "weight": 0.141},
    {"name": "Indore",    "lat": 22.72, "lon": 75.86, "elevation": 553, "weight": 0.124},
]


def _mp_soybean(daily, y):
    onset = C.monsoon_onset_doy(daily, y)

    return {
        # Onset date as the guide defines it: first day June rainfall reaches
        # 50 mm (§2A)
        "onset_doy": onset,
        # max(0, onset - 15 June), the delay penalty
        "onset_delay": C.days_late(onset),
        # sum over August of (dry spell > 7 days) * VPD (§2B)
        "flowering_stress": C.flowering_drought_stress(daily, y),
        # The same August spells unweighted, so the VPD multiplication can be
        # shown to earn its place rather than assumed.
        "longest_dry_aug": C.longest_dry_spell(daily, [(8, 0)], y),
        # Harvest-period waterlogging: the guide puts a rotting crop in the
        # field alongside drought as the two ways this system fails.
        "harvest_waterlog": C.waterlogging_penalty(
            daily, [(9, 0), (10, 0)], y, 300.0),
        # Total monsoon rainfall -- the control the guide says is weak.
        "precip_jun_sep": C.window_totals(
            daily, [(6, 0), (7, 0), (8, 0), (9, 0)], y),
        "precip_flowering": C.window_totals(daily, [(8, 0)], y),
        "heat_days_35": C.heat_days(daily, [(7, 0), (8, 0)], y, 35.0),
    }


MP_SOYBEAN = RegionCrop(
    key="mp_soybean",
    label="Madhya Pradesh soybeans",
    crop="soybean",
    selector=[(6, None)],                   # Madhya Pradesh
    points=MP_POINTS,
    build=_mp_soybean,
    doc="Regions/인도/중부_마디아프라데시/대두/대두_상세분석_및_수식.md",
    critical_window=[(6, 0), (7, 0), (8, 0), (9, 0)],
    panel={"spi_monsoon": "precip_jun_sep"},
    core=["onset_delay", "flowering_stress", "harvest_waterlog",
          "oni_season", "dmi_season"],
    caveat="The guide asks for an ENSO-coupled LSTM. With roughly forty "
           "labelled seasons a recurrent network cannot be trained -- it would "
           "memorise the record -- so the temporal narrative the LSTM was "
           "meant to learn is encoded explicitly instead, as the three "
           "features the guide itself names (onset delay, flowering dry-spell "
           "stress, harvest waterlogging), fed to a regularised linear model. "
           "That is a weaker claim than the guide's and is the largest "
           "departure in this set.",
    non_weather_drivers=(
        "Madhya Pradesh soybean area has moved with the relative price of "
        "soybean against maize and pulses, and a shift in the area mix changes "
        "the average yield without any weather having changed. Seed "
        "replacement rate and yellow mosaic virus pressure are also real "
        "drivers that no climate feature reaches."),
)


# ---------------------------------------------------------------------------
# 서부_마하라슈트라 -- 면화: inverted-U, and the pest is the right-hand arm.
#
# The guide bans linear regression outright, on the grounds that cotton loses
# in both directions -- drought sheds bolls, and a wet, humid season brings
# pink bollworm. The ban is about the *shape*, not the estimator: what a linear
# model cannot do is turn around at a threshold. So the non-linearity is put
# into the features (a moisture deficit that is signed, a pest counter that
# only fires inside a temperature-humidity box) rather than into a tree
# ensemble that forty rows cannot support. This is a substitution and is
# recorded as one.
#
# Region: Vidarbha (Amravati + Nagpur divisions) and Marathwada (Aurangabad +
# Latur divisions), which is what the guide is actually about, plus Gujarat.
# Maharashtra as a whole would fold in the irrigated cane belt around Pune and
# Kolhapur, which is a different farming system entirely.
# ---------------------------------------------------------------------------

VIDARBHA = ["Amravati division", "Nagpur division"]
MARATHWADA = ["Aurangabad division", "Latur division"]

COTTON_POINTS = [
    {"name": "Yeotmal",        "lat": 20.39, "lon": 78.13, "elevation": 445, "weight": 0.207},
    {"name": "Akola",          "lat": 20.71, "lon": 77.00, "elevation": 282, "weight": 0.081},
    {"name": "Amarawati",      "lat": 20.93, "lon": 77.75, "elevation": 343, "weight": 0.097},
    {"name": "Nanded",         "lat": 19.15, "lon": 77.32, "elevation": 362, "weight": 0.138},
    {"name": "Rajkot",         "lat": 22.30, "lon": 70.80, "elevation": 134, "weight": 0.132},
    {"name": "Surendranagar",  "lat": 22.73, "lon": 71.65, "elevation": 78,  "weight": 0.197},
    {"name": "Amreli",         "lat": 21.60, "lon": 71.22, "elevation": 127, "weight": 0.149},
]


def _cotton(daily, y):
    return {
        # sum over Aug-Sep of (PET - Rainfall), the boll-formation ledger (§2A)
        "moisture_deficit": C.moisture_deficit(daily, [(8, 0), (9, 0)], y),
        # Days with 25-30 C AND RH > 80% on the same day (§2B)
        "pest_risk_days": C.pest_risk_days(
            daily, [(8, 0), (9, 0), (10, 0)], y),
        # The wet arm of the inverted U, measured directly
        "harvest_rain": C.window_totals(daily, [(10, 0), (11, 0)], y),
        "monsoon_rain": C.window_totals(
            daily, [(6, 0), (7, 0), (8, 0), (9, 0)], y),
        # Heat x VPD over boll formation -- not in this guide's formulas, but
        # the mechanism it describes qualitatively.
        "boll_heat": C.boll_shedding_index(daily, [(8, 0), (9, 0)], y),
        "onset_delay": C.days_late(C.monsoon_onset_doy(daily, y)),
        "longest_dry_aug": C.longest_dry_spell(daily, [(8, 0)], y),
    }


COTTON = RegionCrop(
    key="vidarbha_cotton",
    label="Vidarbha + Marathwada + Gujarat cotton",
    crop="cotton",
    selector=[(7, VIDARBHA + MARATHWADA), (3, None)],   # Maharashtra, Gujarat
    points=COTTON_POINTS,
    build=_cotton,
    doc="Regions/인도/서부_마하라슈트라/면화/면화_상세분석_및_수식.md",
    critical_window=[(8, 0), (9, 0), (10, 0)],
    panel={"spi_monsoon": "monsoon_rain"},
    core=["moisture_deficit", "pest_risk_days", "harvest_rain",
          "spi_monsoon"],
    # Bt cotton was approved in India in 2002 and went from nothing to almost
    # the entire crop within a decade. Yield roughly doubled and the pest
    # complex itself changed -- bollworm was suppressed, then pink bollworm
    # developed resistance. Fitting one trend and one set of coefficients
    # across that break would corrupt both eras at once, exactly as the
    # pre-2000 MATOPIBA cotton did. The date is set from the policy change;
    # the training run reports what the series does either side of it.
    regime_start=2003,
    min_train=12,
    caveat="The guide requires XGBoost/LightGBM and bans linear regression "
           "because cotton's yield-rainfall response is an inverted U. The "
           "shape is preserved in the features -- a signed moisture deficit "
           "and a pest counter that fires only inside a temperature-humidity "
           "box give the model both arms of the curve -- but the estimator is "
           "the same ridge used elsewhere, because a gradient-boosted "
           "ensemble on ~20 post-Bt seasons would fit noise. The guide's "
           "irrigation-percentage categorical is not implemented: it would "
           "need a district irrigation series joined per year.",
    non_weather_drivers=(
        "Cotton is the crop in this set least explainable by weather. The "
        "post-2002 Bt transition, seed pricing and availability, the spread of "
        "pink bollworm resistance from about 2015, and the minimum support "
        "price relative to soybean and pigeonpea all move planted area and "
        "input intensity from year to year. ICRISAT also reports cotton in "
        "lint terms, so a change in ginning ratio moves the series without "
        "any change in the field."),
)


ALL = [PUNJAB_WHEAT, MP_SOYBEAN, COTTON]

BY_KEY = {r.key: r for r in ALL}
