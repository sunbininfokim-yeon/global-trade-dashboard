"""Open-data clients for West African cocoa labels and climate inputs."""

import csv
from datetime import date, timedelta
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile


HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
FAOSTAT_URL = (
    "https://bulks-faostat.fao.org/production/"
    "Production_Crops_Livestock_E_All_Data_(Normalized).zip"
)
CIV_REGIONAL_URL = (
    "https://data.gouv.ci/data-fair/api/v1/datasets/"
    "repartition-de-la-production-de-cafe-et-cacao-par-region-administrative-en-tonnes/lines"
    "?size=1000"
)
COCOBOD_URL = "https://cocobod.gh/cocoa-purchases"
POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER_PARAMETERS = (
    "T2M_MAX,T2M_MIN,T2M,T2MDEW,RH2M,PRECTOTCORR,WS10M,"
    "GWETROOT,ALLSKY_SFC_SW_DWN"
)


def log(message):
    print("[west-africa:data] " + message, flush=True)


def fetch(url, timeout=300):
    request = urllib.request.Request(url, headers={"User-Agent": "west-africa-cocoa-audit/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def retry_fetch(url, attempts=4, timeout=300):
    delay = 3
    for attempt in range(attempts):
        try:
            return fetch(url, timeout=timeout)
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay *= 2


def cached_bytes(name, url, refresh=False, max_age_days=None, timeout=300):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    fresh = path.exists()
    if fresh and max_age_days is not None:
        age = date.today() - date.fromtimestamp(path.stat().st_mtime)
        fresh = age <= timedelta(days=max_age_days)
    if not fresh or refresh:
        log("downloading {}".format(url))
        payload = retry_fetch(url, timeout=timeout)
        temporary = path.with_suffix(path.suffix + ".part")
        temporary.write_bytes(payload)
        os.replace(str(temporary), str(path))
    return path.read_bytes()


def _repair_faostat_text(value):
    if "Ã" not in value:
        return value
    try:
        return value.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return value


def faostat_zip(refresh=False):
    existing = HERE.parent / "indonesia" / "cache" / "faostat_production.zip"
    if existing.exists() and not refresh:
        return existing
    cached_bytes("faostat_production.zip", FAOSTAT_URL, refresh=refresh, timeout=600)
    return CACHE / "faostat_production.zip"


def faostat_cocoa(refresh=False):
    """Return long official country-year cocoa labels with source quality flags."""
    rows = []
    path = faostat_zip(refresh=refresh)
    with zipfile.ZipFile(path) as archive:
        member = next(name for name in archive.namelist() if name.endswith("Normalized).csv"))
        with archive.open(member) as raw:
            source = io.TextIOWrapper(raw, encoding="latin-1", newline="")
            for row in csv.DictReader(source):
                country = _repair_faostat_text(row.get("Area", ""))
                if country not in {"Côte d'Ivoire", "Ghana"}:
                    continue
                if row.get("Item") != "Cocoa beans":
                    continue
                element = row.get("Element")
                if element not in {"Area harvested", "Yield", "Production"}:
                    continue
                rows.append({
                    "country": country,
                    "year": int(row["Year"]),
                    "element": element,
                    "unit": row.get("Unit", ""),
                    "value": float(row["Value"]),
                    "flag": row.get("Flag", ""),
                    "source": "FAOSTAT",
                })
    if not rows:
        raise RuntimeError("No FAOSTAT cocoa rows found for Côte d'Ivoire or Ghana")
    return rows


def civ_regional_cocoa(refresh=False):
    payload = cached_bytes(
        "civ_regional_cocoa.json", CIV_REGIONAL_URL, refresh=refresh, max_age_days=30)
    results = json.loads(payload.decode("utf-8"))["results"]
    rows = []
    for row in results:
        if row.get("produit") != "Cacao":
            continue
        region = row.get("regions_administratives", "").strip()
        if region.casefold().startswith("total"):
            continue
        rows.append({
            "country": "Côte d'Ivoire",
            "region": unicodedata.normalize("NFC", region),
            "crop_year": str(row["annee"]),
            "year": int(row["annee"]),
            "measure": "production",
            "value_tonnes": float(row["valeur"]),
            "source": "Conseil Café-Cacao via data.gouv.ci",
        })
    return sorted(rows, key=lambda row: (row["year"], row["region"]))


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in {"th", "td"} and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"th", "td"} and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def parse_cocobod_purchases(html):
    parser = _TableParser()
    parser.feed(html)
    table = next(
        (table for table in parser.tables if table and "Crop Year" in table[0]), None)
    if table is None:
        raise RuntimeError("COCOBOD regional purchases table was not found")
    headers = table[0]
    year_index = headers.index("Crop Year")
    ignore = {"No.", "Crop Year", "Total", "Leading Producer"}
    rows = []
    for values in table[1:]:
        if len(values) < len(headers):
            values += [""] * (len(headers) - len(values))
        crop_year = values[year_index]
        if "/" not in crop_year:
            continue
        harvest_year = int(crop_year.split("/")[0][:2] + crop_year.split("/")[1])
        if harvest_year < 1950:
            harvest_year += 100
        for header, value in zip(headers, values):
            if header in ignore or value.upper() in {"", "N/A", "NA", "-"}:
                continue
            try:
                tonnes = float(value.replace(",", ""))
            except ValueError:
                continue
            rows.append({
                "country": "Ghana", "region": header, "crop_year": crop_year,
                "year": harvest_year, "measure": "purchases", "value_tonnes": tonnes,
                "source": "Ghana Cocoa Board",
            })
    return rows


def ghana_regional_purchases(refresh=False):
    payload = cached_bytes(
        "ghana_cocobod_purchases.html", COCOBOD_URL, refresh=refresh, max_age_days=30)
    return parse_cocobod_purchases(payload.decode("utf-8", "replace"))


def _slug(point):
    text = "{}_{}_{:.2f}_{:.2f}".format(
        point["country"], point["region"], point["lat"], point["lon"])
    return "".join(char.lower() if char.isalnum() else "_" for char in text).strip("_")


def power_daily(point, refresh=False):
    end = (date.today() - timedelta(days=3)).strftime("%Y%m%d")
    query = urllib.parse.urlencode({
        "parameters": POWER_PARAMETERS, "community": "AG",
        "longitude": point["lon"], "latitude": point["lat"],
        "start": "19810101", "end": end, "format": "JSON",
    })
    name = "power_{}.json".format(_slug(point))
    payload = cached_bytes(
        name, POWER_URL + "?" + query, refresh=refresh, max_age_days=30, timeout=600)
    parameters = json.loads(payload.decode("utf-8"))["properties"]["parameter"]
    keys = sorted(set().union(*(values.keys() for values in parameters.values())))
    rows = []
    for key in keys:
        row = {"date": key}
        valid = True
        for parameter, values in parameters.items():
            value = values.get(key)
            if value is None or float(value) <= -900:
                valid = False
                break
            row[parameter] = float(value)
        if valid:
            rows.append(row)
    return rows


def write_rows(path, rows, fieldnames=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    if not rows:
        raise ValueError("Cannot write empty table to {}".format(path))
    fieldnames = fieldnames or list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path
