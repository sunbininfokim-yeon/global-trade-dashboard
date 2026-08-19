"""BLS CPI release parsing and structure mapping."""

from .bls import build_cpi_structure, fetch_release_tables
from .api import build_cpi_api_history, fetch_series
from .official_sources import build_official_inflation_sources

__all__ = [
    "build_cpi_api_history",
    "build_cpi_structure",
    "build_official_inflation_sources",
    "fetch_release_tables",
    "fetch_series",
]
