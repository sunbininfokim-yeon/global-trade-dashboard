#!/usr/bin/env python3
"""Graft real GDP growth (gdp_yoy) onto the deployed macro pack.

Does not rebuild macro_monitor_v1.json or touch any other indicator --
overlays onto the gdp_yoy indicator that already exists in every country's
pack (currently fixture_synth/demo), the same graft-not-rebuild shape as
the other *_in_pack.py refreshers. A country whose fetch came back empty or
errored keeps its previous card untouched.
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
SNAPSHOT = ROOT / "config" / "peer_gdp_v1.json"


def _axis_from_indicator(ind: dict) -> dict[str, list[str]] | None:
    history = ind.get("history") or {}
    if not all(k in history and history[k].get("dates") for k in ("5y", "10y")):
        return None
    return {k: list(history[k]["dates"]) for k in ("5y", "10y")}


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    retrieved_at = snapshot.get("retrieved_at")
    source_url_tpl = "https://api.worldbank.org/v2/country/{iso3}/indicator/NY.GDP.MKTP.KD.ZG"

    refreshed: list[str] = []
    skipped: list[str] = []
    for country in pack.get("countries") or []:
        iso3 = country.get("iso3")
        row = (snapshot.get("countries") or {}).get(iso3) or {}
        observations = row.get("observations") or []
        if not observations:
            skipped.append(f"{iso3}:{row.get('status', 'no-data')}")
            continue

        ind = next((i for i in country.get("indicators") or [] if i.get("id") == "gdp_yoy"), None)
        if ind is None:
            skipped.append(f"{iso3}:no-indicator")
            continue

        # A country whose own pipeline (wire_*_public_series.py) already carries quarterly observed GDP
        # keeps it: the annual World Bank figure is the fallback, not an override. Before this check the
        # weekly run swapped those cards to annual data until the next daily wire put them back.
        if ind.get("data_status") == "live":
            skipped.append(f"{iso3}:has-quarterly")
            continue

        axes = _axis_from_indicator(ind)
        if axes is None:
            skipped.append(f"{iso3}:no-axis")
            continue

        latest = observations[-1]
        history: dict[str, dict] = {}
        for window, dates in axes.items():
            values = _official_observations_to_monthly(observations, dates, hold_after_latest=False)
            history[window] = {"dates": dates, "values": values}

        ind["history"] = history
        ind["value"] = latest["value"]
        ind["display"] = format_value(latest["value"], ind.get("format") or "pct1")
        ind["change_1m_pct"] = None
        ind["change_1y_pct"] = None
        ind["asof"] = latest["date"]
        ind["observed_at"] = latest["date"]
        ind["retrieved_at"] = retrieved_at
        ind["source"] = "World Bank NY.GDP.MKTP.KD.ZG"
        ind["source_urls"] = [source_url_tpl.format(iso3=iso3)]
        ind["quality"] = "engine"
        ind["data_status"] = "official_snapshot"
        ind["note_ko"] = "세계은행 실질GDP 성장률 연간 실측치만 표시합니다. 전망치는 포함하지 않습니다."
        refreshed.append(iso3)

    # The headline is a projection of the card, including for countries skipped above: it used to keep
    # the fixture's figure (Russia 3.5% over a 1.0% card).
    for country in pack.get("countries") or []:
        ind = next((i for i in country.get("indicators") or [] if i.get("id") == "gdp_yoy"), None)
        for h in country.get("headlines") or []:
            if ind and h.get("id") == "gdp_yoy":
                h["display"] = ind.get("display_chip") or ind.get("display")
                h["data_status"] = ind.get("data_status")
        # ... and so is the chip (it kept the fixture's demo badge over a World Bank card)
        for chips in (country.get("categories") or {}).values():
            for ch in chips:
                if ind and ch.get("id") == "gdp_yoy":
                    for k in ("display", "value", "asof", "observed_at", "source", "data_status"):
                        if k in ind:
                            ch[k] = ind.get("display_chip") if k == "display" and ind.get("display_chip") else ind[k]

    PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"refreshed gdp_yoy for {len(refreshed)} countries: {', '.join(refreshed)}")
    if skipped:
        print(f"skipped {len(skipped)}: {', '.join(skipped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
