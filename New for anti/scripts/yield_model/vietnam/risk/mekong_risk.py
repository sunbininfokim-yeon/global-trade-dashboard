"""
Mekong Delta hydrology / salinity **risk monitor** (early-warning style).

This product does **not** claim yield skill vs trend. It surfaces open-data
proxies for dry-season freshwater push, coastal salt stress, and ENSO context.

Inputs (all labeled as proxies where not gauged):
  · NASA POWER precip / ET0 / GWETROOT at Mekong provinces + Pakse / Tan Chau
  · NOAA CPC ONI (DJF + lag-2 OND/NDJ)
  · Composite q_upstream_proxy (POWER stand-in for MRC Tan Chau Q — portal 403)

Skipped without auth / access:
  · MRC real discharge
  · Field EC / SIWRP alerts
  · Sentinel-1 / GEE planted-area or inundation

Usage (from scripts/yield_model):

    python3 -m vietnam.risk
    python3 -m vietnam.risk --year 2026
    python3 -m vietnam.risk --start-year 2000 --out ../../public/data/vietnam_mekong_risk_v1.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import date, datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from .. import climate as C
from ..collect import (
    current_season,
    load_oni,
    oni_djf,
    oni_lag2,
    point_weather,
    upstream_q_features,
)
from ..regions import (
    COAST_KM_THRESHOLD,
    MEKONG_ALL_PROVINCE_POINTS,
    MEKONG_UPSTREAM_POINTS,
    WS_DRY,
    WS_PEAK,
    WS_WET_PRIOR,
)

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
PUBLIC_DEFAULT = os.path.normpath(
    os.path.join(PKG, "..", "..", "..", "public", "data", "vietnam_mekong_risk_v1.json")
)

SCHEMA = "mekong_risk_v1"


def _finite(x: Any) -> bool:
    try:
        return x is not None and math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _clip01(x: float) -> float:
    return float(max(0.0, min(1.0, x)))


def _level(score: float) -> str:
    if score >= 75:
        return "high"
    if score >= 55:
        return "elevated"
    if score >= 35:
        return "watch"
    return "low"


def _enso_label(oni: float | None) -> str:
    if oni is None or not _finite(oni):
        return "unknown"
    v = float(oni)
    if v >= 1.5:
        return "strong_el_nino"
    if v >= 0.5:
        return "el_nino"
    if v <= -1.5:
        return "strong_la_nina"
    if v <= -0.5:
        return "la_nina"
    return "neutral"


def _z_to_risk_high_is_bad(z: float | None, scale: float = 1.5) -> float:
    """Map z-score where higher z = worse stress → 0–100."""
    if z is None or not _finite(z):
        return 50.0
    # z=+scale → ~84, z=-scale → ~16
    return 100.0 * _clip01(0.5 + 0.5 * (float(z) / scale))


def _z_to_risk_low_is_bad(z: float | None, scale: float = 1.5) -> float:
    """Map z-score where lower z = worse (dry / low Q) → 0–100."""
    if z is None or not _finite(z):
        return 50.0
    return 100.0 * _clip01(0.5 - 0.5 * (float(z) / scale))


def province_hydrology(daily: pd.DataFrame, year: int, point: dict,
                       oni_val: float, q_upstream: float | None) -> dict:
    dry_p = C.window_sum(daily, "precip", WS_DRY, year)
    wet_p = C.window_sum(daily, "precip", WS_WET_PRIOR, year)
    wd = C.water_deficit(daily, WS_DRY, year)
    sm = C.window_mean(daily, "gwetroot", WS_PEAK, year)
    spei4 = C.spei_like_min(daily, year, peak_months=(1, 2, 3, 4), timescale=4)
    spi_ws = C.spi_like_window(daily, WS_DRY, year)
    coast_km = float(point.get("coast_km", 50.0))
    salt = C.salinity_proxy(coast_km, dry_p, oni_val or 0.0, wet_p,
                            q_upstream=q_upstream)

    # Heuristic coastal stress 0–100 (proxy blend — not calibrated EC).
    salt_term = 100.0 * _clip01(salt["salt_proxy"] / 1.2)
    dry_term = _z_to_risk_low_is_bad(spi_ws)
    spei_term = _z_to_risk_low_is_bad(spei4)
    coastal_score = (
        0.45 * salt_term
        + 0.25 * dry_term
        + 0.20 * spei_term
        + 0.10 * (100.0 * salt["coastal_exposure"])
    )
    # Inland provinces: salinity channel muted; drought still counts.
    if coast_km > COAST_KM_THRESHOLD:
        coastal_score = 0.55 * dry_term + 0.35 * spei_term + 0.10 * salt_term

    flags: list[str] = []
    if coast_km <= COAST_KM_THRESHOLD and salt["salt_proxy"] >= 0.55:
        flags.append("high_salt_proxy")
    if _finite(spi_ws) and spi_ws <= -1.0:
        flags.append("dry_spi_ws")
    if _finite(spei4) and spei4 <= -1.0:
        flags.append("dry_spei4")
    if _finite(sm) and sm < 0.35:
        flags.append("low_rootzone_sm_proxy")

    return {
        "name": point["name"],
        "lat": point["lat"],
        "lon": point["lon"],
        "coast_km": coast_km,
        "zone": "coastal_salt_belt" if coast_km <= COAST_KM_THRESHOLD
                else "inland_freshwater",
        "precip_dry_ws_mm": _round(dry_p),
        "precip_wet_prior_mm": _round(wet_p),
        "wd_dry_ws_mm": _round(wd),
        "sm_peak_gwetroot": _round(sm, 3),
        "spi_ws": _round(spi_ws, 3),
        "spei4_ws_min": _round(spei4, 3),
        "salt_proxy": _round(salt["salt_proxy"], 4),
        "ec_proxy": _round(salt["ec_proxy"], 3),
        "ec_proxy_note": "scaled hydro proxy — NOT field ECe dS/m",
        "coastal_exposure": _round(salt["coastal_exposure"], 4),
        "coastal_stress_score_0_100": _round(coastal_score, 1),
        "risk_level": _level(coastal_score),
        "flags": flags,
    }


def _round(x: Any, nd: int = 2) -> float | None:
    if not _finite(x):
        return None
    return round(float(x), nd)


def _series_z(values: list[float], target: float | None) -> float | None:
    arr = [v for v in values if _finite(v)]
    if target is None or not _finite(target) or len(arr) < 8:
        return None
    a = np.asarray(arr, dtype=float)
    sd = float(a.std(ddof=0)) or 1.0
    return float((float(target) - float(a.mean())) / sd)


def build_history(dailies: dict, dailies_up: dict, oni: pd.DataFrame,
                  start_year: int, end_year: int) -> list[dict]:
    rows = []
    q_hist: list[float] = []
    salt_hist: list[float] = []
    for year in range(start_year, end_year + 1):
        oni_l2 = oni_lag2(oni, year)
        oni_d = oni_djf(oni, year)
        oni_use = oni_l2 if oni_l2 is not None else (oni_d or 0.0)
        qf = upstream_q_features(dailies_up, year)
        q = qf.get("q_upstream_proxy")
        coastal = []
        for p in MEKONG_ALL_PROVINCE_POINTS:
            daily = dailies.get(p["name"])
            if daily is None:
                continue
            if float(p.get("coast_km", 99)) > COAST_KM_THRESHOLD:
                continue
            dry_p = C.window_sum(daily, "precip", WS_DRY, year)
            wet_p = C.window_sum(daily, "precip", WS_WET_PRIOR, year)
            if not (_finite(dry_p) and _finite(wet_p)):
                continue
            salt = C.salinity_proxy(
                float(p["coast_km"]), dry_p, float(oni_use), wet_p,
                q_upstream=q)
            coastal.append(salt["salt_proxy"])
        salt_mean = float(np.mean(coastal)) if coastal else None
        if _finite(q):
            q_hist.append(float(q))
        if _finite(salt_mean):
            salt_hist.append(float(salt_mean))
        rows.append({
            "year": year,
            "oni_lag2": _round(oni_l2, 3),
            "oni_djf": _round(oni_d, 3),
            "q_upstream_proxy": _round(q, 3),
            "q_wet_pakse_mm": _round(qf.get("q_wet_pakse")),
            "salt_proxy_coastal_mean": _round(salt_mean, 4),
            "n_coastal_provinces": len(coastal),
        })

    # Attach climatological z and basin risk after full pass.
    for row in rows:
        qz = _series_z(q_hist, row["q_upstream_proxy"])
        sz = _series_z(salt_hist, row["salt_proxy_coastal_mean"])
        oni_v = row["oni_lag2"] if row["oni_lag2"] is not None else row["oni_djf"]
        q_risk = _z_to_risk_low_is_bad(qz)
        salt_risk = _z_to_risk_high_is_bad(sz)
        enso_risk = 100.0 * _clip01(0.5 + 0.35 * max(float(oni_v or 0.0), 0.0))
        basin = 0.40 * q_risk + 0.40 * salt_risk + 0.20 * enso_risk
        row["q_upstream_z"] = _round(qz, 3)
        row["salt_proxy_z"] = _round(sz, 3)
        row["basin_risk_score_0_100"] = _round(basin, 1)
        row["basin_risk_level"] = _level(basin)
    return rows


def build_risk_payload(year: int | None = None,
                       start_year: int = 2000) -> dict:
    today = date.today()
    season = year or current_season()
    # History ends at last completed WS-ish year if mid-season incomplete;
    # still emit current season with whatever POWER days exist.
    hist_end = max(season, today.year)

    oni = load_oni()
    log_pts = []

    dailies: dict[str, pd.DataFrame] = {}
    for p in MEKONG_ALL_PROVINCE_POINTS:
        dailies[p["name"]] = point_weather(p)
        log_pts.append(p["name"])

    dailies_up: dict[str, pd.DataFrame] = {}
    for p in MEKONG_UPSTREAM_POINTS:
        dailies_up[p["name"]] = point_weather(p)

    oni_l2 = oni_lag2(oni, season)
    oni_d = oni_djf(oni, season)
    oni_use = oni_l2 if oni_l2 is not None else (oni_d or 0.0)
    qf = upstream_q_features(dailies_up, season)
    q = qf.get("q_upstream_proxy")

    history = build_history(dailies, dailies_up, oni, start_year, hist_end)
    hist_by_year = {r["year"]: r for r in history}
    current_hist = hist_by_year.get(season, {})

    provinces = {}
    for p in MEKONG_ALL_PROVINCE_POINTS:
        provinces[p["name"]] = province_hydrology(
            dailies[p["name"]], season, p, float(oni_use), q)

    coastal_scores = [
        v["coastal_stress_score_0_100"]
        for v in provinces.values()
        if v["zone"] == "coastal_salt_belt"
        and v["coastal_stress_score_0_100"] is not None
    ]
    overall_from_prov = float(np.mean(coastal_scores)) if coastal_scores else 50.0
    basin_score = current_hist.get("basin_risk_score_0_100")
    if basin_score is None:
        basin_score = overall_from_prov
    overall = 0.55 * float(basin_score) + 0.45 * overall_from_prov

    flags: list[str] = []
    if _finite(q) and current_hist.get("q_upstream_z") is not None:
        if current_hist["q_upstream_z"] <= -0.8:
            flags.append("low_q_upstream_proxy")
    if _enso_label(oni_l2 if oni_l2 is not None else oni_d).startswith("el_nino") \
            or _enso_label(oni_l2 if oni_l2 is not None else oni_d) == "strong_el_nino":
        flags.append("el_nino_context")
    if any("high_salt_proxy" in p["flags"] for p in provinces.values()):
        flags.append("coastal_salt_proxy_alert")
    if any("dry_spi_ws" in p["flags"] for p in provinces.values()):
        flags.append("regional_dry_spi")

    coastal_salt_alert = "coastal_salt_proxy_alert" in flags
    n_coastal_alert = sum(
        1 for p in provinces.values()
        if p.get("zone") == "coastal_salt_belt" and "high_salt_proxy" in p.get("flags", [])
    )

    return {
        "schema_version": SCHEMA,
        "product": "hydrology_salinity_early_warning",
        "product_ko": "메콩 수문·염분 조기경보 모니터",
        "region": "Mekong Delta (Viet Nam)",
        "region_ko": "메콩 삼각주",
        "season_window": "WS_dry_Dec_to_Apr",
        "target_season_year": season,
        "as_of": today.isoformat(),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "yield_model_status": "abandoned_for_ops",
        "yield_model_note": (
            "Mekong WS climate→yield learning deferred/abandoned for ops "
            "(provincial panel skill vs trend negative; T too short). "
            "This file is a risk monitor only — no yield point / skill claim."
        ),
        "forecast_available": False,
        "panel_mode": "risk_monitor",
        "claim_boundary": {
            "ships": [
                "heuristic_hydro_salinity_early_warning_scores",
                "proxy_labeled_inputs",
                "discrete_risk_levels_and_flags",
            ],
            "does_not_ship": [
                "yield_kg_ha_point_or_range",
                "skill_vs_trend",
                "calibrated_loss_probability",
                "planted_area_ha_forecast",
            ],
        },
        "honesty": {
            "q_upstream": "proxy_from_POWER_Pakse_TanChau_not_MRC_Q",
            "salinity": "coast_km_x_hydro_x_ENSO_proxy_not_field_EC",
            "spei_spi": "POWER_based_zscore_approx_not_station_SPEI",
            "s1_gee_area_inundation": "skipped_no_auth",
            "mrc_real_discharge": "unavailable_do_not_block",
            "scores": "transparent_weights_not_estimated_loss_function",
        },
        "data_gaps": {
            "mrc_discharge": "portal_request_or_403 — using POWER q_upstream_proxy",
            "field_ec_siwrp": "not_wired",
            "chirps_smap_s1_gee": "skipped_no_gee_auth",
            "official_area_panel": (
                "provincial planted-area cells often contaminated 2017–2020; "
                "not used as a skill target"
            ),
        },
        "how_to_read": {
            "en": (
                "Read overall.risk_level + flags first, then basin Q-proxy and "
                "coastal provinces. Scores are relative early-warning heuristics. "
                "Do not interpret as kg/ha or as beating a yield trend."
            ),
            "ko": (
                "먼저 overall.risk_level과 flags를 보고, 이어서 basin Q-proxy와 "
                "해안성 점수를 확인하세요. 점수는 상대적 조기경보 휴리스틱이며 "
                "단수(kg/ha)나 추세 대비 skill로 읽지 마세요."
            ),
            "levels": {
                "low": "<35",
                "watch": "35–54",
                "elevated": "55–74",
                "high": "≥75",
            },
            "flag_glossary": {
                "low_q_upstream_proxy": "Freshwater-push proxy weak vs history",
                "el_nino_context": "ONI in El Niño range — stress context only",
                "coastal_salt_proxy_alert": "≥1 coastal province high salt_proxy",
                "regional_dry_spi": "≥1 province SPI_WS ≤ −1 (POWER-based)",
            },
        },
        "field_guide": {
            "overall.risk_score_0_100": (
                "0.55·basin + 0.45·mean(coastal province stress). Not a probability."
            ),
            "basin.q_upstream_proxy": (
                "POWER Pakse wet precip + Tan Chau dry SM/precip composite. "
                "Higher ⇒ more freshwater push. Not MRC Q."
            ),
            "basin.q_upstream_z": "Climatological z of q_upstream_proxy (low ⇒ risk↑)",
            "enso.oni_lag2": "NOAA CPC ONI lag-2 — risk context, not a yield coefficient",
            "provinces.*.salt_proxy": (
                "coast_km × dry hydro × wet memory × ONI × Q-proxy — not field EC"
            ),
            "provinces.*.ec_proxy": "Scaled hydro stand-in — NOT field ECe dS/m",
            "provinces.*.spi_ws": "POWER Dec–Apr precip z approx",
            "provinces.*.spei4_ws_min": "POWER CWB-like 4-mo min z for Jan–Apr window",
            "provinces.*.coastal_stress_score_0_100": (
                "Province heuristic blend; inland mutes salinity channel"
            ),
            "area_risk.soft_flag": (
                "True when coastal salt proxy alerts fire — planting/abandonment "
                "watch only; no ha model"
            ),
            "time_series": "Annual basin risk components for charts",
            "yield_model_status": "Always abandoned_for_ops on this product file",
            "forecast_available": "Always false",
        },
        "score_recipe": {
            "basin_weights": {
                "q_upstream_risk": 0.40,
                "salt_proxy_risk": 0.40,
                "enso_risk": 0.20,
            },
            "overall_weights": {"basin": 0.55, "coastal_province_mean": 0.45},
            "z_mapping": "z=±1.5 ≈ risk ≈16/84 via logistic-like clip; missing→50",
            "note": "Transparent heuristics — not an estimated damage function.",
        },
        "enso": {
            "oni_djf": _round(oni_d, 3),
            "oni_lag2": _round(oni_l2, 3),
            "label": _enso_label(oni_l2 if oni_l2 is not None else oni_d),
            "role": "risk_context_not_yield_driver_claim",
            "source": "NOAA CPC oni.ascii.txt",
        },
        "basin": {
            "q_upstream_proxy": _round(q, 3),
            "q_upstream_z": current_hist.get("q_upstream_z"),
            "q_wet_pakse_mm": _round(qf.get("q_wet_pakse")),
            "precip_dry_tanchau_mm": _round(qf.get("precip_dry_tanchau")),
            "q_sm_tanchau": _round(qf.get("q_sm_tanchau"), 3),
            "basin_risk_score_0_100": _round(basin_score, 1),
            "basin_risk_level": _level(float(basin_score)),
            "note": (
                "Higher q_upstream_proxy ⇒ more freshwater push (less intrusion "
                "pressure). Not MRC Tan Chau discharge."
            ),
        },
        "overall": {
            "risk_score_0_100": _round(overall, 1),
            "risk_level": _level(overall),
            "flags": flags,
            "interpretation": (
                "Heuristic 0–100 early-warning blend of basin Q-proxy, coastal "
                "salt_proxy, and ENSO. Not a calibrated probability and not a "
                "yield forecast."
            ),
        },
        "area_risk": {
            "status": "proxy_flag_only",
            "channel": "planted_area_abandonment_under_salt",
            "claim": "none",
            "s1_gee_status": "skipped_no_auth",
            "soft_flag": coastal_salt_alert,
            "n_coastal_provinces_high_salt_proxy": n_coastal_alert,
            "interpretation_en": (
                "Area is a separate risk channel from yield (salt → delayed / "
                "abandoned planting). No ha forecast and no area skill metric. "
                "soft_flag mirrors coastal salt alerts as a watch banner only."
            ),
            "interpretation_ko": (
                "면적은 단수와 별도 채널(염수 → 파종 지연·포기). ha 예측·면적 skill "
                "없음. soft_flag는 해안 염분 프록시 경보를 주의 배너로만 반영."
            ),
            "upgrade_path": (
                "Wire Sentinel-1 / GEE planted-area anomaly vs multi-year baseline "
                "when auth exists; keep separate from kg/ha."
            ),
        },
        "provinces": provinces,
        "time_series": history,
        "sources": [
            "NASA POWER daily (precip, ET0 via FAO-56, GWETROOT)",
            "NOAA CPC ONI",
            "coast_km static province approx.",
        ],
        "docs": {
            "package_readme": "vietnam/README.md",
            "risk_readme": "vietnam/risk/README.md",
            "panel_significance_ko": "vietnam/PANEL_SIGNIFICANCE_KO.md",
            "vault": "기후 모델링/Regions/베트남/메콩_리스크모니터_피벗.md",
        },
        "points_used": log_pts,
    }


def write_risk_json(payload: dict, out_path: str | None = None) -> str:
    path = out_path or PUBLIC_DEFAULT
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Mekong hydrology/salinity risk monitor → JSON")
    ap.add_argument("--year", type=int, default=None,
                    help="WS harvest year (default: current season)")
    ap.add_argument("--start-year", type=int, default=2000,
                    help="time_series start year")
    ap.add_argument("--out", type=str, default=None,
                    help="output JSON path")
    args = ap.parse_args(argv)

    print(f"[mekong_risk] building season={args.year or 'auto'} …", flush=True)
    payload = build_risk_payload(year=args.year, start_year=args.start_year)
    path = write_risk_json(payload, args.out)
    o = payload["overall"]
    print(f"[mekong_risk] wrote {path}", flush=True)
    print(
        f"[mekong_risk] year={payload['target_season_year']} "
        f"score={o['risk_score_0_100']} level={o['risk_level']} "
        f"flags={o['flags']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
