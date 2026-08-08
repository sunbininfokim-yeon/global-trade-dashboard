"""Peer benchmarks (BOK FSA) + qualitative industry background."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def load_bok_peers(path: Path | None = None) -> dict[str, Any]:
    p = path or (CONFIG_DIR / "bok_peer_benchmarks.json")
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def load_industry_background(path: Path | None = None) -> dict[str, Any]:
    p = path or (CONFIG_DIR / "industry_background.json")
    if not p.exists():
        return {"kits": {}}
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def _kit_ksic_candidates(kit: dict[str, Any], corp: dict[str, Any] | None) -> list[str]:
    cands: list[str] = []
    industry = str((corp or {}).get("industry") or "")
    if industry:
        cands.append(industry)
        # also try without letter quirks
        if len(industry) >= 3:
            cands.append(industry[:3] if industry[0].isalpha() else industry)
            cands.append(industry[:4] if industry[0].isalpha() and len(industry) >= 4 else industry[:3])
    for p in kit.get("ksic_prefixes") or []:
        cands.append(str(p))
    # unique preserve order
    seen = set()
    out = []
    for c in cands:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def resolve_peer_row(
    *,
    kit: dict[str, Any],
    corp: dict[str, Any] | None,
    peers_doc: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    doc = peers_doc or load_bok_peers()
    by = doc.get("by_ksic") or {}
    best = None
    best_len = -1
    for code in _kit_ksic_candidates(kit, corp):
        # longest matching key where code startswith key or key startswith code
        for ksic, row in by.items():
            if code.startswith(ksic) or ksic.startswith(code):
                if len(ksic) > best_len:
                    best = dict(row)
                    best["matched_ksic"] = ksic
                    best_len = len(ksic)
        if code in by and len(code) > best_len:
            best = dict(by[code])
            best["matched_ksic"] = code
            best_len = len(code)
    return best


# Map our metric ids → BOK peer fields
_METRIC_PEER_FIELD = {
    "current_ratio": ("current_ratio", "higher_better"),
    "debt_ratio": ("debt_ratio", "lower_better"),
    "net_margin": ("net_margin", "higher_better"),
    "asset_turnover": ("asset_turnover", "higher_better"),
    "roe": None,  # no direct BOK field in this snapshot
    "operating_margin": None,  # not in table; see net_margin
}


def compare_to_peers(
    metrics: dict[str, Any],
    peer_row: dict[str, Any] | None,
) -> dict[str, Any]:
    if not peer_row:
        return {"available": False, "reason": "no_bok_peer_row"}

    comps: dict[str, Any] = {}
    for mid, spec in _METRIC_PEER_FIELD.items():
        if spec is None:
            continue
        field, polarity = spec
        firm = (metrics.get(mid) or {}).get("value")
        peer = peer_row.get(field)
        if firm is None or peer is None:
            comps[mid] = {
                "firm": firm,
                "peer_avg": peer,
                "delta": None,
                "vs_peer": None,
                "reason": "missing_firm_or_peer",
            }
            continue
        delta = float(firm) - float(peer)
        if polarity == "higher_better":
            vs = "above_peer" if delta > 0 else ("below_peer" if delta < 0 else "at_peer")
        else:
            vs = "below_peer_better" if delta < 0 else ("above_peer_worse" if delta > 0 else "at_peer")
        comps[mid] = {
            "firm": round(float(firm), 4),
            "peer_avg": peer,
            "delta": round(delta, 4),
            "vs_peer": vs,
            "polarity": polarity,
            "unit": (metrics.get(mid) or {}).get("unit"),
        }

    # soft hint: operating margin vs peer net margin (different definitions!)
    om = (metrics.get("operating_margin") or {}).get("value")
    if om is not None and peer_row.get("net_margin") is not None:
        comps["operating_margin_vs_peer_net_margin"] = {
            "firm_operating_margin": om,
            "peer_net_margin": peer_row["net_margin"],
            "note_ko": "한은 표는 매출액순이익률만 제공. 영업이익률과 직접 동일하지 않음.",
        }

    return {
        "available": True,
        "matched_ksic": peer_row.get("matched_ksic") or peer_row.get("ksic"),
        "peer_label_ko": peer_row.get("label_ko"),
        "metrics": comps,
    }


def background_for_kit(kit_id: str) -> dict[str, Any]:
    doc = load_industry_background()
    return (doc.get("kits") or {}).get(kit_id) or {}
