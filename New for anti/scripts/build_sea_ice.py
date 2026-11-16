#!/usr/bin/env python3
"""Arctic sea ice extent from NSIDC's Sea Ice Index (G02135 v3).

The crop monitor reads the oceans through temperature; the Arctic is read
through ice. Two uses on this dashboard:
  - the Northern Sea Route: how much ice there is, against the same day in
    every year since 1979, says how long the summer route stays open;
  - context for mid-latitude winters, where the link to low ice is argued in
    the literature and is shown as a note, not as a model input.

Source (daily, satellite passive microwave, 10^6 km^2):
  https://noaadata.apps.nsidc.org/NOAA/G02135/north/daily/data/N_seaice_extent_daily_v3.0.csv
The 1981-2010 baseline is computed here from the same file, by day of year,
which is what NSIDC's own climatology file is.

Usage:
    python3 build_sea_ice.py            # write public/data/sea_ice_v1.json
"""

import csv
import io
import json
import os
import statistics
import urllib.request
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "public", "data", "sea_ice_v1.json"))
URL = ("https://noaadata.apps.nsidc.org/NOAA/G02135/north/daily/data/"
       "N_seaice_extent_daily_v3.0.csv")
BASE = (1981, 2010)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "global-trade-dashboard"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8", "replace")


def parse(text):
    out = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 4:
            continue
        try:
            d = date(int(row[0]), int(row[1]), int(row[2]))
            v = float(row[3])
        except ValueError:
            continue
        if 0 < v < 30:
            out[d] = v
    return dict(sorted(out.items()))


def doy(d):
    """Day of year on a 365-day calendar (Feb 29 folded into Feb 28)."""
    n = d.timetuple().tm_yday
    if d.month > 2 and (d.year % 4 == 0 and (d.year % 100 != 0 or d.year % 400 == 0)):
        n -= 1
    return min(n, 365)


def nearest(daily, d, slack=1):
    """Value on d, or the closest day within `slack` (the record before 1988 is every other day)."""
    for k in range(slack + 1):
        for dd in (d - timedelta(days=k), d + timedelta(days=k)):
            if dd in daily:
                return daily[dd]
    return None


def main():
    daily = parse(fetch(URL))
    if not daily:
        raise SystemExit("NSIDC 파싱 실패")
    last = max(daily)
    v = daily[last]

    # Baseline by day of year.
    by_doy = {}
    for d, x in daily.items():
        if BASE[0] <= d.year <= BASE[1]:
            by_doy.setdefault(doy(d), []).append(x)
    clim = [round(statistics.fmean(by_doy.get(i, [float("nan")])), 3) if by_doy.get(i) else None
            for i in range(1, 366)]
    sd = [round(statistics.pstdev(by_doy[i]), 3) if len(by_doy.get(i, [])) > 2 else None
          for i in range(1, 366)]
    c = clim[doy(last) - 1]

    # Same calendar day in every year on record.
    same = []
    for y in range(daily and min(daily).year, last.year + 1):
        try:
            d = last.replace(year=y)
        except ValueError:
            d = last.replace(year=y, day=28)
        x = nearest(daily, d)
        if x is not None:
            same.append((y, round(x, 3)))
    lower = sum(1 for y, x in same if y != last.year and x < v)

    # Annual minimum (the September low) and maximum (the March high).
    years = sorted({d.year for d in daily})
    minima, maxima = [], []
    for y in years:
        vals = [(d, x) for d, x in daily.items() if d.year == y]
        if y == last.year and last < date(y, 9, 30):
            pass                                       # minimum not reached yet
        elif y > years[0] and len(vals) > 150:
            dmin, xmin = min(vals, key=lambda t: t[1])
            minima.append({"year": y, "min": round(xmin, 2), "date": dmin.isoformat()})
        if len(vals) > 150 and (y < last.year or last >= date(y, 4, 30)):
            dmax, xmax = max(vals, key=lambda t: t[1])
            maxima.append({"year": y, "max": round(xmax, 2), "date": dmax.isoformat()})
    rec = min(minima, key=lambda m: m["min"]) if minima else None
    sep_trend = None
    if len(minima) > 10:
        xs = [m["year"] for m in minima]
        ys = [m["min"] for m in minima]
        mx, my = statistics.fmean(xs), statistics.fmean(ys)
        slope = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / sum((a - mx) ** 2 for a in xs)
        early = statistics.fmean(ys[:10])
        sep_trend = {"per_decade_mkm2": round(slope * 10, 3),
                     "per_decade_pct_of_1980s": round(100 * slope * 10 / early, 1)}

    def year_series(y):
        return [[doy(d), round(x, 3)] for d, x in daily.items() if d.year == y]

    lowest_min = sorted(minima, key=lambda m: m["min"])[:5]
    doc = {
        "schema_version": "sea-ice-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "NSIDC Sea Ice Index v3 (G02135)",
        "source_url": URL,
        "unit": "백만 km²",
        "baseline": f"{BASE[0]}-{BASE[1]}",
        "latest": {
            "date": last.isoformat(),
            "extent": round(v, 3),
            "clim": c,
            "anomaly": round(v - c, 3) if c else None,
            "anomaly_pct": round(100 * (v - c) / c, 1) if c else None,
            "rank_low": lower + 1,
            "n_years": len(same),
            "since": same[0][0] if same else None,
            "rank_ko": (f"{last.month}월 {last.day}일 기준 {same[0][0]}년 이후 {len(same)}년 중 "
                        + ("가장 작음" if lower == 0 else f"{lower + 1}번째로 작음")),
        },
        "same_day": same,
        "clim_by_doy": clim,
        "clim_sd_by_doy": sd,
        "years": {str(y): year_series(y) for y in (last.year, last.year - 1, 2012) if y in years},
        "annual_min": minima,
        "annual_max": maxima,
        "record_min": rec,
        "lowest_minima": lowest_min,
        "september_trend": sep_trend,
        "note_ko": ("해빙 면적(extent)은 해빙 농도 15% 이상인 격자의 면적입니다. 9월이 연중 최소, "
                    "3월이 최대입니다. 북극항로(북동항로)는 보통 8~10월에 열립니다."),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    L = doc["latest"]
    print(f"{L['date']}  {L['extent']:.2f}  평년 {L['clim']:.2f}  {L['anomaly_pct']:+.1f}%  {L['rank_ko']}")
    if rec:
        print(f"최저 {rec['year']} {rec['min']}  · 9월 추세 {sep_trend}")


if __name__ == "__main__":
    main()
