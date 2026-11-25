#!/usr/bin/env python3
"""Build public/data/oil_balance_v1.json: the world oil balance from EIA's STEO, OECD stocks, and a Brent
fair value from stocks (see oil_balance/model.py). Keyless.

    python3 build_oil_balance.py                   # current STEO + FRED Brent; archived history from the cache
    python3 build_oil_balance.py --rebuild-history # re-read the December STEO archives 2007-2022 into the cache

A read that fails leaves the previous file and exits 1.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "macro_monitor"))

from oil_balance import model as om  # noqa: E402
from oil_balance import steo  # noqa: E402

OUT = ROOT.parent.parent / "public" / "data" / "oil_balance_v1.json"
HISTORY = ROOT / "config" / "steo_history_v1.json"
REFERENCE = ROOT / "config" / "bank_views_v1.json"


def brent_monthly() -> tuple[dict[str, float], tuple[str, float]]:
    from macro_monitor import us_public_series as ups
    pts = ups.fetch_fred("DCOILBRENTEU")
    by: dict[str, list[float]] = {}
    for d, v in pts:
        by.setdefault(d[:7], []).append(v)
    return {k: sum(v) / len(v) for k, v in by.items()}, pts[-1]


def annual(series: dict[str, float], year: str) -> float | None:
    v = [x for m, x in series.items() if m.startswith(year)]
    return round(st.mean(v), 2) if len(v) == 12 else None


def build() -> dict:
    hist = json.loads(HISTORY.read_text(encoding="utf-8"))["series"]
    raw = steo.fetch(steo.CURRENT)
    cur = steo.parse(raw)
    vdate = steo.vintage_date(raw, False)
    first_fc = vdate[:7] if vdate else None          # STEO months from the release month on are forecast
    series = {}
    for f in steo.CODES.values():
        s = {k: v for k, v in hist.get(f, {}).items() if k < "2022-01"}
        s.update(cur.get(f, {}))
        series[f] = dict(sorted(s.items()))
    brent, last_day = brent_monthly()
    doc = om.days_of_cover(series["oecd_stocks_mb"], series["oecd_demand_mbd"])
    dev = om.deviation(doc)
    coef = om.fit(dev, brent)
    fv = om.fair_value(dev, coef)
    gaps = om.gap_stats(brent, fv, coef["from"], coef["to"])
    months = [m for m in sorted(dev) if m >= "2019-01"]
    recent = [(m, brent[m] - fv[m]) for m in sorted(fv) if m > coef["to"] and m in brent]
    if recent:
        top = max(recent, key=lambda x: x[1])
        gaps["since_fit"] = {"from": recent[0][0], "max_premium": round(top[1], 1), "max_premium_month": top[0],
                             "latest": round(recent[-1][1], 1), "latest_month": recent[-1][0],
                             "partial_month": recent[-1][0] == last_day[0][:7]}
    hist_last = max(m for m in brent if m in fv)
    path = [{"month": m, "forecast": bool(first_fc and m >= first_fc),
             "supply": round(series["world_supply_mbd"].get(m, float("nan")), 2),
             "demand": round(series["world_demand_mbd"].get(m, float("nan")), 2),
             "balance": round(series["world_supply_mbd"][m] - series["world_demand_mbd"][m], 2)
             if m in series["world_supply_mbd"] and m in series["world_demand_mbd"] else None,
             "oecd_stocks_mb": round(series["oecd_stocks_mb"][m], 1), "oecd_demand_mbd": round(series["oecd_demand_mbd"][m], 3),
             "days": round(doc[m], 2), "dev_days": round(dev[m], 2), "fair_value": round(fv[m], 2),
             "brent": round(brent[m], 2) if m in brent else None,
             "brent_eia": round(series["brent_steo"][m], 2) if m in series.get("brent_steo", {}) else None}
            for m in months]
    years = sorted({m[:4] for m in months if m >= "2024"})
    ann = [{"year": y, "fair_value": annual(fv, y), "brent": annual(brent, y),
            "brent_ytd": round(st.mean([v for m, v in brent.items() if m.startswith(y)]), 2) if any(m.startswith(y) for m in brent) else None,
            "brent_eia": annual(series.get("brent_steo", {}), y),
            "balance": annual({m: series["world_supply_mbd"][m] - series["world_demand_mbd"][m]
                               for m in series["world_supply_mbd"] if m in series["world_demand_mbd"]}, y),
            "supply": annual(series["world_supply_mbd"], y), "demand": annual(series["world_demand_mbd"], y)}
           for y in years]
    ref = json.loads(REFERENCE.read_text(encoding="utf-8")) if REFERENCE.exists() else {"views": []}
    return {
        "schema": "oil_balance_v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "steo": {"vintage": vdate, "first_forecast_month": first_fc, "url": "https://www.eia.gov/outlooks/steo/"},
        "brent_last": {"date": last_day[0], "value": last_day[1], "fair_value_month": round(fv.get(last_day[0][:7], float("nan")), 2)
                       if last_day[0][:7] in fv else None},
        "model": {**{k: round(v, 5) if isinstance(v, float) else v for k, v in coef.items()},
                  "per_day_pct": round((pow(2.718281828, coef["b"]) - 1) * 100, 2), "gaps": gaps,
                  "hist_last": hist_last},
        "path": path, "annual": ann, "bank_views": ref.get("views", []),
        "sources": ["EIA Short-Term Energy Outlook (STEO_m.xlsx, December archives 2007-2022)", "FRED DCOILBRENTEU"],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rebuild-history", action="store_true")
    a = ap.parse_args()
    if a.rebuild_history or not HISTORY.exists():
        HISTORY.write_text(json.dumps({"schema": "steo_history_v1", "note": "Year Y from the December Y+1 STEO archive.",
                                       "series": steo.history_from_archives()}, separators=(",", ":")) + "\n", encoding="utf-8")
    try:
        doc = build()
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED oil balance: {exc}", file=sys.stderr)
        return 1
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    m = doc["model"]
    print(f"oil balance: STEO {doc['steo']['vintage']}, fit {m['from']}..{m['to']} R2 {m['r2']:.2f}, "
          f"{m['per_day_pct']:+.1f}%/day; " + "; ".join(f"{y['year']} FV {y['fair_value']} EIA {y['brent_eia']}" for y in doc["annual"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
