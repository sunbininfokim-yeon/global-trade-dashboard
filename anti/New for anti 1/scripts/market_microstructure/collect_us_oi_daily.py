"""Daily US equity/ETF options OI snapshot archive (Cboe delayed CDN).

No historical vendor purchase required going forward — append one JSONL line/day.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fetch_cboe_public import fetch_cboe_options, fetch_vol_indices

ROOT = Path(__file__).resolve().parent
DEFAULT_SYMBOLS = ["MU", "NVDA", "AMD", "AMZN", "SOXL", "SMH", "AVGO", "TSM"]
ARCHIVE = ROOT / "../../public/data/us_oi_daily_archive.jsonl"


def snapshot_symbols(symbols: list[str] | None = None) -> dict[str, Any]:
    symbols = list(symbols or DEFAULT_SYMBOLS)
    names = []
    errors = []
    for sym in symbols:
        try:
            opt = fetch_cboe_options(sym)
            names.append(
                {
                    "symbol": sym,
                    "put_call_oi": opt.get("put_call_oi"),
                    "put_call_volume": opt.get("put_call_volume"),
                    "put_oi": opt.get("put_oi"),
                    "call_oi": opt.get("call_oi"),
                    "put_volume": opt.get("put_volume"),
                    "call_volume": opt.get("call_volume"),
                    "atm_call_iv": opt.get("atm_call_iv"),
                    "total_volume": opt.get("total_volume"),
                    "source": opt.get("source"),
                    "quality": opt.get("quality"),
                }
            )
        except Exception as e:  # noqa: BLE001
            errors.append(f"{sym}:{e}")
            names.append({"symbol": sym, "quality": "missing", "error": str(e)})
    vol = {}
    try:
        vol = fetch_vol_indices()
    except Exception as e:  # noqa: BLE001
        errors.append(f"vol:{e}")
    return {
        "schema_version": "us-oi-daily-v1",
        "as_of": datetime.now().astimezone().strftime("%Y-%m-%d"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "names": names,
        "vol_indices": vol,
        "errors": errors,
        "disclaimer_ko": "Cboe 지연 스냅샷 일별 적재. 투자 권유 아님.",
    }


def append_archive(snap: dict[str, Any], path: Path = ARCHIVE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # replace same-day line if re-run
    lines = []
    if path.exists():
        for ln in path.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                obj = json.loads(ln)
                if obj.get("as_of") == snap.get("as_of"):
                    continue
            except json.JSONDecodeError:
                continue
            lines.append(ln)
    lines.append(json.dumps(snap, ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def rule_based_kr_watch(snap: dict[str, Any], link_graph: dict[str, Any]) -> dict[str, Any]:
    """OI/volume rules → KR tickers via Tier A graph (no ML)."""
    by = {n["symbol"]: n for n in snap.get("names") or []}
    alerts = []
    for edge in link_graph.get("edges") or []:
        us = edge.get("us")
        kr = edge.get("kr")
        n = by.get(us) or {}
        if n.get("quality") != "observed":
            continue
        pc_oi = n.get("put_call_oi")
        pc_vol = n.get("put_call_volume")
        put_v = float(n.get("put_volume") or 0)
        call_v = float(n.get("call_volume") or 0)
        total = put_v + call_v
        level = None
        reasons = []
        if pc_vol is not None and pc_vol >= 1.5 and total >= 50_000:
            level = "경계"
            reasons.append(f"P/C vol={pc_vol:.2f} (≥1.5) vol={total:.0f}")
        elif pc_vol is not None and pc_vol >= 1.1 and total >= 30_000:
            level = "주의"
            reasons.append(f"P/C vol={pc_vol:.2f} (≥1.1)")
        elif pc_oi is not None and pc_oi >= 1.3:
            level = level or "주의"
            reasons.append(f"P/C OI={pc_oi:.2f} (≥1.3)")
        if pc_vol is not None and pc_vol <= 0.55 and call_v >= 40_000:
            # upside watch separate channel
            alerts.append(
                {
                    "channel": "upside",
                    "level": "주의",
                    "us": us,
                    "kr": kr,
                    "edge_type": edge.get("edge_type"),
                    "reasons": [f"call-heavy P/C vol={pc_vol:.2f}"],
                    "metrics": {"put_call_volume": pc_vol, "call_volume": call_v},
                }
            )
        if level:
            alerts.append(
                {
                    "channel": "downside",
                    "level": level,
                    "us": us,
                    "kr": kr,
                    "edge_type": edge.get("edge_type"),
                    "reasons": reasons,
                    "metrics": {
                        "put_call_oi": pc_oi,
                        "put_call_volume": pc_vol,
                        "put_oi": n.get("put_oi"),
                        "call_oi": n.get("call_oi"),
                    },
                }
            )

    # collapse by KR
    by_kr: dict[str, list] = {}
    for a in alerts:
        by_kr.setdefault(a["kr"], []).append(a)
    headline = "관찰"
    for a in alerts:
        if a["level"] == "경계" and a["channel"] == "downside":
            headline = "경계"
            break
        if a["level"] == "주의":
            headline = "주의"

    return {
        "schema_version": "us-oi-kr-rules-v1",
        "as_of": snap.get("as_of"),
        "headline_level": headline,
        "alerts": sorted(alerts, key=lambda x: (0 if x["level"] == "경계" else 1, x["kr"])),
        "by_kr": {k: v for k, v in by_kr.items()},
        "rule_ko": {
            "경계": "링크된 US 종목 P/C 거래량≥1.5 & 옵션거래≥5만",
            "주의": "P/C vol≥1.1 또는 P/C OI≥1.3",
            "관찰": "해당 없음",
        },
        "note_ko": "당일 OI/거래량 스냅샷 룰. 히스토리 학습 아님. 주체 특정 없음.",
    }
