#!/usr/bin/env python3
"""Wire real NY Fed SOMA maturity-bucket holdings onto the deployed macro pack.

build_soma_maturity.py already fetches the real, CUSIP-level bucketed
holdings into public/data/soma_maturity_v1.json -- but nothing ever
connected that file to the fed_ust_le_1y/1_5y/5_10y/gt_10y indicators
themselves (still fixture_synth/demo) or to their derived sum,
fed_ust_holdings (engine.py only computes that composite once, when the
indicator doesn't exist yet, at full-build time -- a graft-only refresh
never re-derives it, so this script recomputes the sum itself whenever it
overlays new bucket data).

Does not rebuild macro_monitor_v1.json or touch any other indicator.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.engine import _official_observations_to_monthly  # noqa: E402
from macro_monitor.series import format_value  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"
SOMA = ROOT.parent.parent / "public" / "data" / "soma_maturity_v1.json"

BUCKET_INDICATOR_IDS = {
    "le_1y": "fed_ust_le_1y",
    "1_5y": "fed_ust_1_5y",
    "5_10y": "fed_ust_5_10y",
    "gt_10y": "fed_ust_gt_10y",
}


def _axis_from_indicator(ind: dict) -> dict[str, list[str]] | None:
    history = ind.get("history") or {}
    if not all(k in history and history[k].get("dates") for k in ("5y", "10y")):
        return None
    return {k: list(history[k]["dates"]) for k in ("5y", "10y")}


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    soma = json.loads(SOMA.read_text(encoding="utf-8"))
    retrieved_at = soma.get("retrieved_at")
    source_url = "https://markets.newyorkfed.org/api/soma/tsy/get/all/asof/<date>.json"

    usa = next((c for c in pack.get("countries") or [] if c.get("iso3") == "USA"), None)
    if usa is None:
        print("no USA country pack found")
        return 1
    by_id = {i["id"]: i for i in usa.get("indicators") or []}

    weekly_dates = soma.get("dates") or []
    bucket_values: dict[str, list[float | None]] = {b["id"]: b["values"] for b in soma.get("buckets") or []}
    if not weekly_dates or len(bucket_values) != 4:
        print("soma_maturity_v1.json missing dates or buckets -- nothing to wire")
        return 1

    wired: list[str] = []
    monthly_series: dict[str, list[float | None]] = {}
    axes: dict[str, list[str]] | None = None
    for soma_key, indicator_id in BUCKET_INDICATOR_IDS.items():
        ind = by_id.get(indicator_id)
        values = bucket_values.get(soma_key)
        if ind is None or values is None:
            continue
        this_axes = _axis_from_indicator(ind)
        if this_axes is None:
            continue
        axes = axes or this_axes
        observations = [
            {"date": d, "value": v} for d, v in zip(weekly_dates, values) if v is not None
        ]
        if not observations:
            continue
        latest = observations[-1]
        history: dict[str, dict] = {}
        for window, dates in this_axes.items():
            monthly = _official_observations_to_monthly(observations, dates, hold_after_latest=False)
            history[window] = {"dates": dates, "values": monthly}
            monthly_series.setdefault(window, {})[soma_key] = monthly

        ind["history"] = history
        ind["value"] = latest["value"]
        ind["display"] = format_value(latest["value"], ind.get("format") or "bn0")
        ind["change_1m_pct"] = None
        ind["change_1y_pct"] = None
        ind["asof"] = latest["date"]
        ind["observed_at"] = latest["date"]
        ind["retrieved_at"] = retrieved_at
        ind["source"] = "NY Fed SOMA holdings (public API)"
        ind["source_urls"] = [source_url]
        ind["quality"] = "live"
        ind["data_status"] = "live"
        wired.append(indicator_id)

    holdings = by_id.get("fed_ust_holdings")
    if holdings is not None and axes is not None and len(wired) == 4:
        combined_history: dict[str, dict] = {}
        for window, dates in axes.items():
            per_bucket = monthly_series.get(window, {})
            n = len(dates)
            totals: list[float | None] = []
            for i in range(n):
                parts = [per_bucket[k][i] for k in BUCKET_INDICATOR_IDS if per_bucket.get(k) and per_bucket[k][i] is not None]
                totals.append(round(sum(parts), 6) if parts else None)
            combined_history[window] = {"dates": dates, "values": totals}
        # The monthly grid's last point lags behind the true latest observation
        # until that month closes (same reason each bucket's own "value" is set
        # from latest["value"] directly, not history[...][-1]) -- summing the
        # buckets' own latest values here keeps the headline total and the
        # components list it's built from on the same as-of date.
        latest_total = round(sum(by_id[indicator_id]["value"] for indicator_id in BUCKET_INDICATOR_IDS.values()), 6)
        holdings["history"] = combined_history
        holdings["value"] = latest_total
        holdings["display"] = format_value(latest_total, holdings.get("format") or "bn0")
        holdings["change_1m_pct"] = None
        holdings["change_1y_pct"] = None
        holdings["asof"] = by_id[BUCKET_INDICATOR_IDS["le_1y"]]["asof"]
        holdings["observed_at"] = holdings["asof"]
        holdings["retrieved_at"] = retrieved_at
        holdings["components"] = [
            {
                "id": indicator_id,
                "label_ko": by_id[indicator_id]["label_ko"],
                "value": by_id[indicator_id]["value"],
                "display": by_id[indicator_id]["display"],
                "unit": by_id[indicator_id]["unit"],
            }
            for indicator_id in BUCKET_INDICATOR_IDS.values()
        ]
        holdings["source"] = "derived(NY Fed SOMA holdings)"
        holdings["source_urls"] = [source_url]
        holdings["quality"] = "live"
        holdings["data_status"] = "live"
        wired.append("fed_ust_holdings")

    PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"wired {len(wired)} indicators: {', '.join(wired)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
