"""
MODIS NDVI correction for the Canadian models: australia.ndvi with the
prairie and Ontario sites and season.

Usage: python3 -m canada.ndvi [--shard K --shards N --out FILE]
       python3 -m canada.ndvi merge FILE [FILE ...]
       python3 -m canada.ndvi backtest

Window fixed before any NDVI was read: July-August, flowering to grain fill
for canola, spring wheat, soybeans and corn alike ("half" is July). Many of
the weather points are cities, whose box would read roofs and parks, so
those move 15-30 km onto the surrounding cropland; small towns stay. Peace
River sits in its valley and moves up onto the plateau at Grimshaw.
"""

from australia import ndvi as N

WINDOW = ((7, 1), (8, 31))

SITES = {
    "Winnipeg": (49.80, -97.55),
    "Regina": (50.45, -104.95),
    "Saskatoon": (52.10, -106.35),
    "Edmonton": (53.30, -113.10),
    "Ottawa": (45.20, -75.80),
    "London": (42.90, -81.50),
    "Guelph": (43.65, -80.38),
    "Lethbridge": (49.80, -112.60),
    "Red Deer": (52.20, -113.60),
    "Brandon": (49.90, -100.20),
    "Moose Jaw": (50.30, -105.75),
    "Prince Albert": (53.05, -105.75),
    "Grande Prairie": (55.10, -118.55),
    "Swift Current": (50.20, -107.60),
    "Peace River": (56.20, -117.60),
}


def canada():
    from .regions import ALL
    return N.Country("canada", ALL, SITES, WINDOW)


if __name__ == "__main__":
    N.cli(canada())
