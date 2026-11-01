"""Keyless public reference data. Auction prices are not executable spot quotes."""
import argparse
import csv
import hashlib
import io
import json
import ssl
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

EEX_URL = "https://public.eex-group.com/eex/eua-auction-report/emission-spot-primary-market-auction-report-{year}-data.xlsx"
ECB_URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.KRW.EUR.SP00.A"


def positive(value):
    n = Decimal(str(value))
    if not n.is_finite() or n <= 0:
        raise ValueError("Expected finite positive observation")
    return str(n)


def parse_eex_rows(rows, as_of):
    header = None
    records = []
    excluded = {"future": 0, "unsuccessful": 0}
    required = ["Date", "Auction Name", "Contract", "Status", "Auction Price €/tCO2", "Auction Volume tCO2"]
    for row_no, row in enumerate(rows, 1):
        if header is None:
            if all(v in row for v in required):
                header = {v: row.index(v) for v in required}
            continue
        def cell(name):
            return row[header[name]]
        d = cell("Date")
        if not isinstance(d, datetime):
            continue
        if d.date() > as_of:
            excluded["future"] += 1
            continue
        if str(cell("Status")).strip().lower() != "successful":
            excluded["unsuccessful"] += 1
            continue
        records.append({"observation_date": d.date().isoformat(),
                        "price": positive(cell("Auction Price €/tCO2")),
                        "auction_name": str(cell("Auction Name")),
                        "source_contract": str(cell("Contract")),
                        "auction_volume_tco2": positive(cell("Auction Volume tCO2")),
                        "source_row": row_no})
    if header is None or not records:
        raise ValueError("EEX expected headers or successful observations missing")
    records.sort(key=lambda r: (r["observation_date"], r["auction_name"]))
    return records, excluded


def parse_eex(data, as_of):
    from openpyxl import load_workbook  # Read-only source extraction; no workbook authoring.
    book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        if "EU ETS1" not in book.sheetnames:
            raise ValueError("EEX expected EU ETS1 sheet missing")
        return parse_eex_rows(book["EU ETS1"].iter_rows(values_only=True), as_of)
    finally:
        book.close()


def parse_ecb(data, as_of):
    records = []
    for r in csv.DictReader(io.StringIO(data.decode("utf-8-sig"))):
        if r["KEY"] != "EXR.D.KRW.EUR.SP00.A" or r["CURRENCY"] != "KRW" or r["CURRENCY_DENOM"] != "EUR" or r["FREQ"] != "D":
            raise ValueError("ECB series/currency mismatch")
        if r.get("UNIT_MULT") != "0":
            raise ValueError("ECB unexpected unit multiplier")
        d = date.fromisoformat(r["TIME_PERIOD"])
        if d > as_of:
            continue
        if r["OBS_STATUS"] != "A" or not r["OBS_VALUE"].strip():
            continue
        records.append({"observation_date": d.isoformat(), "price": positive(r["OBS_VALUE"])})
    if not records:
        raise ValueError("ECB has no valid observations")
    records.sort(key=lambda r: r["observation_date"])
    return records, {}


def fetch(url):
    req = Request(url, headers={"User-Agent": "ShippingCarbonResearch/0.1", "Accept": "*/*"})
    context = ssl.create_default_context()
    # Supplement the OS CA store for bundled Python; TLS verification remains enabled.
    try:
        import certifi
        context.load_verify_locations(cafile=certifi.where())
    except ImportError:
        pass
    with urlopen(req, timeout=30, context=context) as response:
        data = response.read(10_000_001)
        if len(data) > 10_000_000:
            raise ValueError("Response exceeds size limit")
        return data


def collect(as_of, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = [
        ("eex_eua_auction", EEX_URL.format(year=as_of.year), parse_eex, "auction_clearing", "EUR/EUA"),
        ("ecb_eurkrw", ECB_URL + "?" + urlencode({"startPeriod": date(as_of.year, 1, 1).isoformat(), "endPeriod": as_of.isoformat(), "format": "csvdata"}), parse_ecb, "reference_fx", "KRW/EUR")]
    result = {"schema": "shipping_carbon_reference_prices_v1", "as_of": as_of.isoformat(),
              "retrieved_at": datetime.now(timezone.utc).isoformat(), "sources": {}}
    for key, url, parser, kind, unit in sources:
        try:
            raw = fetch(url)
            records, excluded = parser(raw, as_of)
            digest = hashlib.sha256(raw).hexdigest()
            suffix = "xlsx" if key.startswith("eex") else "csv"
            raw_name = f"{key}_{digest[:16]}.{suffix}"
            (output_dir / raw_name).write_bytes(raw)
            latest_date = records[-1]["observation_date"]
            latest = [r for r in records if r["observation_date"] == latest_date]
            result["sources"][key] = {"status": "observed", "price_type": kind, "unit": unit,
                "source_url": url, "raw_file": raw_name, "sha256": digest,
                "authentication": "none", "redistribution_status": "not_verified",
                "latest_observation_date": latest_date,
                "calendar_age_days": (as_of - date.fromisoformat(latest_date)).days,
                "latest_observations": latest, "count": len(records), "excluded": excluded,
                "observations": records}
        except Exception as exc:
            result["sources"][key] = {"status": "source_unavailable", "source_url": url,
                "price_type": kind, "unit": unit, "latest_observations": [], "error": str(exc)}
    complete = all(s["status"] == "observed" for s in result["sources"].values())
    result["status"] = "complete" if complete else "partial"
    name = "reference_prices.json" if complete else "last_failed_attempt.json"
    dest = output_dir / name
    temp = dest.with_suffix(".tmp")
    temp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    temp.replace(dest)  # Failure diagnostics never replace the last successful snapshot.
    return result, dest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--as-of", type=date.fromisoformat, required=True)
    p.add_argument("--output-dir", type=Path, default=Path(__file__).with_name("source_data"))
    args = p.parse_args()
    result, dest = collect(args.as_of, args.output_dir)
    print(json.dumps({"status": result["status"], "output": str(dest), "sources": {
        k: {x: v.get(x) for x in ("status", "count", "latest_observation_date", "error")}
        for k, v in result["sources"].items()}}, ensure_ascii=False))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
