"""Brazil MDIC Comex Stat open CSV — monthly export kg by HS4 stem.

Source (no key):
  https://balanca.economia.gov.br/balanca/bd/comexstat-bd/ncm/EXP_{year}.csv
Layout: CO_ANO;CO_MES;CO_NCM;...;KG_LIQUIDO;VL_FOB

NCM 8-digit is a child of HS4/HS6 stems (hs_match parent/child).
"""

from __future__ import annotations

import csv
import math
import ssl
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from hs_match import hs_relation, normalize_hs

BASE = "https://balanca.economia.gov.br/balanca/bd/comexstat-bd/ncm/EXP_{year}.csv"

# HS4 stems we pull for minerals (and can extend)
STEM_TO_COMMODITY: dict[str, str] = {
    # minerals
    "2601": "iron_ore",
    "2602": "manganese",  # ore/concentrate only; not ferroalloys in HS72
    "2603": "copper",
    "2604": "nickel",
    "7501": "nickel_mattes",
    "7502": "nickel_unwrought",
    "2606": "bauxite",
    "7601": "aluminum",
    "2605": "cobalt",
    "2504": "graphite",
    "2611": "tungsten",
    "8101": "tungsten",
    "8110": "antimony",
    "2617": "antimony",
    # agri trade
    "1001": "wheat",
    "1003": "barley",
    "1005": "corn",
    "1006": "rice",
    "1201": "soybeans",
    "2304": "soybean_meal",
    "1507": "soybean_oil",  # optional extra; board may not list
    "1511": "palm_oil",
    "1512": "sunflowerseed_oil",
    "1701": "sugar",
    "5201": "cotton",
}


def _ssl_ctx():
    ctx = ssl.create_default_context()
    # gov.br intermediate chain incomplete in some sandboxes
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_year_csv(year: int, cache_dir: Path, timeout: int = 180) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / f"BRA_EXP_{year}.csv"
    if dest.exists() and dest.stat().st_size > 1_000_000:
        return dest
    url = BASE.format(year=year)
    req = Request(url, headers={"User-Agent": "commodity-trade-comexstat/1.0"})
    data = urlopen(req, timeout=timeout, context=_ssl_ctx()).read()
    dest.write_bytes(data)
    return dest


def _aggregate_file(path: Path) -> dict[str, dict[str, float | None]]:
    """commodity/form -> month -> kg sum, or None for incomplete mass.

    One missing source weight invalidates that form/month total; the original
    CSV remains in cache, rather than silently treating the row as zero.
    """
    monthly: dict[str, dict[str, float | None]] = defaultdict(lambda: defaultdict(float))
    incomplete: set[tuple[str, str]] = set()
    with path.open(newline="", encoding="latin-1", errors="replace") as f:
        sample = f.read(400)
        f.seek(0)
        delim = ";" if sample.count(";") >= sample.count(",") else ","
        reader = csv.DictReader(f, delimiter=delim)
        for row in reader:
            ncm = (row.get("CO_NCM") or "").strip()
            hs = normalize_hs(ncm)
            if len(hs) < 4:
                continue
            stem4 = hs[:4]
            cid = STEM_TO_COMMODITY.get(stem4)
            if not cid:
                continue
            # record hierarchy
            _ = hs_relation(stem4, hs)  # parent/child when len>4
            mes = (row.get("CO_MES") or "0").strip().zfill(2)
            ano = (row.get("CO_ANO") or "").strip()
            if not ano.isdigit() or len(ano) != 4 or not mes.isdigit() or not 1 <= int(mes) <= 12:
                continue
            month = f"{ano}-{mes}"
            raw = str(row.get("KG_LIQUIDO") or "").strip()
            try:
                kg = float(raw.replace(",", "."))
            except ValueError:
                incomplete.add((cid, month))
                continue
            if not math.isfinite(kg) or kg < 0:
                incomplete.add((cid, month))
                continue
            monthly[cid][month] += kg
    for cid, month in incomplete:
        monthly[cid][month] = None
    return monthly


def load_mineral_exports(
    *,
    cache_dir: Path,
    years: list[int] | None = None,
) -> dict[str, Any]:
    years = years or [2025, 2026]
    files = []
    merged: dict[str, dict[str, float | None]] = defaultdict(dict)
    for y in years:
        try:
            path = fetch_year_csv(y, cache_dir)
            files.append({"year": y, "path": str(path), "bytes": path.stat().st_size})
            part = _aggregate_file(path)
            for cid, months in part.items():
                for m, kg in months.items():
                    previous = merged[cid].get(m, 0.0)
                    merged[cid][m] = previous + kg if previous is not None and kg is not None else None
        except Exception as exc:
            files.append({"year": y, "error": str(exc)})

    series: dict[str, dict[str, list]] = {}
    incomplete_cells = []
    for cid, months in merged.items():
        stems = [s for s, c in STEM_TO_COMMODITY.items() if c == cid]
        incomplete_cells.extend({"commodity_id": cid, "month": m, "reason": "missing_or_invalid_source_mass"}
                                for m, kg in months.items() if kg is None)
        pts = [
            {
                "month": m,
                "value": months[m],
                "unit": "kg",
                "product_code": ",".join(stems),
                "source": "brazil_comexstat",
                "hs_bridge": stems[0] if len(stems) == 1 else None,
                "hs_relation": "child_ncm_to_hs4" if len(stems) == 1 else "mixed_hs_not_comparable",
                "measurement_basis": "goods_net_mass",
                "product_form": {"nickel": "ore_concentrate", "nickel_mattes": "matte_intermediate",
                                 "nickel_unwrought": "unwrought_metal"}.get(cid),
                "comparison_scope": "HS:" + ",".join(stems),
                "code_system": "NCM",
            }
            for m in sorted(months.keys()) if months[m] is not None
        ]
        if pts:
            series[cid] = {"BRA": pts}  # single reporter Brazil

    return {
        "available": bool(series),
        "source": "brazil_comexstat",
        "source_url": "https://www.gov.br/mdic/pt-br/assuntos/comercio-exterior/estatisticas/base-de-dados-bruta",
        "reporter": "BRA",
        "files": files,
        "incomplete_cells": incomplete_cells,
        "series": series,
        "note_ko": (
            "브라질 수출만. NCM 8자리→HS4 상위 버킷 합산(parent/child). "
            "철광·구리·니켈 등. Comtrade 대체. 단위 kg."
        ),
    }
