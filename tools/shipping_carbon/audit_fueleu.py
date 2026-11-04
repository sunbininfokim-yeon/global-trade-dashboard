"""Collect source receipts and audit Claude's FuelEU estimator without changing it."""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from collect_prices import fetch
from fueleu_adapter import call_fueleu

BASE = "https://mrv.emsa.europa.eu/api/public-emission-report"


def collect(output, year, transport="urllib", local_files=None, listing_file=None):
    def get(url):
        if transport == "curl":
            result = subprocess.run(["curl", "--fail", "--silent", "--show-error", "--location",
                "--max-time", "60", "--max-filesize", "60000000", url], capture_output=True, timeout=65, check=True)
            if len(result.stdout) > 60_000_000:
                raise ValueError("MRV response too large")
            return result.stdout
        return fetch(url, max_bytes=60_000_000)
    listing = json.loads(Path(listing_file).read_bytes() if listing_file else get(BASE + "/downloadable-files"))
    output.mkdir(parents=True, exist_ok=True)
    sources = {}
    for y in (year - 1, year):
        matches = [r for r in listing["results"] if int(r["reportingPeriod"]) == y]
        if len(matches) != 1:
            raise ValueError("MRV year is not uniquely listed")
        meta = matches[0]
        url = f"{BASE}/reporting-period-document/binary/{y}/{meta['version']}"
        local = (local_files or {}).get(y)
        print(f"{'Reading local official file' if local else 'Downloading official MRV'} {y} v{meta['version']}", file=sys.stderr, flush=True)
        raw = Path(local).read_bytes() if local else get(url)
        if len(raw) > 60_000_000:
            raise ValueError("MRV response too large")
        sha = hashlib.sha256(raw).hexdigest()
        file = output / f"audit_mrv_{y}_{sha[:16]}.xlsx"
        file.write_bytes(raw)
        sources[y] = {"source_url": url, "sha256": sha, "version": meta["version"],
                      "source_generation_date": meta.get("generationDate"), "file": str(file.resolve()),
                      "input_mode": "local_official_file_version_from_listing" if local else "direct_download"}
    result = call_fueleu({"mode": "audit", "year": year,
                          "file": sources[year]["file"], "baseline_file": sources[year - 1]["file"]}, timeout=120)
    result.update(sources={str(y): s for y, s in sources.items()},
                  retrieved_at=datetime.now(timezone.utc).isoformat(), redistribution_status="not_verified")
    dest = output / "fueleu_audit.json"
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    tmp.replace(dest)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--year", type=int, default=2025)
    p.add_argument("--output-dir", type=Path, default=Path(__file__).with_name("source_data"))
    p.add_argument("--transport", choices=("urllib", "curl"), default="urllib")
    p.add_argument("--local-file", action="append", default=[], help="YEAR=official.xlsx; never use partial downloads")
    p.add_argument("--listing-file", type=Path, help="Saved official downloadable-files response")
    a = p.parse_args()
    try:
        files = {int(value.split("=", 1)[0]): Path(value.split("=", 1)[1]) for value in a.local_file}
        if any(path.suffix == ".partial" for path in files.values()):
            raise ValueError("Partial downloads cannot be audited")
        r = collect(a.output_dir, a.year, a.transport, files, a.listing_file)
    except Exception as exc:
        a.output_dir.mkdir(parents=True, exist_ok=True)
        (a.output_dir / "fueleu_audit_failed_attempt.json").write_text(json.dumps({"status": "source_unavailable", "error": str(exc)}))
        raise
    print(json.dumps({"full_reports": r["full_reports"], "strict_usable_reports": r["strict_usable_reports"],
        "coverage": r["coverage"], "scenarios": [{"id": s["id"], "selected_reports": s["selected_reports"],
        "net_tco2e": s["total"].get("net_2025"), "net_with_bio_assumption": s["with_bio_assumption"].get("net_2025")} for s in r["scenarios"]]}, ensure_ascii=False))
