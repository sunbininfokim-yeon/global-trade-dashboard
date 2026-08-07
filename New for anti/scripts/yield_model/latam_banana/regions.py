"""Belt sampling points for risk proxies (not yield labels)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import climate as C


@dataclass(frozen=True)
class Belt:
    key: str
    country: str
    label: str
    label_ko: str
    points: list
    build: Callable
    hurricane_prone: bool


ECUADOR = Belt(
    key="ecuador_coast_banana",
    country="ecuador",
    label="Ecuador coastal banana",
    label_ko="에콰도르 연안 바나나",
    points=[
        {"name": "Quevedo", "lat": -1.03, "lon": -79.45, "weight": 0.40},
        {"name": "Guayaquil", "lat": -2.17, "lon": -79.90, "weight": 0.30},
        {"name": "Machala", "lat": -3.26, "lon": -79.96, "weight": 0.30},
    ],
    build=C.ecuador_features,
    hurricane_prone=False,
)

GUATEMALA = Belt(
    key="guatemala_banana",
    country="guatemala",
    label="Guatemala banana",
    label_ko="과테말라 바나나",
    points=[
        {"name": "Puerto Barrios", "lat": 15.73, "lon": -88.59, "weight": 0.55},
        {"name": "Escuintla", "lat": 14.30, "lon": -90.79, "weight": 0.45},
    ],
    build=C.caribbean_features,
    hurricane_prone=True,
)

COSTA_RICA = Belt(
    key="costa_rica_banana",
    country="costa_rica",
    label="Costa Rica banana",
    label_ko="코스타리카 바나나",
    points=[
        {"name": "Limon", "lat": 9.99, "lon": -83.04, "weight": 0.70},
        {"name": "Sixaola", "lat": 9.51, "lon": -82.63, "weight": 0.30},
    ],
    build=C.caribbean_features,
    hurricane_prone=True,
)

HONDURAS = Belt(
    key="honduras_banana",
    country="honduras",
    label="Honduras banana",
    label_ko="온두라스 바나나",
    points=[
        {"name": "La Lima", "lat": 15.43, "lon": -87.92, "weight": 0.55},
        {"name": "El Progreso", "lat": 15.40, "lon": -87.80, "weight": 0.45},
    ],
    build=C.caribbean_features,
    hurricane_prone=True,
)

ALL = [ECUADOR, GUATEMALA, COSTA_RICA, HONDURAS]
BY_KEY = {b.key: b for b in ALL}
BY_COUNTRY: dict[str, list] = {}
for belt in ALL:
    BY_COUNTRY.setdefault(belt.country, []).append(belt)
