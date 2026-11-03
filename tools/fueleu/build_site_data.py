"""Bundle what the dashboard's 해운 › FuelEU tab shows into one static file.

Reads source_data/pool_prices.json and source_data/mrv_supply_*.json (run the
collectors first) and writes New for anti/public/data/fueleu_market_v1.json.

The user chose to publish the OPX series and MRV estimate for one month as a
personal project, although redistribution terms are unconfirmed. DISPLAY_UNTIL
is enforced by the page itself: after that date the tab stops showing the
price and supply data even if nobody removes the file.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import engine

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "source_data"
DEST = ROOT.parents[1] / "New for anti" / "public" / "data" / "fueleu_market_v1.json"
DISPLAY_UNTIL = "2026-12-03"
SUPPLY_KEYS = ("ships", "avg_intensity", "energy_mj") + tuple(
    f"{k}_{y}" for y in (2025, 2030, 2035) for k in ("surplus", "deficit", "net", "surplus_ships"))


def rules():
    periods = [{"from_year": y, "reduction_pct": pct, "target": round(engine.target(y), 4)} for y, pct in sorted(engine.REDUCTIONS)]
    fuels = []
    for key, f in engine.FUELS.items():
        i = engine.intensity([{"fuel": key, "tonnes": 1, "scope": "intra_eu"}], 2025)["ghg_intensity"]
        fuels.append({"key": key, "label": f["label"], "intensity": round(i, 3),
                      "first_deficit_period": next((p["from_year"] for p in periods if p["target"] < i), None),
                      "penalty_eur_per_tco2e": round(engine.penalty_per_tco2e(i), 1)})
    return {"reference": engine.REFERENCE, "periods": periods, "fuels": sorted(fuels, key=lambda x: -x["intensity"]),
            "penalty_eur_per_t_vlsfo": engine.PENALTY_EUR_PER_T_VLSFO}


def slim(bucket):
    return {k: (round(bucket[k], 3) if isinstance(bucket.get(k), float) else bucket.get(k)) for k in SUPPLY_KEYS}


def supply():
    out = {}
    for path in sorted(SRC.glob("mrv_supply_*.json")):
        d = json.loads(path.read_text())
        out[str(d["reporting_year"])] = {
            "source_version": d.get("source_version"), "source_url": d.get("source_url"), "retrieved_at": d.get("retrieved_at"),
            "total": slim(d["total"]), "total_with_bio_assumption": slim(d["total_with_bio_assumption"]),
            "size_filter": d.get("size_filter"), "by_propulsion": {k: slim(v) for k, v in d["by_propulsion"].items()},
            "by_ship_type": {k: slim(v) for k, v in list(d["by_ship_type"].items())[:16]},
            "unestimated": d["unestimated"], "skipped": d["skipped"]}
    return out


def main(today=None):
    today = today or datetime.now(timezone.utc).date().isoformat()
    live = today <= DISPLAY_UNTIL
    prices = json.loads((SRC / "pool_prices.json").read_text()) if live else None
    data = {
        "schema": "fueleu_market_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "display_until": DISPLAY_UNTIL,
        "regulation": {"name": "Regulation (EU) 2023/1805 (FuelEU Maritime)", "oj": "OJ L 234, 22.9.2023",
                       "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R1805"},
        "rules": rules(),
        # Past the window the third-party data leaves the file, not just the page.
        "prices": {"source": prices["source"], "source_index_url": prices["source_index_url"],
                   "retrieved_at": prices["retrieved_at"], "price_type": prices["price_type"], "unit": prices["unit"],
                   "series": prices["series"], "latest_topbar": prices.get("latest_topbar"),
                   "missing_pages": prices.get("missing_pages", [])} if live else None,
        "supply": supply() if live else None,
    }
    DEST.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(f"wrote {DEST} ({DEST.stat().st_size:,} bytes), live={live}, years {list(data['supply'] or [])}")


if __name__ == "__main__":
    main()
