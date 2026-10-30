#!/usr/bin/env python3
"""Monthly SST anomaly history for the ocean regions the map lets you click.

The map shows one snapshot. A snapshot cannot say whether the North Atlantic
subpolar cold patch is a bad month or a thirty-year trend, and that distinction
is the whole reason the patch is interesting -- it is read as a fingerprint of a
weakening Atlantic overturning circulation, which is what moves European
rainfall and the monsoon that West African cocoa and Indian wheat depend on.

So each region gets a monthly series back to 1982, plus a trend fitted over it.

Only region means are stored, not grids. Ten regions x ~530 months is about
100KB; the equivalent gridded history would be tens of megabytes and says
nothing extra at this zoom.

Source: NOAA OISST v2.1 via NOAA PSL THREDDS (open access; see psl_oisst.py).

Usage:
    python3 build_sst_regions.py            # write public/data/sst_regions_v1.json
    python3 build_sst_regions.py --check    # fetch one region and report
"""

import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone

import psl_oisst

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "public", "data", "sst_regions_v1.json"))
N_MONTHS = None      # length of the monthly file's time axis, set in main()

START = "1982-01-01"

# lat/lon box per region, plus why a crop-and-trade dashboard cares.
# Longitudes are 0-360 to match the file axis.
REGIONS = [
    {
        "id": "subpolar_atlantic", "label_ko": "북대서양 아북극 (블루 블롭)",
        "lat": [45, 60], "lon": [-45 % 360, -20 % 360],
        "why_ko": "그린란드 남쪽 한랭역. 대서양 자오선 역전 순환(AMOC) 약화의 지표로 읽힙니다. "
                  "약해지면 유럽 강수와 겨울 한파 패턴이 바뀌어 EU 밀·유채에 영향합니다.",
        "affects": ["EU 밀", "유럽 유채", "북대서양 어장"],
    },
    {
        "id": "gulf_stream", "label_ko": "멕시코만류 (걸프스트림)",
        "lat": [32, 42], "lon": [-75 % 360, -55 % 360],
        "why_ko": "AMOC 의 표층 구간. 열을 북쪽으로 실어 나르는 쪽이라, 아북극 한랭역과 "
                  "함께 봐야 순환 전체의 상태가 읽힙니다.",
        "affects": ["미 동부 기후", "대서양 허리케인"],
    },
    {
        "id": "mediterranean", "label_ko": "지중해",
        "lat": [33, 44], "lon": [0, 30],
        "why_ko": "남유럽·북아프리카 강수의 수분 공급원. 수온이 높으면 겨울 폭우와 "
                  "여름 가뭄이 함께 강해집니다. MENA 밀 산지에 직결됩니다.",
        "affects": ["모로코·알제리 밀", "남유럽 올리브·듀럼밀"],
    },
    {
        "id": "nino34", "label_ko": "적도 동태평양 (Niño 3.4)",
        "lat": [-5, 5], "lon": [-170 % 360, -120 % 360],
        "why_ko": "ENSO 를 정의하는 해역. 엘니뇨는 인도네시아·호주 가뭄과 "
                  "아르헨티나 다우로, 라니냐는 그 반대로 나타납니다.",
        "affects": ["인니 팜유", "호주 밀", "아르헨 대두·옥수수", "브라질 커피"],
    },
    {
        "id": "west_pacific", "label_ko": "서태평양 웜풀",
        "lat": [-5, 15], "lon": [130, 160],
        "why_ko": "지구에서 가장 따뜻한 해역. 아시아 몬순의 에너지원이며 "
                  "Niño 3.4 와 반대 위상으로 움직이는 경향이 있습니다.",
        "affects": ["동남아 쌀", "인니 팜유·고무"],
    },
    {
        "id": "iod_west", "label_ko": "인도양 서 (IOD 서극)",
        "lat": [-10, 10], "lon": [50, 70],
        "why_ko": "IOD 양의 위상에서 따뜻해지는 쪽. 동아프리카 다우와 "
                  "호주 가뭄이 동반됩니다.",
        "affects": ["호주 밀", "동아프리카 커피"],
    },
    {
        "id": "iod_east", "label_ko": "인도양 동 (IOD 동극)",
        "lat": [-10, 0], "lon": [90, 110],
        "why_ko": "IOD 의 반대쪽 극. 서극과의 온도차가 곧 IOD 지수입니다.",
        "affects": ["인니 팜유", "호주 밀"],
    },
    {
        "id": "bay_of_bengal", "label_ko": "벵골만",
        "lat": [10, 22], "lon": [80, 95],
        "why_ko": "인도 몬순의 수분 공급원. 수온이 높으면 몬순 강수가 늘지만 "
                  "사이클론 강도도 함께 올라갑니다.",
        "affects": ["인도 쌀·밀", "방글라데시 쌀"],
    },
    {
        "id": "south_atlantic", "label_ko": "남대서양",
        "lat": [-35, -15], "lon": [-40 % 360, -10 % 360],
        "why_ko": "브라질 남부·아르헨티나 강수에 관여합니다.",
        "affects": ["브라질 대두·커피", "아르헨 팜파스"],
    },
    {
        "id": "north_pacific", "label_ko": "북태평양",
        "lat": [30, 50], "lon": [-180 % 360, -140 % 360],
        "why_ko": "북미 서해안 기압계와 미 중서부 겨울 기후에 영향합니다.",
        "affects": ["미국 겨울밀", "캐나다 캐놀라"],
    },
]


def fetch_series(region):
    """Monthly anomaly for one box: PSL monthly mean minus its 1991-2020 ltm.

    Two small requests per region. (Stitching the daily files year by year was
    tried first: ~40s per yearly request, 30 min per region -- a timeout.)
    """
    lat, lon = region["lat"], region["lon"]
    i = (psl_oisst.lat_index(lat[0]), 8, psl_oisst.lat_index(lat[1]))
    j = (psl_oisst.lon_index(lon[0]), 8, psl_oisst.lon_index(lon[1]))
    n = N_MONTHS
    dates, _, _, mean = psl_oisst.fetch_var(psl_oisst.MONTHLY_MEAN, "sst", (0, 1, n - 1), i, j)
    _, _, _, ltm = psl_oisst.fetch_var(psl_oisst.MONTHLY_LTM, "sst", (0, 1, 11), i, j)

    out = []
    for ti, d in enumerate(dates):
        if d.isoformat() < START:
            continue
        vals = []
        for (t, ii), row in mean.items():
            if t != ti:
                continue
            clim = ltm.get((d.month - 1, ii)) or []
            vals += [v - c for v, c in zip(row, clim) if v is not None and c is not None]
        if vals:
            out.append([d.strftime("%Y-%m"), round(statistics.fmean(vals), 2)])
    return out


def linear_trend(series):
    """Least-squares slope in °C per decade, over the whole record."""
    if len(series) < 24:
        return None
    xs = list(range(len(series)))
    ys = [v for _, v in series]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    return round(slope * 120, 3)          # per month -> per decade


def main():
    global N_MONTHS
    check = "--check" in sys.argv
    N_MONTHS = psl_oisst.time_length_of(psl_oisst.MONTHLY_MEAN)
    regions = REGIONS[:1] if check else REGIONS
    out = []

    for r in regions:
        series = fetch_series(r)
        if not series:
            print(f"  {r['label_ko']}: 데이터 없음", file=sys.stderr)
            continue
        recent = [v for _, v in series[-12:]]
        first10 = [v for _, v in series[:120]]
        out.append({
            "id": r["id"],
            "label_ko": r["label_ko"],
            "bounds": {"lat": r["lat"], "lon": [((x + 180) % 360) - 180 for x in r["lon"]]},
            "why_ko": r["why_ko"],
            "affects": r["affects"],
            "latest": series[-1][1],
            "latest_month": series[-1][0],
            "mean_12m": round(statistics.fmean(recent), 2),
            "trend_c_per_decade": linear_trend(series),
            # Against the record's own first decade, so "warmer than it was"
            # has a stated reference rather than an implied one.
            "vs_1980s": (round(statistics.fmean(recent) - statistics.fmean(first10), 2)
                         if first10 else None),
            "series": series,
        })
        print(f"  {r['label_ko']:26} {series[-1][1]:+.2f}°C  "
              f"추세 {out[-1]['trend_c_per_decade']:+.3f}°C/10년  "
              f"80년대 대비 {out[-1]['vs_1980s']:+.2f}°C  ({len(series)}개월)")
        time.sleep(0.5)

    doc = {
        "schema_version": "sst-regions-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": psl_oisst.SOURCE,
        "source_url": psl_oisst.MONTHLY_MEAN,
        "baseline": psl_oisst.BASELINE,
        "start": START,
        "note_ko": "해역 평균 월별 편차입니다. 격자가 아니라 박스 평균이므로 "
                   "해역 내부의 세부 구조는 표현하지 않습니다.",
        "regions": out,
    }

    if check:
        print("(--check: 파일을 쓰지 않음)")
        return 0
    if len(out) < len(REGIONS):
        # A region that came back empty would silently vanish from the map's
        # click targets. Keep last week's complete file instead.
        print(f"해역 {len(REGIONS) - len(out)}곳이 비어 있어 파일을 덮어쓰지 않음",
              file=sys.stderr)
        return 1
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")
    print(f"→ {os.path.relpath(OUT, HERE)}  ({os.path.getsize(OUT)/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
