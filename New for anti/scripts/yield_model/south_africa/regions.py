"""Production-belt geometry and pre-registered model choices."""

BELT_KEY = "commercial_maize_belt"

# Fixed recent production weights are used only to aggregate climate. They do
# not pretend that province-level historical yield labels exist. Province
# weights are the mean core-belt shares in the 2023-2025 CEC crops: Free State
# 52.0%, North West 17.7%, Mpumalanga 30.3%. Each province is represented by
# two non-identical production locations instead of one circular sample.
POINTS = [
    {
        "province": "Free State",
        "name": "Kroonstad",
        "lat": -27.65,
        "lon": 27.23,
        "weight": 0.260,
    },
    {
        "province": "Free State",
        "name": "Wesselsbron",
        "lat": -27.85,
        "lon": 26.37,
        "weight": 0.260,
    },
    {
        "province": "North West",
        "name": "Lichtenburg",
        "lat": -26.15,
        "lon": 26.16,
        "weight": 0.0885,
    },
    {
        "province": "North West",
        "name": "Schweizer-Reneke",
        "lat": -27.19,
        "lon": 25.33,
        "weight": 0.0885,
    },
    {
        "province": "Mpumalanga",
        "name": "Bethal",
        "lat": -26.46,
        "lon": 29.47,
        "weight": 0.1515,
    },
    {
        "province": "Mpumalanga",
        "name": "Standerton",
        "lat": -26.94,
        "lon": 29.24,
        "weight": 0.1515,
    },
]

RAW_FEATURES = [
    "rain_planting_mm",
    "rain_critical_mm",
    "edd29_critical_c_days",
    "root_sm_critical",
    "vpd_critical_kpa",
]

# Small, agronomically distinct ablations. Selection is made only by causal
# forward folds, never by in-sample fit.
FEATURE_SETS = {
    "rain_heat": ["rain_critical_mm_z", "edd29_critical_c_days_z"],
    "soil_heat": ["root_sm_critical_z", "edd29_critical_c_days_z"],
    "water_demand": ["root_sm_critical_z", "vpd_critical_kpa_z"],
    "phase_rain_heat": [
        "rain_planting_mm_z",
        "rain_critical_mm_z",
        "edd29_critical_c_days_z",
    ],
}

CRITICAL_WINDOW = ((1, 1), (2, 28))
