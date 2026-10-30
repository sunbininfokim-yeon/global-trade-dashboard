"""Summary of Economic Projections -- Table 1 of the Fed's projection materials.

Published with the March/June/September/December meetings (fomc_calendar_v1's
has_sep). Table 1 is the compact one: for each variable, the median /
central tendency / range across participants for each projected year plus the
longer run, with the previous SEP's projection right underneath ("June
projection"), and the "projected appropriate policy path" (the dot plot's
median) as a memo block. Only what the table states is stored -- no
interpolation, and a cell the Fed leaves blank (2029 in the prior SEP, the
longer run for core PCE) stays None.
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

_LABELS = {
    "change in real gdp": ("gdp", "실질 GDP 성장률"),
    "unemployment rate": ("unemployment", "실업률"),
    "pce inflation": ("pce", "PCE 물가"),
    "core pce inflation": ("core_pce", "근원 PCE 물가"),
    "federal funds rate": ("fed_funds_rate", "정책금리(점도표 중앙값)"),
}


def sep_url(meeting_date: str) -> str:
    return f"https://www.federalreserve.gov/monetarypolicy/fomcprojtabl{meeting_date.replace('-', '')}.htm"


def _num(text: str) -> float | None:
    text = text.strip()
    if not text or text in {"-", "—"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _cells(row) -> list[str]:
    return [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]


def parse_sep_summary(html: str, *, meeting_date: str, source_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        raise ValueError(f"{meeting_date}: no projection table at {source_url}")
    rows = table.find_all("tr")
    # The column count changes when a new projection year enters the table
    # (four years + longer run in September, three + longer run in the
    # March/June SEPs): the header row repeats the year labels once each for
    # median, central tendency and range, so its length says how many.
    years: list[str] | None = None
    for row in rows[:4]:
        cells = _cells(row)
        if len(cells) >= 6 and len(cells) % 3 == 0 and cells[0].isdigit():
            years = cells[: len(cells) // 3]
            break
    if not years:
        raise ValueError(f"{meeting_date}: could not read the projection year header at {source_url}")

    n = len(years)
    variables: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for row in rows:
        cells = _cells(row)
        if len(cells) != 1 + 3 * n:
            continue
        label = re.sub(r"\s+\d+$", "", cells[0]).strip()  # drop footnote marker
        values = cells[1:]
        medians = {y: _num(v) for y, v in zip(years, values[0:n])}
        if label.lower().endswith("projection"):
            if current is not None:
                current["prior_period"] = label.replace(" projection", "")
                current["prior_median"] = medians
            continue
        key = _LABELS.get(label.lower())
        if key is None:
            continue
        current = {
            "id": key[0],
            "label": label,
            "label_ko": key[1],
            "median": medians,
            "central_tendency": dict(zip(years, values[n : 2 * n])),
            "range": dict(zip(years, values[2 * n : 3 * n])),
            "prior_period": None,
            "prior_median": None,
        }
        variables.append(current)

    found = {v["id"] for v in variables}
    missing = {v[0] for v in _LABELS.values()} - found
    if missing:
        raise ValueError(f"{meeting_date}: SEP table missing {sorted(missing)} at {source_url}")
    return {
        "meeting_date": meeting_date,
        "source_url": source_url,
        "years": years,
        "variables": variables,
    }
