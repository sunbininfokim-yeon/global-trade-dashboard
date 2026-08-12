#!/usr/bin/env python3
"""Extract Ember yearly electricity totals + fuel mix → config/electricity_ember_v1.json.

Source (CC-BY-4.0): https://ember-energy.org/data/yearly-electricity-data/
CSV: files.ember-energy.org/.../release_generation_yearly_global.csv

Usage:
  curl -fsSL -o cache/ember/release_generation_yearly_global.csv \\
    https://files.ember-energy.org/public-downloads/generation/outputs/release_generation_yearly_global.csv
  python3 tools/extract_ember_electricity.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "cache" / "ember" / "release_generation_yearly_global.csv"
OUT_PATH = ROOT / "config" / "electricity_ember_v1.json"

# Monitor iso3 → Ember Area (Country or economy / Region)
ENTITY = {
    "USA": ("United States", "Country or economy"),
    "KOR": ("South Korea", "Country or economy"),
    "JPN": ("Japan", "Country or economy"),
    "CHN": ("China", "Country or economy"),
    "EMU": ("EU", "Region"),  # eurozone proxy — EU27 generation
    "GBR": ("United Kingdom", "Country or economy"),
    "CAN": ("Canada", "Country or economy"),
    "AUS": ("Australia", "Country or economy"),
    "CHE": ("Switzerland", "Country or economy"),
    "BRA": ("Brazil", "Country or economy"),
    "ZAF": ("South Africa", "Country or economy"),
    "SGP": ("Singapore", "Country or economy"),
    "HKG": ("Hong Kong (SAR of China)", "Country or economy"),
    "RUS": ("Russia", "Country or economy"),
    "IND": ("India", "Country or economy"),
    "TWN": ("Taiwan (China)", "Country or economy"),
    "VNM": ("Viet Nam", "Country or economy"),
    "KAZ": ("Kazakhstan", "Country or economy"),
    "ISR": ("Israel", "Country or economy"),
}

# Fuel-level mix (exclude aggregates / net imports)
FUELS = [
    ("Coal", "coal", "석탄"),
    ("Gas", "gas", "가스"),
    ("Nuclear", "nuclear", "원자력"),
    ("Hydro", "hydro", "수력"),
    ("Wind", "wind", "풍력"),
    ("Solar", "solar", "태양광"),
    ("Bioenergy", "bioenergy", "바이오"),
    ("Other renewables", "other_renewables", "기타재생"),
    ("Other fossil", "other_fossil", "기타화석"),
]


def _f(x: str | None) -> float | None:
    if x is None or x == "":
        return None
    try:
        return float(x)
    except ValueError:
        return None


def main() -> int:
    if not CSV_PATH.is_file():
        print(f"missing {CSV_PATH}", file=sys.stderr)
        print("download release_generation_yearly_global.csv first", file=sys.stderr)
        return 1

    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    by_area: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        key = (r["Area"], r["Area type"])
        by_area.setdefault(key, []).append(r)

    countries: dict[str, dict] = {}
    for iso3, (area, atype) in ENTITY.items():
        subset = by_area.get((area, atype)) or []
        if not subset:
            print(f"WARN no rows for {iso3} {area}", file=sys.stderr)
            continue

        totals: dict[int, float] = {}
        mix_by_year: dict[int, dict[str, dict]] = {}
        for r in subset:
            y = int(r["Year"])
            src = r["Electricity source"]
            gen = _f(r["Generation (TWh)"])
            share = _f(r["Share of generation (%)"])
            if src == "Total generation" and gen is not None:
                totals[y] = gen
            for ember_name, sid, label_ko in FUELS:
                if src == ember_name:
                    mix_by_year.setdefault(y, {})[sid] = {
                        "id": sid,
                        "label_ko": label_ko,
                        "label_en": ember_name,
                        "twh": gen,
                        "share_pct": share,
                    }

        if not totals:
            print(f"WARN no totals for {iso3}", file=sys.stderr)
            continue
        latest_y = max(totals)
        mix = mix_by_year.get(latest_y) or {}
        series = []
        for _en, sid, label_ko in FUELS:
            row = mix.get(sid)
            if not row:
                continue
            if row.get("share_pct") is None and row.get("twh") is None:
                continue
            # drop near-zero noise unless we want full set
            share = row.get("share_pct") or 0.0
            twh = row.get("twh") or 0.0
            if share < 0.05 and twh < 0.05:
                continue
            series.append(
                {
                    "id": sid,
                    "label_ko": label_ko,
                    "label_en": row["label_en"],
                    "value": round(float(share), 2),
                    "twh": round(float(twh), 2) if twh is not None else None,
                    "unit": "pct",
                }
            )
        # normalize display order by share desc
        series.sort(key=lambda s: -(s.get("value") or 0))

        history = [
            {"year": y, "value": round(totals[y], 2)}
            for y in sorted(totals)
            if y >= latest_y - 15
        ]

        countries[iso3] = {
            "area": area,
            "ember_area_type": atype,
            "asof_year": latest_y,
            "generation_twh": round(totals[latest_y], 2),
            "history_yearly": history,
            "energy_mix": {
                "asof_year": latest_y,
                "unit": "pct",
                "basis": "share_of_generation",
                "series": series,
            },
            "source": "Ember Yearly Electricity Data",
            "license": "CC-BY-4.0",
            "note_ko": (
                "발전량=Ember Total generation (TWh). "
                "클릭 믹스=연료별 발전 비중(%). "
                + ("EMU는 EU 지역 합산 프록시." if iso3 == "EMU" else "")
            ).strip(),
        }

    doc = {
        "schema_version": "macro-electricity-ember-v1",
        "source": {
            "name": "Ember",
            "dataset": "Yearly Electricity Data",
            "url": "https://ember-energy.org/data/yearly-electricity-data/",
            "license": "CC-BY-4.0",
            "csv": "release_generation_yearly_global.csv",
        },
        "countries": countries,
    }
    OUT_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT_PATH} n={len(countries)}")
    for iso3, row in sorted(countries.items()):
        print(f"  {iso3} {row['asof_year']} {row['generation_twh']} TWh mix={len(row['energy_mix']['series'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
