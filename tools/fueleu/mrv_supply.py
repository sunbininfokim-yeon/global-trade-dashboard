"""Who makes FuelEU surplus and who needs it: a structural estimate from EMSA MRV.

The FuelEU database is not public, so there is no official market-wide
surplus/deficit figure. EMSA's public MRV workbook is the closest thing: per
ship and year it gives total fuel, and CO2/CH4/N2O split into voyages between
EU ports, departing, arriving and within EU ports. From that this estimates
each ship's FuelEU intensity and balance, then adds them up by propulsion and
ship type.

How a ship is read:
  - CO2 per tonne of fuel separates oil (HFO 3.114 ... MGO 3.206) from LNG
    (2.750); CH4 per tonne flags LNG (slip) -- oil engines emit ~0.00005.
  - Oil-only ships: LCV and WtT are interpolated between HFO and MGO on that
    ratio. LNG ships: the LNG share comes from the same ratio, oil part as LFO.
  - TtW uses the ship's reported CO2, CH4 and N2O (so reported slip counts),
    with FuelEU GWP100 (CH4 25, N2O 298).
  - FuelEU share = (between EU ports + within EU ports + half of departing and
    arriving) / total, applied to energy.

What it cannot see, stated wherever the numbers are shown:
  - Biofuel blends. Their CO2 per tonne looks like a mix and their WtW credit
    is not in MRV; such ships (low ratio, no methane) are counted apart as
    "바이오 혼합 추정" and left out of the totals -- so surplus is understated.
  - Methanol and other fuels (ratio below LNG) -- counted apart, left out.
  - Outermost-region voyages are inside "between EU ports" here (FuelEU: 50 %).
  - Wind and shore power rewards, ice derogations, pooling already done.
Not an official balance for any ship.

Run: python3 mrv_supply.py --year 2025 [--year 2024]
     python3 mrv_supply.py --year 2025 --file path/to/official.xlsx
"""
import argparse
import hashlib
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

import engine

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "source_data"
BASE = "https://mrv.emsa.europa.eu/api/public-emission-report"
F = engine.FUELS
HFO, MGO, LFO = F["hfo"], F["mdo_mgo"], F["lfo"]
LNG = F["lng_otto_ms"]  # LCV and WtT only; slip comes from the reported CH4
CH4_LNG_PER_T = 0.0005   # 10x the oil default; LNG slip is 0.2-3.1 % of mass
RATIO_LNG_FLOOR = 2.60   # below LNG's 2.75 even with slip: methanol/other

COLS = {
    "imo": "IMO Number", "ship_type": "Ship type", "fuel": "Total fuel consumption [m tonnes]",
    "co2": "Total CO₂ emissions [m tonnes]", "ch4": "Total CH₄ emissions [m tonnes]",
    "n2o": "Total N₂O emissions [m tonnes]",
    "between": "CO₂ emissions from all voyages between ports under a MS jurisdiction [m tonnes]",
    "departed": "CO₂ emissions from all voyages which departed from ports under a MS jurisdiction [m tonnes]",
    "arrived": "CO₂ emissions from all voyages to ports under a MS jurisdiction [m tonnes]",
    "in_port": "CO₂ emissions which occurred within ports under a MS jurisdiction [m tonnes]",
}


def num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and x >= 0 else None


def lerp(a, b, t):
    return a + (b - a) * min(1.0, max(0.0, t))


def classify(fuel_t, co2_t, ch4_t):
    ratio = co2_t / fuel_t
    ch4_per_t = (ch4_t or 0.0) / fuel_t
    if ratio < RATIO_LNG_FLOOR:
        return "other", ratio
    if ch4_per_t >= CH4_LNG_PER_T:
        return "lng", ratio
    if ratio < HFO["cf_co2"] - 0.02:
        return "bio_blend_suspected", ratio
    return "oil", ratio


def estimate_ship(row):
    """row: dict with COLS keys (tonnes). Returns the estimate or a reason it was skipped."""
    fuel, co2 = row["fuel"], row["co2"]
    if not fuel or not co2:
        return {"status": "skipped", "reason": "no_fuel_or_co2"}
    kind, ratio = classify(fuel, co2, row.get("ch4"))
    if kind in ("other", "bio_blend_suspected"):
        return {"status": "unestimated", "propulsion": kind, "ratio": ratio}
    if kind == "oil":
        t = (ratio - HFO["cf_co2"]) / (MGO["cf_co2"] - HFO["cf_co2"])
        lcv, wtt = lerp(HFO["lcv"], MGO["lcv"], t), lerp(HFO["wtt"], MGO["wtt"], t)
        energy = fuel * 1e6 * lcv
        wtt_num = energy * wtt
        lng_share = 0.0
    else:
        lng_share = min(1.0, max(0.0, (LFO["cf_co2"] - ratio) / (LFO["cf_co2"] - LNG["cf_co2"])))
        e_lng = fuel * lng_share * 1e6 * LNG["lcv"]
        e_oil = fuel * (1 - lng_share) * 1e6 * LFO["lcv"]
        energy = e_lng + e_oil
        wtt_num = e_lng * LNG["wtt"] + e_oil * LFO["wtt"]
    ttw_g = (co2 + (row.get("ch4") or 0.0) * engine.GWP["CH4"] + (row.get("n2o") or 0.0) * engine.GWP["N2O"]) * 1e6
    intensity = (wtt_num + ttw_g) / energy
    scoped = (row.get("between") or 0) + (row.get("in_port") or 0) + 0.5 * ((row.get("departed") or 0) + (row.get("arrived") or 0))
    share = scoped / co2
    return {"status": "estimated", "propulsion": kind, "ratio": ratio, "lng_energy_share_est": lng_share,
            "intensity": intensity, "fueleu_energy_mj": energy * share, "fueleu_share": share}


def balance(est, year):
    return (engine.target(year) - est["intensity"]) * est["fueleu_energy_mj"] / 1e6


def aggregate(rows, years=(2025, 2030, 2035)):
    """rows: iterable of dicts with COLS keys. Totals by propulsion and ship type."""
    def bucket():
        return {"ships": 0, **{f"surplus_{y}": 0.0 for y in years}, **{f"deficit_{y}": 0.0 for y in years},
                **{f"surplus_ships_{y}": 0 for y in years}, "energy_mj": 0.0, "intensity_weighted": 0.0}
    by_prop, by_type, unest, skipped = defaultdict(bucket), defaultdict(bucket), defaultdict(int), 0
    total = bucket()
    for row in rows:
        est = estimate_ship(row)
        if est["status"] == "skipped":
            skipped += 1
            continue
        if est["status"] == "unestimated":
            unest[est["propulsion"]] += 1
            continue
        for b in (total, by_prop[est["propulsion"]], by_type[row.get("ship_type") or "?"]):
            b["ships"] += 1
            b["energy_mj"] += est["fueleu_energy_mj"]
            b["intensity_weighted"] += est["intensity"] * est["fueleu_energy_mj"]
            for y in years:
                cb = balance(est, y)
                if cb >= 0:
                    b[f"surplus_{y}"] += cb
                    b[f"surplus_ships_{y}"] += 1
                else:
                    b[f"deficit_{y}"] += -cb
    def finish(b):
        b["avg_intensity"] = b.pop("intensity_weighted") / b["energy_mj"] if b["energy_mj"] else None
        for y in years:
            b[f"net_{y}"] = b[f"surplus_{y}"] - b[f"deficit_{y}"]
        return b
    return {"total": finish(total), "by_propulsion": {k: finish(v) for k, v in by_prop.items()},
            "by_ship_type": {k: finish(v) for k, v in sorted(by_type.items(), key=lambda kv: -kv[1]["energy_mj"])},
            "unestimated": dict(unest), "skipped": skipped, "years": list(years)}


def read_workbook(raw, year):
    from openpyxl import load_workbook
    book = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    try:
        sheet = f"{year} Full ERs"  # Partial ERs cover part-year changes of company; left out to avoid double counting
        it = book[sheet].iter_rows(values_only=True)
        header = next(r for r in it if r and "IMO Number" in r)
        idx = {}
        for key, name in COLS.items():
            if name not in header:
                raise ValueError(f"MRV column missing: {name}")
            idx[key] = list(header).index(name)
        for r in it:
            imo = str(r[idx["imo"]] or "").strip()
            if not (imo.isdigit() and len(imo) == 7):
                continue
            yield {k: (r[i] if k in ("imo", "ship_type") else num(r[i])) for k, i in idx.items()}
    finally:
        book.close()


def fetch(year):
    with urlopen(BASE + "/downloadable-files", timeout=30) as res:
        listing = json.load(res)
    meta = next(r for r in listing["results"] if int(r["reportingPeriod"]) == year)
    url = f"{BASE}/reporting-period-document/binary/{year}/{meta['version']}"
    with urlopen(url, timeout=120) as res:
        return res.read(60_000_001), url, meta["version"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, action="append", required=True)
    ap.add_argument("--file", type=Path, help="official workbook already downloaded (single --year only)")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    for year in a.year:
        if a.file:
            raw, url, version = a.file.read_bytes(), "local_official_file", None
        else:
            raw, url, version = fetch(year)
        agg = aggregate(read_workbook(raw, year))
        result = {"schema": "fueleu_mrv_supply_estimate_v1", "reporting_year": year, "source_url": url,
                  "source_version": version, "sha256": hashlib.sha256(raw).hexdigest(),
                  "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "kind": "structural_estimate_not_official_balance", "unit": "tCO2e",
                  "redistribution": "emsa_reuse_terms_not_verified", **agg}
        (OUT / f"mrv_supply_{year}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        t = agg["total"]
        print(f"{year}: {t['ships']} ships estimated, unestimated {agg['unestimated']}, skipped {agg['skipped']}")
        for y in agg["years"]:
            print(f"  target {y}: surplus {t[f'surplus_{y}']:,.0f} t ({t[f'surplus_ships_{y}']} ships)  "
                  f"deficit {t[f'deficit_{y}']:,.0f} t  net {t[f'net_{y}']:,.0f} t")
        for k, v in agg["by_propulsion"].items():
            print(f"  {k}: {v['ships']} ships, avg {v['avg_intensity']:.2f} g/MJ, net2025 {v['net_2025']:,.0f} t")


if __name__ == "__main__":
    main()
