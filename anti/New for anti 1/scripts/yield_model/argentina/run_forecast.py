"""
Produce the Argentina regional yield forecast the dashboard reads.

Usage: python3 -m argentina.run_forecast [season]

Writes public/data/argentina_yield_forecast.json with, per region-crop: the
season's central estimate and interval, the trend and weather components split
apart, the last published actual for comparison, and enough provenance (which
guide the methodology came from, what was substituted for missing data, how
much of the season is observed, measured skill) that a number on screen can be
judged rather than just believed.

Region-crops whose weather features do not beat a trend-only baseline are still
published, flagged `beats_trend: false` and given the trend's own error as
their band. Hiding them would misrepresent which of the six methodologies
actually carries at this resolution.

Two fields exist here that the Brazil payload has no use for:

  - `enso.iod_spring` and the shock flag, because 팜파스/옥수수 §2A's claim is
    specifically about the conjunction of a La Niña with a positive dipole, and
    a reader should be able to see whether that conjunction is live.
  - `abandonment`, the mean share of sown area written off before harvest.
    Argentine yield is computed over harvested area, so a drought severe enough
    to destroy fields partly removes itself from the target. Publishing the
    abandonment rate alongside the yield is what stops a reader from mistaking
    "yield held up" for "the crop was fine".
"""

import json
import os
import sys
from datetime import datetime, timezone

import pandas as pd

from .collect import current_season, load_dmi, load_oni
from .predict import predict_one
from .regions import ALL, BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training")
OUT = os.path.abspath(os.path.join(
    HERE, "..", "..", "..", "public", "data", "argentina_yield_forecast.json"))

# The dashboard reads `label_ko` first and falls back to `label`, so without
# these the panel shows "Pampas soybeans (BA + Córdoba + Santa Fe)" in the
# middle of a Korean page. (DATA_LAYOUT.md §2)
LABEL_KO = {
    "pampas_soja": "팜파스 대두",
    "pampas_maiz": "팜파스 옥수수",
    "pampas_trigo": "팜파스 밀",
    "norte_soja": "북부 NOA/NEA 대두",
    "chaco_algodon": "차코 면화",
    "tucuman_cana": "투쿠만 사탕수수",
}

# Why a region has no forecast, in the reader's language. A region that simply
# disappears from the panel reads as an oversight; a region that says why it
# declined reads as a decision, which is what it is. (DATA_LAYOUT.md §4)
SKIP_REASON_KO = {
    "pampas_trigo": (
        "밀은 10월 중순 개화기가 지나야 예측합니다. 수확량을 결정하는 서리·"
        "등숙 구간이 아직 오지 않아 이번 갱신에서는 기후 평년값으로 채워 넣지 "
        "않고 예측을 보류합니다. 11월부터 값이 나옵니다."),
    "tucuman_cana": (
        "MAGyP 작황 통계가 2004/05 캠페인에서 끊기고 1998~2002년이 결측이라, "
        "위성 기상 기록(1981~)과 겹치는 검증 가능 시즌이 부족합니다. FAOSTAT "
        "전국 시리즈를 대체재로 검토했으나 최근 10년이 단조 감소하는 면적 보고 "
        "아티팩트로 판정해 기각했습니다. EEAOC 투쿠만 시리즈를 연결하면 "
        "복구됩니다."),
}

# Displayed when a region is skipped for a reason not listed above -- a feature
# that failed to build, a feed outage. Better than showing the raw English.
GENERIC_SKIP_KO = "이번 갱신에서 필요한 입력을 만들지 못해 예측을 보류했습니다."


def log(msg):
    print(f"[run] {msg}", flush=True)


def last_actual(key):
    """Most recent published yield for a region, for the no-forecast card."""
    path = os.path.join(TRAINING, f"{key}.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path).dropna(subset=["yield_kg_ha"])
    if df.empty:
        return None
    row = df.iloc[-1]
    return {"year": int(row.year), "yield": float(row.yield_kg_ha)}


def enso_label(oni):
    """NOAA's convention: +/-0.5 for El Nino / La Nina, +/-1.5 for strong."""
    if oni is None:
        return "unknown", None
    if oni >= 1.5:
        return "strong El Nino", oni
    if oni >= 0.5:
        return "El Nino", oni
    if oni <= -1.5:
        return "strong La Nina", oni
    if oni <= -0.5:
        return "La Nina", oni
    return "neutral", oni


def main():
    override = int(sys.argv[1]) if len(sys.argv) > 1 else None
    oni, dmi = load_oni(), load_dmi()

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": override or current_season(),
        "country": "Argentina",
        "source_note": (
            "Yields: MAGyP Estimaciones Agrícolas, department level, "
            "aggregated as sum(production)/sum(harvested area). "
            "Weather: NASA POWER daily, production-weighted across each "
            "region's growing points, ET0 by FAO-56 Penman-Monteith. "
            "ENSO: NOAA CPC ONI. IOD: NOAA PSL HadISST DMI."),
        "methodology_note": (
            "One model per region-crop, each implementing the derived "
            "variables of its own guide in Regions/아르헨티나. Yield is a log "
            "technology trend plus a weather deviation; only the deviation is "
            "modelled. Skill is measured by forward chaining with the trend "
            "refit inside every fold, scored over the most recent folds. "
            "Yield is measured over harvested area, so seasons with heavy "
            "abandonment understate the damage -- see `abandonment`."),
        "regions": {},
    }

    predicted = {}
    skipped = []

    for cfg in ALL:
        # Resolved per crop: in August, wheat is a standing crop and the summer
        # crops are not yet sown, so they are not on the same harvest year.
        season = override or current_season(cfg)
        prior = predict_one(cfg, season - 1, oni, dmi, predicted)
        if prior and "error" not in prior:
            predicted[season - 1] = prior["point"]

        r = predict_one(cfg, season, oni, dmi, predicted)
        if r is None:
            skipped.append((cfg.key, "no trained model"))
            continue
        if "error" in r:
            skipped.append((cfg.key, r["error"]))
            continue

        label, value = enso_label(r.get("oni"))
        iod = r.get("iod")

        payload["regions"][cfg.key] = {
            "label": r["label"],
            "label_ko": LABEL_KO.get(cfg.key),
            "crop": cfg.crop,
            "provinces": cfg.provinces,
            "season": season,
            "unit": r["unit"],
            "point": round(r["point"], 1),
            "range_68": [round(r["range_68"][0], 1), round(r["range_68"][1], 1)],
            "range_95": [round(r["range_95"][0], 1), round(r["range_95"][1], 1)],
            "trend": round(r["trend"], 1),
            "weather_effect_pct": round(r["weather_effect_pct"], 2),
            "last_actual": r["last_actual"],
            "enso": {
                "state": label,
                "oni_growing_season": value,
                "iod_spring": round(iod, 3) if iod is not None else None,
                # The guide's own conjunction, surfaced so a reader can see
                # whether the shock condition is actually live this season.
                "la_nina_positive_iod": bool(
                    value is not None and iod is not None
                    and value < -0.5 and iod > 0.4),
            },
            "skill": {
                "method": ("forward chaining, trend refit inside each fold, "
                           "scored on the most recent folds"),
                "skill_vs_trend_only": round(r["skill_vs_trend"], 3),
                "weather_skill": round(r["weather_skill"], 3),
                "weather_driven": bool(r["weather_skill"] > 0),
                "non_weather_features": r["non_weather_features"],
                "beats_trend": r["beats_trend"],
                "sigma_kg_ha": round(r["sigma"], 1),
            },
            "provenance": {
                "guide": r["doc"],
                "caveat": r["caveat"],
                "non_weather_drivers": r["non_weather_drivers"],
                "weather_through": r["weather_through"],
                "critical_window_observed": (
                    round(r["critical_window_observed"], 3)
                    if r["critical_window_observed"] is not None else None),
                "season_complete": r["season_complete"],
                "notes": r["notes"],
            },
        }
        flag = "" if r["beats_trend"] else "  [no skill vs trend]"
        log(f"{cfg.key:22} {r['point']:9,.0f} {r['unit']} "
            f"({r['weather_effect_pct']:+.1f}% weather){flag}")

    # A skipped region is still published, as a card that states why it has no
    # number and shows the last published actual instead. DATA_LAYOUT.md §4 is
    # explicit that `point` must not be invented to fill the gap, and dropping
    # the region entirely -- which is what this did before -- makes a
    # deliberate abstention look like a missing model.
    for key, why in skipped:
        cfg = BY_KEY[key]
        payload["regions"][key] = {
            "label": cfg.label,
            "label_ko": LABEL_KO.get(key),
            "crop": cfg.crop,
            "provinces": cfg.provinces,
            "forecast_available": False,
            "reason_ko": SKIP_REASON_KO.get(key, GENERIC_SKIP_KO),
            "reason": why,
            "unit": "kg/ha",
            "last_actual": last_actual(key),
            "provenance": {"guide": cfg.doc, "caveat": cfg.caveat,
                           "non_weather_drivers": cfg.non_weather_drivers},
        }
        log(f"{key:22} no forecast -- {why}")
    payload["skipped"] = {k: w for k, w in skipped}

    if not payload["regions"]:
        log("nothing to write")
        return 1

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    log(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
