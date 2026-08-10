"""ECTA production-weighted Ethiopian coffee climate geometry."""

BELT_KEY = "national_arabica_belt"

# Regional shares are the MY 2023/24-2025/26 three-year averages published by
# USDA/FAS from ECTA data. Rounded shares sum to 99.5%, so climate aggregation
# renormalizes them. Large regions use multiple locations while preserving the
# reported regional total.
POINTS = [
    {"region": "Oromia", "name": "Jimma", "lat": 7.667, "lon": 36.833, "weight": 0.595 / 3},
    {"region": "Oromia", "name": "Guji", "lat": 5.900, "lon": 38.650, "weight": 0.595 / 3},
    {"region": "Oromia", "name": "West Arsi", "lat": 7.200, "lon": 38.600, "weight": 0.595 / 3},
    {"region": "South-West Ethiopia", "name": "Kaffa", "lat": 7.270, "lon": 36.240, "weight": 0.137 / 2},
    {"region": "South-West Ethiopia", "name": "Bench Sheko", "lat": 6.990, "lon": 35.580, "weight": 0.137 / 2},
    {"region": "Sidama", "name": "Aleta Wondo", "lat": 6.600, "lon": 38.420, "weight": 0.129},
    {"region": "South Ethiopia", "name": "Yirgacheffe", "lat": 6.160, "lon": 38.210, "weight": 0.071},
    {"region": "Central Ethiopia", "name": "Hadiya", "lat": 7.560, "lon": 37.850, "weight": 0.037},
    {"region": "Gambella", "name": "Godere", "lat": 7.020, "lon": 35.180, "weight": 0.015},
    {"region": "Amhara", "name": "Awi", "lat": 10.950, "lon": 36.700, "weight": 0.011},
]

CLIMATE_FEATURES = [
    "rain_prev_aug_dec_mm",
    "rain_flowering_mar_may_mm",
    "rain_filling_jun_jul_mm",
    "hot30_mar_jul_c_days",
    "root_sm_mar_jul",
    "vpd_mar_jul_kpa",
]

STRUCTURAL_FEATURES = ["yield_lag2_kg_ha", "area_growth_lag2"]

FEATURE_SETS = {
    "cycle_only": STRUCTURAL_FEATURES,
    "rain_heat": ["rain_flowering_mar_may_mm", "hot30_mar_jul_c_days"],
    "water_demand": ["root_sm_mar_jul", "vpd_mar_jul_kpa"],
    "rain_heat_cycle": STRUCTURAL_FEATURES + ["rain_flowering_mar_may_mm", "hot30_mar_jul_c_days"],
    "water_cycle": STRUCTURAL_FEATURES + ["root_sm_mar_jul", "vpd_mar_jul_kpa"],
    "phase_cycle": STRUCTURAL_FEATURES + ["rain_prev_aug_dec_mm", "rain_flowering_mar_may_mm", "rain_filling_jun_jul_mm"],
}

FULL_FEATURE_SETS = {name: features for name, features in FEATURE_SETS.items() if name.endswith("_cycle") and name != "cycle_only"}
