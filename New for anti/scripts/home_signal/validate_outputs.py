#!/usr/bin/env python3
"""Validate the four public home-signal JSON contracts.

Full JSON Schema validation is used when ``jsonschema`` is installed.  A
dependency-free contract check covers the required production invariants on a
clean checkout.
"""

from __future__ import annotations

import json
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
APP_DIR = SCRIPT_DIR.parents[1]
PAIRS = (
    ("chokepoint_stress_v1.json", "chokepoint_stress_v1.schema.json"),
    ("home_signal_series_v1.json", "home_signal_series_v1.schema.json"),
    ("kospi_risk_slot_v1.json", "kospi_risk_slot_v1.schema.json"),
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _fallback_validate(name: str, data: dict) -> None:
    if name == "chokepoint_stress_v1.json":
        _require(data.get("schema_version") == "chokepoint-stress-v1", "bad stress version")
        components = data.get("components")
        _require(isinstance(components, list) and components, "stress components required")
        _require(data.get("contributor_count") == len(components), "stress contributor count mismatch")
        changes = [row.get("change_pct") for row in components]
        _require(all(isinstance(value, (int, float)) for value in changes), "invalid stress change")
        expected = round(sum(changes) / len(changes), 6)
        _require(data.get("index_pct") == expected, "stress arithmetic mean mismatch")
        worst = min(components, key=lambda row: row["change_pct"])
        _require(data.get("worst_id") == worst.get("id"), "stress worst_id mismatch")
        _require(data.get("as_of") == min(row["as_of"] for row in components), "stress as_of mismatch")
        return

    if name == "home_signal_series_v1.json":
        _require(data.get("schema_version") == "home-signal-series-v1", "bad manifest version")
        pages = data.get("pages")
        _require(isinstance(pages, dict) and set(pages) == set("ABCDE"), "manifest pages must be A-E")
        ids = []
        for page_id, page in pages.items():
            slots = page.get("slots") if isinstance(page, dict) else None
            _require(isinstance(slots, list) and len(slots) == 4, f"page {page_id} needs four slots")
            for slot in slots:
                _require(all(slot.get(key) for key in ("id", "label_ko", "source", "series_id", "unit", "cadence", "availability")), f"incomplete slot on page {page_id}")
                ids.append(slot["id"])
        _require(len(ids) == len(set(ids)), "manifest slot ids must be unique")
        return

    if name == "kospi_risk_slot_v1.json":
        _require(data.get("schema_version") == "kospi-risk-slot-v1", "bad KOSPI slot version")
        _require(data.get("status") == "pending_derivatives", "KOSPI slot must stay pending")
        _require("score" not in data and "as_of" not in data, "pending KOSPI slot cannot carry data fields")
        _require(data.get("display_ko") == "분석 예정", "bad KOSPI placeholder")
        return

    raise ValueError(f"no fallback validator for {name}")


def main() -> None:
    try:
        import jsonschema
    except ImportError:  # pragma: no cover - depends on local environment
        jsonschema = None

    for data_name, schema_name in PAIRS:
        data_path = APP_DIR / "public" / "data" / data_name
        schema_path = SCRIPT_DIR / "schemas" / schema_name
        with data_path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if jsonschema is not None:
            with schema_path.open(encoding="utf-8") as handle:
                schema = json.load(handle)
            jsonschema.validate(data, schema, format_checker=jsonschema.FormatChecker())
            mode = "jsonschema"
        else:
            _fallback_validate(data_name, data)
            mode = "built-in contract"
        print(f"ok {data_path} ({mode})")


if __name__ == "__main__":
    main()
