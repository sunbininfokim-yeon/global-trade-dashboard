"""
Write public/data/thailand_yield_forecast.json for the dashboard.

Usage: PYTHONPATH=. python3 -m thailand.run_forecast [season]

Emits Canada-style climate_risk + reason_ko so the UI can colour
favorable/unfavorable seasons and show why a crop is trend-only / reference.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from .collect import current_season, load_oni, oni_djf
from .predict import predict_one
from .regions import ALL

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(
    HERE, "..", "..", "..", "public", "data", "thailand_yield_forecast.json"))


def log(msg):
    print(f"[run] {msg}", flush=True)


def enso_label(oni):
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


def climate_stance(pct):
    """Map diagnostic weather gap → UI colour band (regionStressFromPct)."""
    if pct is None:
        return None, None
    if pct >= 2.0:
        return "favorable", "유리"
    if pct <= -2.0:
        return "unfavorable", "불리"
    return "near_neutral", "중립"


# Per-crop honesty copy (why skill fails / what data is missing).
CROP_STATUS_KO = {
    "central_ne_sugarcane": (
        "사탕수수는 천수답·ENSO 신호가 추세를 이김(검증 +16%). "
        "지금 패널이 애매해 보이면 생육창(1–10월)이 아직 덜 끝나 운영값은 추세만 "
        "쓰고, 기후 유리/불리는 진단 %로 표시한다. FAOSTAT 전국 라벨·OCSB 미연결."
    ),
    "chao_phraya_rice_wet": (
        "우기 쌀 기상(몬순 지연·ENSO)은 문헌상 먹힌다. "
        "막히는 쪽은 라벨: FAOSTAT 전국 쌀이 우기+건기를 섞어 산지 신호가 희석됨. "
        "OAE 우기/건기 분리 통계는 존재·구할 수 있으나 아직 파이프 미연결."
    ),
    "chao_phraya_rice_off": (
        "건기 쌀의 핵심은 RID 푸미폰·시리킷 Nov-1 저수·파종 허가(면적)다. "
        "데이터 '없음'이 아니라 Thaiwater/RID 포털은 있으나 공개 API·시계열을 "
        "아직 자동 수집하지 못해 상류 강수×ENSO 프록시만 씀 → 신뢰 낮음."
    ),
    "thailand_rubber": (
        "우천·채취일 가설은 문헌(PSU Songkhla)에 있으나, 전국 단수는 "
        "가격·채취강도·병이 더 커서 기상 잔차가 추세를 못 이김. "
        "기후 영향력이 낮은 작물로 표시 (색 없음)."
    ),
    "isan_cassava": (
        "카사바 모자이크병(CMD)·가루이가 공급을 좌우. "
        "기상만으로 단수 예측하지 않음 — 기후 영향력 낮은(병 지배) 참고 패널."
    ),
}


def build_climate_risk(r):
    """Canada-like climate_risk block for map colour + side copy."""
    key = r["key"]
    beats = bool(r.get("beats_trend"))

    # Rubber: climate residual does not beat trend — do not colour as 유리/불리.
    if key == "thailand_rubber":
        return {
            "stance": "low_climate_influence",
            "stance_ko": "기후영향 낮음",
            "diagnostic_gap_pct": None,
            "drivers": [],
            "risks": [],
            "favors": [],
            "reason_ko": CROP_STATUS_KO[key],
            "note": "weather_effect_pct null → map uses neutral/gray band",
        }

    pct = r.get("diagnostic_weather_effect_pct")
    if pct is None:
        pct = r.get("weather_effect_pct")
    stance, stance_ko = climate_stance(pct)

    parts = [CROP_STATUS_KO.get(key, "")]
    if r.get("weather_withheld_incomplete_season"):
        parts.append(
            f"생육창 관측 {100 * (r.get('critical_window_observed') or 0):.0f}% "
            f"— 운영 전망은 추세. 기후 진단은 추세 대비 {pct:+.1f}% ({stance_ko})."
        )
    elif beats:
        parts.append(f"기후 전망은 추세 대비 {pct:+.1f}% ({stance_ko}).")
    else:
        parts.append(
            f"검증 스킬 미달로 운영은 추세. 기후 진단 {pct:+.1f}% ({stance_ko})는 참고."
        )
    if r.get("dam_storage_is_proxy"):
        parts.append("댐 실측 미연결(프록시).")

    return {
        "stance": stance,
        "stance_ko": stance_ko,
        "diagnostic_gap_pct": None if pct is None else round(float(pct), 2),
        "drivers": [],
        "risks": [],
        "favors": [],
        "reason_ko": " ".join(p for p in parts if p).strip(),
        "note": (
            "diagnostic_gap_pct colours the map via weather_effect_pct. "
            "Operational point may stay on trend when season incomplete or "
            "skill gate fails."
        ),
    }


def region_payload(cfg, r, low_conf):
    risk = build_climate_risk(r)
    # Map colour: use diagnostic % when we claim climate still matters;
    # null when climate influence is the wrong story (rubber).
    if risk["stance"] == "low_climate_influence":
        map_pct = None
    else:
        map_pct = risk["diagnostic_gap_pct"]
        if map_pct is None and r.get("weather_effect_pct") is not None:
            map_pct = round(float(r["weather_effect_pct"]), 2)

    return {
        "label": r["label"],
        "label_ko": r["label_ko"],
        "unit": r["unit"],
        "point": round(r["point"], 1),
        "range_68": [round(r["range_68"][0], 1), round(r["range_68"][1], 1)],
        "range_95": [round(r["range_95"][0], 1), round(r["range_95"][1], 1)],
        "trend": round(r["trend"], 1),
        "weather_effect_pct": map_pct,
        "weather_model_point": round(
            r["trend"] * (1 + (r.get("diagnostic_weather_effect_pct") or 0) / 100),
            1),
        "operational_choice": (
            "trend_incomplete_season"
            if r.get("weather_withheld_incomplete_season")
            else ("ridge_weather" if r.get("beats_trend") else "trend_no_skill")
        ),
        "climate_risk": risk,
        "reason_ko": risk["reason_ko"],
        "last_actual": {
            "year": r["last_actual"]["year"],
            "yield": round(r["last_actual"]["yield"], 1),
            "provisional": r.get("labels_provisional", True),
        },
        "skill": {
            "beats_trend": r["beats_trend"],
            "recent_skill_vs_trend": r["skill_vs_trend"],
            "low_confidence": low_conf,
            "sigma_kg_ha": r["sigma"],
        },
        "weather_through": r["weather_through"],
        "critical_window_observed": r.get("critical_window_observed"),
        "season_complete": r.get("season_complete"),
        "provenance": {
            "doc": r["doc"],
            "caveat": r["caveat"],
            "non_weather_drivers": r.get("non_weather_drivers", ""),
            "label_source": r.get("label_source", ""),
            "labels_provisional": r.get("labels_provisional", True),
            "labels_season_imperfect": r.get("labels_season_imperfect", False),
            "dam_storage_is_proxy": r.get("dam_storage_is_proxy", False),
            "weather_withheld_incomplete_season": r.get(
                "weather_withheld_incomplete_season", False),
            "rid_dam_wired": False,
            "gee_used": False,
            "sources": r.get("sources", []),
            "status_ko": CROP_STATUS_KO.get(cfg.key, ""),
        },
        "crops": {
            cfg.crop: {
                "label_ko": r["label_ko"],
                "unit": r["unit"],
                "point": round(r["point"], 1),
                "range_68": [round(r["range_68"][0], 1),
                             round(r["range_68"][1], 1)],
                "range_95": [round(r["range_95"][0], 1),
                             round(r["range_95"][1], 1)],
                "weather_effect_pct": map_pct,
                "reason_ko": risk["reason_ko"],
                "skill": {
                    "beats_trend": r["beats_trend"],
                    "low_confidence": low_conf,
                },
            }
        },
    }


def main():
    override = int(sys.argv[1]) if len(sys.argv) > 1 else None
    oni = load_oni()
    season = override or current_season()

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "season": season,
        "country": "Thailand",
        "forecast_available": True,
        "source_note": (
            "Weather: NASA POWER daily (GWETROOT, TEMP, precip), ET0 FAO-56. "
            "ENSO: NOAA CPC ONI. Labels: FAOSTAT Thailand national Yield "
            "(Sugar cane / Rice / Natural rubber) unless labels_official "
            "override. RID Bhumibol–Sirikit Nov-1 storage NOT wired — "
            "off-season rice uses dam_recharge_proxy only. "
            "OAE wet/dry rice split and OCSB province cane not wired. "
            "Isan cassava is T2 stub (CMD disease-primary)."),
        "methodology_note": (
            "T1 from Regions/태국 + peer-reviewed Thai sources (see SOURCES.md). "
            "Each region carries reason_ko + climate_risk (favorable/unfavorable "
            "or low_climate_influence). Map colour uses weather_effect_pct."),
        "regions": {},
    }

    enso_name, enso_val = enso_label(oni_djf(oni, season))
    payload["climate_context"] = {
        "oni_djf": enso_val,
        "enso": enso_name,
    }

    any_ok = False
    for cfg in ALL:
        target = override or current_season(cfg)
        r = predict_one(cfg, target, oni)
        if not r or "error" in r:
            if r and "error" in r:
                log(f"{cfg.key}: {r['error']}")
            continue
        any_ok = True
        low_conf = (
            (not r["beats_trend"])
            or r.get("labels_provisional", True)
            or r.get("labels_season_imperfect", False)
            or r.get("dam_storage_is_proxy", False)
            or r.get("weather_withheld_incomplete_season", False)
        )
        payload["regions"][cfg.key] = region_payload(cfg, r, low_conf)
        risk = payload["regions"][cfg.key]["climate_risk"]
        log(f"{cfg.key}: point={r['point']:.0f} "
            f"map_pct={payload['regions'][cfg.key]['weather_effect_pct']} "
            f"stance={risk['stance']} low_conf={low_conf}")

    cassava_reason = CROP_STATUS_KO["isan_cassava"]
    payload["regions"]["isan_cassava"] = {
        "label": "Isan cassava (reference)",
        "label_ko": "이산 카사바",
        "unit": "kg/ha",
        "point": None,
        "weather_effect_pct": None,
        "forecast_available": False,
        "panel_mode": "reference",
        "reason_ko": cassava_reason,
        "climate_risk": {
            "stance": "low_climate_influence",
            "stance_ko": "기후영향 낮음",
            "diagnostic_gap_pct": None,
            "reason_ko": cassava_reason,
            "note": "CMD / whitefly — not a weather-yield crop in this panel",
        },
        "unavailable_reason": cassava_reason,
        "provenance": {
            "doc": "Regions/태국/북동부_이산/카사바",
            "status_ko": cassava_reason,
            "sources": [
                "Regions cassava guide — CMD mechanism",
                "OAE cassava statistics (not wired as climate yield)",
            ],
        },
        "crops": {
            "cassava": {
                "label_ko": "카사바",
                "point": None,
                "weather_effect_pct": None,
                "reason_ko": cassava_reason,
                "forecast_available": False,
                "skill": {"low_confidence": True, "beats_trend": False},
            }
        },
    }

    if not any_ok:
        payload["forecast_available"] = False
        payload["unavailable_reason"] = (
            "No trained models; run thailand.collect && thailand.train first.")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    log(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
