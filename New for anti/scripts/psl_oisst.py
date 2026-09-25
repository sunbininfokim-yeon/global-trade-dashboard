"""NOAA OISST v2.1 daily anomaly from NOAA PSL THREDDS (OPeNDAP).

Why not ERDDAP: from 2026-09-24 both NOAA CoastWatch West Coast ERDDAPs
(coastwatch.pfeg / upwell.pfeg) answer GitHub Actions runners with
"Your IP address is on this ERDDAP's request blacklist" -- the runners share
Azure address space, so someone else's traffic got the range listed. PSL
serves the same OISST v2.1 grid as one file per year and has no such block.

Differences from the ERDDAP product that matter downstream:
  * anomaly baseline is 1991-2020 (ERDDAP's was 1971-2000), so every value
    reads cooler by that difference; trends and differences are unaffected.
  * one file per year, so a time series is stitched from yearly requests.

Grid: lat -89.875..89.875 ascending (720), lon 0.125..359.875 (1440), 0.25°.
Only the stdlib, like the scripts that use it.
"""

import datetime as _dt
import re
import time
import urllib.error
import urllib.request

BASE = "https://psl.noaa.gov/thredds/dodsC/Datasets/noaa.oisst.v2.highres"
SOURCE = "NOAA OISST v2.1 (NOAA PSL THREDDS)"
BASELINE = "1991-2020 climatology (OISST v2.1, NOAA PSL)"
NLAT, NLON = 720, 1440
_EPOCH = _dt.date(1800, 1, 1)          # PSL time axis: days since 1800-01-01


def year_url(year):
    return f"{BASE}/sst.day.anom.{year}.nc"


def lat_index(lat):
    return min(NLAT - 1, max(0, round((lat + 89.875) / 0.25)))


def lon_index(lon):
    """lon in either -180..180 or 0..360."""
    return min(NLON - 1, max(0, round(((lon % 360) - 0.125) / 0.25)))


def lat_of(i):
    return -89.875 + 0.25 * i


def lon_of(j):
    return 0.125 + 0.25 * j


def _get(url, timeout=240, tries=3):
    req = urllib.request.Request(url, headers={"User-Agent": "global-trade-dashboard"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404 or attempt == tries - 1:
                raise
        except urllib.error.URLError:
            if attempt == tries - 1:
                raise
        time.sleep(5 * (attempt + 1))


def time_length(year):
    """Days present in that year's file (the current year is partial)."""
    dds = _get(year_url(year) + ".dds", timeout=60)
    m = re.search(r"time\[time = (\d+)\]", dds)
    if not m:
        raise RuntimeError(f"{year}: time 축을 DDS에서 찾지 못함")
    return int(m.group(1))


def latest_year():
    """(year, n_days) of the newest file; early January falls back a year."""
    y = _dt.date.today().year
    try:
        return y, time_length(y)
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        return y - 1, time_length(y - 1)


def fetch(year, t, i, j):
    """anom over index slices t, i, j given as (start, stride, stop), inclusive.

    Returns (dates, lats, lons, rows) where rows[(ti, ii)] is a list over lon;
    missing cells (land, ice) come back as None.
    """
    sl = lambda s: f"[{s[0]}:{s[1]}:{s[2]}]"
    url = f"{year_url(year)}.ascii?anom{sl(t)}{sl(i)}{sl(j)}"
    text = _get(url)

    # Layout (Grid): "anom.anom[T][Y][X]", then one line per [t][y] with X
    # comma-separated values, then "anom.time[T]" / "anom.lat[Y]" / "anom.lon[X]"
    # each followed by a line of values.
    rows = {}
    axes = {}
    lines = text.splitlines()
    k = 0
    while k < len(lines):
        line = lines[k].strip()
        m = re.match(r"^\[(\d+)\]\[(\d+)\],\s*(.*)$", line)
        if m:
            vals = []
            for v in m.group(3).split(","):
                v = v.strip()
                try:
                    f = float(v)
                except ValueError:
                    f = None
                vals.append(None if f is None or f != f or abs(f) > 100 else f)
            rows[(int(m.group(1)), int(m.group(2)))] = vals
        else:
            a = re.match(r"^anom\.(time|lat|lon)\[\d+\]$", line)
            if a and k + 1 < len(lines):
                axes[a.group(1)] = [float(x) for x in lines[k + 1].split(",") if x.strip()]
                k += 1
        k += 1

    if not rows or "time" not in axes:
        raise RuntimeError(f"OPeNDAP 응답 해석 실패: {url}\n{text[:300]}")
    dates = [_EPOCH + _dt.timedelta(days=d) for d in axes["time"]]
    return dates, axes.get("lat", []), axes.get("lon", []), rows
