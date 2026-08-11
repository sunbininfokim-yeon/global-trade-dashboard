#!/usr/bin/env python3
"""Temperature and rainfall for producing-region cities, against their own normals.

The panel showed a current temperature and nothing else. "27.4°C in Zhengzhou"
is not information for a crop monitor -- 27.4 in July is unremarkable and 27.4
in March is an event, and the reader has to know the local climate to tell which.
What matters is the departure from normal, and the same for rainfall, over the
window that has actually affected the crop.

So: the last 30 days of observations against the same 30 calendar days averaged
over the previous ten years, per city.

Computed here rather than in the browser. It is four requests per city across a
decade of daily records; doing that on every page load would be slow for the
reader and rude to a free API.

Source: Open-Meteo ERA5 archive (archive-api.open-meteo.com), open access.

Usage:
    python3 build_city_wx.py            # write public/data/city_wx_v1.json
    python3 build_city_wx.py --check    # fetch and report, write nothing
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DATA = os.path.abspath(os.path.join(HERE, "..", "public", "data"))
GLOBAL = os.path.join(PUBLIC_DATA, "climate_global_v1.json")
OUT = os.path.join(PUBLIC_DATA, "city_wx_v1.json")

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
WINDOW_DAYS = 30
NORMAL_YEARS = 10
# ERA5 lands about five days behind; asking for yesterday returns nulls.
LAG_DAYS = 6


def fetch(params):
    url = f"{ARCHIVE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "global-trade-dashboard"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def window_stats(lat, lon, start, end):
    """Mean temperature and total rainfall for one date range."""
    d = fetch({
        "latitude": lat, "longitude": lon,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "daily": "temperature_2m_mean,precipitation_sum",
        "timezone": "UTC",
    }).get("daily") or {}
    temps = [v for v in (d.get("temperature_2m_mean") or []) if v is not None]
    rain = [v for v in (d.get("precipitation_sum") or []) if v is not None]
    if not temps:
        return None
    return {
        "temp_mean": sum(temps) / len(temps),
        "precip_sum": sum(rain),
        "days": len(temps),
    }


def main():
    check = "--check" in sys.argv
    cities = (json.load(open(GLOBAL, encoding="utf-8")).get("cities") or [])
    if not cities:
        print("climate_global_v1.json 에 cities 없음", file=sys.stderr)
        return 1

    end = date.today() - timedelta(days=LAG_DAYS)
    start = end - timedelta(days=WINDOW_DAYS - 1)
    out = []

    for c in cities:
        lat, lon = c.get("lat"), c.get("lon")
        name = c.get("label_ko") or c.get("name")
        if lat is None or lon is None:
            continue

        cur = window_stats(lat, lon, start, end)
        if not cur:
            print(f"  {name}: 관측 없음", file=sys.stderr)
            continue

        # Same calendar window in each of the previous ten years. Comparing to a
        # rolling 30 days of last year would mix seasons; the point is "warm for
        # this time of year here".
        t_hist, p_hist = [], []
        for back in range(1, NORMAL_YEARS + 1):
            try:
                s = start.replace(year=start.year - back)
                e = end.replace(year=end.year - back)
            except ValueError:            # 2/29
                continue
            h = window_stats(lat, lon, s, e)
            if h:
                t_hist.append(h["temp_mean"])
                p_hist.append(h["precip_sum"])
            time.sleep(0.2)               # be polite to a free endpoint

        if not t_hist:
            continue
        t_norm = sum(t_hist) / len(t_hist)
        p_norm = sum(p_hist) / len(p_hist)

        out.append({
            "name": c.get("name"),
            "label_ko": name,
            "temp_c": round(cur["temp_mean"], 1),
            "temp_normal_c": round(t_norm, 1),
            "temp_anom_c": round(cur["temp_mean"] - t_norm, 1),
            "precip_mm": round(cur["precip_sum"], 1),
            "precip_normal_mm": round(p_norm, 1),
            # Percent, because 40mm short means very different things in Perth
            # and in São Paulo.
            "precip_anom_pct": (round((cur["precip_sum"] - p_norm) / p_norm * 100)
                                if p_norm > 1 else None),
            "normal_years": len(t_hist),
        })
        print(f"  {name:22} {out[-1]['temp_c']:>5}°C "
              f"({out[-1]['temp_anom_c']:+.1f})   "
              f"강수 {out[-1]['precip_mm']:>6.1f}mm "
              f"({out[-1]['precip_anom_pct']:+d}%)" if out[-1]["precip_anom_pct"] is not None
              else f"  {name}: 강수 평년값 부족")

    doc = {
        "schema_version": "city-wx-v1",
        "generated_at": date.today().isoformat(),
        "window": {"start": start.isoformat(), "end": end.isoformat(), "days": WINDOW_DAYS},
        "normal": f"직전 {NORMAL_YEARS}년 동일 기간 평균",
        "source": "Open-Meteo ERA5 archive",
        "source_url": ARCHIVE,
        "cities": out,
    }

    if check:
        print("(--check: 파일을 쓰지 않음)")
        return 0
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"→ {os.path.relpath(OUT, HERE)}  ({len(out)}개 도시)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
