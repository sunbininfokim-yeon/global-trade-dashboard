"""
One config per guide in Regions/중국.

The six guides diverge even more than Brazil's nine did. Northeast soy and
corn are a race between maturity and the first frost; Henan wheat is a
compound-extreme problem at grain fill; Yangtze rice is heat persistence
against flood; South China is not a yield problem at all but a cropping-
intensity one; Shandong vegetables are a built-infrastructure problem wearing
a weather model's clothes. Each `build` implements only its own guide.

Every config also declares what its target actually is. Five of the six are
national series standing in for a provincial question -- see labels.py -- and
the dilution differs enough between them that it belongs in the config rather
than in one blanket disclaimer.
"""

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from . import climate as C
from . import labels as L


@dataclass
class RegionCrop:
    key: str
    label: str
    points: list                    # [{name, lat, lon, elevation, weight}]
    build: Callable                 # (daily, harvest_year) -> dict
    doc: str                        # source guide
    target: Callable                # () -> DataFrame[year, target]
    target_label: str
    target_unit: str
    label_source: str
    # Share of the national target the modelled region actually produces. The
    # honest ceiling on how much of the target a regional weather model could
    # explain even if every formula were perfect.
    region_share: str
    # NASA POWER opens 1981-01-01. Winter crops need the previous October, so
    # 1982 is the first complete season for wheat; summer crops could start in
    # 1981 but are kept aligned.
    start_year: int = 1982
    panel: dict = field(default_factory=dict)
    core: list = field(default_factory=list)
    # Months that actually decide the target, as (month, year_offset). predict.py
    # reports how much of this window the live weather record covers, so a
    # number published while the deciding months are still ahead reads as a
    # climatology projection rather than as a read on the season.
    critical_window: list = field(default_factory=list)
    regime_start: int = 0
    min_train: int = 0
    non_weather_drivers: str = ""
    caveat: str = ""


# ---------------------------------------------------------------------------
# 동북3성 -- 대두 / 옥수수: maturity against the first frost.
# ---------------------------------------------------------------------------

# Heilongjiang, Jilin and Liaoning. Nenjiang is included because the northern
# margin of the soy belt is where the frost risk the guide describes actually
# bites -- a point set clustered around Harbin would understate it.
NE_POINTS_SOY = [
    {"name": "Harbin",    "lat": 45.80, "lon": 126.53, "elevation": 142, "weight": 0.20},
    {"name": "Jiamusi",   "lat": 46.80, "lon": 130.32, "elevation": 80,  "weight": 0.20},
    {"name": "Qiqihar",   "lat": 47.35, "lon": 123.92, "elevation": 146, "weight": 0.15},
    {"name": "Nenjiang",  "lat": 49.17, "lon": 125.23, "elevation": 243, "weight": 0.15},
    {"name": "Changchun", "lat": 43.88, "lon": 125.32, "elevation": 217, "weight": 0.15},
    {"name": "Shenyang",  "lat": 41.80, "lon": 123.43, "elevation": 45,  "weight": 0.15},
]

# Corn sits further south in the same three provinces: Jilin's Golden Maize
# Belt outweighs the northern Heilongjiang points that dominate soybeans.
NE_POINTS_CORN = [
    {"name": "Harbin",    "lat": 45.80, "lon": 126.53, "elevation": 142, "weight": 0.18},
    {"name": "Jiamusi",   "lat": 46.80, "lon": 130.32, "elevation": 80,  "weight": 0.12},
    {"name": "Qiqihar",   "lat": 47.35, "lon": 123.92, "elevation": 146, "weight": 0.15},
    {"name": "Nenjiang",  "lat": 49.17, "lon": 125.23, "elevation": 243, "weight": 0.10},
    {"name": "Changchun", "lat": 43.88, "lon": 125.32, "elevation": 217, "weight": 0.25},
    {"name": "Siping",    "lat": 43.17, "lon": 124.35, "elevation": 165, "weight": 0.10},
    {"name": "Shenyang",  "lat": 41.80, "lon": 123.43, "elevation": 45,  "weight": 0.10},
]

# Thermal time to physiological maturity, base 10 C, on the plain
# (Tmax + Tmin)/2 - Tbase accumulation this pipeline uses -- not the US
# convention that caps Tmax at 30 and floors Tmin at 10, which would give
# larger numbers for the same crop.
#
# These have to sit below what the region actually accumulates or the variable
# breaks. Season-total GDD across these points averages ~1410 and ranges
# 1240-1680. An earlier 1600 for corn put maturity above the mean season, so
# the crop never reached maturity in the model, every October frost scored as
# damage, and frost_penalty degenerated into a proxy for warming: its six
# largest values were all 1984-93. Northeast hybrids are short-season by
# necessity, and these values -- corn ~1300, soy ~1100 -- let a normal year
# finish before the frost while a cold year does not, which is the mechanism
# the guide is describing.
SOY_GDD_MATURITY = 1100.0
CORN_GDD_MATURITY = 1300.0


def _ne_soy(daily, y):
    return {
        # Σ(Tmin < 0) × (1 - maturity), guide §2B
        "frost_penalty": C.frost_penalty_by_maturity(
            daily, y, 5, 5, tbase=10.0, gdd_to_maturity=SOY_GDD_MATURITY,
            frost_months=[(9, 0), (10, 0)]),
        "frost_days_sep": C.frost_days(daily, [(9, 0)], y, 0.0),
        "gdd_season": C.gdd_total(daily, y, 5, 5, tbase=10.0),
        # Pod fill: 35 C halts nitrogen fixation in soybeans
        "heat_days_podfill": C.heat_days(daily, [(7, 0), (8, 0)], y, 35.0),
        "precip_podfill": C.window_totals(daily, [(7, 0), (8, 0)], y),
        "precip_veg": C.window_totals(daily, [(5, 0), (6, 0)], y),
        "vpd_peak_summer": C.vpd_peak(daily, [(7, 0), (8, 0)], y),
    }


NE_SOY = RegionCrop(
    key="northeast_soy",
    label="Northeast China soybeans (Heilongjiang, Jilin, Liaoning)",
    points=NE_POINTS_SOY,
    build=_ne_soy,
    doc="Regions/중국/동북3성/대두_옥수수/대두_옥수수_상세분석_및_수식.md",
    target=lambda: L.psd_yield_kg_ha("Oilseed, Soybean"),
    target_label="soybean yield",
    target_unit="kg/ha",
    label_source="USDA PSD, national",
    region_share=(
        "The Northeast produces roughly 40% of China's soybeans, so a perfect "
        "regional model still leaves 60% of the national target driven by "
        "weather this point set never sees."),
    panel={"spi3_summer": "precip_podfill"},
    core=["frost_penalty", "gdd_season", "heat_days_podfill",
          "precip_podfill"],
    critical_window=[(7, 0), (8, 0), (9, 0)],
    caveat=(
        "The guide's first instruction is to recompute planted area from "
        "Sentinel-1 SAR rather than accept the official figure. That needs a "
        "SAR archive and a classifier this pipeline does not have, so area is "
        "not corrected and only yield is modelled. Maturity is tracked by "
        "accumulated GDD from a fixed 5 May planting date, not an observed "
        "one, and one GDD-to-maturity constant stands for the whole region's "
        "cultivar mix."),
    non_weather_drivers=(
        "Chinese soybean area and yield both move with the state procurement "
        "price and the rotation subsidy that pays farmers to switch between "
        "soy and corn, and Heilongjiang's subsidy has been retuned repeatedly "
        "since 2016. None of that is weather, and the national target absorbs "
        "it directly."),
)


def _ne_corn(daily, y):
    planting = pd.Timestamp(year=y, month=5, day=5)
    return {
        "frost_penalty": C.frost_penalty_by_maturity(
            daily, y, 5, 5, tbase=10.0, gdd_to_maturity=CORN_GDD_MATURITY,
            frost_months=[(9, 0), (10, 0)]),
        "frost_days_sep": C.frost_days(daily, [(9, 0)], y, 0.0),
        "gdd_season": C.gdd_total(daily, y, 5, 5, tbase=10.0),
        # Silking sits ~60-75 days after a 5 May planting, i.e. July
        "silking_stress": C.silking_stress(daily, planting),
        "heat_days_silking": C.heat_days(daily, [(7, 0)], y, 35.0),
        "precip_silking": C.window_totals(daily, [(7, 0), (8, 0)], y),
        "precip_veg": C.window_totals(daily, [(5, 0), (6, 0)], y),
        "vpd_peak_summer": C.vpd_peak(daily, [(7, 0), (8, 0)], y),
    }


NE_CORN = RegionCrop(
    key="northeast_corn",
    label="Northeast China corn (Heilongjiang, Jilin, Liaoning)",
    points=NE_POINTS_CORN,
    build=_ne_corn,
    doc="Regions/중국/동북3성/대두_옥수수/대두_옥수수_상세분석_및_수식.md",
    target=lambda: L.psd_yield_kg_ha("Corn"),
    target_label="corn yield",
    target_unit="kg/ha",
    label_source="USDA PSD, national",
    region_share=(
        "The Northeast grows roughly 30% of China's corn. The North China "
        "Plain summer crop, which this point set excludes by design, is a "
        "comparable share and has entirely different weather."),
    panel={"spi3_summer": "precip_silking"},
    core=["frost_penalty", "gdd_season", "silking_stress",
          "heat_days_silking"],
    critical_window=[(7, 0), (8, 0), (9, 0)],
    caveat=(
        "Same SAR-area departure as the soybean model. Silking is placed by "
        "days after a fixed planting date rather than observed phenology."),
    non_weather_drivers=(
        "The 2016 abolition of the corn stockpiling programme cut planted "
        "area sharply and then policy pushed it back up; the national yield "
        "series also carries a steady varietal and density trend that the log "
        "trend absorbs rather than the weather features."),
)


# ---------------------------------------------------------------------------
# 중부_허난 -- 겨울밀: 干热风 at grain fill, rain at harvest.
# ---------------------------------------------------------------------------

# Henan plus the rest of the Huang-Huai-Hai plain. Together these five
# provinces are about three quarters of Chinese wheat, which makes this the
# one config whose national target is nearly a regional one.
HHH_POINTS = [
    {"name": "Zhengzhou", "lat": 34.75, "lon": 113.63, "elevation": 110, "weight": 0.12},
    {"name": "Zhoukou",   "lat": 33.63, "lon": 114.65, "elevation": 50,  "weight": 0.12},
    {"name": "Shangqiu",  "lat": 34.45, "lon": 115.65, "elevation": 50,  "weight": 0.11},
    {"name": "Xinxiang",  "lat": 35.30, "lon": 113.93, "elevation": 74,  "weight": 0.10},
    {"name": "Jining",    "lat": 35.42, "lon": 116.58, "elevation": 40,  "weight": 0.20},
    {"name": "Handan",    "lat": 36.60, "lon": 114.48, "elevation": 58,  "weight": 0.15},
    {"name": "Bengbu",    "lat": 32.92, "lon": 117.38, "elevation": 20,  "weight": 0.12},
    {"name": "Xuzhou",    "lat": 34.27, "lon": 117.18, "elevation": 41,  "weight": 0.08},
]


def _hhh_wheat(daily, y):
    # Sown October of y-1, overwinters, fills in May, harvested early June.
    return {
        # Tmax >= 30 AND RH <= 30% AND wind >= 3 m/s, guide §2A
        "dhw_days": C.dry_hot_wind_days(daily, [(5, 0)], y),
        "dhw_severity": C.dry_hot_wind_severity(daily, [(5, 0)], y),
        # Rain inside the pre-harvest window is what sprouts the grain in the
        # ear (수발아) and demotes milling wheat to feed, guide §2B. The window
        # is 25 May - 10 June, per the guide's "5월 하순~6월 초": June alone
        # misses the 2023 Henan disaster, which fell in the last week of May.
        "preharvest_rain": C.date_window_rain(daily, y, (5, 25), (6, 10)),
        "preharvest_rain_excess": C.date_window_rain(
            daily, y, (5, 25), (6, 10), threshold=30.0),
        "late_may_rain": C.window_totals(daily, [(5, 0)], y),
        "winterkill_days": C.winterkill_days(daily,
                                             [(12, -1), (1, 0), (2, 0)], y, -12.0),
        "heat_excess_fill": C.heat_excess(daily, [(5, 0)], y, 32.0),
        "precip_jointing": C.window_totals(daily, [(3, 0), (4, 0)], y),
        "gdd_spring": C.gdd_total(daily, y, 3, 1, tbase=0.0, horizon=100),
    }


HHH_WHEAT = RegionCrop(
    key="henan_wheat",
    label="Henan + Huang-Huai-Hai winter wheat",
    points=HHH_POINTS,
    build=_hhh_wheat,
    doc="Regions/중국/중부_허난/밀/겨울밀_상세분석_및_수식.md",
    target=lambda: L.psd_yield_kg_ha("Wheat"),
    target_label="wheat yield",
    target_unit="kg/ha",
    label_source="USDA PSD, national",
    region_share=(
        "Henan alone is about a quarter of Chinese wheat and the Huang-Huai-"
        "Hai plain as a whole roughly three quarters, so the national target "
        "is closer to a regional one here than for any other config in the "
        "set."),
    panel={"spi3_spring": "precip_jointing"},
    core=["dhw_days", "dhw_severity", "preharvest_rain", "winterkill_days"],
    critical_window=[(5, 0), (6, 0)],
    caveat=(
        "SIF (solar-induced fluorescence) from §2A is omitted: the satellite "
        "record starts in 2007 and would cut the series roughly in half. The "
        "guide's proposal to reverse-engineer bad years from UN Comtrade "
        "milling-wheat imports is implemented as a separate diagnostic in "
        "imports.py rather than as a second label, because rewriting the "
        "target from trade data would make the yield model unfalsifiable."),
    non_weather_drivers=(
        "The guide's own example is the point: in 2023 Beijing reported a "
        "0.9% wheat decline while quality collapsed and milling-wheat imports "
        "hit a record. A tonnage yield series cannot represent a quality "
        "failure, so the single most consequential Henan weather event of the "
        "last decade is largely invisible in this target by construction."),
)


# ---------------------------------------------------------------------------
# 남부_장강 -- 쌀: heat persistence against flood.
# ---------------------------------------------------------------------------

YANGTZE_POINTS = [
    {"name": "Changsha", "lat": 28.20, "lon": 112.98, "elevation": 45,  "weight": 0.22},
    {"name": "Nanchang", "lat": 28.68, "lon": 115.90, "elevation": 25,  "weight": 0.18},
    {"name": "Wuhan",    "lat": 30.58, "lon": 114.30, "elevation": 23,  "weight": 0.18},
    {"name": "Hefei",    "lat": 31.87, "lon": 117.28, "elevation": 30,  "weight": 0.15},
    {"name": "Nanjing",  "lat": 32.05, "lon": 118.78, "elevation": 20,  "weight": 0.15},
    {"name": "Chengdu",  "lat": 30.67, "lon": 104.07, "elevation": 500, "weight": 0.12},
]


def _yangtze_rice(daily, y):
    return {
        # Σ max(0, Tmax - 35) × run length over heading and filling, guide §2A
        "heat_penalty": C.heat_penalty_with_duration(
            daily, [(7, 0), (8, 0)], y, 35.0),
        "max_heat_run": C.max_heat_run(daily, [(7, 0), (8, 0)], y, 35.0),
        "heat_days_heading": C.heat_days(daily, [(7, 0), (8, 0)], y, 35.0),
        # Flood proxy: heaviest 7-day fall in the Meiyu window, guide §2B
        "max_7day_rain": C.max_nday_rain(daily, [(6, 0), (7, 0)], y, 7),
        "monsoon_rain": C.window_totals(daily, [(6, 0), (7, 0)], y),
        "waterlogging": C.waterlogging_penalty(
            daily, [(6, 0), (7, 0)], y, 400.0),
        "precip_season": C.window_totals(
            daily, [(5, 0), (6, 0), (7, 0), (8, 0), (9, 0)], y),
        "radiation_fill": C.radiation_total(daily, [(8, 0), (9, 0)], y),
    }


YANGTZE_RICE = RegionCrop(
    key="yangtze_rice",
    label="Yangtze basin rice",
    points=YANGTZE_POINTS,
    build=_yangtze_rice,
    doc="Regions/중국/남부_장강/쌀/쌀_상세분석_및_수식.md",
    target=lambda: L.psd_yield_kg_ha("Rice, Milled"),
    target_label="milled rice yield",
    target_unit="kg/ha",
    label_source="USDA PSD, national, milled basis",
    region_share=(
        "The Yangtze basin provinces are the majority of Chinese rice, but "
        "the national series also averages single-season japonica in the "
        "Northeast against double-cropped indica in the far south -- three "
        "cropping systems with three different weather sensitivities in one "
        "number."),
    panel={"spi3_monsoon": "monsoon_rain"},
    core=["heat_penalty", "max_heat_run", "max_7day_rain", "waterlogging"],
    critical_window=[(7, 0), (8, 0)],
    caveat=(
        "The guide's dynamic crop calendar -- back out each pixel's heading "
        "date from an NDVI time series -- is replaced by a fixed "
        "July-August heading window, because MODIS starts in 2000 and would "
        "halve the record. The Sentinel-1 inundation mask is replaced by the "
        "heaviest 7-day rainfall total, named max_7day_rain."),
    non_weather_drivers=(
        "Rice area has been shifting from double- to single-cropping for two "
        "decades, which raises measured yield per harvested hectare without "
        "any agronomic improvement. That composition drift sits inside the "
        "trend, not the weather features."),
)


# ---------------------------------------------------------------------------
# 남부_화남 -- 다모작: an area problem, not a yield problem.
# ---------------------------------------------------------------------------

SOUTH_POINTS = [
    {"name": "Guangzhou", "lat": 23.13, "lon": 113.26, "elevation": 21,  "weight": 0.25},
    {"name": "Nanning",   "lat": 22.82, "lon": 108.32, "elevation": 79,  "weight": 0.25},
    {"name": "Shaoguan",  "lat": 24.81, "lon": 113.60, "elevation": 61,  "weight": 0.20},
    {"name": "Guilin",    "lat": 25.28, "lon": 110.29, "elevation": 150, "weight": 0.15},
    {"name": "Zhanjiang", "lat": 21.27, "lon": 110.36, "elevation": 25,  "weight": 0.15},
]


def _south_china(daily, y):
    return {
        # 倒春寒: cold snaps on transplanted early-rice seedlings in March.
        # A farmer who loses the early crop often does not replant it, which
        # is the decision this model is trying to see.
        "spring_chill_days": C.cold_days(daily, [(3, 0)], y, 12.0),
        "spring_rain": C.window_totals(daily, [(3, 0), (4, 0)], y),
        # 寒露风: cold-dew wind sterilising late rice at heading
        "cold_dew_days": C.cold_days(daily, [(9, 0), (10, 0)], y, 22.0),
        # Early-rice harvest and late-rice transplanting overlap in July;
        # rain then is what makes the double crop fail to turn around in time
        "turnaround_rain": C.window_totals(daily, [(7, 0)], y),
        "typhoon_days": C.typhoon_proxy(daily, [(7, 0), (8, 0), (9, 0)], y),
        "heat_days_summer": C.heat_days(daily, [(7, 0), (8, 0)], y, 35.0),
        "precip_annual": C.window_totals(
            daily, [(m, 0) for m in range(1, 13)], y),
    }


SOUTH_CHINA_RICE = RegionCrop(
    key="south_china_rice_area",
    label="South China rice cropping intensity (harvested area)",
    points=SOUTH_POINTS,
    build=_south_china,
    doc="Regions/중국/남부_화남/복합식량안보_및_다모작/식량안보_레드라인_다모작_분석.md",
    # The guide's subject is whether farmers planted the second rice crop the
    # state told them to. Yield per harvested hectare cannot answer that --
    # dropping the second crop *raises* it. Harvested area can: it counts each
    # crop separately, so a province going from double to single halves its
    # contribution. This is the closest observable to the guide's compliance
    # measure, and it is an area target, not a yield one.
    target=lambda: L.psd_area_1000ha("Rice, Milled"),
    target_label="rice area harvested",
    target_unit="1000 ha",
    label_source="USDA PSD, national",
    region_share=(
        "Guangdong and Guangxi are where double-cropping is actually being "
        "abandoned, but they are a minority of national rice area, so most of "
        "the movement in this target is Jiangxi, Hunan and Hubei -- and most "
        "of that is policy."),
    core=["spring_chill_days", "cold_dew_days", "turnaround_rain",
          "typhoon_days"],
    critical_window=[(3, 0), (7, 0), (9, 0), (10, 0)],
    caveat=(
        "The guide's method is a Sentinel-1 SAR time series read for the "
        "flood-transplant-flood signature of a second crop, classified by "
        "CNN-LSTM. None of that is implemented. This substitutes national "
        "harvested area as an aggregate proxy for cropping intensity and the "
        "weather events that make a farmer abandon the second crop. It is a "
        "much weaker instrument than the guide's and should be read as a "
        "screening indicator, not a compliance measurement."),
    non_weather_drivers=(
        "Cropping intensity in South China is set by the minimum purchase "
        "price, the rural wage that makes a second crop uneconomic, "
        "urbanisation taking paddy out of production, and since 2021 the "
        "退林还耕 campaign forcing it back in. Policy dominates weather here "
        "by a wide margin, and a weather model failing on this target is the "
        "expected result rather than a broken one."),
)


# ---------------------------------------------------------------------------
# 산둥_화북 -- 채소: light and structure, not rain.
# ---------------------------------------------------------------------------

SHANDONG_POINTS = [
    {"name": "Shouguang", "lat": 36.88, "lon": 118.74, "elevation": 20, "weight": 0.30},
    {"name": "Weifang",   "lat": 36.71, "lon": 119.16, "elevation": 30, "weight": 0.20},
    {"name": "Jinan",     "lat": 36.65, "lon": 117.12, "elevation": 52, "weight": 0.20},
    {"name": "Linyi",     "lat": 35.10, "lon": 118.35, "elevation": 80, "weight": 0.15},
    {"name": "Qingdao",   "lat": 36.07, "lon": 120.38, "elevation": 25, "weight": 0.15},
]


def _shandong_veg(daily, y):
    winter = [(12, -1), (1, 0), (2, 0)]
    return {
        # Σ(Solar_Radiation < threshold) over winter, guide §2B
        "low_light_days": C.low_radiation_days(daily, winter, y, 8.0),
        "winter_radiation": C.radiation_total(daily, winter, y),
        "snow_load": C.snow_load_proxy(daily, winter, y, 2.0),
        "winter_cold_days": C.frost_days(daily, winter, y, -8.0),
        # Open-field summer vegetables still feel heat and flooding
        "heat_days_summer": C.heat_days(daily, [(6, 0), (7, 0), (8, 0)], y, 35.0),
        "summer_rain": C.window_totals(daily, [(6, 0), (7, 0), (8, 0)], y),
        "spring_radiation": C.radiation_total(daily, [(3, 0), (4, 0)], y),
    }


SHANDONG_VEG = RegionCrop(
    key="shandong_vegetables",
    label="Shandong vegetables (protected + open field)",
    points=SHANDONG_POINTS,
    build=_shandong_veg,
    doc="Regions/중국/산둥_화북/채소/채소_원예_상세분석_및_수식.md",
    target=lambda: L.faostat_yield_kg_ha("Vegetables Primary"),
    target_label="vegetable yield",
    target_unit="kg/ha",
    label_source="FAOSTAT, national, compiled from NBS returns",
    region_share=(
        "Shandong is around a tenth of national vegetable output. This is the "
        "weakest region-to-target match in the set, and unlike the other five "
        "the label cannot fall back on USDA: PSD carries no vegetables, so "
        "FAOSTAT's China figures -- compiled from the very NBS returns every "
        "guide says to distrust -- are the only series available."),
    core=["low_light_days", "winter_radiation", "snow_load"],
    critical_window=[(12, -1), (1, 0), (2, 0)],
    caveat=(
        "The guide's actual method is Swin-UNet segmentation of Sentinel-2 "
        "and GF-2 imagery to map plastic greenhouse area, on the argument "
        "that built area sets the production ceiling and weather only "
        "modulates it. None of that is implemented; greenhouse expansion is "
        "left entirely to the technology trend, which is why the weather "
        "features here are expected to add little. This is the largest "
        "departure from any guide in the China set."),
    non_weather_drivers=(
        "Vegetable output is driven by how much protected-cultivation "
        "structure exists, which is an investment series, not a climate one. "
        "The guide says so itself in §1: greenhouse crops are largely "
        "insulated from outside weather, which is the reason the conventional "
        "climate model fails on them."),
)


ALL = [
    NE_SOY,
    NE_CORN,
    HHH_WHEAT,
    YANGTZE_RICE,
    SOUTH_CHINA_RICE,
    SHANDONG_VEG,
]

BY_KEY = {r.key: r for r in ALL}
