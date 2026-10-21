"""Favourable / unfavourable / neutral weather per growth stage, every region.

For each crop in public/data/crop_stages_v1.json this places the stage
calendar on the current season, measures the weather inside each stage
window at the region's map point (NASA POWER), compares it with the same
window in the 30 seasons before, and calls each stage favourable,
unfavourable or neutral by a stage-specific rule. The stage calls roll up to
one verdict per crop. Nothing here moves a forecast number.

A stage that is still running is compared with the same number of days in
past seasons, so half a season is not read as a drought. Stages that have
not started are listed as upcoming.

Where the crop's yield label is in the repo, past seasons are scored the same
way and the verdict classes are checked against how yield landed relative to
its trailing ten-year trend.

Output: public/data/stage_conditions_v1.json
    python -m stage_conditions.build            # needs NASA POWER
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
YIELD_MODEL = os.path.dirname(HERE)
DATA = os.path.abspath(os.path.join(YIELD_MODEL, "..", "..", "public", "data"))
STAGES_JSON = os.path.join(DATA, "crop_stages_v1.json")
REGISTRY_JSON = os.path.join(DATA, "climate_registry_v1.json")
OUT = os.path.join(DATA, "stage_conditions_v1.json")
CACHE = os.path.join(HERE, "cache")

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER_PARAMS = "PRECTOTCORR,T2M_MAX,T2M_MIN,GWETROOT"
FIRST_DAY = date(1983, 1, 1)
FILL = -900

Z = 0.75            # |z| that counts as a signal; fixed, not tuned
WET_SOW_Z = 1.5     # sowing rain this far above normal is waterlogging / delay
NORMAL_SEASONS = 30
MIN_SEASONS = 10
DRY_MM = 1.0
WINTERKILL_C = -15.0
# Maturity and harvest weather changes quality and harvest pace more than the
# yield the label records, so those stages are shown but not scored.
WEIGHTS = {"sow": 1.0, "veg": 1.0, "repro": 2.0, "fill": 2.0,
           "mature": 0.0, "harvest": 0.0, "dormant": 1.0}
VERDICT_AT = 2.0

# Daily maximum above which a day counts as heat stress for the crop.
HEAT_C = {
    "wheat": 32.0, "winter_wheat": 32.0, "spring_wheat": 32.0, "canola": 30.0,
    "barley": 32.0, "corn": 35.0, "corn_safrinha": 35.0, "soy": 35.0,
    "soybeans": 35.0, "sunflower": 35.0, "cotton": 37.0, "sugarcane": 38.0,
    "coffee": 34.0, "orange": 38.0,
}

LABEL_KO = {"favorable": "유리", "unfavorable": "불리", "neutral": "중립",
            "upcoming": "예정"}

# Region/crop -> yield label already in the repo (year = harvest year).
# Anything not listed falls back to {country}/training/{region key}.csv.
LABEL_FILES = {
    ("corn_belt", "corn"): "us_corn_training.csv",
    ("corn_belt", "soybeans"): "us_soybeans_training.csv",
    ("corn_belt", "soy"): "us_soybeans_training.csv",
    ("great_plains", "winter_wheat"): "us_winter_wheat_training.csv",
    ("northern_plains", "spring_wheat"): "us_spring_wheat_training.csv",
    ("cotton_belt", "cotton"): "us_cotton_training.csv",
    # Several crops share one map region; each has its own label table.
    ("parana_soja", "corn"): "brazil/training/parana_milho.csv",
    ("parana_soja", "wheat"): "brazil/training/parana_trigo.csv",
    ("mato_grosso_soja", "corn_safrinha"): "brazil/training/mato_grosso_milho.csv",
    ("matopiba_soja", "cotton"): "brazil/training/matopiba_algodao.csv",
    ("sp_cana", "coffee"): "brazil/training/sp_cafe.csv",
    ("sp_cana", "orange"): "brazil/training/sp_laranja.csv",
}
LABEL_COLUMNS = ("yield_kg_ha", "yield", "target")


def log(msg):
    print(f"[stage_conditions] {msg}", flush=True)


# --- inputs -----------------------------------------------------------------

def load_stages():
    with open(STAGES_JSON, encoding="utf-8") as handle:
        return json.load(handle)["regions"]


def load_points():
    """crops_region_key -> {lat, lon, country} from the climate registry."""
    with open(REGISTRY_JSON, encoding="utf-8") as handle:
        registry = json.load(handle)
    points = {}
    for country, cfg in registry["countries"].items():
        for region in cfg.get("regions", []):
            coords = region.get("coordinates")
            if not coords:
                continue
            for key in region.get("crops_region_keys") or [region.get("key")]:
                points.setdefault(key, {"lon": float(coords[0]), "lat": float(coords[1]),
                                        "country": country,
                                        "folder": cfg.get("country")})
    return points


def _get_json(url, attempts=6):
    delay = 20
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "yield-model/1.0"})
            with urllib.request.urlopen(request, timeout=300) as response:
                return json.loads(response.read())
        except Exception as exc:  # noqa: BLE001
            if attempt == attempts - 1:
                raise
            log(f"retry {attempt + 1} in {delay}s after {exc}")
            time.sleep(delay)
            delay = min(delay * 2, 240)


def point_daily(point, today):
    """Daily precip / tmax / tmin / root-zone wetness, cached for the day."""
    os.makedirs(CACHE, exist_ok=True)
    slug = f"{point['lat']:.2f}_{point['lon']:.2f}".replace("-", "m").replace(".", "p")
    cached = os.path.join(CACHE, f"power_{slug}_{today.isoformat()}.csv")
    if os.path.exists(cached):
        return pd.read_csv(cached, parse_dates=["date"])
    url = (f"{POWER_URL}?parameters={POWER_PARAMS}&community=AG"
           f"&longitude={point['lon']}&latitude={point['lat']}"
           f"&start={FIRST_DAY:%Y%m%d}&end={today:%Y%m%d}&format=JSON")
    p = _get_json(url)["properties"]["parameter"]
    frame = pd.DataFrame({
        "date": pd.to_datetime(list(p["T2M_MAX"].keys()), format="%Y%m%d"),
        "precip": list(p["PRECTOTCORR"].values()),
        "tmax": list(p["T2M_MAX"].values()),
        "tmin": list(p["T2M_MIN"].values()),
        "soil": list(p["GWETROOT"].values()),
    })
    frame = frame[(frame[["precip", "tmax", "tmin", "soil"]] > FILL).all(axis=1)]
    frame = frame.sort_values("date").reset_index(drop=True)
    frame.to_csv(cached, index=False)
    return frame


# --- calendar ---------------------------------------------------------------

def _md(text):
    month, day = (int(x) for x in text.split("-"))
    return month, day


def _on_or_after(month, day, floor):
    """First date with this month/day on or after ``floor`` (Feb 29 -> 28)."""
    for year in (floor.year, floor.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            candidate = date(year, month, 28)
        if candidate >= floor:
            return candidate
    raise ValueError("unreachable")


def place(stages, anchor):
    """Concrete [start, end] for each stage of the season that starts in ``anchor``."""
    m, d = _md(stages[0]["start"])
    season_start = date(anchor, m, d)
    placed = []
    for stage in stages:
        start = _on_or_after(*_md(stage["start"]), season_start - timedelta(days=30))
        if start < season_start - timedelta(days=30):
            start = _on_or_after(*_md(stage["start"]), season_start)
        end = _on_or_after(*_md(stage["end"]), start)
        placed.append((start, end))
    return placed


def current_anchor(stages, today):
    m, d = _md(stages[0]["start"])
    return today.year if date(today.year, m, d) <= today else today.year - 1


def harvest_year(stages, placed):
    for stage, (start, _) in zip(stages, placed):
        if stage["kind"] == "harvest":
            return start.year
    return placed[-1][1].year


# --- weather inside a window --------------------------------------------------

def _max_run(mask):
    best = run = 0
    for value in mask:
        run = run + 1 if value else 0
        best = max(best, run)
    return best


def window_metrics(daily, start, end, heat_c):
    stamps = daily.date.values
    lo = stamps.searchsorted(np.datetime64(start), "left")
    hi = stamps.searchsorted(np.datetime64(end), "right")
    days = daily.iloc[lo:hi]
    if len(days) < max(5, 0.8 * ((end - start).days + 1)):
        return None
    return {
        "precip": float(days.precip.sum()),
        "dry_spell": float(_max_run((days.precip < DRY_MM).values)),
        "heat_days": float((days.tmax >= heat_c).sum()),
        "soil": float(days.soil.mean()),
        "winterkill_days": float((days.tmin <= WINTERKILL_C).sum()),
    }


def stage_table(daily, stages, anchor, heat_c, today, history=NORMAL_SEASONS):
    """Per stage: metrics for ``anchor`` and for each earlier season (same cut)."""
    placed = place(stages, anchor)
    rows = []
    for index, stage in enumerate(stages):
        start, end = placed[index]
        if start > today:
            rows.append({"state": "upcoming", "start": start, "end": end})
            continue
        cut = min(end, today)
        span = (cut - start).days
        current = window_metrics(daily, start, cut, heat_c)
        past = []
        for back in range(1, history + 1):
            p_start, _ = place(stages, anchor - back)[index]
            metrics = window_metrics(daily, p_start, p_start + timedelta(days=span), heat_c)
            if metrics:
                past.append(metrics)
        rows.append({
            "state": "done" if end <= today else "in_progress",
            "start": start, "end": end,
            "observed_share": round(min(1.0, (span + 1) / ((end - start).days + 1)), 2),
            "current": current, "past": past,
        })
    return placed, rows


# --- rules ------------------------------------------------------------------

def _z(value, past, key):
    values = np.array([p[key] for p in past], dtype=float)
    if len(values) < MIN_SEASONS:
        return None, None
    mean, std = float(values.mean()), float(values.std(ddof=1))
    if std <= 1e-9:
        return 0.0, mean
    return (value - mean) / std, mean


METRIC_KO = {
    "precip": ("강수량", "mm"), "dry_spell": ("최장 무강우", "일"),
    "heat_days": ("고온일", "일"), "soil": ("토양수분", ""),
    "winterkill_days": ("혹한일", "일"),
}


def _say(key, value, normal):
    name, unit = METRIC_KO[key]
    if key == "soil":
        return f"{name} {value:.2f} (평년 {normal:.2f})"
    return f"{name} {value:.0f}{unit} (평년 {normal:.0f}{unit})"


def judge(kind, current, past):
    """(status, reason_ko, metrics) for one stage window."""
    if current is None or len(past) < MIN_SEASONS:
        return "neutral", "기상 자료 부족", {}
    z, normal = {}, {}
    for key in ("precip", "dry_spell", "heat_days", "soil", "winterkill_days"):
        z[key], normal[key] = _z(current[key], past, key)
    metrics = {k: {"value": round(current[k], 2), "normal": round(normal[k], 2),
                   "z": round(z[k], 2)} for k in z if z[k] is not None}
    bad, good = [], []

    def hot():
        return z["heat_days"] >= Z and current["heat_days"] >= 2

    if kind == "sow":
        if z["precip"] >= WET_SOW_Z:
            bad.append(("precip", "과습·파종 지연 위험"))
        elif z["precip"] <= -Z or z["soil"] <= -Z:
            bad.append(("soil" if z["soil"] <= -Z else "precip", "파종기 건조"))
        elif z["precip"] >= Z or z["soil"] >= Z:
            good.append(("soil" if z["soil"] >= Z else "precip", "파종 수분 충분"))
    elif kind == "veg":
        if z["soil"] <= -Z or z["precip"] <= -Z:
            bad.append(("soil" if z["soil"] <= -Z else "precip", "생육기 수분 부족"))
        if hot():
            bad.append(("heat_days", "고온"))
        if not bad and z["soil"] >= Z:
            good.append(("soil", "수분 넉넉"))
    elif kind in ("repro", "fill"):
        if z["dry_spell"] >= Z:
            bad.append(("dry_spell", "가뭄 길어짐"))
        if hot():
            bad.append(("heat_days", "고온 스트레스"))
        if z["soil"] <= -Z and not bad:
            bad.append(("soil", "토양수분 부족"))
        if not bad and (z["soil"] >= Z or z["precip"] >= Z) and z["heat_days"] <= 0:
            good.append(("soil" if z["soil"] >= Z else "precip", "수분 넉넉·고온 없음"))
    elif kind in ("mature", "harvest"):
        if z["precip"] >= Z:
            bad.append(("precip", "수확기 비 많음(품질·지연)"))
        elif z["precip"] <= -Z:
            good.append(("precip", "건조한 수확기"))
    elif kind == "dormant":
        if z["winterkill_days"] >= Z and current["winterkill_days"] >= 3:
            bad.append(("winterkill_days", "혹한(동해 위험)"))

    if bad:
        key, label = bad[0]
        reason = label + " · " + _say(key, current[key], normal[key])
        if len(bad) > 1:
            k2, l2 = bad[1]
            reason += f" · {l2} " + _say(k2, current[k2], normal[k2])
        return "unfavorable", reason, metrics
    if good:
        key, label = good[0]
        return "favorable", label + " · " + _say(key, current[key], normal[key]), metrics
    return "neutral", "평년 수준", metrics


def score_season(stages, rows):
    calls, score = [], 0.0
    for stage, row in zip(stages, rows):
        if row["state"] == "upcoming":
            calls.append({"state": "upcoming", "status": "upcoming"})
            continue
        status, reason, metrics = judge(stage["kind"], row["current"], row["past"])
        weight = WEIGHTS.get(stage["kind"], 1.0)
        score += weight * {"favorable": 1, "unfavorable": -1}.get(status, 0)
        calls.append({"state": row["state"], "status": status, "reason_ko": reason,
                      "metrics": metrics, "observed_share": row["observed_share"]})
    verdict = ("unfavorable" if score <= -VERDICT_AT
               else "favorable" if score >= VERDICT_AT else "neutral")
    return calls, score, verdict


# --- history check ----------------------------------------------------------

def label_series(key, crop, folder):
    if (key, crop) in LABEL_FILES:
        path = os.path.join(YIELD_MODEL, LABEL_FILES[(key, crop)])
    else:
        path = os.path.join(YIELD_MODEL, folder or "", "training", key + ".csv")
    if not os.path.exists(path):
        return None
    frame = pd.read_csv(path)
    column = next((c for c in LABEL_COLUMNS if c in frame.columns), None)
    if column is None or "year" not in frame.columns:
        return None
    series = frame[["year", column]].dropna()
    series = series[series[column] > 0]
    return series.set_index("year")[column].astype(float)


def trend_residuals(series):
    out = {}
    for year in series.index:
        prior = series[(series.index < year) & (series.index >= year - 10)]
        if len(prior) < 8:
            continue
        fit = np.polyfit(prior.index.values.astype(float), np.log(prior.values), 1)
        out[int(year)] = float(np.log(series[year]) - np.polyval(fit, year))
    return pd.Series(out, dtype=float)


def history_check(daily, stages, heat_c, labels, today):
    residual = trend_residuals(labels)
    rows = []
    last = current_anchor(stages, today) - 1
    for anchor in range(FIRST_DAY.year + MIN_SEASONS + 1, last + 1):
        placed, table = stage_table(daily, stages, anchor, heat_c, today)
        year = harvest_year(stages, placed)
        if year not in residual.index or placed[-1][1] > today:
            continue
        _, score, verdict = score_season(stages, table)
        rows.append({"year": year, "score": score, "verdict": verdict,
                     "residual_pct": round(residual[year] * 100, 1)})
    if len(rows) < 8:
        return None
    table = pd.DataFrame(rows)
    classes = {}
    for verdict, group in table.groupby("verdict"):
        classes[verdict] = {
            "n": int(len(group)),
            "years": [int(y) for y in group.year],
            "mean_residual_pct": round(float(group.residual_pct.mean()), 1),
            "below_trend_share": round(float((group.residual_pct < 0).mean()), 2),
        }
    corr = float(np.corrcoef(table.score, table.residual_pct)[0, 1]) if table.score.std() > 0 else None
    return {"years": [int(table.year.min()), int(table.year.max())], "n": int(len(table)),
            "classes": classes, "score_residual_corr": None if corr is None else round(corr, 2)}


def history_ko(history):
    if not history:
        return None
    c = history["classes"]
    parts = []
    for verdict in ("unfavorable", "neutral", "favorable"):
        if verdict in c:
            parts.append("{} {}번 평균 {:+.1f}%".format(
                LABEL_KO[verdict], c[verdict]["n"], c[verdict]["mean_residual_pct"]))
    text = "{}~{}년 추세 대비 수확량: ".format(*history["years"]) + ", ".join(parts)
    unf, fav = c.get("unfavorable"), c.get("favorable")
    rest = [c[v]["mean_residual_pct"] for v in c if v != "unfavorable"]
    if unf and rest and unf["mean_residual_pct"] < min(rest):
        text += " · 불리 판정이 실제 감수와 맞았다"
    elif unf and rest:
        text += " · 불리 판정이 실제 수확량과 잘 맞지 않았다(참고만)"
    if fav and unf is not None and fav["mean_residual_pct"] <= unf["mean_residual_pct"]:
        text += " · 유리 판정은 증수로 이어지지 않았다"
    return text


# --- assemble ---------------------------------------------------------------

def crop_entry(key, crop, daily, today, folder):
    stages = crop["stages"]
    heat_c = HEAT_C.get(crop["crop"], 35.0)
    anchor = current_anchor(stages, today)
    placed, table = stage_table(daily, stages, anchor, heat_c, today)
    calls, score, verdict = score_season(stages, table)
    out_stages = []
    for stage, (start, end), call in zip(stages, placed, calls):
        item = {"kind": stage["kind"], "name_ko": stage["name_ko"],
                "start": start.isoformat(), "end": end.isoformat(), **call}
        item["status_ko"] = LABEL_KO[item["status"]]
        out_stages.append(item)
    judged = [s for s in out_stages if s["status"] != "upcoming"]
    scored = [s for s in judged if WEIGHTS.get(s["kind"], 1.0) > 0]
    bad = [s["name_ko"] for s in scored if s["status"] == "unfavorable"]
    good = [s["name_ko"] for s in scored if s["status"] == "favorable"]
    late = [s for s in judged if WEIGHTS.get(s["kind"], 1.0) == 0 and s["status"] != "neutral"]
    if not judged:
        reason = "아직 시작한 단계가 없다"
    else:
        bits = []
        if bad:
            bits.append("불리: " + ", ".join(bad))
        if good:
            bits.append("유리: " + ", ".join(good))
        reason = " · ".join(bits) if bits else "판정 단계 모두 평년 수준"
        if late:
            reason += " · " + ", ".join(f"{s['name_ko']} {s['status_ko']}" for s in late) + "(품질·수확 진도, 판정 제외)"
    labels = label_series(key, crop["crop"], folder)
    history = None
    if labels is not None:
        try:
            history = history_check(daily, stages, heat_c, labels, today)
        except Exception as exc:  # noqa: BLE001 -- the check is optional
            log(f"{key}/{crop['crop']}: history check failed: {exc}")
    season = (str(placed[0][0].year) if placed[0][0].year == placed[-1][1].year
              else f"{placed[0][0].year}/{str(placed[-1][1].year)[-2:]}")
    return {
        "crop": crop["crop"], "label_ko": crop["label_ko"],
        "season": season, "harvest_year": harvest_year(stages, placed),
        "heat_threshold_c": heat_c,
        "stages": out_stages,
        "overall": {"verdict": verdict, "verdict_ko": LABEL_KO[verdict],
                    "score": score, "reason_ko": reason,
                    "judged_stages": len(judged), "total_stages": len(out_stages)},
        "history": history, "history_ko": history_ko(history),
    }


def build(today=None):
    today = today or date.today() - timedelta(days=3)
    stages = load_stages()
    points = load_points()
    out = {"schema_version": 1,
           "generated_at": datetime.now(timezone.utc).isoformat(),
           "weather_through": None,
           "method_ko": ("단계별 기상(NASA POWER, 산지 대표 지점)을 직전 30개 시즌의 같은 구간과 "
                         "비교해 유리·불리·중립으로 판정한다. 진행 중인 단계는 같은 일수끼리 비교한다. "
                         "예측치에는 반영하지 않는다."),
           "rules_ko": {
               "sow": "강수·토양수분 부족이면 불리, 강수 +1.5σ 이상이면 과습으로 불리, 넉넉하면 유리",
               "veg": "토양수분·강수 부족 또는 고온일 증가면 불리, 토양수분 넉넉하면 유리",
               "repro": "무강우 연속일·고온일 증가 또는 토양수분 부족이면 불리",
               "fill": "무강우 연속일·고온일 증가 또는 토양수분 부족이면 불리",
               "mature": "비가 많으면 불리, 건조하면 유리",
               "harvest": "비가 많으면 불리, 건조하면 유리",
               "dormant": "혹한일(최저 -15°C 이하)이 평년보다 많으면 불리",
               "overall": "개화·비대 단계 가중 2배, 성숙·수확 단계는 표시만(수량보다 품질·수확 진도에 영향), 합계 -2 이하 불리 · +2 이상 유리",
           },
           "regions": {}, "skipped": {}}
    through = []
    for key, crops in stages.items():
        point = points.get(key)
        if point is None:
            out["skipped"][key] = "no coordinates in climate registry"
            continue
        try:
            daily = point_daily(point, today)
        except Exception as exc:  # noqa: BLE001
            out["skipped"][key] = f"weather unavailable: {exc}"
            log(f"{key}: {exc}")
            continue
        through.append(daily.date.max().date())
        entries = []
        for crop in crops:
            try:
                entries.append(crop_entry(key, crop, daily, min(today, through[-1]),
                                          point.get("folder")))
            except Exception as exc:  # noqa: BLE001
                log(f"{key}/{crop['crop']}: {exc}")
        out["regions"][key] = entries
        log(f"{key}: " + ", ".join(f"{e['label_ko']} {e['overall']['verdict_ko']}" for e in entries))
    out["weather_through"] = min(through).isoformat() if through else None
    return out


def main():
    out = build()
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(out, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    log(f"wrote {len(out['regions'])} regions, skipped {len(out['skipped'])} -> {OUT}")


if __name__ == "__main__":
    sys.exit(main())
