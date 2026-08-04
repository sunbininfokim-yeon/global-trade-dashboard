"""Create small, country-separated, GitHub-ready dataset snapshots.

This exports normalized CSV/JSON products only. Source caches, credentials and
Earth Engine authentication material are never copied into the publication tree.
"""

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil


HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
TRAINING = HERE / "training"
MODELS = HERE / "models"
REFERENCE = HERE / "reference"
OUTPUT = HERE / "datasets"
COUNTRIES = {
    "ghana": "Ghana",
    "cote_divoire": "Côte d'Ivoire",
}


def copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def filter_csv(source, destination, country):
    with Path(source).open(encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("country") == country]
    if not rows:
        raise ValueError("No {} rows in {}".format(country, source))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return destination


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def export_country(slug, country):
    written = []
    for filename in ["faostat_cocoa_long.csv", "faostat_cocoa_country_year.csv"]:
        written.append(filter_csv(
            DATA / filename, OUTPUT / slug / "labels" / filename, country))
    written.append(filter_csv(
        DATA / "cocoa_country_climate.csv",
        OUTPUT / slug / "climate" / "cocoa_country_climate.csv", country))
    written.append(filter_csv(
        TRAINING / "cocoa_faostat_country.csv",
        OUTPUT / slug / "training" / "cocoa_faostat_country.csv", country))

    prefix = country + "_"
    for source in sorted((DATA / "climate_points").glob(prefix + "*.csv")):
        name = source.name[len(prefix):].replace(" ", "_")
        written.append(copy(source, OUTPUT / slug / "climate" / "nasa_power_points" / name))

    if slug == "ghana":
        for filename in ["ghana_country_purchases.csv", "ghana_regional_purchases.csv"]:
            written.append(copy(DATA / filename, OUTPUT / slug / "labels" / filename))
        for filename in ["ghana_cocoa_purchases.csv", "ghana_cocoa_regional_purchases.csv"]:
            written.append(copy(TRAINING / filename, OUTPUT / slug / "training" / filename))
        decision = MODELS / "ghana_forecast_decision.json"
        if decision.exists():
            written.append(copy(decision, OUTPUT / slug / "models" / decision.name))
    else:
        written.append(copy(
            DATA / "civ_regional_cocoa.csv",
            OUTPUT / slug / "labels" / "civ_regional_cocoa.csv"))

    profiles = json.loads(
        (REFERENCE / "cocoa_country_profiles.json").read_text(encoding="utf-8"))
    profile = {
        "as_of": profiles["as_of"],
        "mode": profiles["mode"],
        "interpretation": profiles["interpretation"],
        "country": profiles["countries"][slug],
    }
    profile_path = OUTPUT / slug / "reference" / "cocoa_profile.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    written.append(profile_path)
    written.append(filter_csv(
        REFERENCE / "cocoa_country_profiles.csv",
        OUTPUT / slug / "reference" / "cocoa_profile.csv", country))
    return written


def run():
    written = []
    for slug, country in COUNTRIES.items():
        written.extend(export_country(slug, country))
    for source in [
        DATA / "source_catalog.csv",
        DATA / "source_catalog.json",
        DATA / "earth_engine_status.json",
        DATA / "model_feasibility.json",
        MODELS / "feasibility_screen.json",
    ]:
        written.append(copy(source, OUTPUT / "shared" / "metadata" / source.name))

    records = [{
        "path": str(path.relative_to(OUTPUT)),
        "bytes": path.stat().st_size,
        "sha256": checksum(path),
    } for path in sorted(written)]
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "storage_target": "GitHub repository",
        "contains_credentials": False,
        "countries": COUNTRIES,
        "notes": [
            "COCOBOD tables measure purchases, not biological production or yield.",
            "NASA POWER point features are screening inputs, not cocoa-mask area averages.",
            "Source terms and update URLs are recorded in shared/metadata/source_catalog.*.",
        ],
        "files": records,
    }
    manifest_path = OUTPUT / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest_path, records


if __name__ == "__main__":
    result, files = run()
    print("wrote {} files and {}".format(len(files), result))
