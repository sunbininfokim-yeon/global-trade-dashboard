"""Korean indicators from official statistics (KOSIS) instead of the fixture generator.

Same contract as us_public_series.py: every value is a published observation or arithmetic on one,
a series that cannot be read leaves the previous card, and nothing is estimated.

Exports are shown in won. The customs service publishes them in dollars, so the won figure is
dollars x the month's average KRW/USD (Federal Reserve H.10 via FRED, EXKOUS) -- a conversion, and the
card says so. A month whose average rate is not out yet is left out rather than filled.
"""

from __future__ import annotations

from typing import Any

from . import kosis
from . import us_public_series as ups
from .us_public_series import Points

# KOSIS table for each series: organisation id, table id, period type, and the NAMES of the
# classification value and item to take (names survive a re-coding of the table). None = not
# located yet; the wire script reports these as "not configured" instead of guessing.
KOSIS_TABLES: dict[str, dict[str, Any] | None] = {
    "cpi_yoy": {"org": "101", "tbl": "DT_1J22003", "prd_se": "M", "c1_nm": "총지수", "itm_nm": "전년동월비"},
    "core_cpi_yoy": {"org": "101", "tbl": "DT_1J22003", "prd_se": "M", "c1_nm": "농산물및석유류제외지수", "itm_nm": "전년동월비"},
    "ip_yoy": None,
    "export_usd": None,
    "gdp_yoy": None,
    "gdp_qoq": None,
}

_USD_UNITS = {"달러": 1.0, "천달러": 1e3, "백만달러": 1e6, "억달러": 1e8, "십억달러": 1e9}


def usd_multiplier(unit_nm: str) -> float:
    """Dollars per printed unit, from KOSIS's UNIT_NM. An unknown unit raises: guessing the unit
    of a money series is off by a factor of a thousand or a million."""
    key = "".join(str(unit_nm or "").split())
    if key not in _USD_UNITS:
        raise ValueError(f"unrecognised money unit {unit_nm!r}")
    return _USD_UNITS[key]


def export_krw_tn(usd_rows_unit: str, usd_points: Points, krw_per_usd: Points) -> Points:
    """Monthly exports in trillions of won: dollars x that month's average KRW per USD. Only months
    that have both an export figure and an average rate."""
    mult = usd_multiplier(usd_rows_unit)
    fx = dict(krw_per_usd)
    return [(d, v * mult * fx[d] / 1e12) for d, v in usd_points if d in fx]


def rename_indicator(country: dict[str, Any], old_id: str, new_id: str, patch: dict[str, Any]) -> bool:
    """Replace one indicator (and its chip and headline) by another id with a new definition -- the
    card changes what it is (a YoY rate -> an amount in won), not just its value."""
    changed = False
    for ind in country["indicators"]:
        if ind["id"] in (old_id, new_id):
            before = dict(ind)
            ind["id"] = new_id
            ind.update({k: v for k, v in patch.items() if k != "retrieved_at"})
            if ind != before:
                ind["retrieved_at"] = patch.get("retrieved_at")
                changed = True
    for chips in (country.get("categories") or {}).values():
        for chip in chips:
            if chip.get("id") in (old_id, new_id):
                chip["id"] = new_id
    for h in country.get("headlines") or []:
        if h.get("id") == old_id:
            h["id"] = new_id
    return changed
