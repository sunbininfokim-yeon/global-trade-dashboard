#!/usr/bin/env python3
"""Refresh climate_global_v1.json from NOAA, replacing the hardcoded seed.

The dashboard's global climate panel shipped with ONI, DMI and the Atlantic
anomaly written into the file by hand, carrying "(seed)" in the source label and
a note saying live refresh was pending. The yield pipelines meanwhile were
already pulling the same indices live -- india/collect.py and its siblings read
exactly these two URLs -- so the site was showing stale numbers next to models
trained on current ones.

Same sources as the pipelines, so the panel and the models cannot disagree:
  ONI  https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt
  DMI  https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data

Fields we cannot source live -- city temperatures, continental anomalies -- are
carried over from the existing file untouched rather than invented here.

Usage:
    python3 build_climate_global.py           # rewrite public/data/climate_global_v1.json
    python3 build_climate_global.py --check   # print what it would write
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "public", "data", "climate_global_v1.json"))

ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
DMI_URL = "https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data"
# Pacific Decadal Oscillation, ERSST v5 (NOAA NCEI), monthly since 1854.
PDO_URL = "https://www.ncei.noaa.gov/pub/data/cmb/ersst/v5/index/ersst.v5.pdo.dat"
PDO_SINCE = 1900

# NOAA's own thresholds: ±0.5 for an event, then weak / moderate / strong.
def enso_state(oni):
    a = abs(oni)
    if a < 0.5:
        return "중립", "Neutral"
    strength_ko = "약" if a < 1.0 else ("중" if a < 1.5 else ("강" if a < 2.0 else "매우 강"))
    strength_en = "weak" if a < 1.0 else ("moderate" if a < 1.5 else ("strong" if a < 2.0 else "very strong"))
    if oni <= -0.5:
        return f"라니냐 · {strength_ko}", f"La Niña {strength_en}"
    return f"엘니뇨 · {strength_ko}", f"El Niño {strength_en}"


def enso_history(rows, top=4):
    """Context for the latest value: past El Nino peaks and where it ranks.

    An episode is NOAA's definition: ONI >= +0.5 for at least five
    overlapping seasons in a row. The episode still running at the end of
    the record is left out of the peaks so the current one is compared with
    history, not with itself.
    """
    episodes, run = [], []
    for row in rows:
        if row[2] >= 0.5:
            run.append(row)
            continue
        if len(run) >= 5:
            episodes.append(run)
        run = []
    peaks = []
    for ep in episodes:
        s, y, v = max(ep, key=lambda r: r[2])
        # An NDJ/DJF peak belongs to the winter that started the year before.
        start = y - 1 if s in ("DJF", "JFM", "FMA") else y
        peaks.append({"label": f"{start}–{str(start + 1)[2:]}", "peak": round(v, 2), "season": f"{s} {y}"})
    peaks.sort(key=lambda p: -p["peak"])
    latest = rows[-1][2]
    higher = sum(1 for r in rows[:-1] if r[2] > latest)
    return {
        "since": rows[0][1],
        "seasons": len(rows),
        "rank_ko": (f"{rows[0][1]}년 관측 이래 가장 높음" if higher == 0
                    else f"{rows[0][1]}년 이후 {len(rows)}개 계절 중 {higher + 1}번째로 높음"),
        "rank": higher + 1,
        "top_peaks": peaks[:top],
        # NOAA strength bands, drawn as reference lines on the bars.
        "thresholds": [
            {"value": 0.5, "label_ko": "엘니뇨 기준"},
            {"value": 1.5, "label_ko": "강"},
            {"value": 2.0, "label_ko": "매우 강"},
            {"value": -0.5, "label_ko": "라니냐 기준"},
        ],
    }


SST_REGIONS = os.path.abspath(os.path.join(HERE, "..", "public", "data", "sst_regions_v1.json"))


def oisst_dmi():
    """DMI from the OISST boxes the SST refresh already keeps (west - east).

    Same boxes as the standard DMI (50-70E/10S-10N minus 90-110E/10S-0), but
    OISST is current to last month, where PSL's HadISST file runs months
    behind -- in Nov 2026 it still ended in May and read "neutral" while the
    dipole was already positive.
    """
    try:
        with open(SST_REGIONS, encoding="utf-8") as fh:
            regions = {r["id"]: dict(r["series"]) for r in json.load(fh)["regions"]}
        west, east = regions["iod_west"], regions["iod_east"]
    except (OSError, KeyError, ValueError):
        return []
    return [(m, round(west[m] - east[m], 2)) for m in sorted(west) if m in east]


def iod_history(rows, top=4):
    """Past positive-IOD peaks (>= +0.4 for 3+ months running) and the rank."""
    episodes, run = [], []
    for row in rows + [("end", -9)]:
        if row[1] >= 0.4:
            run.append(row)
            continue
        if len(run) >= 3:
            episodes.append(run)
        run = []
    ongoing = rows and rows[-1][1] >= 0.4
    if ongoing and episodes and episodes[-1][-1] == rows[-1]:
        episodes = episodes[:-1]
    peaks = []
    for ep in episodes:
        m, v = max(ep, key=lambda r: r[1])
        peaks.append({"label": m[:4], "peak": v, "season": m})
    peaks.sort(key=lambda p: -p["peak"])
    latest = rows[-1][1]
    higher = sum(1 for r in rows[:-1] if r[1] > latest)
    since = rows[0][0][:4]
    return {
        "since": int(since),
        "rank": higher + 1,
        "rank_ko": (f"{since}년 관측 이래 가장 높음" if higher == 0
                    else f"{since}년 이후 {len(rows)}개월 중 {higher + 1}번째로 높음"),
        "top_peaks": peaks[:top],
        "thresholds": [
            {"value": 0.4, "label_ko": "양의 IOD 기준"},
            {"value": -0.4, "label_ko": "음의 IOD 기준"},
        ],
    }


def parse_pdo(text):
    """NCEI's table: year then twelve monthly values, 99.99 for not yet out."""
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2 or not parts[0].isdigit() or len(parts[0]) != 4:
            continue
        year = int(parts[0])
        for month, raw in enumerate(parts[1:13], start=1):
            try:
                v = float(raw)
            except ValueError:
                continue
            if abs(v) > 90:
                continue
            out.append((f"{year}-{month:02d}", round(v, 2)))
    return out


def pdo_history(rows, top=4):
    """Rank and past extremes on the side the PDO is on now.

    The PDO swings for decades, so the reference that matters is how deep
    past phases went: an episode is 12+ months running beyond +-0.5 on the
    current sign, its extreme is the peak. The episode still running is left
    out so the present is compared with history, not with itself.
    """
    latest = rows[-1][1]
    sign = -1 if latest < 0 else 1
    episodes, run = [], []
    for row in rows + [("end", 0.0)]:
        if row[1] * sign >= 0.5:
            run.append(row)
            continue
        if len(run) >= 12:
            episodes.append(run)
        run = []
    if episodes and episodes[-1][-1] == rows[-1]:
        episodes = episodes[:-1]
    peaks = []
    for ep in episodes:
        m, v = max(ep, key=lambda r: r[1] * sign)
        peaks.append({"label": m[:4], "peak": v, "season": m})
    peaks.sort(key=lambda p: -p["peak"] * sign)
    beyond = sum(1 for r in rows[:-1] if r[1] * sign > latest * sign)
    word = "낮음" if sign < 0 else "높음"
    since = rows[0][0][:4]
    return {
        "since": int(since),
        "rank": beyond + 1,
        "rank_ko": (f"{since}년 이후 가장 {word}" if beyond == 0
                    else f"{since}년 이후 {len(rows)}개월 중 {beyond + 1}번째로 {word}"),
        "peak_word_ko": "최저" if sign < 0 else "최고",
        "top_peaks": peaks[:top],
        "thresholds": [
            {"value": 0.5, "label_ko": "양의 PDO 기준"},
            {"value": -0.5, "label_ko": "음의 PDO 기준"},
            {"value": -1.5, "label_ko": "강한 음"},
        ],
    }


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "global-trade-dashboard"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def parse_oni(text):
    """CPC's table: SEAS YR TOTAL ANOM, one row per overlapping 3-month season."""
    rows = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            rows.append((parts[0], int(parts[1]), float(parts[3])))
        except ValueError:
            continue
    return rows


def parse_dmi(text):
    """PSL's grid: year followed by twelve monthly values, -9999 for missing."""
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 13:
            continue
        try:
            year = int(parts[0])
        except ValueError:
            continue
        for month, raw in enumerate(parts[1:13], start=1):
            try:
                v = float(raw)
            except ValueError:
                continue
            if v < -900:
                continue
            out.append((year, month, v))
    return out


def main():
    check = "--check" in sys.argv
    with open(OUT, encoding="utf-8") as fh:
        doc = json.load(fh)

    # --- ENSO -------------------------------------------------------------
    oni_rows = parse_oni(fetch(ONI_URL))
    if not oni_rows:
        print("ONI 파싱 실패 — 기존 값 유지", file=sys.stderr)
        return 1
    latest = oni_rows[-1]
    recent = oni_rows[-12:]
    ko, en = enso_state(latest[2])
    doc["enso"] = {
        "index": "Niño 3.4 ONI",
        "source": "NOAA CPC (live)",
        "source_url": ONI_URL,
        "season": latest[0],
        "latest_c": round(latest[2], 2),
        "state_ko": ko,
        "state_en": en,
        # Persistence probability is a CPC forecast product, not in this file.
        # Better absent than carried over from a seed and read as current.
        "prob_continue_pct": None,
        "series": [
            {"label": f"{str(y)[2:]}-{s}", "oni": round(v, 2)} for s, y, v in recent
        ],
        "history": enso_history(oni_rows),
    }

    # --- IOD --------------------------------------------------------------
    oisst = oisst_dmi()
    dmi_rows = parse_dmi(fetch(DMI_URL))
    if oisst and (not dmi_rows or oisst[-1][0] > f"{dmi_rows[-1][0]}-{dmi_rows[-1][1]:02d}"):
        m, v = oisst[-1]
        doc["iod"] = {
            "index": "Indian Ocean Dipole DMI (OISST)",
            "source": "NOAA OISST v2.1",
            "source_url": "https://psl.noaa.gov/data/gridded/data.noaa.oisst.v2.highres.html",
            "latest": v,
            "as_of": m,
            "state_ko": "양성 (Positive)" if v >= 0.4 else (
                "음성 (Negative)" if v <= -0.4 else "중립"),
            "note_ko": "양의 IOD는 호주 밀·인니 팜유 쪽 가뭄, 동아프리카 다우와 연동되는 경우가 많음",
            "series": [{"label": f"{mm[2:4]}-{mm[5:]}", "dmi": vv} for mm, vv in oisst[-12:]],
            "history": iod_history(oisst),
        }
    elif dmi_rows:
        y, m, v = dmi_rows[-1]
        doc["iod"] = {
            "index": "Indian Ocean Dipole DMI",
            "source": "NOAA PSL / HadISST (live)",
            "source_url": DMI_URL,
            "latest": round(v, 2),
            "as_of": f"{y}-{m:02d}",
            "state_ko": "양성 (Positive)" if v >= 0.4 else (
                "음성 (Negative)" if v <= -0.4 else "중립"),
            "note_ko": doc.get("iod", {}).get("note_ko", ""),
        }

    # --- PDO --------------------------------------------------------------
    try:
        pdo_rows = [r for r in parse_pdo(fetch(PDO_URL)) if int(r[0][:4]) >= PDO_SINCE]
    except OSError as e:
        print(f"PDO 실패 — 기존 값 유지: {e}", file=sys.stderr)
        pdo_rows = []
    if pdo_rows:
        m, v = pdo_rows[-1]
        doc["pdo"] = {
            "index": "Pacific Decadal Oscillation (ERSST v5)",
            "source": "NOAA NCEI ERSST v5",
            "source_url": PDO_URL,
            "latest": v,
            "as_of": m,
            "state_ko": "양 (따뜻한 국면)" if v >= 0.5 else ("음 (차가운 국면)" if v <= -0.5 else "중립"),
            "note_ko": ("음의 PDO는 미 남부 대평원 가뭄·겨울밀 작황 부진, 라니냐 영향 강화와 "
                        "자주 겹칩니다. 수십 년 단위로 국면이 바뀝니다."),
            "series": [{"label": f"{mm[2:4]}-{mm[5:]}", "pdo": vv} for mm, vv in pdo_rows[-12:]],
            "history": pdo_history(pdo_rows),
        }

    doc["generated_at"] = datetime.now(timezone.utc).isoformat()
    doc["note"] = (
        "ENSO·IOD·PDO 는 NOAA 원본에서 실시간 갱신됩니다 (build_climate_global.py). "
        "도시 기온·대륙 편차 등 나머지 항목은 아직 seed 이며 갱신 예정입니다."
    )

    print(f"ONI {doc['enso']['season']}  {doc['enso']['latest_c']:+.2f}  {doc['enso']['state_ko']}")
    if doc.get("pdo"):
        print(f"PDO {doc['pdo']['as_of']}  {doc['pdo']['latest']:+.2f}  {doc['pdo']['state_ko']}")
    if dmi_rows:
        print(f"DMI {doc['iod']['as_of']}  {doc['iod']['latest']:+.2f}  {doc['iod']['state_ko']}")
    if check:
        print("(--check: 파일을 쓰지 않음)")
        return 0

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"→ {os.path.relpath(OUT, HERE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
