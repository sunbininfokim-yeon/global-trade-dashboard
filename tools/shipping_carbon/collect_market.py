"""EEX published gross OI, not ICE-wide OI or market prices. Keyless, local research."""
import argparse
import hashlib
import io
import json
from datetime import date, datetime, timezone
from pathlib import Path
from collect_prices import fetch

URL = "https://www.eex.com/fileadmin/Global/Upload/EEX_Emissions_Open_Interest.xlsx"


def parse_oi_rows(rows, as_of):
    rows = list(rows)
    header = next((i for i, r in enumerate(rows) if "Contract" in r and "Synthetic Net OI" in r and "Open Interest" in r), None)
    if header is None:
        raise ValueError("EEX OI header missing")
    dates = []
    for row in rows[:header]:
        for cell in row:
            if isinstance(cell, datetime):
                dates.append(cell.date())
            elif isinstance(cell, str):
                try:
                    dates.append(datetime.strptime(cell.strip(), "%m/%d/%Y").date())
                except ValueError:
                    pass
    if len(set(dates)) != 1 or dates[0] > as_of:
        raise ValueError("EEX OI observation date missing/ambiguous/future")
    h = {v: i for i, v in enumerate(rows[header]) if isinstance(v, str)}
    records = []
    seen = set()
    for n, row in enumerate(rows[header + 1:], header + 2):
        if row[h["Contract"]] != "FEUA":
            continue
        month = row[h["Expiry"]]
        year = row[h["Expiry"] + 1]
        if month is None and year is None:  # Published total, not another expiry.
            continue
        if row[h["P/C"]] not in (None, ""):
            raise ValueError("Unexpected option in FEUA futures")
        expiry = f"{int(year):04d}-{int(month):02d}"
        date(int(year), int(month), 1)
        if expiry in seen:
            raise ValueError("Duplicate FEUA expiry")
        seen.add(expiry)
        values = []
        for key in ("Open Interest", "Synthetic Net OI"):
            v = float(row[h[key]])
            if not v.is_integer() or v < 0:
                raise ValueError("Invalid OI lots")
            values.append(int(v))
        records.append({"expiry_month": expiry, "gross_oi_lots": values[0],
                        "eex_synthetic_net_oi_lots": values[1], "source_row": n})
    if not records:
        raise ValueError("No EUA futures OI")
    return {"status": "observed", "venue": "EEX", "product": "EUA futures", "source_contract": "FEUA",
            "observation_date": dates[0].isoformat(), "unit": "lots", "records": sorted(records, key=lambda r: r["expiry_month"]),
            "scope_note": "EEX only. Published gross OI and EEX-calculated synthetic net OI are different measures; neither is ICE market OI."}


def collect(as_of, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {"schema": "carbon_market_structure_v1", "as_of": as_of.isoformat(),
              "retrieved_at": datetime.now(timezone.utc).isoformat(), "source_url": URL,
              "redistribution_status": "not_verified"}
    try:
        from openpyxl import load_workbook
        raw = fetch(URL)
        b = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        try:
            result.update(parse_oi_rows(b["OI"].iter_rows(values_only=True), as_of))
        finally:
            b.close()
        digest = hashlib.sha256(raw).hexdigest()
        name = f"eex_oi_{digest[:16]}.xlsx"
        (output_dir / name).write_bytes(raw)
        result.update(sha256=digest, raw_file=name)
        target = output_dir / "market_structure.json"
    except Exception as exc:
        result.update(status="source_unavailable", records=[], error=str(exc))
        target = output_dir / "market_structure_failed_attempt.json"
    temp = target.with_suffix(".tmp")
    temp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    temp.replace(target)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--as-of", required=True, type=date.fromisoformat)
    p.add_argument("--output-dir", type=Path, default=Path(__file__).with_name("source_data"))
    a = p.parse_args()
    s = collect(a.as_of, a.output_dir)
    print(json.dumps({k: s.get(k) for k in ("status", "observation_date", "error")}))
    raise SystemExit(0 if s["status"] == "observed" else 1)
