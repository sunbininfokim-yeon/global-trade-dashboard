"""Real GDP growth (YoY, annual actuals only) from the World Bank API.

IMF WEO's NGDP_RPCH (the only real-GDP-growth series on IMF DataMapper) has
no actual/forecast flag and runs years into projections -- fine for
sovereign_fiscal.py's debt/interest, which happens to get a real cutoff for
free by intersecting against a shorter-running companion series, but GDP
growth has no such companion here. The World Bank's NY.GDP.MKTP.KD.ZG only
ever publishes years it has actually measured -- there is no equivalent
"projected" row to accidentally graft as if it were an actual, so it is
used here instead even though it is not the IMF vintage the rest of this
dashboard leans on.

No key, no custom User-Agent needed (unlike the IMF host, worldbank.org does
not block on that).
"""

from __future__ import annotations

import json
import urllib.request
from datetime import date, datetime, timezone
from typing import Any

WORLD_BANK_BASE = "https://api.worldbank.org/v2"
GDP_GROWTH_INDICATOR = "NY.GDP.MKTP.KD.ZG"

# Same 19-country roster the rest of macro_monitor covers. EMU resolves to
# the World Bank's "Euro area" aggregate (id XC) under this same ISO3-ish code.
MONITOR_COUNTRIES: tuple[str, ...] = (
    "USA", "KOR", "JPN", "CHN", "EMU", "ZAF", "SGP", "HKG", "RUS", "GBR",
    "CAN", "AUS", "CHE", "BRA", "VNM", "KAZ", "TWN", "IND", "ISR",
)


def _get_json(url: str, timeout: int = 30) -> Any:
    request = urllib.request.Request(url)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_gdp_growth(iso3: str, *, start_year: int = 2010) -> list[dict[str, Any]]:
    """Annual real GDP growth (%) observations, oldest first. Never invents a year."""
    end_year = date.today().year
    url = (
        f"{WORLD_BANK_BASE}/country/{iso3}/indicator/{GDP_GROWTH_INDICATOR}"
        f"?format=json&per_page=100&date={start_year}:{end_year}"
    )
    doc = _get_json(url)
    rows = doc[1] if isinstance(doc, list) and len(doc) > 1 and doc[1] else []
    observations = []
    for row in rows:
        value = row.get("value")
        year = row.get("date")
        if value is None or not year:
            continue  # World Bank returns a null row for years not yet published
        observations.append({"date": f"{year}-12-31", "value": round(float(value), 4)})
    observations.sort(key=lambda o: o["date"])
    return observations


def build_snapshot(*, countries: tuple[str, ...] = MONITOR_COUNTRIES) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "schema_version": "peer-gdp-v1",
        "source": {
            "indicator": GDP_GROWTH_INDICATOR,
            "provider": "World Bank",
            "api": f"{WORLD_BANK_BASE}/country/<iso3>/indicator/{GDP_GROWTH_INDICATOR}",
        },
        "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "countries": {},
    }
    for iso3 in countries:
        try:
            observations = fetch_gdp_growth(iso3)
        except Exception as exc:  # noqa: BLE001 -- one country's failure must not drop the rest
            snapshot["countries"][iso3] = {"status": "error", "error": str(exc), "observations": []}
            continue
        status = "ok" if observations else "unavailable"
        snapshot["countries"][iso3] = {"status": status, "observations": observations}
    return snapshot
