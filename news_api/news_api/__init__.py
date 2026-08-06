"""news_api package root — climate/yield-independent news ranking helpers."""

from .tiers import (
    NewsTier,
    legacy_geo_letter_to_int,
    legacy_info_to_int,
    map_legacy_scored_fields,
)

__all__ = [
    "NewsTier",
    "legacy_geo_letter_to_int",
    "legacy_info_to_int",
    "map_legacy_scored_fields",
]
