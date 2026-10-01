"""Rebuild a per-season climate table without re-reading every past season.

The climate columns of finished seasons are already in each model's committed
training table, so a weekly run only recomputes the newest seasons and copies
the rest. Rows are copied only when the table was built from the same climate
source (`climate_source` column; tables without it predate the tag and came
from Google Earth Engine), so two sources never mix in one training table.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd

# Seasons always recomputed: the current one and the one before it, so a
# window that was still filling when the table was written gets final values.
RECENT_SEASONS = 2


def collect_incremental(
    fetch: Callable[[int], dict],
    start_year: int,
    end_year: int,
    training_csv: Path,
    source: str,
    refresh: bool = False,
) -> pd.DataFrame:
    first_fresh = start_year if refresh else max(start_year, end_year - RECENT_SEASONS + 1)
    records = {year: fetch(year) for year in range(first_fresh, end_year + 1)}
    columns = sorted({key for record in records.values() for key in record})

    copied = 0
    if not refresh and Path(training_csv).exists():
        history = pd.read_csv(training_csv)
        tag = history.get("climate_source", pd.Series("gee", index=history.index)).fillna("gee")
        history = history[tag.eq(source) & history.year.between(start_year, first_fresh - 1)]
        if set(columns) <= set(history.columns):
            for row in history[columns].dropna().to_dict("records"):
                row["year"] = int(row["year"])
                records[row["year"]] = row
                copied += 1

    for year in range(start_year, end_year + 1):
        if year not in records:
            records[year] = fetch(year)
    print(
        f"[climate] {source}: {len(records) - copied} seasons computed, "
        f"{copied} copied from {Path(training_csv).name}",
        flush=True,
    )
    frame = pd.DataFrame([records[year] for year in sorted(records)])
    frame["year"] = frame["year"].astype(int)
    frame["climate_source"] = source
    return frame.reset_index(drop=True)
