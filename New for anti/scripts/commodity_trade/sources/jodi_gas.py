"""JODI-Gas free ZIP/CSV adapter — LNG exports (EXPLNG), no API key.

API discovery:
  GET https://api.publisher.jodidata.org/web/files/gas
  download https://www.jodidata.org/jodi-publisher/gas/{publicationId}/{filename}
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

PUBLISHER_API = "https://api.publisher.jodidata.org"
DOWNLOAD_BASE = "https://www.jodidata.org/jodi-publisher"

# Prefer mass if present, else volumetric M3, else energy TJ
PREFERRED_UNITS = ("KTONS", "M3", "TJ")

FLOW_LNG_EXPORT = "EXPLNG"
PRODUCT = "NATGAS"


def _get_json(url: str, timeout: int = 60) -> dict:
    req = Request(url, headers={"User-Agent": "commodity-trade-jodi-gas/1.0", "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def resolve_gas_csv_zip(cache_dir: Path, timeout: int = 120) -> dict[str, Any]:
    """Download GAS_world_NewFormat.zip (or first CSV format file) to cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    meta = _get_json(f"{PUBLISHER_API}/web/files/gas", timeout=timeout)
    pub_id = meta.get("publicationId")
    files = meta.get("files") or []
    target = None
    for f in files:
        if f.get("ignore"):
            continue
        name = f.get("filename") or ""
        fmt = (f.get("format") or "").upper()
        if fmt == "CSV" or name.lower().endswith(".zip") and "newformat" in name.lower():
            target = name
            break
    if not target:
        # fallback first non-ignored
        for f in files:
            if not f.get("ignore") and f.get("filename"):
                target = f["filename"]
                break
    if not target or pub_id is None:
        return {"available": False, "reason": "no gas file in publisher API", "meta": meta}

    url = f"{DOWNLOAD_BASE}/gas/{pub_id}/{target}"
    dest = cache_dir / target
    complete = dest.with_suffix(dest.suffix + ".complete")
    if not dest.exists() or not complete.exists() or dest.stat().st_size < 1000:
        req = Request(url, headers={"User-Agent": "commodity-trade-jodi-gas/1.0"})
        temporary = dest.with_suffix(dest.suffix + ".tmp")
        with urlopen(req, timeout=timeout) as response, temporary.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
        temporary.replace(dest)
        complete.write_text("complete\n", encoding="utf-8")
    return {
        "available": True,
        "publication_id": pub_id,
        "filename": target,
        "path": str(dest),
        "url": url,
        "bytes": dest.stat().st_size,
    }


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


def _iter_csv_rows(zip_path: Path):
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not names:
            return
        with z.open(names[0]) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
            yield from csv.DictReader(text)


def load_lng_export_series(*, cache_dir: Path) -> dict[str, Any]:
    """Monthly LNG export series: commodity lng → iso2 → points."""
    info = resolve_gas_csv_zip(cache_dir)
    if not info.get("available"):
        return {"available": False, "reason": info.get("reason"), "series": {"lng": {}}}

    zip_path = Path(info["path"])
    # iso2 -> month -> best unit row
    bucket: dict[str, dict[str, dict[str, Any]]] = {}
    rank = {u: i for i, u in enumerate(PREFERRED_UNITS)}

    for row in _iter_csv_rows(zip_path):
        if row.get("FLOW_BREAKDOWN") != FLOW_LNG_EXPORT:
            continue
        if (row.get("ENERGY_PRODUCT") or "") != PRODUCT:
            continue
        unit = row.get("UNIT_MEASURE") or ""
        if unit not in PREFERRED_UNITS:
            continue
        val = _parse_value(row.get("OBS_VALUE") or "")
        if val is None:
            continue
        iso2 = (row.get("REF_AREA") or "").strip().upper()
        month = (row.get("TIME_PERIOD") or "").strip()
        if not iso2 or len(month) < 7:
            continue
        month = month[:7]
        ctry = bucket.setdefault(iso2, {})
        prev = ctry.get(month)
        if prev is None or rank.get(unit, 99) < rank.get(prev.get("unit"), 99):
            ctry[month] = {
                "value": val,
                "unit": unit,
                "product_code": PRODUCT,
                "flow": FLOW_LNG_EXPORT,
                "source": "jodi_gas",
                "code_system": "JODI",
                "hs_bridge": "271111",
                "hs_relation": "alias",
                "note": "NATGAS EXPLNG is LNG export flow (not pipeline gas)",
            }

    series_lng: dict[str, list] = {}
    for iso2, months in bucket.items():
        pts = [
            {
                "month": m,
                "value": months[m]["value"],
                "unit": months[m]["unit"],
                "product_code": PRODUCT,
                "flow": FLOW_LNG_EXPORT,
                "source": "jodi_gas",
                "hs_bridge": "271111",
                "hs_relation": "alias",
            }
            for m in sorted(months.keys())
        ]
        series_lng[iso2] = pts

    return {
        "available": bool(series_lng),
        "source": "jodi_gas",
        "source_url": "https://www.jodidata.org/gas/database/data-downloads.aspx",
        "download": info,
        "flow": FLOW_LNG_EXPORT,
        "series": {"lng": series_lng},
        "note_ko": (
            "JODI-Gas EXPLNG(액화가스 수출). NATGAS≠파이프라인 전부 — EXPLNG만 LNG로 매핑. "
            "HS 271111 별칭. 단위 KTONS>M3>TJ 우선."
        ),
    }
