"""Read EMSA's public annual workbook; keep Full and Partial ERs separate."""
import argparse
import hashlib
import io
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.request import urlopen

BASE = "https://mrv.emsa.europa.eu/api/public-emission-report"


def quantity(value):
    if value is None or str(value).strip() in ("", "N/A"):
        return None
    try:
        n = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Unexpected MRV numeric value") from exc
    if not n.is_finite() or n < 0:
        raise ValueError("Invalid MRV emission value")
    return str(n)


def parse_rows(rows, scope, sheet):
    records = []
    header = None
    for row_no, row in enumerate(rows, 1):
        if header is None:
            if "Total CO₂ emissions [m tonnes]" in row and "IMO Number" in row:
                header = row
            continue
        def cell(name):
            return row[header.index(name)]
        imo = str(cell("IMO Number") or "").strip()
        if not (imo.isdigit() and len(imo) == 7):
            continue
        name_index = header.index("Name")
        company_index = header.index("Name", name_index + 1)
        records.append({"record_id": f"{sheet}:{row_no}", "imo": imo,
            "name": str(row[name_index]), "company": str(row[company_index]),
            "ship_type": str(cell("Ship type")), "report_scope": scope,
            "source_reporting_period": str(cell("Reporting Period")),
            "doc_issue_date": str(cell("DoC issue date")),
            "total_co2_t": quantity(cell("Total CO₂ emissions [m tonnes]")),
            "ets_reported_co2_t": quantity(cell("CO2 emissions to be reported under Directive 2003/87/EC [m tonnes]")),
            "fuel_t": quantity(cell("Total fuel consumption [m tonnes]")),
            "source_sheet": sheet, "source_row": row_no, "source_unit": "m tonnes (metric tonnes)"})
    if header is None:
        raise ValueError(f"Expected MRV headers missing: {sheet}")
    return records


def collect(year, output_dir, local_file=None):
    from openpyxl import load_workbook
    output_dir.mkdir(parents=True, exist_ok=True)
    with urlopen(BASE + "/downloadable-files", timeout=30) as response:
        listing = json.load(response)
    match = [r for r in listing["results"] if int(r["reportingPeriod"]) == year]
    if len(match) != 1:
        raise ValueError("Requested reporting year is not uniquely listed")
    meta = match[0]
    url = f"{BASE}/reporting-period-document/binary/{year}/{meta['version']}"
    if local_file:
        raw = local_file.read_bytes()
    else:
        with urlopen(url, timeout=60) as response:
            raw = response.read(50_000_001)
    if len(raw) > 50_000_000:
        raise ValueError("MRV source exceeds size limit")
    digest = hashlib.sha256(raw).hexdigest()
    book = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    records = []
    counts = {}
    try:
        for scope, sheet in (("full", f"{year} Full ERs"), ("partial", f"{year} Partial ERs")):
            if sheet not in book.sheetnames:
                raise ValueError(f"MRV sheet missing: {sheet}")
            subset = parse_rows(book[sheet].iter_rows(values_only=True), scope, sheet)
            counts[scope] = len(subset)
            records.extend(subset)
    finally:
        book.close()
    if not records:
        raise ValueError("MRV has no ship records")
    result = {"schema": "shipping_mrv_observations_v1", "status": "observed",
        "reporting_year": year, "version": meta["version"], "generation_date_source": meta["generationDate"],
        "retrieved_at": datetime.now(timezone.utc).isoformat(), "source_url": url,
        "sha256": digest, "count": len(records), "counts_by_scope": counts,
        "redistribution_status": "not_verified", "records": records,
        "input_mode": "local_official_file" if local_file else "direct_download",
        "coverage": "published_full_and_partial_reports_not_current_voyage_or_allowance_inventory"}
    (output_dir / f"mrv_{year}_{digest[:16]}.xlsx").write_bytes(raw)
    dest = output_dir / "vessel_emissions.json"
    temp = dest.with_suffix(".tmp")
    temp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    temp.replace(dest)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--file", type=Path, help="Official workbook already downloaded for this listed version")
    p.add_argument("--output-dir", type=Path, default=Path(__file__).with_name("source_data"))
    a = p.parse_args()
    r = collect(a.year, a.output_dir, a.file)
    print(json.dumps({k: r[k] for k in ("status", "reporting_year", "version", "count", "counts_by_scope")}, ensure_ascii=False))
