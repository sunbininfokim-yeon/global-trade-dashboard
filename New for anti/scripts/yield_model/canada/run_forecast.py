"""Write Canada forecast JSON: SAD first, province fallback, else trend."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from .predict import predict_one
from .regions import ALL, BY_KEY, PROVINCE, SAD

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(
    HERE, "..", "..", "..", "public", "data", "canada_yield_forecast.json"))


def main() -> int:
    # Train artifacts must already exist (run canada.train first).
    results = {}
    for cfg in ALL:
        result = predict_one(cfg)
        results[cfg.key] = result

    regions = {}
    skipped = {}
    hierarchy = []

    for cfg in SAD:
        sad = results[cfg.key]
        if "error" in sad:
            skipped[cfg.key] = sad["error"]
            choice = "missing"
            used = None
        elif sad.get("operational_choice") == "ridge_weather":
            choice = "sad_weather"
            used = {**{"label": cfg.label, "label_ko": cfg.label_ko,
                       "crop": cfg.crop, "label_scale": "sad"}, **sad}
            regions[cfg.key] = used
        else:
            # SAD climate lost → try province weather, else province/SAD trend
            fb_key = cfg.province_fallback_key
            fb = results.get(fb_key, {}) if fb_key else {}
            if fb and "error" not in fb and fb.get("operational_choice") == "ridge_weather":
                choice = "province_weather_fallback"
                used = {
                    "label": cfg.label,
                    "label_ko": cfg.label_ko,
                    "crop": cfg.crop,
                    "label_scale": "sad",
                    "fallback_from": fb_key,
                    **fb,
                    # Keep SAD identity but province weather point
                    "note": (
                        f"SAD climate skill failed; using province weather model "
                        f"{fb_key}"),
                }
                # Re-tag operational
                used["operational_choice"] = "province_weather_fallback"
                regions[cfg.key] = used
            else:
                choice = "trend"
                # Prefer SAD trend series if available, else province trend
                base = sad if "error" not in sad else fb
                if "error" in base:
                    skipped[cfg.key] = base.get("error", "no trend base")
                    used = None
                else:
                    used = {
                        "label": cfg.label,
                        "label_ko": cfg.label_ko,
                        "crop": cfg.crop,
                        "label_scale": cfg.label_scale,
                        **base,
                    }
                    used["operational_choice"] = "trend_only"
                    used["point"] = used["trend"]
                    used["weather_effect_pct"] = 0.0
                    regions[cfg.key] = used
        hierarchy.append({
            "key": cfg.key,
            "resolution": choice,
            "beats_trend_sad": (
                False if "error" in sad
                else bool(sad.get("beats_trend"))),
            "province_fallback": cfg.province_fallback_key,
        })

    # Also publish province tracks for dashboard completeness
    for cfg in PROVINCE:
        prov = results[cfg.key]
        if "error" in prov:
            skipped[cfg.key] = prov["error"]
            continue
        regions[cfg.key] = {
            "label": cfg.label,
            "label_ko": cfg.label_ko,
            "crop": cfg.crop,
            "label_scale": "province",
            **prov,
        }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "country": "Canada",
        "season": datetime.now(timezone.utc).year,
        "method": (
            "SAD/CAR first (StatsCan 32-10-0002) with region-specific feature "
            "packs; province (32-10-0359) weather fallback; else log-linear trend. "
            "NASA POWER climate; forward-chaining skill gate ≥10%."),
        "literature_note": (
            "ICCYF Chipanshi 2015 CAR R2 canola/wheat ~0.66-0.67; "
            "Morrison HSU@29.5C; Mkhabela SMOS excess moisture; "
            "MASC Excess Moisture (MB). Phase-2 uses SAD labels + POWER."),
        "hierarchy": hierarchy,
        "regions": regions,
        "skipped": skipped,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)

    n_wx = sum(1 for h in hierarchy if h["resolution"] in
               ("sad_weather", "province_weather_fallback"))
    n_tr = sum(1 for h in hierarchy if h["resolution"] == "trend")
    print(f"[forecast] SAD tracks: weather={n_wx} trend={n_tr} "
          f"missing={len(hierarchy) - n_wx - n_tr}", flush=True)
    for key, row in regions.items():
        print(f"[forecast] {key}: {row['point']:.0f} kg/ha "
              f"({row.get('operational_choice')})", flush=True)
    print(f"[forecast] wrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
