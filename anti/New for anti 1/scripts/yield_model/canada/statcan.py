"""Statistics Canada yield labels: province (32-10-0359) and SAD (32-10-0002)."""

from __future__ import annotations

import io
import json
import os
import re
import time
import urllib.request
import zipfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
WDS_PROVINCE = (
    "https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/"
    "32100359/en"
)
WDS_SAD = (
    "https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/"
    "32100002/en"
)
UA = {"User-Agent": "yield-model/1.0 (public climate-data client)"}
CACHE_DAYS = 14
YIELD_DISP = "Average yield (kilograms per hectare)"


def log(message: str) -> None:
    print(f"[statcan] {message}", flush=True)


def fetch(url: str, timeout: int = 300, attempts: int = 5) -> bytes:
    last = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:
            last = exc
            if attempt + 1 < attempts:
                time.sleep(min(2 ** attempt, 12))
    raise RuntimeError(f"failed after {attempts} attempts: {url}: {last}")


def _fresh(path: str, days: int = CACHE_DAYS) -> bool:
    return (os.path.exists(path)
            and time.time() - os.path.getmtime(path) < days * 86400)


def _download_table(wds_url: str, table_id: str) -> str:
    os.makedirs(CACHE, exist_ok=True)
    csv_path = os.path.join(CACHE, f"{table_id}.csv")
    if _fresh(csv_path):
        return csv_path
    log(f"resolving WDS {table_id}")
    meta = json.loads(fetch(wds_url, timeout=60).decode("utf-8"))
    if meta.get("status") != "SUCCESS":
        raise RuntimeError(f"StatsCan WDS failed: {meta}")
    payload = fetch(meta["object"], timeout=600)
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        member = next(name for name in zf.namelist()
                      if name.endswith(".csv") and "MetaData" not in name)
        with zf.open(member) as src, open(csv_path, "wb") as dst:
            dst.write(src.read())
    log(f"cached {csv_path}")
    return csv_path


def province_csv_path() -> str:
    return _download_table(WDS_PROVINCE, "32100359")


def sad_csv_path() -> str:
    return _download_table(WDS_SAD, "32100002")


def _yield_frame(path: str, geos: list[str], crop_label: str) -> pd.DataFrame:
    frame = pd.read_csv(path, low_memory=False)
    subset = frame[
        (frame["GEO"].isin(geos))
        & (frame["Type of crop"] == crop_label)
        & (frame["Harvest disposition"] == YIELD_DISP)
    ].copy()
    if subset.empty:
        return pd.DataFrame(columns=["year", "yield_kg_ha", "geo_used"])
    subset["year"] = pd.to_numeric(subset["REF_DATE"], errors="coerce")
    subset["yield_kg_ha"] = pd.to_numeric(subset["VALUE"], errors="coerce")
    subset = subset.dropna(subset=["year", "yield_kg_ha"])
    subset["year"] = subset["year"].astype(int)
    return subset[["year", "yield_kg_ha", "GEO"]].rename(columns={"GEO": "geo_used"})


def province_yield_series(geo: str, crop_label: str,
                          path: str | None = None) -> pd.DataFrame:
    path = path or province_csv_path()
    out = _yield_frame(path, [geo], crop_label)
    if out.empty:
        raise ValueError(f"no province yield for {geo} / {crop_label}")
    out = (out.sort_values("year")
           .drop_duplicates("year", keep="last")
           .reset_index(drop=True))
    out["target_status"] = out["year"].map(
        lambda y: "estimate" if y >= 2020 else "final")
    out["label_scale"] = "province"
    return out[["year", "yield_kg_ha", "target_status", "label_scale", "geo_used"]]


def _sk_aliases(region_no: int) -> list[str]:
    """Pre-2017 SAD name + post-2016 Census Division name for SK."""
    short = f"Small Area Data Region {region_no} - Saskatchewan"
    # Exact strings vary for 16 (two CDs). Match by startswith+contains.
    return [short]


def sad_yield_series(geo: str, crop_label: str, *,
                     path: str | None = None,
                     stitch_sk_cd: int | None = None) -> pd.DataFrame:
    """
    Small Area Data (CAR/CD) yield in kg/ha.

    For Saskatchewan, pass ``stitch_sk_cd=N`` to merge the 1976–2016 SAD
    series with the 2012– present Census Division series (prefer CD from 2017).
    """
    path = path or sad_csv_path()
    frame = pd.read_csv(path, low_memory=False)

    if stitch_sk_cd is not None:
        short = f"Small Area Data Region {stitch_sk_cd} - Saskatchewan"
        long_pat = (
            f"Small Area Data Region {stitch_sk_cd} - Saskatchewan "
            f"(corresponds to Census Division"
        )
        geos = [g for g in frame.GEO.dropna().unique()
                if g == short or str(g).startswith(long_pat)]
        if not geos:
            raise ValueError(f"no SK SAD/CD geos for region {stitch_sk_cd}")
        subset = _yield_frame(path, geos, crop_label)
        if subset.empty:
            raise ValueError(
                f"no SAD yield rows for SK region {stitch_sk_cd} / {crop_label}")
        short_rows = subset[subset.geo_used == short]
        long_rows = subset[subset.geo_used != short]
        early = short_rows[short_rows.year <= 2016]
        late = long_rows[long_rows.year >= 2017]
        ymax = int(subset.year.max())
        missing = set(range(2017, ymax + 1)) - set(late.year.tolist())
        fill = short_rows[short_rows.year.isin(missing)]
        out = pd.concat([early, late, fill], ignore_index=True)
    else:
        out = _yield_frame(path, [geo], crop_label)

    if out.empty:
        raise ValueError(f"no SAD yield for {geo} / {crop_label}")
    out = (out.sort_values("year")
           .drop_duplicates("year", keep="last")
           .reset_index(drop=True))
    out["target_status"] = out["year"].map(
        lambda y: "estimate" if y >= 2020 else "final")
    out["label_scale"] = "sad"
    return out[["year", "yield_kg_ha", "target_status", "label_scale", "geo_used"]]


# Back-compat alias used by collect.py
def workbook_csv_path() -> str:
    return province_csv_path()
