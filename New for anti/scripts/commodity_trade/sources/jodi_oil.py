"""JODI-Oil free CSV adapter (no Comtrade key required).

Downloads annual-but-monthly-grained primary/secondary CSVs from jodidata.org.
Maps ENERGY_PRODUCT + FLOW TOTEXPSB/TOTIMPSB → board commodity series.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from hs_match import resolve_commodity_id

JODI_BASE = "https://www.jodidata.org"
PRIMARY_URLS = {
    2025: f"{JODI_BASE}/_resources/files/downloads/oil-data/annual-csv/primary/2025.csv",
    2026: f"{JODI_BASE}/_resources/files/downloads/oil-data/annual-csv/primary/primaryyear2026.csv",
}
SECONDARY_URLS = {
    2025: f"{JODI_BASE}/_resources/files/downloads/oil-data/annual-csv/secondary/2025.csv",
    2026: f"{JODI_BASE}/_resources/files/downloads/oil-data/annual-csv/secondary/secondaryyear2026.csv",
}

# Prefer kbbl / ktons numeric when present; skip '-', 'x'
PREFERRED_UNITS = ("KTONS", "KBBL")  # CONVBBL is a conversion factor, not volume.

PRODUCT_TO_COMMODITY = {
    "CRUDEOIL": "crude_oil",
    "TOTCRUDE": "crude_oil",
    "GASDIES": "petroleum_products",
    "MOTORGAS": "petroleum_products",
    "JETKERO": "petroleum_products",
    "RESFUEL": "petroleum_products",
    "LPG": "petroleum_products",
}


def _fetch(url: str, cache_dir: Path, timeout: int = 120) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    name = url.rstrip("/").split("/")[-1]
    dest = cache_dir / name
    complete = dest.with_suffix(dest.suffix + ".complete")
    if dest.exists() and complete.exists() and dest.stat().st_size > 1000:
        return dest
    req = Request(url, headers={"User-Agent": "commodity-trade-jodi/1.0"})
    temporary = dest.with_suffix(dest.suffix + ".tmp")
    with urlopen(req, timeout=timeout) as response, temporary.open("wb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
    temporary.replace(dest)
    complete.write_text("complete\n", encoding="utf-8")
    return dest


def _parse_value(raw: str) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if s in ("", "-", "x", "X", "na", "NA"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_export_series(
    *,
    cache_dir: Path,
    years: list[int] | None = None,
    flow: str = "TOTEXPSB",
    products: list[str] | None = None,
) -> dict[str, Any]:
    """Return monthly export series keyed by commodity_id → country → [{month, value, unit}]."""
    years = years or [2025, 2026]
    products = products or list(PRODUCT_TO_COMMODITY.keys())
    # commodity -> iso2 -> month -> {value, unit, product, source}
    bucket: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    files_used = []

    url_maps = [PRIMARY_URLS, SECONDARY_URLS]
    for url_map in url_maps:
        for y in years:
            url = url_map.get(y)
            if not url:
                continue
            try:
                path = _fetch(url, cache_dir)
            except Exception as exc:
                files_used.append({"url": url, "error": str(exc)})
                continue
            files_used.append({"url": url, "path": str(path), "bytes": path.stat().st_size})
            with path.open(newline="", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("FLOW_BREAKDOWN") != flow:
                        continue
                    prod = row.get("ENERGY_PRODUCT") or ""
                    if prod not in products:
                        continue
                    unit = row.get("UNIT_MEASURE") or ""
                    if unit not in PREFERRED_UNITS:
                        continue
                    val = _parse_value(row.get("OBS_VALUE") or "")
                    if val is None:
                        continue
                    cid = PRODUCT_TO_COMMODITY.get(prod) or resolve_commodity_id(prod)
                    if not cid:
                        continue
                    iso2 = (row.get("REF_AREA") or "").strip().upper()
                    month = (row.get("TIME_PERIOD") or "").strip()  # YYYY-MM
                    if not iso2 or len(month) < 7:
                        continue
                    ctry = bucket.setdefault(cid, {}).setdefault(iso2, {})
                    prev = ctry.get(month)
                    # Prefer KTONS > KBBL; if same unit keep first
                    rank = {u: i for i, u in enumerate(PREFERRED_UNITS)}
                    if prev is None or rank.get(unit, 99) < rank.get(prev.get("unit"), 99):
                        ctry[month] = {
                            "value": val,
                            "unit": unit,
                            "product_code": prod,
                            "flow": flow,
                            "source": "jodi_oil",
                            "code_system": "JODI",
                            "hs_bridge": "2709" if cid == "crude_oil" else "2710",
                            "hs_relation": "alias",
                        }

    # flatten
    out_series: dict[str, Any] = {}
    for cid, countries in bucket.items():
        out_series[cid] = {}
        for iso2, months in countries.items():
            pts = [
                {
                    "month": m,
                    "value": months[m]["value"],
                    "unit": months[m]["unit"],
                    "product_code": months[m]["product_code"],
                    "source": "jodi_oil",
                    "hs_bridge": months[m]["hs_bridge"],
                    "hs_relation": months[m]["hs_relation"],
                }
                for m in sorted(months.keys())
            ]
            out_series[cid][iso2] = pts

    return {
        "available": bool(out_series),
        "source": "jodi_oil",
        "source_url": "https://www.jodidata.org/oil/database/data-downloads.aspx",
        "flow": flow,
        "files": files_used,
        "series": out_series,
        "note_ko": "JODI 월별 수출(TOTEXPSB). CRUDEOIL↔HS2709 별칭. 단위는 KTONS 우선.",
    }
