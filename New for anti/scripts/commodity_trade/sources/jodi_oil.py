"""JODI-Oil free CSV adapter (no Comtrade key required).

Downloads annual-but-monthly-grained primary/secondary CSVs from jodidata.org.
Maps ENERGY_PRODUCT + FLOW TOTEXPSB/TOTIMPSB → board commodity series.
"""

from __future__ import annotations

import csv
import io
import math
import json
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

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
    "TOTCRUDE": "crude_ngl_other",
    # Only the explicitly published source total is the petroleum-products
    # total. Subproducts are separate supplemental series, not substitutes.
    "TOTPRODS": "petroleum_products",
    "GASDIES": "gasoil_diesel",
    "MOTORGAS": "motor_gasoline",
    "JETKERO": "jet_kerosene",
    "RESFUEL": "residual_fuel_oil",
    "LPG": "lpg",
}


def product_scope(product: str) -> dict[str, Any]:
    crude = product == "CRUDEOIL"
    return {
        "product_code": product,
        "comparison_scope": f"JODI:{product}",
        "measurement_basis": "goods_net_mass",
        "hs_bridge": "2709" if crude else None,
        "hs_relation": "alias" if crude else "source_product_not_hs_equivalent",
        "scope_note": "JODI source product; not an exact HS basket" if not crude else "JODI crude source product",
    }


def _fetch(url: str, cache_dir: Path, timeout: int = 120) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    # primary/2025.csv and secondary/2025.csv must never share a cache.
    # Do not reuse the ambiguous legacy basename cache.
    name = sha256(url.encode()).hexdigest()[:20] + "-" + url.rstrip("/").split("/")[-1]
    dest = cache_dir / name
    complete = dest.with_suffix(dest.suffix + ".complete")
    if dest.exists() and complete.exists():
        try:
            stamp = json.loads(complete.read_text())
            if (stamp.get('url') == url and stamp.get('bytes') == dest.stat().st_size
                    and stamp.get('sha256') == sha256(dest.read_bytes()).hexdigest()):
                return dest
        except (OSError, ValueError, AttributeError):
            pass  # unverified legacy/truncated cache must be reacquired
    req = Request(url, headers={"User-Agent": "commodity-trade-jodi/1.0"})
    temporary = dest.with_suffix(dest.suffix + ".tmp")
    size = 0
    digest = sha256()
    with urlopen(req, timeout=timeout) as response, temporary.open("wb") as output:
        length = getattr(response, 'headers', {}).get('Content-Length')
        expected = int(length) if length is not None else None
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
            size += len(chunk)
            digest.update(chunk)
    if size == 0 or (expected is not None and size != expected):
        raise OSError('incomplete JODI download; previous completed snapshot preserved')
    temporary.replace(dest)
    complete.write_text(json.dumps({'url':url,'bytes':size,'sha256':digest.hexdigest()})+'\n', encoding="utf-8")
    return dest


def _parse_value(raw: str) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if s in ("", "-", "x", "X", "na", "NA"):
        return None
    try:
        value = float(s)
        return value if math.isfinite(value) and value >= 0 else None
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
    products = list(PRODUCT_TO_COMMODITY) if products is None else products
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
                    cid = PRODUCT_TO_COMMODITY.get(prod)
                    if not cid:
                        continue
                    iso2 = (row.get("REF_AREA") or "").strip().upper()
                    month = (row.get("TIME_PERIOD") or "").strip()  # YYYY-MM
                    if not iso2 or len(month) < 7:
                        continue
                    ctry = bucket.setdefault(cid, {}).setdefault(iso2, {})
                    prev = ctry.get(month)
                    # Prefer KTONS > KBBL within the same source product.
                    # Identical duplicates are harmless; conflicting ones fail.
                    rank = {u: i for i, u in enumerate(PREFERRED_UNITS)}
                    if prev is not None and unit == prev.get('unit') and prev['value'] != val:
                        raise ValueError(f'conflicting JODI product/month/unit: {prod}/{iso2}/{month}/{unit}')
                    if prev is None or rank.get(unit, 99) < rank.get(prev.get("unit"), 99):
                        ctry[month] = {
                            "value": val,
                            "unit": unit,
                            **product_scope(prod),
                            "flow": flow,
                            "source": "jodi_oil",
                            "code_system": "JODI",
                            "assessment_code": row.get("ASSESSMENT_CODE"),
                            "source_file_url": url,
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
                    **product_scope(months[m]["product_code"]),
                    "source": "jodi_oil",
                    "assessment_code": months[m].get("assessment_code"),
                    "source_file_url": months[m].get("source_file_url"),
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
        "note_ko": "JODI 원천 상품별 월별 수출. 석유제품 합계는 TOTPRODS만 사용하며 경유 등 하위품목을 합계로 대체하지 않음. TOTPRODS도 HS2710과 동일 범위는 아님. 단위는 KTONS 우선.",
    }
