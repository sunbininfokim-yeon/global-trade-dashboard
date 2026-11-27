#!/usr/bin/env python3
"""SOMA card: 'SOMA + TGA' tab and the duration rail; government interest card: 'GDP 대비' and '평균 금리' tabs;
national debt card: '듀레이션' (years) and '만기별 잔액' tabs.
See macro_monitor/us_fiscal_soma.py.

    python3 wire_soma_interest.py

Runs after wire_fed_balance_sheet.py and wire_ust_maturity.py (it reads what they build). Keyless. A source that
fails leaves the card's previous tab; exit status 1 names it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from macro_monitor import sovereign_fiscal as sf  # noqa: E402
from macro_monitor import us_fiscal_soma as fs  # noqa: E402
from macro_monitor import us_public_series as ups  # noqa: E402

DATA = ROOT.parent.parent / "public" / "data"
PACK = DATA / "macro_monitor_v1.json"
BS = DATA / "fed_balance_sheet_v1.json"


def put_panel(ind: dict, panel: dict | None) -> bool:
    if not panel:
        return False
    old = ind.get("panels") or []
    at = next((i for i, p in enumerate(old) if p.get("id") == panel["id"]), None)
    if at is not None and old[at] == panel:
        return False
    panels = [*old[:at], panel, *old[at + 1:]] if at is not None else [*old, panel]      # keep its place
    ind["panels"] = panels
    return True


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    usa = next(c for c in pack["countries"] if c["iso3"] == "USA")
    by = {i["id"]: i for i in usa["indicators"]}
    changed, errors = [], []

    soma = by.get("fed_ust_holdings")
    if soma:
        if BS.exists() and put_panel(soma, fs.soma_tga_panel(json.loads(BS.read_text(encoding="utf-8")))):
            changed.append("soma_tga")
        rail = fs.duration_rail(by.get("ust_debt_wam"))
        if rail and soma.get("duration_rail") != rail:
            soma["duration_rail"] = rail
            changed.append("duration_rail")

    debt = by.get("sovereign_debt")
    store = ROOT / "config" / "ust_mspd_wam_v1.json"
    if debt and store.exists():
        if put_panel(debt, fs.debt_duration_panel(json.loads(store.read_text(encoding="utf-8"))["months"])):
            changed.append("debt_duration")
        if put_panel(debt, fs.maturity_wall_copy(by.get("ust_debt_wam"))):
            changed.append("debt_maturity_wall")

    intr = by.get("sovereign_interest")
    if intr:
        try:
            panel = fs.interest_gdp_panel(sf._completed_us_fiscal_years(), ups.fetch_fred("GDP"), ups.fetch_fred("FYOIGDA188S"))
            if put_panel(intr, panel):
                changed.append("interest_gdp")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"interest/GDP: {exc}")
        try:
            if put_panel(intr, fs.avg_rate_panel(fs.fetch_avg_rates())):
                changed.append("avg_rate")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"average rate: {exc}")

    if changed:
        PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"SOMA / interest: changed {changed or 'none'}")
    for e in errors:
        print(f"  FAILED {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
