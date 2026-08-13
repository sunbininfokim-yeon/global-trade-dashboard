"""Extract BPS province tables into a provenance-rich SQLite database."""

import csv
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys

from .manifest import PUBLICATIONS


HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
DATA = os.path.join(HERE, "data")
DATABASE = os.path.join(DATA, "indonesia_crop_panel.sqlite")
CLIMATE_CSV = os.path.join(DATA, "province_climate.csv")

CATEGORY_ALIASES = {
    "government_estates": [
        "Government Estates",
        "Government Plantations",
        "Goverment Plantations",  # Spelling used in early oil-palm books.
    ],
    "private_estates": ["Private Estates", "Private Plantations"],
    "smallholders": ["Smallholders"],
    "total": ["Total"],
}

PROVINCES = [
    "Nanggroe Aceh Darussalam", "Kepulauan Bangka Belitung",
    "Daerah Istimewa Yogyakarta", "Nusa Tenggara Barat",
    "Nusa Tenggara Timur", "Kepulauan Riau", "Sumatera Utara",
    "Sumatera Barat", "Sumatera Selatan", "Bangka Belitung",
    "Kalimantan Barat", "Kalimantan Tengah", "Kalimantan Selatan",
    "Kalimantan Timur", "Kalimantan Utara", "Sulawesi Utara",
    "Sulawesi Tengah", "Sulawesi Selatan", "Sulawesi Tenggara",
    "Sulawesi Barat", "Maluku Utara", "Papua Barat Daya",
    "Papua Pegunungan", "Papua Selatan", "Papua Tengah", "Papua Barat",
    "DKI Jakarta", "D.I. Yogyakarta", "DI Yogyakarta", "Jawa Barat",
    "D I Yogyakarta",
    "Jawa Tengah", "Jawa Timur", "Aceh", "Riau", "Jambi", "Bengkulu",
    "Lampung", "Banten", "Bali", "Gorontalo", "Maluku", "Papua",
    "N.A.D", "NAD", "Irian Jaya Barat", "Irian Jaya",
]

CANONICAL = {
    "Nanggroe Aceh Darussalam": "Aceh",
    "Kepulauan Bangka Belitung": "Bangka Belitung",
    "Daerah Istimewa Yogyakarta": "DI Yogyakarta",
    "D.I. Yogyakarta": "DI Yogyakarta",
    "D I Yogyakarta": "DI Yogyakarta",
    "N.A.D": "Aceh",
    "NAD": "Aceh",
    "Irian Jaya": "Papua",
    "Irian Jaya Barat": "Papua Barat",
}

NUMBER = re.compile(r"(?:[-–—]|\.?\d+(?:\.\d{3})*)")


def find_pdftotext():
    configured = os.environ.get("PDFTOTEXT")
    candidates = [configured, shutil.which("pdftotext")]
    runtime = os.path.expanduser(
        "~/.cache/codex-runtimes/codex-primary-runtime/dependencies")
    candidates.extend([
        os.path.join(runtime, "native", "poppler", "poppler", "bin", "pdftotext"),
        os.path.join(runtime, "native", "poppler", "bin", "pdftotext"),
    ])
    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError("pdftotext was not found; set PDFTOTEXT to a Poppler binary")


def pdf_pages(path, layout=False):
    command = [find_pdftotext(), "-layout" if layout else "-raw", path, "-"]
    result = subprocess.run(command, check=True, capture_output=True)
    return result.stdout.decode("utf-8", "replace").split("\f")


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def normalize_number(token):
    if token.strip() in {"-", "–", "—"}:
        return None
    cleaned = token.strip().lstrip(".").replace(".", "").replace(" ", "")
    return int(cleaned) if cleaned else None


def _space_grouped_candidates(tokens, expected, relaxed=False):
    """Rebuild old BPS values such as ``1 310 739`` from raw PDF text.

    Old publications use spaces both as thousands separators and as column
    separators.  Enumerate the small set of valid groupings and let the
    printed total columns identify the most plausible eight-value row.
    """
    candidates = []

    def visit(position, values, implicit_gaps=0):
        remaining_values = expected - len(values)
        remaining_tokens = len(tokens) - position
        if remaining_values == 0:
            if remaining_tokens == 0:
                candidates.append((values, implicit_gaps))
            return
        if remaining_tokens > remaining_values * 3:
            return
        # Some early PDFs render genuinely blank cells without a dash.  Keep
        # an explicit candidate for such a missing column; sum consistency
        # determines its position.
        if remaining_tokens <= (remaining_values - 1) * 3:
            visit(position, values + [None], implicit_gaps + 1)
        if position >= len(tokens):
            return
        token = tokens[position]
        if token in {"-", "–", "—"}:
            visit(position + 1, values + [None], implicit_gaps)
            return
        for width in range(1, 5):
            group = tokens[position:position + width]
            if len(group) != width or any(not item.isdigit() for item in group):
                break
            if (width > 1 and not relaxed
                    and any(len(item) != 3 for item in group[1:])):
                break
            if len("".join(group)) > 9:
                break
            visit(position + width, values + [int("".join(group))], implicit_gaps)

    visit(0, [])
    return candidates


def _total_consistency(values):
    score = 0.0
    for component_indexes, total_index in [([0, 2, 4], 6), ([1, 3, 5], 7)]:
        total = values[total_index]
        if total is None:
            score += 1e12
            continue
        component_sum = sum(values[index] or 0 for index in component_indexes)
        score += abs(component_sum - total) / max(1, total)
    # Several space-grouped interpretations can satisfy the same sums.  The
    # correct one is also the one with realistic province-scale magnitudes;
    # this prevents ``55 222 272 483`` becoming 55 and 222,272,483.
    magnitude_penalty = sum(value or 0 for value in values) / 10_000_000_000
    return score + magnitude_penalty


def extract_values(text, expected=8):
    tokens = NUMBER.findall(text)
    # From 2023 onward BPS uses dots, so every regex token is one complete
    # value.  Leading dots are PDF watermark artefacts and are stripped by
    # normalize_number (for example ``.24.461`` -> 24461).
    if "." in text:
        if len(tokens) == expected:
            return [normalize_number(token) for token in tokens]
        # Diagonal BPS watermarks occasionally split one dotted value into
        # fragments (``6 5.231`` for 65,231).  Remove dots and use the printed
        # component/total identities to reassemble only these mixed rows.
        cleaned_tokens = NUMBER.findall(text.replace(".", ""))
        candidates = _space_grouped_candidates(
            cleaned_tokens, expected, relaxed=True)
        if not candidates:
            return None
        values, _ = min(
            candidates,
            key=lambda candidate: (_total_consistency(candidate[0])
                                   + candidate[1] * 0.001),
        )
        return values

    candidates = _space_grouped_candidates(tokens, expected)
    if not candidates:
        return None
    values, _ = min(
        candidates,
        key=lambda candidate: (_total_consistency(candidate[0])
                               + candidate[1] * 0.001),
    )
    return values


def province_row(line):
    normalized = re.sub(r"\s+", " ", line).strip()
    match = re.match(r"^(\d+)\s+(.+)$", normalized)
    if not match:
        return None
    rest = match.group(2)
    folded = rest.casefold()
    for province in sorted(PROVINCES, key=len, reverse=True):
        if folded.startswith(province.casefold() + " "):
            values = extract_values(rest[len(province):].strip())
            if values is not None:
                return CANONICAL.get(province, province), values
    return None


LAYOUT_NUMBER = re.compile(r"[-–—]|\.?\d{1,3}(?:(?:[ .])\d{3})*")


def _layout_labeled_rows(page):
    labeled = []
    for line in page.splitlines():
        number_match = re.match(r"^\s*\d+\s+", line)
        label_start = number_match.end() if number_match else None
        label = None
        if label_start is not None:
            remainder = line[label_start:]
            folded = remainder.casefold()
            for province in sorted(PROVINCES, key=len, reverse=True):
                if folded.startswith(province.casefold()):
                    label = CANONICAL.get(province, province)
                    value_start = label_start + len(province)
                    break
        else:
            national_match = re.match(r"^\s*INDONESIA\b", line, re.IGNORECASE)
            if national_match:
                label = "INDONESIA"
                value_start = national_match.end()
        if label is None:
            continue
        values = []
        for match in LAYOUT_NUMBER.finditer(line, value_start):
            values.append((match.end(), normalize_number(match.group())))
        if values:
            labeled.append((label, values))
    return labeled


def layout_table_values(page, expected=8):
    """Read fixed-width rows while preserving early-PDF blank columns."""
    labeled = _layout_labeled_rows(page)
    complete = [values for label, values in labeled
                if label != "INDONESIA" and len(values) == expected]
    if not complete:
        return {}, None
    endpoints = []
    for index in range(expected):
        points = sorted(values[index][0] for values in complete)
        endpoints.append(points[len(points) // 2])

    rows = {}
    national = None
    for label, positioned in labeled:
        if label == "INDONESIA" and len(positioned) != expected:
            continue
        values = [None] * expected
        valid = True
        for endpoint, value in positioned:
            index = min(range(expected), key=lambda item: abs(endpoints[item] - endpoint))
            if abs(endpoints[index] - endpoint) > 8 or values[index] is not None:
                valid = False
                break
            values[index] = value
        if not valid:
            continue
        if label == "INDONESIA":
            # Footer/title lines such as ``Indonesia 2017`` can align with
            # table columns after PDF extraction.  A genuine national row
            # satisfies the same component-total identities as province rows.
            if _total_consistency(values) <= 0.05:
                national = values
        else:
            rows[label] = values
    return rows, national


def table_year(page, allowed):
    # Some 2016--2022 tables place their title after the rows at the bottom of
    # the physical PDF page, so the complete page must be searched.
    matches = re.findall(
        r"(?:Producers|Pengusahaan)(?:\s*\([^)]*\))?"
        r"(?:\s+in\s+Indonesia)?(?:,?\s+(?:Tahun\s+)?)"
        r"(20\d{2})(\*{0,2})",
        page,
        flags=re.IGNORECASE,
    )
    for year, stars in reversed(matches):
        if int(year) in allowed:
            return int(year), stars
    return None, ""


def category_order(page):
    first_row = re.search(r"(?m)^\s*1\s+", page)
    header = page[:first_row.start()] if first_row else page
    header = re.sub(r"\s+", " ", header)
    positions = []
    for category, aliases in CATEGORY_ALIASES.items():
        matching = [header.find(label) for label in aliases
                    if header.find(label) >= 0]
        if matching:
            positions.append((min(matching), category))
    order = [category for _, category in sorted(positions)]
    return order if len(order) == 4 else None


def parse_page(page, publication, page_number, layout_page=None):
    year, stars = table_year(page, publication["data_years"])
    if year is None:
        return None
    if not any(label in page for label in ["Provinsi", "Propinsi"]):
        return None
    if "Produksi" not in page:
        return None
    order = category_order(page)
    if order is None:
        return None
    raw_rows = []
    for line in page.splitlines():
        parsed = province_row(line)
        if parsed is not None:
            raw_rows.append(parsed)
    rows = raw_rows
    layout_national = None
    if layout_page is not None:
        layout_rows, layout_national = layout_table_values(layout_page)
        # Raw order is resilient to diagonal watermarks; fixed-width layout
        # is only used to replace rows it could confidently position, thereby
        # retaining zero/blank provinces that layout extraction may omit.
        resolved = []
        seen = set()
        for province, raw_values in raw_rows:
            seen.add(province)
            layout_values = layout_rows.get(province)
            if (layout_values is not None
                    and _total_consistency(layout_values)
                    < _total_consistency(raw_values)):
                resolved.append((province, layout_values))
            else:
                resolved.append((province, raw_values))
        for province, layout_values in layout_rows.items():
            if province not in seen:
                resolved.append((province, layout_values))
        rows = resolved
    # Diagonal watermarks occasionally duplicate an entire rendered line.
    # Keep one province row, preferring the version that best satisfies the
    # three producer components = printed total identities.
    unique_rows = {}
    for province, values in rows:
        existing = unique_rows.get(province)
        if existing is None or _total_consistency(values) < _total_consistency(existing):
            unique_rows[province] = values
    rows = list(unique_rows.items())
    if len(rows) < 20:
        return None

    indonesia = layout_national
    if indonesia is None:
        for line in page.splitlines():
            match = re.match(r"^\s*INDONESIA\b", line, re.IGNORECASE)
            if match:
                candidate = extract_values(line[match.end():].strip())
                if (candidate is not None
                        and _total_consistency(candidate) <= 0.05):
                    indonesia = candidate
                    break
    table_match = re.search(r"(?m)^\s*(\d+\.\d+(?:\.\d+)?)\s*$", page)
    table_id = table_match.group(1) if table_match else None
    status = "final" if not stars else ("preliminary" if stars == "*" else "very_preliminary")
    observations = []
    for province, values in rows:
        for offset, category in enumerate(order):
            observations.append({
                "crop": publication["crop"], "product": publication["product"],
                "year": year, "province": province, "category": category,
                "area_ha": values[offset * 2],
                "production_tonnes": values[offset * 2 + 1],
                "data_status": status, "publication_id": publication["id"],
                "source_page": page_number, "source_table": table_id,
            })
    national = None
    if indonesia:
        national = {
            category: {"area_ha": indonesia[i * 2],
                       "production_tonnes": indonesia[i * 2 + 1]}
            for i, category in enumerate(order)
        }
    return observations, national


SCHEMA = """
CREATE TABLE publications (
  publication_id TEXT PRIMARY KEY, crop TEXT, publication_year INTEGER,
  product TEXT, page_url TEXT, local_path TEXT, sha256 TEXT, page_count INTEGER
);
CREATE TABLE observations (
  crop TEXT, product TEXT, year INTEGER, province TEXT, category TEXT,
  area_ha REAL, production_tonnes REAL, data_status TEXT,
  publication_id TEXT, source_page INTEGER, source_table TEXT,
  PRIMARY KEY (publication_id, year, province, category)
);
CREATE TABLE national_totals (
  crop TEXT, product TEXT, year INTEGER, category TEXT,
  area_ha REAL, production_tonnes REAL, data_status TEXT,
  publication_id TEXT, source_page INTEGER,
  PRIMARY KEY (publication_id, year, category)
);
CREATE TABLE audit_issues (
  severity TEXT, publication_id TEXT, year INTEGER, check_name TEXT,
  province TEXT, detail TEXT
);
CREATE TABLE climate_observations (
  crop TEXT, year INTEGER, province TEXT, window TEXT,
  window_start TEXT, window_end_exclusive TEXT, metric TEXT, value REAL,
  source TEXT, scale_m INTEGER, extracted_at TEXT,
  PRIMARY KEY (crop, year, province, window, metric)
);
"""


def load_climate(connection):
    if not os.path.exists(CLIMATE_CSV):
        return 0
    with open(CLIMATE_CSV, encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    connection.executemany(
        "INSERT INTO climate_observations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [(row["crop"], int(row["year"]), row["province"], row["window"],
          row["window_start"], row["window_end_exclusive"], row["metric"],
          float(row["value"]), row["source"], int(row["scale_m"]),
          row["extracted_at"]) for row in rows],
    )
    connection.commit()
    return len(rows)


def audit(connection):
    connection.execute("DELETE FROM audit_issues")
    keys = connection.execute(
        "SELECT DISTINCT publication_id, year FROM observations").fetchall()
    for publication_id, year in keys:
        rows = connection.execute(
            "SELECT province, category, area_ha, production_tonnes FROM observations "
            "WHERE publication_id=? AND year=?", (publication_id, year)).fetchall()
        provinces = sorted({row[0] for row in rows})
        by_key = {(row[0], row[1]): row[2:] for row in rows}
        for province in provinces:
            total = by_key.get((province, "total"))
            parts = [by_key.get((province, category)) for category in
                     ["government_estates", "private_estates", "smallholders"]]
            if total and all(part is not None for part in parts):
                for index, metric in enumerate(["area", "production"]):
                    observed = total[index]
                    if observed is None:
                        continue
                    component_sum = sum(part[index] or 0 for part in parts)
                    if abs(component_sum - observed) > max(2, observed * 0.0001):
                        connection.execute(
                            "INSERT INTO audit_issues VALUES (?,?,?,?,?,?)",
                            ("warning", publication_id, year, "category_sum_" + metric,
                             province, "components={} total={}".format(
                                 component_sum, observed)))

        for metric, column in [("area", "area_ha"),
                               ("production", "production_tonnes")]:
            summed = connection.execute(
                "SELECT SUM(COALESCE({},0)) FROM observations WHERE "
                "publication_id=? AND year=? AND category='total'".format(column),
                (publication_id, year)).fetchone()[0]
            national = connection.execute(
                "SELECT {} FROM national_totals WHERE publication_id=? AND year=? "
                "AND category='total'".format(column), (publication_id, year)).fetchone()
            if national and national[0] is not None:
                difference = summed - national[0]
                if abs(difference) > max(5, national[0] * 0.0002):
                    connection.execute(
                        "INSERT INTO audit_issues VALUES (?,?,?,?,?,?)",
                        ("warning", publication_id, year, "province_sum_" + metric,
                         None, "province_sum={} national={} difference={}".format(
                             summed, national[0], difference)))
    connection.commit()


def main():
    os.makedirs(DATA, exist_ok=True)
    if os.path.exists(DATABASE):
        os.unlink(DATABASE)
    connection = sqlite3.connect(DATABASE)
    connection.executescript(SCHEMA)
    failures = []
    for publication in PUBLICATIONS:
        path = os.path.join(RAW, publication["crop"], publication["id"] + ".pdf")
        if not os.path.exists(path):
            failures.append(publication["id"] + ": source PDF missing")
            continue
        pages = pdf_pages(path)
        layout_pages = pdf_pages(path, layout=True)
        connection.execute(
            "INSERT INTO publications VALUES (?,?,?,?,?,?,?,?)",
            (publication["id"], publication["crop"], publication["publication_year"],
             publication["product"], publication["page_url"], path, digest(path),
             len(pages)))
        found = set()
        for page_number, page in enumerate(pages, start=1):
            layout_page = layout_pages[page_number - 1] if page_number <= len(layout_pages) else None
            parsed = parse_page(page, publication, page_number, layout_page)
            if parsed is None:
                continue
            observations, national = parsed
            year = observations[0]["year"]
            if year in found:
                continue
            found.add(year)
            connection.executemany(
                "INSERT OR REPLACE INTO observations VALUES "
                "(:crop,:product,:year,:province,:category,:area_ha,"
                ":production_tonnes,:data_status,:publication_id,:source_page,"
                ":source_table)", observations)
            if national:
                for category, values in national.items():
                    connection.execute(
                        "INSERT OR REPLACE INTO national_totals VALUES (?,?,?,?,?,?,?,?,?)",
                        (publication["crop"], publication["product"], year, category,
                         values["area_ha"], values["production_tonnes"],
                         observations[0]["data_status"], publication["id"], page_number))
        missing = set(publication["data_years"]) - found
        for year in sorted(missing):
            failures.append("{}: table for {} not parsed".format(publication["id"], year))
    climate_rows = load_climate(connection)
    audit(connection)
    connection.commit()
    counts = connection.execute(
        "SELECT crop, MIN(year), MAX(year), COUNT(DISTINCT year), "
        "COUNT(DISTINCT province), COUNT(*) FROM observations GROUP BY crop").fetchall()
    issues = connection.execute("SELECT COUNT(*) FROM audit_issues").fetchone()[0]
    connection.close()
    print("[bps:db] " + DATABASE)
    for row in counts:
        print("[bps:db] {} years {}-{} ({}) provinces {} rows {}".format(
            row[0], row[1], row[2], row[3], row[4], row[5]))
    print("[bps:db] audit issues " + str(issues))
    if climate_rows:
        print("[bps:db] climate rows " + str(climate_rows))
    for failure in failures:
        print("[bps:db] WARNING " + failure)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
