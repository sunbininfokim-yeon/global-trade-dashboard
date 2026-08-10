#!/usr/bin/env python3
"""Build a compact home-board chokepoint stress snapshot.

The input is the existing ``shipping_capacity_v1.json``.  The composite uses
the ``all.change_pct`` metric for every live chokepoint.  A negative index means
current seven-day capacity is below the preceding 28-day mean.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
APP_DIR = SCRIPT_DIR.parents[1]
DEFAULT_INPUT = APP_DIR / "public" / "data" / "shipping_capacity_v1.json"
DEFAULT_OUTPUT = APP_DIR / "public" / "data" / "chokepoint_stress_v1.json"


class ContractError(ValueError):
    """Raised when a shipping snapshot cannot support the composite."""


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ContractError(f"{field} must be finite")
    return number


def build_stress(snapshot: dict[str, Any], *, generated_at: str | None = None) -> dict[str, Any]:
    """Return the v1 arithmetic-mean composite from a shipping snapshot."""

    live = snapshot.get("chokepoints_live")
    if not isinstance(live, dict) or not live:
        raise ContractError("chokepoints_live must be a non-empty object")

    names = {
        row.get("id"): {"name_ko": row.get("name_ko"), "name_en": row.get("name_en")}
        for row in snapshot.get("chokepoints", [])
        if isinstance(row, dict) and row.get("id")
    }
    components: list[dict[str, Any]] = []
    for chokepoint_id in sorted(live):
        status = live[chokepoint_id]
        if not isinstance(status, dict):
            raise ContractError(f"chokepoints_live.{chokepoint_id} must be an object")
        metric = status.get("metrics", {}).get("all")
        if not isinstance(metric, dict):
            raise ContractError(f"chokepoints_live.{chokepoint_id}.metrics.all is required")
        change_pct = _finite_number(
            metric.get("change_pct"),
            f"chokepoints_live.{chokepoint_id}.metrics.all.change_pct",
        )
        latest_date = status.get("latest_date")
        if not isinstance(latest_date, str) or not latest_date:
            raise ContractError(f"chokepoints_live.{chokepoint_id}.latest_date is required")
        label = names.get(chokepoint_id, {})
        components.append(
            {
                "id": chokepoint_id,
                "name_ko": label.get("name_ko") or status.get("portname") or chokepoint_id,
                "name_en": label.get("name_en") or status.get("portname") or chokepoint_id,
                "as_of": latest_date,
                "change_pct": round(change_pct, 6),
                "current_7d_mean_dwt": round(
                    _finite_number(metric.get("current_7d_mean_dwt"), "current_7d_mean_dwt"), 6
                ),
                "prior_28d_mean_dwt": round(
                    _finite_number(metric.get("prior_28d_mean_dwt"), "prior_28d_mean_dwt"), 6
                ),
            }
        )

    worst = min(components, key=lambda row: row["change_pct"])
    index_pct = sum(row["change_pct"] for row in components) / len(components)
    dates = [row["as_of"] for row in components]
    return {
        "schema_version": "chokepoint-stress-v1",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "as_of": min(dates),
        "index_pct": round(index_pct, 6),
        "worst_id": worst["id"],
        "worst_change_pct": worst["change_pct"],
        "contributor_count": len(components),
        "method": "arithmetic_mean_of_chokepoints_live.metrics.all.change_pct",
        "interpretation": "Negative means 7-day capacity is below the preceding 28-day mean; this is a stress proxy, not proof of closure.",
        "freshness_note": "as_of is the oldest contributor date so mixed-date inputs cannot appear fresher than their least-recent component.",
        "source": {
            "dataset": "shipping_capacity_v1.json",
            "upstream": "IMF PortWatch Daily Chokepoints Data",
            "url": "https://portwatch.imf.org/",
        },
        "components": components,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    with args.input.open(encoding="utf-8") as handle:
        snapshot = json.load(handle)
    result = build_stress(snapshot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
