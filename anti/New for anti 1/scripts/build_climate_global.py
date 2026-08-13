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

# NOAA's own thresholds: ±0.5 for an event, then weak / moderate / strong.
def enso_state(oni):
    a = abs(oni)
    if a < 0.5:
        return "중립", "Neutral"
    strength_ko = "약" if a < 1.0 else ("중" if a < 1.5 else "강")
    strength_en = "weak" if a < 1.0 else ("moderate" if a < 1.5 else "strong")
    if oni <= -0.5:
        return f"라니냐 · {strength_ko}", f"La Niña {strength_en}"
    return f"엘니뇨 · {strength_ko}", f"El Niño {strength_en}"


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
    }

    # --- IOD --------------------------------------------------------------
    dmi_rows = parse_dmi(fetch(DMI_URL))
    if dmi_rows:
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

    doc["generated_at"] = datetime.now(timezone.utc).isoformat()
    doc["note"] = (
        "ENSO·IOD 는 NOAA 원본에서 실시간 갱신됩니다 (build_climate_global.py). "
        "도시 기온·대륙 편차 등 나머지 항목은 아직 seed 이며 갱신 예정입니다."
    )

    print(f"ONI {doc['enso']['season']}  {doc['enso']['latest_c']:+.2f}  {doc['enso']['state_ko']}")
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
