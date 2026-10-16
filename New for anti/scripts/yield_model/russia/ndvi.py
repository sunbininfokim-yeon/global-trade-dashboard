"""
MODIS NDVI at the Russian weather points.

Usage: python3 -m russia.ndvi [--full]

Same collector as argentina.ndvi (ORNL DAAC, MOD13Q1, keyless), pointed at
the South / Central Black Earth / Volga points. November through March are
not requested: snow cover makes winter NDVI meaningless, and no crop window
here falls in it.

Writes condition/ndvi_points.csv.
"""

import os

from argentina import ndvi as core
from .regions import ALL

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "condition", "ndvi_points.csv")
SKIP_MONTHS = (11, 12, 1, 2, 3)


def points():
    seen = {}
    for rc in ALL:
        for p in rc.points:
            seen.setdefault(p["name"], (p["lat"], p["lon"]))
    return seen


if __name__ == "__main__":
    core.main(points(), OUT, SKIP_MONTHS)
