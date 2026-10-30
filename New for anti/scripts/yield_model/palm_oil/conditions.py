"""
Favourable / unfavourable / neutral weather read-out for a palm-oil producer.

Usage: python3 -m palm_oil.conditions build      # NASA POWER -> training/{key}_features.csv
       python3 -m palm_oil.conditions backtest   # verdict vs PSD residual -> training/{key}_backtest.json

Same mechanism and fixed thresholds as indonesia/palm_conditions.py, which no
weather regression could beat on the PSD label either: drought cuts palm
bunches with a lag, through abortion of developing bunches (about a year)
and through fewer female flowers (about two years). This module reports which
of those signals are active for the coming marketing year. It does not move
the number.

Windows are tied to the marketing year rather than to a dry season, because
the dry months differ by country (Peninsular Malaysia has two, Colombia's
Llanos one, Nigeria December-March). For label year T (October T-1 to
September T):
  water_deficit_lag1   sum over months of (100 mm - rain) where rain < 100 mm,
                       October T-2 to September T-1 (the oil-palm water-deficit
                       measure; palms need about 100 mm a month)
  dry_spell_lag1       longest run of days under 1 mm, same window
  nino34_lag1          mean Niño3.4 anomaly over the same window
                       (public/data/sst_regions_v1.json, OISST v2.1)
  soil_lag2            root-zone wetness, October T-3 to September T-2

So the read-out for the marketing year that has just started is built from
weather that has already been observed in full.

Each is a z score against the 20 seasons before it (at least 10); Niño3.4 is
read raw. Thresholds are fixed, not tuned: |z| >= 0.75, |Niño3.4| >= 0.5 °C,
a score of -2 or worse is "unfavourable". As in Indonesia there is no
"favourable" verdict, and a wet two-years-back season is not counted as an
upside.
"""

import json
import os
import sys

import numpy as np
import pandas as pd

from .producers import ALL, BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training")
SST_FILE = os.path.normpath(os.path.join(
    HERE, "..", "..", "..", "public", "data", "sst_regions_v1.json"))

Z = 0.75
NINO = 0.5
VERDICT_AT = -2
MONTHLY_NEED_MM = 100.0
MIN_DAYS = 350

LABELS_KO = {"favorable": "유리", "unfavorable": "불리", "neutral": "중립"}

INDICATORS = [
    {"key": "water_deficit_lag1", "lag": 1, "unit": "mm", "high_is": "unfavorable",
     "label_ko": "직전 1년 물부족량",
     "why_ko": "월 강수 100mm 미만인 달의 부족분 합. 부족이 크면 약 12개월 뒤 수확할 송이가 떨어진다."},
    {"key": "dry_spell_lag1", "lag": 1, "unit": "일", "high_is": "unfavorable",
     "label_ko": "직전 1년 최장 무강우 일수",
     "why_ko": "긴 가뭄은 자라던 송이의 낙과·수분 실패로 이어진다."},
    {"key": "nino34_lag1", "lag": 1, "unit": "°C", "high_is": "unfavorable",
     "label_ko": "직전 1년 엘니뇨(Niño3.4)",
     "why_ko": "엘니뇨는 동남아·콜롬비아 북부에 가뭄을 부르고 6~24개월 뒤 생산을 깎는다."},
    {"key": "soil_lag2", "lag": 2, "unit": "", "high_is": "favorable",
     "label_ko": "2년 전 토양수분",
     "why_ko": "2년 전 가뭄은 암꽃 분화를 줄여 약 24개월 뒤 수확량을 낮춘다."},
]
RAW = [s["key"] for s in INDICATORS if s["key"] != "nino34_lag1"]


def log(msg):
    print(f"[palm-oil:conditions] {msg}", flush=True)


def window(year, lag):
    """October (year-1-lag) .. September (year-lag), inclusive."""
    return pd.Timestamp(year - 1 - lag, 10, 1), pd.Timestamp(year - lag, 9, 30)


def season_label(year, lag):
    start, end = window(year, lag)
    return f"{start.year}/{str(end.year)[-2:]}"


def point_features(daily, year):
    """Raw indicators for one point's daily frame (columns date, precip, soil)."""
    out = {}
    start, end = window(year, 1)
    w = daily[(daily.date >= start) & (daily.date <= end)]
    if len(w) >= MIN_DAYS:
        monthly = w.groupby(w.date.dt.to_period("M")).precip.sum()
        out["water_deficit_lag1"] = float(np.clip(MONTHLY_NEED_MM - monthly, 0, None).sum())
        dry = (w.precip.values < 1.0).astype(int)
        run = best = 0
        for d in dry:
            run = run + 1 if d else 0
            best = max(best, run)
        out["dry_spell_lag1"] = float(best)
    start, end = window(year, 2)
    w = daily[(daily.date >= start) & (daily.date <= end)]
    if len(w) >= MIN_DAYS and "soil" in w:
        out["soil_lag2"] = float(w.soil.mean())
    return out


def load_nino34(path=SST_FILE):
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    region = next(r for r in payload["regions"] if r["id"] == "nino34")
    return {month: float(v) for month, v in region["series"]}


def nino34_window(series, year):
    start, _ = window(year, 1)
    months = pd.period_range(start, periods=12, freq="M")
    vals = [series.get(str(m)) for m in months]
    return float(np.mean(vals)) if None not in vals else None


def blend(producer, dailies, year):
    totals, weights = {}, {}
    for p in producer.points:
        for name, value in point_features(dailies[p["name"]], year).items():
            totals[name] = totals.get(name, 0.0) + value * p["weight"]
            weights[name] = weights.get(name, 0.0) + p["weight"]
    return {n: totals[n] / weights[n] for n in totals}


def feature_frame(producer, dailies, nino, last_year):
    first = min(d.date.min().year for d in dailies.values()) + 3
    rows = []
    for year in range(first, last_year + 1):
        row = blend(producer, dailies, year)
        row["year"] = year
        row["nino34_lag1"] = nino34_window(nino, year)
        rows.append(row)
    return pd.DataFrame(rows)


def z_frame(frame):
    out = frame.sort_values("year").reset_index(drop=True).copy()
    for key in RAW:
        if key not in out:
            out[key] = np.nan
        prior = out[key].shift(1)
        mean = prior.rolling(20, min_periods=10).mean()
        std = prior.rolling(20, min_periods=10).std(ddof=1)
        out[key + "_normal"] = mean
        out[key + "_z"] = (out[key] - mean) / std.replace(0, np.nan)
    return out


def _status(spec, row):
    if spec["key"] == "nino34_lag1":
        z, threshold = row.get("nino34_lag1"), NINO
    else:
        z, threshold = row.get(spec["key"] + "_z"), Z
    if z is None or pd.isna(z):
        return None
    high = spec["high_is"]
    low = "favorable" if high == "unfavorable" else "unfavorable"
    status = high if z >= threshold else low if z <= -threshold else "neutral"
    if spec["key"] == "soil_lag2" and status == "favorable":
        status = "neutral"
    return status


def classify(row):
    items, score = [], 0
    for spec in INDICATORS:
        status = _status(spec, row)
        if status is None:
            continue
        score += {"favorable": 1, "unfavorable": -1}.get(status, 0)
        value = row.get(spec["key"])
        normal = row.get(spec["key"] + "_normal")
        z = row.get(spec["key"] + "_z")
        items.append({
            "key": spec["key"],
            "label_ko": spec["label_ko"],
            "season": season_label(int(row["year"]), spec["lag"]),
            "value": None if value is None or pd.isna(value) else round(float(value), 2),
            "normal": None if normal is None or pd.isna(normal) else round(float(normal), 2),
            "z": None if z is None or pd.isna(z) else round(float(z), 2),
            "unit": spec["unit"],
            "status": status,
            "status_ko": LABELS_KO[status],
            "why_ko": spec["why_ko"],
        })
    return items, score, ("unfavorable" if score <= VERDICT_AT else "neutral")


def trend_residuals(labels):
    """log(actual) minus a linear trend on the ten label years before it."""
    series = labels.set_index("year").psd_production_kt
    out = {}
    for year in series.index:
        prior = series[(series.index < year) & (series.index >= year - 10)]
        if len(prior) < 8:
            continue
        coef = np.polyfit(prior.index, np.log(prior.values), 1)
        out[int(year)] = float(np.log(series[year]) - np.polyval(coef, year))
    return pd.Series(out, dtype=float)


def backtest(producer, frame, labels):
    frame = z_frame(frame)
    residual = trend_residuals(labels)
    rows = []
    for _, row in frame.iterrows():
        year = int(row["year"])
        if year not in residual.index or pd.isna(row.get("water_deficit_lag1_z")):
            continue
        _, score, verdict = classify(row)
        rows.append({"year": year, "score": int(score), "verdict": verdict,
                     "residual_pct": round(residual[year] * 100, 1)})
    table = pd.DataFrame(rows, columns=["year", "score", "verdict", "residual_pct"])
    classes = {}
    for verdict, group in table.groupby("verdict"):
        classes[verdict] = {
            "n": int(len(group)),
            "years": [int(y) for y in group.year],
            "mean_residual_pct": round(float(group.residual_pct.mean()), 1),
            "below_trend_share": round(float((group.residual_pct < 0).mean()), 2),
        }
    unf, neu = classes.get("unfavorable", {}), classes.get("neutral", {})
    supported = bool(unf.get("n", 0) >= 2 and neu.get("n")
                     and unf["mean_residual_pct"] < neu["mean_residual_pct"]
                     and unf["below_trend_share"] > 0.5)
    return {
        "label": f"USDA PSD {producer.psd_name} palm oil production, residual vs prior-10-year log trend",
        "years": [int(table.year.min()), int(table.year.max())] if len(table) else None,
        "thresholds": {"z": Z, "nino34": NINO, "verdict_at": VERDICT_AT},
        "classes": classes,
        "unfavorable_supported": supported,
        "rows": rows,
    }


def summary(target, items, score, verdict, history):
    bad = [i["label_ko"] for i in items if i["status"] == "unfavorable"]
    good = [i["label_ko"] for i in items if i["status"] == "favorable"]
    if verdict == "unfavorable":
        reason = "불리 신호 {}개: {}".format(len(bad), ", ".join(bad))
    elif bad:
        reason = "불리 신호 {}개({})뿐이라 판정 기준(2개 이상)에 못 미친다".format(
            len(bad), ", ".join(bad))
    else:
        reason = "가뭄 신호 없음"
    if good and verdict != "unfavorable":
        reason += " · 습윤 신호는 증산 근거가 없어 유리로 보지 않는다"
    classes = history.get("classes", {})
    unf, neu = classes.get("unfavorable", {}), classes.get("neutral", {})
    if unf.get("n"):
        history_ko = ("{}~{}년 중 불리 판정 {}번({}), 생산이 추세보다 낮았던 비율 {:.0%}, "
                      "평균 {:+.1f}% (중립 해 평균 {:+.1f}%)").format(
            history["years"][0], history["years"][1], unf["n"],
            ", ".join(str(y) for y in unf["years"]), unf["below_trend_share"],
            unf["mean_residual_pct"], neu.get("mean_residual_pct", float("nan")))
    elif history.get("years"):
        history_ko = "{}~{}년 중 불리 판정이 나온 해가 없다".format(*history["years"])
    else:
        history_ko = None
    if verdict == "unfavorable" and not history.get("unfavorable_supported"):
        note = "이 나라에서는 과거 불리 판정이 생산 감소로 뚜렷이 이어지지 않아 참고로만 본다."
    else:
        note = "판정은 참고용이며 예측치(추세)에는 반영하지 않는다."
    return {
        "target_year": target,
        "verdict": verdict,
        "verdict_ko": LABELS_KO[verdict],
        "score": int(score),
        "reason_ko": reason,
        "season_observed_share": 1.0,
        "indicators": items,
        "history_ko": history_ko,
        "unfavorable_supported": bool(history.get("unfavorable_supported")),
        "applied_to_forecast": False,
        "note_ko": note,
    }


def features_path(producer):
    return os.path.join(TRAINING, f"{producer.key}_features.csv")


def backtest_path(producer):
    return os.path.join(TRAINING, f"{producer.key}_backtest.json")


def build(producer, last_year):
    """Fetch NASA POWER for the producer's points and write its feature table."""
    from indonesia.data import point_weather

    dailies = {p["name"]: point_weather(p) for p in producer.points}
    frame = feature_frame(producer, dailies, load_nino34(), last_year)
    os.makedirs(TRAINING, exist_ok=True)
    frame.to_csv(features_path(producer), index=False)
    log(f"{producer.key}: {len(frame)} seasons {int(frame.year.min())}-{int(frame.year.max())}")
    return frame


def assess(producer, target, frame, history):
    row = z_frame(frame)
    row = row[row.year == target]
    if row.empty or pd.isna(row.iloc[0].get("water_deficit_lag1")):
        return None
    items, score, verdict = classify(row.iloc[0])
    return summary(target, items, score, verdict, history)


def main(argv):
    from datetime import date

    from . import psd

    command = argv[0]
    keys = argv[1:] or [p.key for p in ALL]
    for key in keys:
        producer = BY_KEY[key]
        if command == "build":
            build(producer, date.today().year + 1)
        elif command == "backtest":
            frame = pd.read_csv(features_path(producer))
            result = backtest(producer, frame, psd.labels(producer))
            with open(backtest_path(producer), "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
                f.write("\n")
            log(f"{key}: {json.dumps(result['classes'])} "
                f"supported={result['unfavorable_supported']}")
        else:
            raise SystemExit(f"unknown command {command}")


if __name__ == "__main__":
    main(sys.argv[1:])
