"""Uganda coffee-belt geometry and pre-registered feature choices.

The weights preserve USDA/FAS's approximate national species mix (85 percent
Robusta, 15 percent Arabica). They are not district production shares. Each
species share is split evenly across representative growing zones so the
national climate proxy does not collapse onto a single coordinate.
"""

BELT_KEY = "national_coffee_belt"

POINTS = [
    {"zone": "Central Robusta", "name": "Mukono", "lat": 0.354, "lon": 32.755, "weight": 0.2125, "species": "robusta"},
    {"zone": "Central Robusta", "name": "Luwero", "lat": 0.849, "lon": 32.473, "weight": 0.2125, "species": "robusta"},
    {"zone": "Southern Robusta", "name": "Masaka", "lat": -0.333, "lon": 31.734, "weight": 0.2125, "species": "robusta"},
    {"zone": "Western Robusta", "name": "Bushenyi", "lat": -0.541, "lon": 30.185, "weight": 0.2125, "species": "robusta"},
    {"zone": "Mount Elgon Arabica", "name": "Sironko", "lat": 1.230, "lon": 34.250, "weight": 0.0500, "species": "arabica"},
    {"zone": "Rwenzori Arabica", "name": "Kasese", "lat": 0.183, "lon": 30.083, "weight": 0.0500, "species": "arabica"},
    {"zone": "Northern Arabica", "name": "Zombo", "lat": 2.514, "lon": 30.909, "weight": 0.0500, "species": "arabica"},
]

RAW_FEATURES = [
    "rain_short_rains_mm",
    "rain_long_rains_mm",
    "rain_jun_jul_mm",
    "hot28_edd_c_days",
    "root_sm_long_rains",
    "vpd_long_rains_kpa",
]

# Selection is restricted to the development folds. Feature sets stay small
# because only about four decades of yield labels overlap the satellite era.
FEATURE_SETS = {
    "rain_heat": ["rain_long_rains_mm_z", "hot28_edd_c_days_z"],
    "water_demand": ["root_sm_long_rains_z", "vpd_long_rains_kpa_z"],
    "bimodal_rain": ["rain_short_rains_mm_z", "rain_long_rains_mm_z"],
    "phase_water": [
        "rain_short_rains_mm_z",
        "rain_long_rains_mm_z",
        "rain_jun_jul_mm_z",
    ],
}
