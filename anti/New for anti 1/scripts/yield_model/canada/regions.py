"""Canadian region-crops: SAD/CAR first, province fallback.

Feature regimes follow Chipanshi ICCYF (CAR), Morrison HSU@29.5 °C,
Mkhabela SMOS excess-moisture (esp. early June), Palliser drought heat,
Manitoba MASC excess moisture, Ontario short-season GDD/EDD.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .climate import (
    canola_features,
    canola_palliser_features,
    canola_peace_features,
    corn_features,
    soy_excess_features,
    spring_wheat_features,
)


@dataclass(frozen=True)
class RegionCrop:
    key: str
    label: str
    label_ko: str
    crop: str
    crop_label: str  # province table name
    points: list[dict]
    build: Callable
    feature_sets: dict[str, list[str]]
    doc: str
    caveat: str
    # Labels
    label_scale: str  # "sad" | "province"
    geo: str = ""  # exact StatsCan GEO when not stitching
    stitch_sk_cd: int | None = None
    province_fallback_key: str | None = None
    sad_crop_label: str = ""  # SAD table name if different from crop_label
    start_year: int = 1982
    min_train: int = 18
    publish: bool = True  # include in forecast JSON

    def sad_crop(self) -> str:
        return self.sad_crop_label or self.crop_label


def z(names: list[str]) -> list[str]:
    return [name + "_z20" for name in names]


def sets(weather: list[str], soil: list[str],
         drivers: list[str] | None = None) -> dict[str, list[str]]:
    drivers = drivers or ["oni_summer_z20"]
    return {
        "weather": weather,
        "weather_soil": soil,
        "weather_soil_drivers": soil + drivers,
    }


# --- Feature packs (region-specific; lit-aligned) ---
# Palliser / semi-arid: heat + drought dominate (Morrison; Qian DSSAT water stress)
PALLISER_W = z(["hsu_flower", "heat_dry_stress", "rain_growing", "vpd_flowering"])
PALLISER_S = PALLISER_W + z(["sm_preseason", "sm_flowering", "rain_winter"])
# Parkland: moisture + moderate heat (Chipanshi CAR skill higher with stations)
PARKLAND_W = z(["rain_growing", "hsu_flower", "frost_sep", "rain_flowering"])
PARKLAND_S = PARKLAND_W + z(["sm_preseason", "sm_flowering", "rain_winter"])
# Peace River: short season / frost (Alberta north)
PEACE_W = z(["frost_sep", "gdd0_growing", "hsu_flower", "rain_growing"])
PEACE_S = PEACE_W + z(["sm_preseason", "sm_flowering", "rain_winter"])
# Spring wheat
WHEAT_DRY_W = z(["heat_excess_jul", "rain_growing", "vpd_heading", "frost_sep"])
WHEAT_DRY_S = WHEAT_DRY_W + z(["sm_preseason", "sm_heading", "rain_winter"])
WHEAT_PK_W = z(["rain_growing", "gdd0_growing", "heat_excess_jul", "frost_sep"])
WHEAT_PK_S = WHEAT_PK_W + z(["sm_preseason", "sm_heading", "rain_winter"])
# Manitoba Red River soy: excess May moisture (MASC; Mkhabela June SM)
SOY_EX_W = z(["rain_may", "sm_may", "excess_may", "frost_sep"])
SOY_EX_S = SOY_EX_W + z(["rain_growing", "sm_flowering", "heat_excess_jul"])
# Ontario corn — no frost_sep: in-season Sep is often incomplete → NaN crash
CORN_W = z(["gdd10_growing", "edd_jul", "rain_jul", "heat_days_32"])
CORN_S = CORN_W + z(["sm_jul", "rain_growing", "vpd_jul"])
# Generic canola (province fallback)
CANOLA_W = z(["rain_growing", "hsu_flower", "heat_dry_stress", "frost_sep"])
CANOLA_S = CANOLA_W + z(["sm_preseason", "sm_flowering", "rain_winter"])


LIT = (
    "ICCYF Chipanshi 2015 CAR R2~0.66-0.67; Morrison HSU@29.5C; "
    "Mkhabela SMOS excess SM; MASC Excess Moisture (MB)."
)

# ========== SAD / CAR tracks (priority) ==========
SAD = [
    RegionCrop(
        key="sad_sk_canola_palliser",
        label="SK SAD 3 canola (Palliser)",
        label_ko="SK 산지3 카놀라(팰리서)",
        crop="canola", crop_label="Canola (rapeseed)",
        sad_crop_label="Canola",
        label_scale="sad", stitch_sk_cd=3,
        province_fallback_key="prov_sk_canola",
        points=[{"name": "Assiniboia", "lat": 49.63, "lon": -105.99, "weight": 0.5},
                {"name": "Swift Current", "lat": 50.29, "lon": -107.80, "weight": 0.5}],
        build=canola_palliser_features,
        feature_sets=sets(PALLISER_W, PALLISER_S),
        doc="Regions/북미_캐나다/서스캐처원_앨버타/카놀라_봄밀/카놀라_봄밀_상세분석.md",
        caveat=LIT + " Semi-arid Palliser Triangle; heat×drought pack.",
    ),
    RegionCrop(
        key="sad_sk_canola_blacksoil",
        label="SK SAD 6 canola (Regina plain)",
        label_ko="SK 산지6 카놀라(레지나)",
        crop="canola", crop_label="Canola (rapeseed)",
        sad_crop_label="Canola",
        label_scale="sad", stitch_sk_cd=6,
        province_fallback_key="prov_sk_canola",
        points=[{"name": "Regina", "lat": 50.45, "lon": -104.61, "weight": 0.6},
                {"name": "Moose Jaw", "lat": 50.39, "lon": -105.55, "weight": 0.4}],
        build=canola_features,
        feature_sets=sets(PARKLAND_W, PARKLAND_S),
        doc="Regions/북미_캐나다/프레리/카놀라_봄밀/캐나다_카놀라_봄밀_상세분석.md",
        caveat=LIT + " Dark Brown / Black soil; balanced moisture-heat.",
    ),
    RegionCrop(
        key="sad_sk_canola_parkland",
        label="SK SAD 5 canola (Yorkton parkland)",
        label_ko="SK 산지5 카놀라(요크턴)",
        crop="canola", crop_label="Canola (rapeseed)",
        sad_crop_label="Canola",
        label_scale="sad", stitch_sk_cd=5,
        province_fallback_key="prov_sk_canola",
        points=[{"name": "Yorkton", "lat": 51.21, "lon": -102.46, "weight": 0.6},
                {"name": "Melville", "lat": 50.93, "lon": -102.81, "weight": 0.4}],
        build=canola_features,
        feature_sets=sets(PARKLAND_W, PARKLAND_S),
        doc="Regions/북미_캐나다/프레리/카놀라_봄밀/캐나다_카놀라_봄밀_상세분석.md",
        caveat=LIT + " Aspen Parkland; moisture-weighted pack.",
    ),
    RegionCrop(
        key="sad_sk_wheat_palliser",
        label="SK SAD 3 spring wheat (Palliser)",
        label_ko="SK 산지3 봄밀(팰리서)",
        crop="spring_wheat", crop_label="Wheat, spring",
        label_scale="sad", stitch_sk_cd=3,
        province_fallback_key="prov_sk_spring_wheat",
        points=[{"name": "Assiniboia", "lat": 49.63, "lon": -105.99, "weight": 0.5},
                {"name": "Swift Current", "lat": 50.29, "lon": -107.80, "weight": 0.5}],
        build=spring_wheat_features,
        feature_sets=sets(WHEAT_DRY_W, WHEAT_DRY_S),
        doc="Regions/북미_캐나다/프레리/카놀라_봄밀/캐나다_카놀라_봄밀_상세분석.md",
        caveat=LIT + " Dryland spring wheat; July heat/VPD pack.",
    ),
    RegionCrop(
        key="sad_sk_wheat_parkland",
        label="SK SAD 5 spring wheat (Yorkton)",
        label_ko="SK 산지5 봄밀(요크턴)",
        crop="spring_wheat", crop_label="Wheat, spring",
        label_scale="sad", stitch_sk_cd=5,
        province_fallback_key="prov_sk_spring_wheat",
        points=[{"name": "Yorkton", "lat": 51.21, "lon": -102.46, "weight": 0.6},
                {"name": "Melville", "lat": 50.93, "lon": -102.81, "weight": 0.4}],
        build=spring_wheat_features,
        feature_sets=sets(WHEAT_PK_W, WHEAT_PK_S),
        doc="Regions/북미_캐나다/프레리/카놀라_봄밀/캐나다_카놀라_봄밀_상세분석.md",
        caveat=LIT,
    ),
    RegionCrop(
        key="sad_ab_canola_south",
        label="AB SAD 20 canola (Lethbridge)",
        label_ko="AB 산지20 카놀라(레스브리지)",
        crop="canola", crop_label="Canola (rapeseed)",
        sad_crop_label="Canola",
        label_scale="sad",
        geo="Small Area Data Region 20 - Alberta",
        province_fallback_key="prov_ab_canola",
        points=[{"name": "Lethbridge", "lat": 49.69, "lon": -112.84, "weight": 0.6},
                {"name": "Taber", "lat": 49.78, "lon": -112.15, "weight": 0.4}],
        build=canola_palliser_features,
        feature_sets=sets(PALLISER_W, PALLISER_S),
        doc="Regions/북미_캐나다/서스캐처원_앨버타/카놀라_봄밀/카놀라_봄밀_상세분석.md",
        caveat=LIT + " Southern AB heat/drought.",
    ),
    RegionCrop(
        key="sad_ab_canola_central",
        label="AB SAD 50 canola (Red Deer)",
        label_ko="AB 산지50 카놀라(레드디어)",
        crop="canola", crop_label="Canola (rapeseed)",
        sad_crop_label="Canola",
        label_scale="sad",
        geo="Small Area Data Region 50 - Alberta",
        province_fallback_key="prov_ab_canola",
        points=[{"name": "Red Deer", "lat": 52.27, "lon": -113.81, "weight": 0.55},
                {"name": "Olds", "lat": 51.79, "lon": -114.10, "weight": 0.45}],
        build=canola_features,
        feature_sets=sets(PARKLAND_W, PARKLAND_S),
        doc="Regions/북미_캐나다/서스캐처원_앨버타/카놀라_봄밀/카놀라_봄밀_상세분석.md",
        caveat=LIT,
    ),
    RegionCrop(
        key="sad_ab_canola_peace",
        label="AB SAD 70 canola (Peace)",
        label_ko="AB 산지70 카놀라(피스)",
        crop="canola", crop_label="Canola (rapeseed)",
        sad_crop_label="Canola",
        label_scale="sad",
        geo="Small Area Data Region 70 - Alberta",
        province_fallback_key="prov_ab_canola",
        points=[{"name": "Grande Prairie", "lat": 55.17, "lon": -118.80, "weight": 0.6},
                {"name": "Peace River", "lat": 56.23, "lon": -117.29, "weight": 0.4}],
        build=canola_peace_features,
        feature_sets=sets(PEACE_W, PEACE_S),
        doc="Regions/북미_캐나다/서스캐처원_앨버타/카놀라_봄밀/카놀라_봄밀_상세분석.md",
        caveat=LIT + " Short season; frost/GDD pack.",
    ),
    RegionCrop(
        key="sad_mb_soy_redriver",
        label="MB SAD 2 soybeans (Red River)",
        label_ko="MB 산지2 대두(레드리버)",
        crop="soybeans", crop_label="Soybeans",
        label_scale="sad",
        geo="Small Area Data Region 2 - Manitoba",
        province_fallback_key="prov_mb_soybeans",
        points=[{"name": "Winnipeg", "lat": 49.90, "lon": -97.14, "weight": 0.45},
                {"name": "Portage la Prairie", "lat": 49.97, "lon": -98.29, "weight": 0.35},
                {"name": "Winkler", "lat": 49.18, "lon": -97.94, "weight": 0.20}],
        build=soy_excess_features,
        feature_sets=sets(SOY_EX_W, SOY_EX_S),
        doc="Regions/북미_캐나다/매니토바/대두_귀리/대두_귀리_상세분석.md",
        caveat=LIT + " Excess May moisture lead feature (MASC).",
        start_year=1995, min_train=15,
    ),
    RegionCrop(
        key="sad_mb_canola_central",
        label="MB SAD 8 canola",
        label_ko="MB 산지8 카놀라",
        crop="canola", crop_label="Canola (rapeseed)",
        sad_crop_label="Canola",
        label_scale="sad",
        geo="Small Area Data Region 8 - Manitoba",
        province_fallback_key="prov_mb_canola",
        points=[{"name": "Brandon", "lat": 49.85, "lon": -99.95, "weight": 0.55},
                {"name": "Dauphin", "lat": 51.15, "lon": -100.05, "weight": 0.45}],
        build=canola_features,
        feature_sets=sets(PARKLAND_W, PARKLAND_S),
        doc="Regions/북미_캐나다/매니토바/대두_귀리/대두_귀리_상세분석.md",
        caveat=LIT,
    ),
    RegionCrop(
        key="sad_on_corn_southern",
        label="ON Southern corn (Region 1)",
        label_ko="온타리오 남부 옥수수",
        crop="corn", crop_label="Corn for grain",
        label_scale="sad",
        geo="Southern Ontario Region 1 - Ontario",
        province_fallback_key="prov_on_corn",
        points=[{"name": "Chatham", "lat": 42.40, "lon": -82.19, "weight": 0.4},
                {"name": "London", "lat": 42.98, "lon": -81.25, "weight": 0.35},
                {"name": "Ridgetown", "lat": 42.44, "lon": -81.82, "weight": 0.25}],
        build=corn_features,
        feature_sets=sets(CORN_W, CORN_S),
        doc="Regions/북미_캐나다/온타리오_퀘벡/옥수수_겨울밀/옥수수_겨울밀_상세분석.md",
        caveat=LIT + " Schlenker EDD@29C + short-season GDD10.",
    ),
    RegionCrop(
        key="sad_on_corn_western",
        label="ON Western corn (Region 2)",
        label_ko="온타리오 서부 옥수수",
        crop="corn", crop_label="Corn for grain",
        label_scale="sad",
        geo="Western Ontario Region 2 - Ontario",
        province_fallback_key="prov_on_corn",
        points=[{"name": "Guelph", "lat": 43.54, "lon": -80.25, "weight": 0.5},
                {"name": "Stratford", "lat": 43.37, "lon": -80.98, "weight": 0.5}],
        build=corn_features,
        feature_sets=sets(CORN_W, CORN_S),
        doc="Regions/북미_캐나다/온타리오_퀘벡/옥수수_겨울밀/옥수수_겨울밀_상세분석.md",
        caveat=LIT,
    ),
]

# ========== Province fallbacks ==========
PROVINCE = [
    RegionCrop(
        key="prov_sk_canola", label="Saskatchewan canola (province)",
        label_ko="서스캐처원 카놀라(주)",
        crop="canola", crop_label="Canola (rapeseed)",
        sad_crop_label="Canola",
        label_scale="province", geo="Saskatchewan",
        points=[{"name": "Saskatoon", "lat": 52.13, "lon": -106.67, "weight": 0.25},
                {"name": "Regina", "lat": 50.45, "lon": -104.61, "weight": 0.25},
                {"name": "Yorkton", "lat": 51.21, "lon": -102.46, "weight": 0.25},
                {"name": "Swift Current", "lat": 50.29, "lon": -107.80, "weight": 0.25}],
        build=canola_features, feature_sets=sets(CANOLA_W, CANOLA_S),
        doc="Regions/북미_캐나다/프레리/카놀라_봄밀/캐나다_카놀라_봄밀_상세분석.md",
        caveat="Province fallback when SAD weather skill fails.",
    ),
    RegionCrop(
        key="prov_ab_canola", label="Alberta canola (province)",
        label_ko="앨버타 카놀라(주)",
        crop="canola", crop_label="Canola (rapeseed)",
        sad_crop_label="Canola",
        label_scale="province", geo="Alberta",
        points=[{"name": "Edmonton", "lat": 53.55, "lon": -113.49, "weight": 0.25},
                {"name": "Lethbridge", "lat": 49.69, "lon": -112.84, "weight": 0.25},
                {"name": "Red Deer", "lat": 52.27, "lon": -113.81, "weight": 0.25},
                {"name": "Grande Prairie", "lat": 55.17, "lon": -118.80, "weight": 0.25}],
        build=canola_features, feature_sets=sets(CANOLA_W, CANOLA_S),
        doc="Regions/북미_캐나다/서스캐처원_앨버타/카놀라_봄밀/카놀라_봄밀_상세분석.md",
        caveat="Province fallback.",
    ),
    RegionCrop(
        key="prov_sk_spring_wheat", label="Saskatchewan spring wheat (province)",
        label_ko="서스캐처원 봄밀(주)",
        crop="spring_wheat", crop_label="Wheat, spring",
        label_scale="province", geo="Saskatchewan",
        points=[{"name": "Saskatoon", "lat": 52.13, "lon": -106.67, "weight": 0.25},
                {"name": "Regina", "lat": 50.45, "lon": -104.61, "weight": 0.25},
                {"name": "Prince Albert", "lat": 53.20, "lon": -105.75, "weight": 0.25},
                {"name": "Moose Jaw", "lat": 50.39, "lon": -105.55, "weight": 0.25}],
        build=spring_wheat_features, feature_sets=sets(WHEAT_PK_W, WHEAT_PK_S),
        doc="Regions/북미_캐나다/프레리/카놀라_봄밀/캐나다_카놀라_봄밀_상세분석.md",
        caveat="Province fallback.",
    ),
    RegionCrop(
        key="prov_mb_soybeans", label="Manitoba soybeans (province)",
        label_ko="매니토바 대두(주)",
        crop="soybeans", crop_label="Soybeans",
        label_scale="province", geo="Manitoba",
        points=[{"name": "Winnipeg", "lat": 49.90, "lon": -97.14, "weight": 1 / 3},
                {"name": "Brandon", "lat": 49.85, "lon": -99.95, "weight": 1 / 3},
                {"name": "Portage la Prairie", "lat": 49.97, "lon": -98.29, "weight": 1 / 3}],
        build=soy_excess_features, feature_sets=sets(SOY_EX_W, SOY_EX_S),
        doc="Regions/북미_캐나다/매니토바/대두_귀리/대두_귀리_상세분석.md",
        caveat="Province fallback.", start_year=1995, min_train=15,
    ),
    RegionCrop(
        key="prov_mb_canola", label="Manitoba canola (province)",
        label_ko="매니토바 카놀라(주)",
        crop="canola", crop_label="Canola (rapeseed)",
        sad_crop_label="Canola",
        label_scale="province", geo="Manitoba",
        points=[{"name": "Brandon", "lat": 49.85, "lon": -99.95, "weight": 0.5},
                {"name": "Dauphin", "lat": 51.15, "lon": -100.05, "weight": 0.5}],
        build=canola_features, feature_sets=sets(PARKLAND_W, PARKLAND_S),
        doc="Regions/북미_캐나다/매니토바/대두_귀리/대두_귀리_상세분석.md",
        caveat="Province fallback for MB canola SAD.",
    ),
    RegionCrop(
        key="prov_on_corn", label="Ontario grain corn (province)",
        label_ko="온타리오 옥수수(주)",
        crop="corn", crop_label="Corn for grain",
        label_scale="province", geo="Ontario",
        points=[{"name": "London", "lat": 42.98, "lon": -81.25, "weight": 0.25},
                {"name": "Chatham", "lat": 42.40, "lon": -82.19, "weight": 0.25},
                {"name": "Guelph", "lat": 43.54, "lon": -80.25, "weight": 0.25},
                {"name": "Ottawa", "lat": 45.42, "lon": -75.70, "weight": 0.25}],
        build=corn_features, feature_sets=sets(CORN_W, CORN_S),
        doc="Regions/북미_캐나다/온타리오_퀘벡/옥수수_겨울밀/옥수수_겨울밀_상세분석.md",
        caveat="Province fallback.",
    ),
]

ALL = SAD + PROVINCE
BY_KEY = {cfg.key: cfg for cfg in ALL}
SAD_KEYS = [cfg.key for cfg in SAD]
PROVINCE_KEYS = [cfg.key for cfg in PROVINCE]
