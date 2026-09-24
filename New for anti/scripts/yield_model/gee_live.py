"""Earth Engine login and incremental seasonal collection shared by the
GEE-based country models (south_africa, ethiopia, uganda).

Login order:
  1. GEE_SERVICE_ACCOUNT_JSON  -- the service-account key JSON itself (CI secret)
  2. GOOGLE_APPLICATION_CREDENTIALS -- path to that key file (local .env)
  3. the credentials saved by `earthengine authenticate` (original local setup)
EE_PROJECT overrides each model's hard-coded project id, because a service
account can only bill Earth Engine calls to the project it belongs to.

Collection: the climate columns of every finished season are already in the
committed training table, so a weekly run only asks Earth Engine for the
newest seasons and copies the rest from that table. A full re-pull of 35-45
seasons one at a time is what `refresh=True` is for.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

import pandas as pd

# Seasons always re-read from Earth Engine: the current one and the one before
# it, so a window that was still filling (or awaiting ERA5-Land's lag) when the
# training table was written gets its final values.
RECENT_SEASONS = 2


def initialize(ee, default_project: str) -> None:
    project = os.environ.get("EE_PROJECT") or default_project
    key_json = os.environ.get("GEE_SERVICE_ACCOUNT_JSON", "").strip()
    key_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if key_json:
        email = json.loads(key_json)["client_email"]
        credentials = ee.ServiceAccountCredentials(email, key_data=key_json)
        ee.Initialize(credentials, project=project)
    elif key_path and Path(key_path).exists():
        email = json.loads(Path(key_path).read_text())["client_email"]
        credentials = ee.ServiceAccountCredentials(email, key_file=key_path)
        ee.Initialize(credentials, project=project)
    else:
        ee.Initialize(project=project)


def collect_incremental(
    fetch: Callable[[int], dict],
    start_year: int,
    end_year: int,
    training_csv: Path,
    refresh: bool = False,
) -> pd.DataFrame:
    """Fetch recent seasons from Earth Engine; copy older ones from training."""
    first_fresh = start_year if refresh else max(start_year, end_year - RECENT_SEASONS + 1)
    records = {}
    for year in range(first_fresh, end_year + 1):
        records[year] = fetch(year)
    columns = sorted({key for record in records.values() for key in record})

    copied = 0
    if not refresh and Path(training_csv).exists():
        history = pd.read_csv(training_csv)
        if set(columns) <= set(history.columns):
            history = history[history.year.between(start_year, first_fresh - 1)]
            for row in history[columns].dropna().to_dict("records"):
                row["year"] = int(row["year"])
                records[row["year"]] = row
                copied += 1

    for year in range(start_year, end_year + 1):
        if year not in records:
            records[year] = fetch(year)
    print(
        f"[climate] Earth Engine: {len(records) - copied} seasons fetched, "
        f"{copied} copied from {Path(training_csv).name}",
        flush=True,
    )
    frame = pd.DataFrame([records[year] for year in sorted(records)])
    frame["year"] = frame["year"].astype(int)
    return frame.reset_index(drop=True)
