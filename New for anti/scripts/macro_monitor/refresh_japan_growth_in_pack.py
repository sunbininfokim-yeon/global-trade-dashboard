#!/usr/bin/env python3
"""Refresh Japan's 3 growth diagnostics in place, without rebuilding the pack.

macro_monitor_v1.json is no longer produced by one clean run of
build_macro_monitor.py -- CPI/PCE observed data, the Fed balance sheet stack,
the hedge-fund UST chip and the QE/QT history all live as separate wire_*.py
passes applied on top of the base engine's output, none of which the engine
itself knows how to reproduce. Rerunning the full builder would regenerate
Japan's numbers correctly and silently drop every one of those.

The engine's own attach function, _attach_japan_growth_indicators(), already
has the real logic (which official series feeds which indicator, how the
net-funding-demand components are split, what counts as this indicator's
source citation) -- but it silently no-ops on an id already present in by_id,
because its normal caller only ever runs it once per fresh build. This script
removes the three indicators before calling it, so the same real logic runs
again instead of being reimplemented by hand a second time (and drifting from
engine.py the next time that function changes).

Pair this with build_japan_growth_snapshot.py, which refreshes
config/japan_growth_v1.json from ESRI/BOJ; run that first, this second.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor.engine import _attach_japan_growth_indicators  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"
SPEC = ROOT / "config" / "series.spec.json"

TARGET_IDS = ("capex_gdp_ratio", "net_funding_demand", "gdp_gap")


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    specs = json.loads(SPEC.read_text(encoding="utf-8"))
    specs_by_id = {s["id"]: s for s in specs["series"]}

    jpn = next(c for c in pack["countries"] if c["iso3"] == "JPN")
    indicators = jpn["indicators"]
    by_id = {i["id"]: i for i in indicators}

    missing = [tid for tid in TARGET_IDS if tid not in by_id]
    if missing:
        print(f"refusing to refresh: {missing} not present yet -- run the initial graft first")
        return 1

    # A pre-existing 10y monthly axis to step-fill the fresh quarterly/annual
    # observations onto. Doesn't need to be the exact axis the engine would
    # generate today -- _official_observations_to_monthly just needs a
    # monotonic monthly grid, and reusing one already in the pack means this
    # script never has to reverse-engineer the engine's date generation.
    dates = by_id["capex_gdp_ratio"]["history"]["10y"]["dates"]

    old_positions = {tid: indicators.index(by_id[tid]) for tid in TARGET_IDS}
    for tid in TARGET_IDS:
        indicators.remove(by_id[tid])
        del by_id[tid]

    _attach_japan_growth_indicators(
        iso3="JPN", specs_by_id=specs_by_id, cfg_map={}, dates=dates,
        by_id=by_id, indicators=indicators,
    )

    rebuilt = [tid for tid in TARGET_IDS if tid in by_id]
    failed = [tid for tid in TARGET_IDS if tid not in by_id]
    if failed:
        print(f"WARNING: {failed} did not rebuild (source fetch likely failed) -- pack left untouched for these ids")

    # Put the rebuilt objects back at their original list position instead of
    # wherever _attach_japan_growth_indicators happened to append them, so the
    # card order in the UI doesn't shift on every refresh.
    for tid in rebuilt:
        indicators.remove(by_id[tid])
    for tid in sorted(rebuilt, key=lambda t: old_positions[t]):
        indicators.insert(old_positions[tid], by_id[tid])

    growth_chips = jpn.get("categories", {}).get("growth", [])
    chip_by_id = {c["id"]: c for c in growth_chips}
    for tid in rebuilt:
        chip = chip_by_id.get(tid)
        ind = by_id[tid]
        if chip:
            for k in ("value", "display", "asof", "data_status", "source"):
                chip[k] = ind.get(k)

    PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")

    print(f"refreshed {len(rebuilt)}/{len(TARGET_IDS)} Japan growth indicators in {PACK}")
    for tid in rebuilt:
        ind = by_id[tid]
        print(f"  {tid}: {ind['display']} (asof {ind['asof']}, retrieved {ind.get('retrieved_at')})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
