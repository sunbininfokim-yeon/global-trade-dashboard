"""Sovereign credit ratings from Wikipedia (S&P / Fitch / Moody's).

Antigravity suggestion validated: Trading Economics is Cloudflare-heavy;
Google SERP scraping is fragile. Wikipedia tables work with a normal UA.
"""

from __future__ import annotations

import io
import re
from typing import Any

# ISO3 → Wikipedia Country/Territory label(s), first hit wins
WIKI_NAMES: dict[str, list[str]] = {
    "USA": ["United States"],
    "KOR": ["South Korea"],
    "JPN": ["Japan"],
    "CHN": ["China"],
    "GBR": ["United Kingdom"],
    "CAN": ["Canada"],
    "AUS": ["Australia"],
    "CHE": ["Switzerland"],
    "BRA": ["Brazil"],
    "IND": ["India"],
    "ISR": ["Israel"],
    "VNM": ["Vietnam"],
    "ZAF": ["South Africa"],
    "SGP": ["Singapore"],
    "HKG": ["Hong Kong"],
    "TWN": ["Taiwan"],
    "KAZ": ["Kazakhstan"],
    "RUS": ["Russia"],
    "IDN": ["Indonesia"],
    # Eurozone pack: Germany as core AAA anchor (not a true EZ sovereign)
    "EMU": ["Germany"],
}

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_countries_by_credit_rating"
UA = "Mozilla/5.0 (compatible; macro-monitor/0.28; +research)"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def fetch_agency_tables() -> dict[str, Any]:
    """Return {agency: DataFrame-like rows} for S&P, Fitch, Moody's."""
    import pandas as pd
    import requests
    from bs4 import BeautifulSoup

    r = requests.get(WIKI_URL, headers={"User-Agent": UA}, timeout=45)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    tables = pd.read_html(io.StringIO(r.text))
    headings: list[str] = []
    for table in soup.select("table.wikitable"):
        prev = table.find_previous(["h2", "h3"])
        headings.append(_norm(prev.get_text(" ", strip=True)) if prev else "")
    out: dict[str, Any] = {}
    for i, heading in enumerate(headings[:3]):
        if i >= len(tables):
            break
        key = None
        h = heading.lower()
        if "standard" in h or "s&p" in h or "poor" in h:
            key = "S&P"
        elif "fitch" in h:
            key = "Fitch"
        elif "moody" in h:
            key = "Moody's"
        if not key:
            continue
        df = tables[i].copy()
        df.columns = [str(c) for c in df.columns]
        name_col = df.columns[0]
        df["_name"] = df[name_col].map(_norm)
        out[key] = df
    if len(out) < 3:
        raise RuntimeError(f"expected 3 agency tables, got {list(out)}")
    return out


def _lookup(df: Any, names: list[str]) -> dict[str, str] | None:
    for name in names:
        hit = df[df["_name"] == name]
        if hit.empty:
            hit = df[df["_name"].str.fullmatch(re.escape(name), case=False, na=False)]
        if hit.empty:
            continue
        row = hit.iloc[0]
        rating = _norm(row.get("Rating"))
        outlook = _norm(row.get("Outlook"))
        if not rating or rating.lower() == "nan":
            continue
        return {"rating": rating, "outlook": outlook}
    return None


def ratings_for_iso(iso3: str, tables: dict[str, Any] | None = None) -> dict[str, Any] | None:
    names = WIKI_NAMES.get(iso3)
    if not names:
        return None
    tables = tables or fetch_agency_tables()
    components = []
    display = None
    for agency, aid in (("S&P", "sp"), ("Moody's", "moodys"), ("Fitch", "fitch")):
        df = tables.get(agency)
        if df is None:
            continue
        hit = _lookup(df, names)
        if not hit:
            continue
        components.append(
            {
                "id": aid,
                "agency": agency,
                "label_ko": agency,
                "rating": hit["rating"],
                "outlook": hit["outlook"],
            }
        )
        if agency == "S&P":
            display = hit["rating"]
    if not components:
        return None
    return {
        "display": display or components[0]["rating"],
        "components": components,
        "source": "wikipedia:List_of_countries_by_credit_rating",
        "quality": "live_latest",
        "note_ko": "Wikipedia 집계(S&P·Moody's·Fitch). 공시 원문보다 지연·오기 가능.",
    }
