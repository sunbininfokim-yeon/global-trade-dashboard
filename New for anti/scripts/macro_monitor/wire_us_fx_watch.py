#!/usr/bin/env python3
"""Wire real Treasury FX-watch criteria onto each country's us_fx_watch indicator.

us_fx_watch had been a demo/fixture_synth binary flag (관찰대상/해당없음) with a
random-walk history array -- no criteria breakdown, nothing tying it to an
actual Treasury determination. build_us_fx_watch.py has now scored the real
July 2026 report's Table 1 against the report's own thresholds; this grafts
that per-country scoring onto the indicator the drawer already knows how to
render (mmFxWatchView reads ind.criteria -- that UI shell existed already,
un-filled, specifically waiting for this).

Only the 13 of this dashboard's 19 non-US countries that are among Treasury's
20 largest trading partners get real criteria. The other 5 (HKG, RUS, KAZ,
ISR, ZAF) are not evaluated in the report at all -- Treasury covers its
largest trading partners by volume, and these did not make that list this
period. Their indicator is marked data_status "not_covered" with a reason
instead of carrying over the old demo flag, which would have implied a real
absence-of-findings rather than an absence of assessment.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "public" / "data"
PACK = ROOT / "macro_monitor_v1.json"
FXW = ROOT / "us_fx_watch_v1.json"

# This dashboard's iso3 -> Treasury's iso3 in the FX-watch data (only where
# they differ or where the dashboard's bloc needs the country-level record).
ISO_MAP = {
    "KOR": "KOR", "JPN": "JPN", "CHN": "CHN", "EMU": "EMU", "SGP": "SGP",
    "CHE": "CHE", "GBR": "GBR", "CAN": "CAN", "AUS": "AUS", "BRA": "BRA",
    "VNM": "VNM", "TWN": "TWN", "IND": "IND",
}
NOT_COVERED = {"HKG": "홍콩", "RUS": "러시아", "KAZ": "카자흐스탄", "ISR": "이스라엘", "ZAF": "남아공"}

STATUS_DISPLAY = {
    "manipulator": "환율조작국",
    "monitoring": "관찰대상",
    "none": "해당없음",
}


def main() -> int:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    fxw = json.loads(FXW.read_text(encoding="utf-8"))

    wired, skipped = [], []
    for c in pack["countries"]:
        ind = next((i for i in c["indicators"] if i["id"] == "us_fx_watch"), None)
        if ind is None:
            continue

        fx_iso = ISO_MAP.get(c["iso3"])
        if fx_iso and fx_iso in fxw["countries"]:
            row = fxw["countries"][fx_iso]
            ind["value"] = row["criteria_met_count"]
            ind["display"] = STATUS_DISPLAY[row["status"]]
            ind["display_chip"] = ind["display"]
            ind["status"] = row["status"]
            ind["criteria"] = row["criteria"]
            ind["criteria_met_count"] = row["criteria_met_count"]
            ind["asof"] = fxw["retrieved_at"]
            ind["observed_at"] = fxw["retrieved_at"]
            ind["source"] = fxw["source"]
            ind["source_url"] = fxw["source_url"]
            ind["review_period"] = fxw["review_period"]
            ind["data_status"] = "official_snapshot"
            ind["quality"] = "engine"
            ind["change_1m_pct"] = None
            ind["change_1y_pct"] = None
            ind.pop("history", None)  # the old random-walk series had no real meaning
            # Always overwritten, never left as-is: the field previously held
            # the old fixture's placeholder text ("fixture -- 반기 보고서 갱신
            # 필요"), which a country with no special note in the config would
            # otherwise have kept sitting next to data now marked official_snapshot.
            edition = fxw["source"].split("—")[-1].strip()
            ind["note_ko"] = row.get("note_ko") or f"재무부 {edition} 보고서 기준 3요건 평가입니다."
            if row["status"] == "manipulator":
                ind["manipulator_note_ko"] = fxw["manipulator_note_ko"]
            elif row["status"] == "monitoring":
                ind["monitoring_note_ko"] = fxw["monitoring_list_note_ko"]
            wired.append(c["iso3"])
        elif c["iso3"] in NOT_COVERED:
            ind["value"] = None
            ind["display"] = "평가대상 아님"
            ind["display_chip"] = ind["display"]
            ind["status"] = "not_covered"
            ind.pop("criteria", None)
            ind["asof"] = fxw["retrieved_at"]
            ind["source"] = fxw["source"]
            ind["source_url"] = fxw["source_url"]
            ind["data_status"] = "not_covered"
            ind["quality"] = "engine"
            ind["change_1m_pct"] = None
            ind["change_1y_pct"] = None
            ind.pop("history", None)
            ind["note_ko"] = f"{NOT_COVERED[c['iso3']]}은(는) 재무부가 평가하는 20대 교역국에 포함되지 않아 이 보고서의 평가 대상이 아닙니다."
            skipped.append(c["iso3"])

        # Chips carry the same fields the drawer's headline reads.
        for chips in (c.get("categories") or {}).values():
            for ch in chips:
                if ch.get("id") == "us_fx_watch":
                    for k in ("value", "display", "asof", "data_status", "source"):
                        ch[k] = ind.get(k)
                    ch.pop("history", None)
                    ch["change_1m_pct"] = None
                    ch["change_1y_pct"] = None

    PACK.write_text(json.dumps(pack, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")

    print(f"wired real criteria onto {len(wired)} countries: {sorted(wired)}")
    print(f"marked not_covered on {len(skipped)} countries: {sorted(skipped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
