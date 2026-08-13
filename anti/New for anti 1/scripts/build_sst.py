#!/usr/bin/env python3
"""Real gridded SST anomaly for the crop monitor, from NOAA OISST v2.1.

What this replaces
------------------
The map painted sixteen hand-placed basin circles whose values were *derived*
from three indices -- ONI, DMI, AMO. That could never show anything those three
do not describe. Two asked-for features were impossible by construction:

  the North Atlantic "blue blob" -- a cold patch amid a warm basin, so an AMO
      average paints over exactly the thing worth seeing
  the Mediterranean, Black Sea, Persian Gulf -- marginal seas no open-ocean
      index speaks for at all

Adding circles for them would have meant inventing numbers. This fetches
measurements instead.

Source
------
NOAA OISST v2.1 daily anomaly (0.25°) via NOAA CoastWatch ERDDAP, subsampled
server-side with a stride so we never download the full grid. ERDDAP serves the
axis in 0-360 longitude; output is converted to -180..180 for the map.

Resolution is a deliberate trade. Stride 6 gives 1.5°, about 11k wet points and
~250KB of JSON -- fine enough that the Mediterranean and the subpolar Atlantic
read as themselves, coarse enough to ship to a browser.

Usage:
    python3 build_sst.py            # write public/data/sst_anomaly_v1.json
    python3 build_sst.py --check    # fetch and report, write nothing
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "public", "data", "sst_anomaly_v1.json"))

ERDDAP = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/ncdcOisst21Agg.csv"
STRIDE = 6           # 0.25° * 6 = 1.5°
LAT_MIN, LAT_MAX = -78, 88


def build_url():
    # [(last)] rather than today's date: OISST runs about two weeks behind, and
    # asking for a date past the axis maximum is a 404, not an empty result.
    q = (f"anom[(last)][(0.0)]"
         f"[({LAT_MIN}):{STRIDE}:({LAT_MAX})]"
         f"[(0.125):{STRIDE}:(359.875)]")
    return f"{ERDDAP}?{urllib.parse.quote(q, safe='()[]:,.-')}"


def fetch_csv(url):
    req = urllib.request.Request(url, headers={"User-Agent": "global-trade-dashboard"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return r.read().decode("utf-8", "replace")


def main():
    check = "--check" in sys.argv
    text = fetch_csv(build_url())
    lines = text.splitlines()
    if not lines or not lines[0].startswith("time"):
        print("ERDDAP 응답이 CSV가 아님:\n" + text[:400], file=sys.stderr)
        return 1

    as_of = None
    points = []
    lo = hi = 0.0
    for line in lines[2:]:                       # row 0 header, row 1 units
        parts = line.split(",")
        if len(parts) < 5:
            continue
        value = parts[4].strip()
        if not value or value == "NaN":          # land, and ice-covered cells
            continue
        try:
            lat = float(parts[2])
            lon = float(parts[3])
            anom = float(value)
        except ValueError:
            continue
        as_of = as_of or parts[0][:10]
        if lon > 180:
            lon -= 360                            # ERDDAP axis is 0-360
        # One decimal is 0.1°C, finer than the colour ramp can show, and halves
        # the file next to full precision.
        points.append([round(lon, 2), round(lat, 2), round(anom, 1)])
        lo = min(lo, anom)
        hi = max(hi, anom)

    if not points:
        print("유효 격자점 없음", file=sys.stderr)
        return 1

    doc = {
        "schema_version": "sst-anomaly-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": as_of,
        "source": "NOAA OISST v2.1 (NOAA CoastWatch ERDDAP)",
        "source_url": ERDDAP,
        "variable": "sea surface temperature anomaly",
        "unit": "degree_C",
        "resolution_deg": round(0.25 * STRIDE, 2),
        "baseline": "1971-2000 climatology (OISST v2.1)",
        "count": len(points),
        "range": [round(lo, 1), round(hi, 1)],
        # [lon, lat, anomaly] rather than objects: 11k points, and the key names
        # would be most of the file.
        "format": "[lon, lat, anomaly_c]",
        "points": points,
    }

    print(f"{as_of}  {len(points):,}개 격자  {lo:+.1f}~{hi:+.1f}°C  "
          f"해상도 {doc['resolution_deg']}°")
    if check:
        print("(--check: 파일을 쓰지 않음)")
        return 0

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")
    print(f"→ {os.path.relpath(OUT, HERE)}  ({os.path.getsize(OUT)/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
