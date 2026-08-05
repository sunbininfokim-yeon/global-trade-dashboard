"""Extract report metadata and PSD tables from GAIN report pages and PDFs.

Every GAIN annual carries the same "Production, Supply and Distribution" grid:
three market years wide, each split into a USDA Official column and a New Post
column. Post leaves the column it is not revising at 0, so a 0 means "no value
here", not "zero tonnes".
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path

PDF_HREF_RE = re.compile(r'href="(/data/gain-report/\d{4}/\d{2}/[^"]+\.pdf)"')
TITLE_RE = re.compile(r"<title>([^<]+)</title>")
DESCRIPTION_RE = re.compile(r'<meta name="description" content="([^"]*)"')

# "Sugar, Centrifugal 2024/2025 2025/2026 2026/2027"
TABLE_HEAD_RE = re.compile(
    r"(?m)^(?P<name>.{2,60}?)\s+(?P<my1>\d{4}/\d{4})\s+(?P<my2>\d{4}/\d{4})\s+(?P<my3>\d{4}/\d{4})\s*$"
)
# "Production (1000 MT)  95900 95900 0 103000 0 95000"
ROW_RE = re.compile(
    r"(?m)^(?P<label>[A-Za-z][A-Za-z ,./%\-()0-9]*?)"
    r"\s*\((?P<unit>[^)]*)\)\s*"
    r"(?P<values>(?:-?[\d.]+\s+){5}-?[\d.]+)\s*$"
)
REPORT_NUMBER_RE = re.compile(r"Report Number:\s*([A-Z]{2}\d{4}-\d{4})")
REPORT_DATE_RE = re.compile(r"Date:\s*([A-Z][a-z]+ \d{1,2}, \d{4})")


@dataclass
class Series:
    """One PSD metric across the three market years in a report."""

    label: str
    unit: str
    # market year -> (usda_official, new_post)
    by_year: dict = field(default_factory=dict)

    def best(self, market_year: str):
        """Post's revision when it published one, else the official number."""
        pair = self.by_year.get(market_year)
        if not pair:
            return None
        official, post = pair
        if post:
            return post
        return official or None


@dataclass
class PsdTable:
    commodity: str
    market_years: list
    series: dict = field(default_factory=dict)

    def value(self, metric: str, market_year: str):
        row = self.series.get(metric)
        return row.best(market_year) if row else None


def page_pdf_path(page_html: str):
    match = PDF_HREF_RE.search(page_html)
    return match.group(1) if match else None


def page_title(page_html: str):
    match = TITLE_RE.search(page_html)
    if not match:
        return None
    # "Brazil: Sugar Annual | USDA Foreign Agricultural Service"
    return html.unescape(match.group(1)).split("|")[0].strip()


def page_summary(page_html: str):
    match = DESCRIPTION_RE.search(page_html)
    return html.unescape(match.group(1)).strip() if match else None


def pdf_text(path: Path) -> str:
    import pypdf

    reader = pypdf.PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def report_meta(text: str) -> dict:
    number = REPORT_NUMBER_RE.search(text)
    date = REPORT_DATE_RE.search(text)
    return {
        "report_number": number.group(1) if number else None,
        "report_date": date.group(1) if date else None,
    }


def parse_psd_tables(text: str) -> list:
    """Return every PSD grid found in the report text, in document order."""
    heads = list(TABLE_HEAD_RE.finditer(text))
    tables = []
    for index, head in enumerate(heads):
        start = head.end()
        end = heads[index + 1].start() if index + 1 < len(heads) else len(text)
        block = text[start:end]
        # The column header band must be present, otherwise this was prose that
        # happened to end in three market-year-looking tokens.
        if "Market Year Begins" not in block:
            continue

        market_years = [head.group("my1"), head.group("my2"), head.group("my3")]
        table = PsdTable(commodity=head.group("name").strip(), market_years=market_years)

        for row in ROW_RE.finditer(block):
            numbers = [float(v) for v in row.group("values").split()]
            label = " ".join(row.group("label").split())
            series = Series(label=label, unit=row.group("unit").strip())
            for slot, market_year in enumerate(market_years):
                official, post = numbers[slot * 2], numbers[slot * 2 + 1]
                series.by_year[market_year] = (official, post)
            table.series[label] = series

        if table.series:
            tables.append(table)
    return tables


def pick_table(tables: list, prefer: list):
    """Choose the commodity grid a report is really about.

    A sugar annual also carries the cane grid; the configured preference list
    decides which one represents the traded commodity.
    """
    for wanted in prefer:
        needle = wanted.lower()
        for table in tables:
            if needle in table.commodity.lower():
                return table
    return tables[0] if tables else None
