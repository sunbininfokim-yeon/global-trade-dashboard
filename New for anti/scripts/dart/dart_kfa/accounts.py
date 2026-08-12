"""L1 — map DART fnltt rows onto a standard account tree."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

_AMOUNT_KEYS = (
    "thstrm_amount",
    "frmtrm_amount",
    "bfefrmtrm_amount",
)


def load_accounts_map(path: Path | None = None) -> dict[str, Any]:
    p = path or (CONFIG_DIR / "accounts.map.json")
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKC", name or "")
    text = text.replace(" ", "").replace("\u3000", "")
    text = text.lower()
    text = re.sub(r"[()（）\[\]【】·・․./_\-]", "", text)
    return text


def _parse_amount(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip().replace(",", "")
    if not s or s in {"-", "—", "–"}:
        return None
    # DART sometimes prefixes losses with parentheses
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    try:
        value = float(s)
    except ValueError:
        return None
    return -value if neg else value


def _currency_unit(row: dict[str, Any]) -> str:
    raw = (row.get("currency") or row.get("currency_unit") or "KRW").strip().upper()
    return raw or "KRW"


def _scale_hint(row: dict[str, Any]) -> str:
    """Return declared unit label if present (원/천원/백만원)."""
    for key in ("currency", "currency_unit", "unit"):
        val = row.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return "원"


def index_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_id: dict[str, list[dict[str, Any]]] = {}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        aid = (row.get("account_id") or "").strip()
        if aid:
            by_id.setdefault(aid, []).append(row)
        nm = normalize_name(row.get("account_nm") or "")
        if nm:
            by_name.setdefault(nm, []).append(row)
    return {"by_id": by_id, "by_name": by_name}


def _pick_row(
    account_spec: dict[str, Any],
    index: dict[str, list[dict[str, Any]]],
    sj_filter: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return (row, match_method). Prefer exact account_id, then name."""
    sj = account_spec.get("sj")
    wanted_sj = sj_filter or sj

    def sj_ok(row: dict[str, Any]) -> bool:
        if not wanted_sj:
            return True
        return (row.get("sj_div") or "").upper() == wanted_sj.upper()

    for aid in account_spec.get("ids") or []:
        for row in index["by_id"].get(aid, []):
            if sj_ok(row):
                return row, f"id:{aid}"

    for name in account_spec.get("names") or []:
        key = normalize_name(name)
        for row in index["by_name"].get(key, []):
            if sj_ok(row):
                return row, f"name:{name}"

    return None, None


def resolve_accounts(
    rows: list[dict[str, Any]],
    accounts_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve standard accounts for thstrm / frmtrm / bfefrmtrm."""
    amap = accounts_map or load_accounts_map()
    specs: dict[str, Any] = amap.get("accounts") or {}
    index = index_rows(rows)

    resolved: dict[str, Any] = {}
    for key, spec in specs.items():
        row, method = _pick_row(spec, index, spec.get("sj"))
        if row is None:
            resolved[key] = {
                "value": None,
                "prior": None,
                "prior2": None,
                "reason": "missing",
                "match": None,
                "account_nm": None,
                "account_id": None,
                "unit": None,
            }
            continue
        th = _parse_amount(row.get("thstrm_amount"))
        fr = _parse_amount(row.get("frmtrm_amount"))
        bf = _parse_amount(row.get("bfefrmtrm_amount"))
        resolved[key] = {
            "value": th,
            "prior": fr,
            "prior2": bf,
            "reason": None if th is not None else "missing_amount",
            "match": method,
            "account_nm": row.get("account_nm"),
            "account_id": row.get("account_id"),
            "unit": _scale_hint(row),
            "currency": _currency_unit(row),
        }
    return resolved


def amounts_only(resolved: dict[str, Any], which: str = "value") -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for key, meta in resolved.items():
        out[key] = meta.get(which)
    return out
