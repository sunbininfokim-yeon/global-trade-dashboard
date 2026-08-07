"""Write Canada forecast JSON: SAD first, province fallback, else trend."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from .gov_outlooks import build_snapshot as build_gov_outlooks
from .predict import predict_one
from .regions import ALL, PROVINCE, SAD

HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DATA = os.path.abspath(os.path.join(HERE, "..", "..", "..", "public", "data"))
OUT = os.path.join(PUBLIC_DATA, "canada_yield_forecast.json")
GOV_OUT = os.path.join(PUBLIC_DATA, "canada_gov_outlooks.json")


def _as_trend(cfg, base: dict, note: str | None = None) -> dict:
    """Operational trend point; keep climate diagnostic fields intact."""
    used = {
        "label": cfg.label,
        "label_ko": cfg.label_ko,
        "crop": cfg.crop,
        "label_scale": "sad",
        **base,
    }
    used["operational_choice"] = "trend_only"
    used["point"] = used["trend"]
    risk = used.get("climate_risk") or {}
    if risk.get("reason_ko"):
        used["reason_ko"] = risk["reason_ko"]
    if note:
        used["note"] = note
    return used


def main() -> int:
    # Train artifacts must already exist (run canada.train first).
    results = {}
    for cfg in ALL:
        results[cfg.key] = predict_one(cfg)

    regions = {}
    skipped = {}
    hierarchy = []

    for cfg in SAD:
        sad = results[cfg.key]
        fb_key = cfg.province_fallback_key
        fb = results.get(fb_key, {}) if fb_key else {}

        if "error" in sad:
            # Short sample / no artifact → still try province track.
            if fb and "error" not in fb:
                if fb.get("operational_choice") == "ridge_weather":
                    choice = "province_weather_fallback"
                    used = {
                        "label": cfg.label,
                        "label_ko": cfg.label_ko,
                        "crop": cfg.crop,
                        "label_scale": "sad",
                        "fallback_from": fb_key,
                        **fb,
                        "operational_choice": "province_weather_fallback",
                        "note": (
                            f"SAD model missing ({sad['error']}); "
                            f"using province weather {fb_key}"),
                    }
                else:
                    choice = "trend"
                    used = _as_trend(
                        cfg, {**fb, "fallback_from": fb_key},
                        note=(
                            f"SAD model missing ({sad['error']}); "
                            f"province trend + climate diagnostic from {fb_key}"),
                    )
                regions[cfg.key] = used
            else:
                skipped[cfg.key] = sad["error"]
                choice = "missing"
                used = None
        elif sad.get("operational_choice") == "ridge_weather":
            choice = "sad_weather"
            used = {**{"label": cfg.label, "label_ko": cfg.label_ko,
                       "crop": cfg.crop, "label_scale": "sad"}, **sad}
            regions[cfg.key] = used
        else:
            # SAD climate lost → province weather, else SAD/province trend.
            # Keep weather_effect_pct / climate_risk as diagnostics.
            if (fb and "error" not in fb
                    and fb.get("operational_choice") == "ridge_weather"):
                choice = "province_weather_fallback"
                used = {
                    "label": cfg.label,
                    "label_ko": cfg.label_ko,
                    "crop": cfg.crop,
                    "label_scale": "sad",
                    "fallback_from": fb_key,
                    **fb,
                    "operational_choice": "province_weather_fallback",
                    "note": (
                        f"SAD climate skill failed; using province weather model "
                        f"{fb_key}"),
                }
                regions[cfg.key] = used
            else:
                choice = "trend"
                base = sad if "error" not in sad else fb
                if not base or "error" in base:
                    skipped[cfg.key] = (
                        (base or {}).get("error", "no trend base"))
                    used = None
                else:
                    used = _as_trend(cfg, base)
                    regions[cfg.key] = used

        hierarchy.append({
            "key": cfg.key,
            "resolution": choice,
            "beats_trend_sad": (
                False if "error" in sad
                else bool(sad.get("beats_trend"))),
            "province_fallback": cfg.province_fallback_key,
        })

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

    try:
        gov = build_gov_outlooks()
    except Exception as exc:  # noqa: BLE001
        gov = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "error": f"{type(exc).__name__}: {exc}",
            "cadence": [],
            "government_outlooks": [],
            "provincial_weekly_crop_reports": [],
        }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "country": "Canada",
        "season": datetime.now(timezone.utc).year,
        "method": (
            "SAD/CAR first (StatsCan 32-10-0002) with region-specific feature "
            "packs; province (32-10-0359) weather fallback; else log-linear trend. "
            "NASA POWER climate; forward-chaining skill gate ≥10%. "
            "Trend-only rows keep climate_risk (stance/gap/risks) for UI. "
            "Monthly refresh also scrapes AAFC/StatsCan outlooks + prairie "
            "weekly crop-report cadence."),
        "literature_note": (
            "ICCYF Chipanshi 2015 CAR R2 canola/wheat ~0.66-0.67; "
            "Morrison HSU@29.5C; Mkhabela SMOS excess moisture; "
            "MASC Excess Moisture (MB). Phase-2 uses SAD labels + POWER."),
        "hierarchy": hierarchy,
        "regions": regions,
        "skipped": skipped,
        "government_outlooks": gov.get("government_outlooks", []),
        "provincial_weekly_crop_reports": gov.get(
            "provincial_weekly_crop_reports", []),
        "gov_cadence": gov.get("cadence", []),
        "gov_notes_ko": gov.get("notes_ko"),
    }
    os.makedirs(PUBLIC_DATA, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    with open(GOV_OUT, "w", encoding="utf-8") as handle:
        json.dump(gov, handle, indent=2, ensure_ascii=False)

    n_wx = sum(1 for h in hierarchy if h["resolution"] in
               ("sad_weather", "province_weather_fallback"))
    n_tr = sum(1 for h in hierarchy if h["resolution"] == "trend")
    print(f"[forecast] SAD tracks: weather={n_wx} trend={n_tr} "
          f"missing={len(hierarchy) - n_wx - n_tr}", flush=True)
    for key, row in regions.items():
        print(f"[forecast] {key}: {row['point']:.0f} kg/ha "
              f"({row.get('operational_choice')})", flush=True)
    print(f"[forecast] wrote {OUT}", flush=True)
    print(f"[forecast] wrote {GOV_OUT}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
