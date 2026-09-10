#!/usr/bin/env python3
"""Score the 3 Treasury criteria from Table 1 of the FX policy report, per country.

config/us_fx_watch_v1.json holds Table 1's numbers as published (July 2026
report, four quarters through December 2025) -- transcribed by hand from the
PDF, not fetched live, because Treasury does not publish this table as
structured data anywhere; the numbers only exist inside the report PDF.
This script does not touch those numbers; it only applies the report's own
published thresholds to decide which criteria each country meets, so that
logic lives in one place and stays auditable against the report text rather
than being duplicated by hand into 20 country records.

The FX intervention criterion needs care: Table 1's Yes/No column is whether
an economy intervened in at least 8 of the past 12 months, but the criterion
in the 2015 Act is that pattern *and* the purchases totaling at least 2% of
GDP -- both conditions, not either. Switzerland and Thailand both show "Yes"
in that column with net purchases at 0.6% and 1.8% of GDP respectively, well
under the 2% threshold, and Treasury's own summary (page 4) says both met
only one of the three criteria (their current-account and bilateral-surplus
criteria respectively) -- confirming persistence alone, without the
magnitude, does not satisfy this criterion. Checked against Treasury's
prose for all 10 Monitoring List economies before trusting this: it
reproduces the published "7 meet 2, 3 meet 1 (carried over)" split exactly.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "config" / "us_fx_watch_v1.json"
DEFAULT_OUT = ROOT.parent.parent / "public" / "data" / "us_fx_watch_v1.json"


def score(cfg: dict, row: dict) -> dict:
    th = cfg["thresholds"]
    bilateral_met = row["bilateral_surplus_usd_bn"] >= th["bilateral_surplus_usd_bn"]
    ca_met = row["ca_pct_gdp"] >= th["current_account_pct_gdp"]
    fx_met = bool(row["fx_persistent"]) and row["fx_pct_gdp"] >= th["fx_intervention_pct_gdp"]
    return {
        "trade_surplus_bn": {
            "met": bilateral_met,
            "value": row["bilateral_surplus_usd_bn"],
            "display": f"{row['bilateral_surplus_usd_bn']:+.0f}억 달러" if False else f"${row['bilateral_surplus_usd_bn']:.0f}B",
        },
        "current_account_pct_gdp": {
            "met": ca_met,
            "value": row["ca_pct_gdp"],
            "display": f"{row['ca_pct_gdp']:+.1f}%",
        },
        "fx_intervention_pct_gdp": {
            "met": fx_met,
            "value": row["fx_pct_gdp"],
            "display": (f"{row['fx_pct_gdp']:+.1f}% ({'8/12개월 지속' if row['fx_persistent'] else '지속성 미충족'})"),
        },
    }, sum([bilateral_met, ca_met, fx_met])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    monitoring = set(cfg["monitoring_list"])
    manipulators = set(cfg["manipulator_designations"])

    countries = {}
    for iso3, row in cfg["countries"].items():
        criteria, met_count = score(cfg, row)
        status = "manipulator" if iso3 in manipulators else ("monitoring" if iso3 in monitoring else "none")
        countries[iso3] = {
            "name_ko": row["name_ko"],
            "criteria": criteria,
            "criteria_met_count": met_count,
            "status": status,
            "note_ko": row.get("note_ko"),
        }
        # A country meeting 2+ criteria by the raw numbers this report but
        # absent from Treasury's published Monitoring List (or vice versa)
        # would mean either a transcription error above or a misunderstanding
        # of the carry-over rule -- either way, silently trusting the
        # mechanical count over Treasury's own published list would be wrong.
        if met_count >= 2 and status != "monitoring" and iso3 not in manipulators:
            print(f"WARNING: {iso3} meets {met_count}/3 criteria but is not on the published Monitoring List -- check config")

    doc = {
        "schema_version": "us-fx-watch-v1",
        "data_status": "official_snapshot",
        "source": cfg["report"]["title"] + " — " + cfg["report"]["edition"],
        "source_url": cfg["report"]["url"],
        "review_period": cfg["report"]["review_period"],
        "retrieved_at": cfg["report"]["retrieved_at"],
        "thresholds": cfg["thresholds"],
        "manipulator_designations": sorted(manipulators),
        "manipulator_note_ko": cfg["manipulator_note_ko"],
        "monitoring_list_note_ko": cfg["monitoring_list_note_ko"],
        "countries": countries,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                        encoding="utf-8")

    print(f"wrote {args.out}")
    print(f"  monitoring list ({len(monitoring)}): {sorted(monitoring)}")
    print(f"  manipulators ({len(manipulators)}): {sorted(manipulators) or 'none'}")
    for iso3 in sorted(countries):
        c = countries[iso3]
        print(f"  {iso3:<4} {c['name_ko']:<8} {c['criteria_met_count']}/3  {c['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
