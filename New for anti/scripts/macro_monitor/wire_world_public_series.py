#!/usr/bin/env python3
"""Replace fixture cards with observed series for the countries in world_public_series.py's family:
each <iso>_public_series.py module lists CARDS (and GDP_SOURCE when it carries real GDP).

    python3 wire_world_public_series.py            # all
    python3 wire_world_public_series.py CAN GBR    # some

Keyless. Idempotent: a series that cannot be read keeps its previous card, the pack is rewritten only
when something changed, and exit status 1 lists the failures.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import us_public_series as ups  # noqa: E402
from macro_monitor.world_public_series import Fetch, run_country  # noqa: E402

PACK = ROOT.parent.parent / "public" / "data" / "macro_monitor_v1.json"
MODULES = {"CAN": "can", "GBR": "gbr", "EMU": "emu", "BRA": "bra", "ISR": "isr", "IND": "ind", "CHN": "chn",
           "KAZ": "kaz", "VNM": "vnm", "JPN": "jpn_world", "RUS": "rus_world"}


def main(argv: list[str]) -> int:
    wanted = [a.upper() for a in argv] or list(MODULES)
    text = PACK.read_text(encoding="utf-8")
    pack = json.loads(text)
    by_iso = {c["iso3"]: c for c in pack["countries"]}
    fetch, retrieved, failures = Fetch(), ups.now_iso(), []
    for iso in wanted:
        try:
            mod = importlib.import_module(f"macro_monitor.{MODULES[iso]}_public_series")
        except ModuleNotFoundError:
            continue
        result, patches, fails = run_country(by_iso[iso], mod.CARDS, fetch, retrieved_at=retrieved,
                                             gdp_source=getattr(mod, "GDP_SOURCE", None))
        failures += fails
        print(f"{iso}: {len(patches)}/{len(mod.CARDS)} read, changed {len(result['changed'])}")
        for sid, p in patches.items():
            print(f"  {sid:22s} {p['display']:>12s}  {p['reference_period']}  (as of {p['asof']})")
    out = json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if out != text:
        PACK.write_text(out, encoding="utf-8")
    for f in failures:
        print(f"  FAILED {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
