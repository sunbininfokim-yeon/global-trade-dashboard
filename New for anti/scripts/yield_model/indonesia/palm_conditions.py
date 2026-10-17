"""Favourable / unfavourable / neutral weather read-out for Indonesian palm oil.

No weather regression beats the trend on the USDA PSD palm-oil label
(training/palm_psd_experiment.json), so the forecast stays trend-only. This
module instead reports which of the known lagged drought mechanisms are
active and whether, taken together, they put the coming marketing year at
risk. It does not move the number.

Indicators for label year T (marketing year T-1/T, Oct-Sep):
  dry_spell_lag1   longest run without rain, Jun-Oct of T-1  (bunch abortion, ~12 months)
  precip_dry_lag1  rainfall total, Jun-Oct of T-1
  oni_season       ENSO over the same dry season (El Nino = drought)
  soil_dry_lag2    root-zone soil wetness, Jun-Oct of T-2   (sex ratio, ~24 months)

Each is a z score against the 20 seasons before it (at least 10). The
thresholds are fixed here, not tuned: |z| >= 0.75, |ONI| >= 0.5. A score of
-2 or worse is "unfavourable". There is no "favourable" verdict: in the
backtest, wet/La Nina years did not land above trend (see ``backtest``), so
claiming an upside would be unsupported.
"""

import json
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

from . import climate as C
from .collect import blend_features
from .regions import PALM

HERE = os.path.dirname(os.path.abspath(__file__))
TRAINING = os.path.join(HERE, "training")
FEATURES_CSV = os.path.join(TRAINING, "indonesia_oil_palm.csv")
BACKTEST_JSON = os.path.join(TRAINING, "palm_conditions_backtest.json")

Z = 0.75
ONI = 0.5
VERDICT_AT = -2
DRY_MONTHS = (6, 7, 8, 9, 10)

LABELS_KO = {
    "favorable": "유리",
    "unfavorable": "불리",
    "neutral": "중립",
}

INDICATORS = [
    {"key": "dry_spell_lag1", "lag": 1, "unit": "일", "high_is": "unfavorable",
     "label_ko": "작년 건기 최장 무강우 일수",
     "why_ko": "건기 가뭄이 길면 약 12개월 뒤 수확할 송이가 떨어진다(낙과·수분 실패)."},
    {"key": "precip_dry_lag1", "lag": 1, "unit": "mm", "high_is": "favorable",
     "label_ko": "작년 건기(6~10월) 강수량",
     "why_ko": "건기 강수 부족은 이듬해 송이 수와 무게를 줄인다."},
    {"key": "oni_season", "lag": 1, "unit": "°C", "high_is": "unfavorable",
     "label_ko": "작년 건기 엘니뇨/라니냐(ONI)",
     "why_ko": "엘니뇨 해 건기는 수마트라·칼리만탄 가뭄과 연무로 이어져 6~24개월 뒤 생산을 깎는다."},
    {"key": "soil_dry_lag2", "lag": 2, "unit": "", "high_is": "favorable",
     "label_ko": "재작년 건기 토양수분",
     "why_ko": "2년 전 가뭄은 암꽃 분화를 줄여 약 24개월 뒤 수확량을 낮춘다."},
]


def _z_frame(frame):
    out = frame.sort_values("year").reset_index(drop=True).copy()
    for spec in INDICATORS:
        if spec["key"] == "oni_season":
            continue
        prior = out[spec["key"]].shift(1)
        mean = prior.rolling(20, min_periods=10).mean()
        std = prior.rolling(20, min_periods=10).std(ddof=1)
        out[spec["key"] + "_normal"] = mean
        out[spec["key"] + "_z"] = (out[spec["key"]] - mean) / std.replace(0, np.nan)
    return out


def _status(spec, row):
    if spec["key"] == "oni_season":
        value = row.get("oni_season")
        z, threshold = value, ONI
    else:
        z, threshold = row.get(spec["key"] + "_z"), Z
    if z is None or pd.isna(z):
        return None
    high = spec["high_is"]
    low = "favorable" if high == "unfavorable" else "unfavorable"
    if z >= threshold:
        status = high
    elif z <= -threshold:
        status = low
    else:
        status = "neutral"
    # Two-year-old drought cuts output; a wet season two years back is not
    # an upside the literature or our backtest supports.
    if spec["key"] == "soil_dry_lag2" and status == "favorable":
        status = "neutral"
    return status


def classify(row):
    """Indicator list, score and verdict for one feature row."""
    items, score = [], 0
    for spec in INDICATORS:
        status = _status(spec, row)
        if status is None:
            continue
        score += {"favorable": 1, "unfavorable": -1}.get(status, 0)
        value = row.get(spec["key"])
        normal = row.get(spec["key"] + "_normal")
        items.append({
            "key": spec["key"],
            "label_ko": spec["label_ko"],
            "season": int(row["year"]) - spec["lag"],
            "value": None if value is None or pd.isna(value) else round(float(value), 2),
            "normal": None if normal is None or pd.isna(normal) else round(float(normal), 2),
            "z": (None if spec["key"] == "oni_season"
                  else round(float(row[spec["key"] + "_z"]), 2)),
            "unit": spec["unit"],
            "status": status,
            "status_ko": LABELS_KO[status],
            "why_ko": spec["why_ko"],
        })
    verdict = "unfavorable" if score <= VERDICT_AT else "neutral"
    return items, score, verdict


def _trend_residuals(labels):
    """log(actual) minus a linear trend on the ten years before it."""
    series = labels.set_index("year").psd_production_kt
    out = {}
    for year in series.index:
        prior = series[(series.index < year) & (series.index >= year - 10)]
        if len(prior) < 8:
            continue
        slope = np.polyfit(prior.index, np.log(prior.values), 1)
        out[int(year)] = float(np.log(series[year]) - np.polyval(slope, year))
    return pd.Series(out)


def backtest(write=True):
    """How production landed against trend in each verdict class, 1996 on."""
    from .palm_psd import psd_labels

    frame = _z_frame(pd.read_csv(FEATURES_CSV))
    residual = _trend_residuals(psd_labels())
    rows = []
    for _, row in frame.iterrows():
        year = int(row["year"])
        if year not in residual.index or pd.isna(row.get("dry_spell_lag1_z")):
            continue
        _, score, verdict = classify(row)
        rows.append({"year": year, "score": score, "verdict": verdict,
                     "residual_pct": round(residual[year] * 100, 1)})
    table = pd.DataFrame(rows)
    classes = {}
    for verdict, group in table.groupby("verdict"):
        classes[verdict] = {
            "n": int(len(group)),
            "years": [int(y) for y in group.year],
            "mean_residual_pct": round(float(group.residual_pct.mean()), 1),
            "below_trend_share": round(float((group.residual_pct < 0).mean()), 2),
        }
    wet = table[table.score >= 2]
    result = {
        "label": "USDA PSD Indonesia palm oil production, residual vs prior-10-year log trend",
        "years": [int(table.year.min()), int(table.year.max())],
        "thresholds": {"z": Z, "oni": ONI, "verdict_at": VERDICT_AT},
        "classes": classes,
        "wet_score_ge_2": {
            "n": int(len(wet)),
            "mean_residual_pct": round(float(wet.residual_pct.mean()), 1) if len(wet) else None,
            "note": "Why no favourable verdict: wet/La Nina seasons did not beat trend.",
        },
        "rows": rows,
    }
    if write:
        with open(BACKTEST_JSON, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
            handle.write("\n")
    return result


def _truncate(daily, year, cutoff):
    """Drop days after ``cutoff`` inside the Jun-Oct window of ``year``."""
    months = daily.date.dt.month
    in_window = months.isin(DRY_MONTHS)
    after = (daily.date.dt.month * 100 + daily.date.dt.day) > cutoff.month * 100 + cutoff.day
    return daily[~(in_window & after & (daily.date.dt.year == year))]


def current_frame(target, dailies, oni, today):
    """Feature rows up to ``target`` from daily weather.

    When the Jun-Oct season before ``target`` is still running, every year's
    lag-1 window is cut at today's day of year, so a half-finished season is
    compared with half-seasons rather than read as a drought.
    """
    from .data import oni_for

    season_year = target - 1
    end = date(season_year, 10, 31)
    cutoff = min(today, end)
    partial = cutoff < end
    rows = []
    first = min(d.date.min().year for d in dailies.values()) + 2
    for year in range(first, target + 1):
        full = blend_features(PALM, dailies, year)
        if partial:
            cut = {name: _truncate(d, year - 1, cutoff) for name, d in dailies.items()}
            lag1 = blend_features(PALM, cut, year)
            for key in ("dry_spell_lag1", "precip_dry_lag1"):
                if key in lag1:
                    full[key] = lag1[key]
        full["year"] = year
        full["oni_season"] = oni_for(oni, year)
        rows.append(full)
    days = (cutoff - date(season_year, 6, 1)).days + 1
    observed = max(0.0, min(1.0, days / 153.0))
    return _z_frame(pd.DataFrame(rows)), observed


def assess(target, today=None):
    """Weather read-out for label year ``target``; None if weather is missing."""
    from .data import load_oni, point_weather

    today = today or date.today()
    dailies = {p["name"]: point_weather(p) for p in PALM.points}
    frame, observed = current_frame(target, dailies, load_oni(), today)
    row = frame[frame.year == target]
    if row.empty:
        return None
    items, score, verdict = classify(row.iloc[0])
    try:
        with open(BACKTEST_JSON, encoding="utf-8") as handle:
            history = json.load(handle)
    except OSError:
        history = backtest(write=False)
    return summary(target, items, score, verdict, observed, history)


def summary(target, items, score, verdict, observed, history):
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
        reason += " · 습윤 신호는 과거에 증산으로 이어지지 않아 유리로 보지 않는다"
    classes = history.get("classes", {})
    unf, neu = classes.get("unfavorable", {}), classes.get("neutral", {})
    history_ko = None
    if unf.get("n"):
        history_ko = ("{}~{}년 중 불리 판정 {}번({}) 모두 생산이 추세보다 낮았고, "
                      "평균 {:+.1f}% (중립 해 평균 {:+.1f}%)").format(
            history["years"][0], history["years"][1], unf["n"],
            ", ".join(str(y) for y in unf["years"]),
            unf["mean_residual_pct"], neu.get("mean_residual_pct", float("nan")))
        if unf.get("below_trend_share", 1) < 1:
            history_ko = history_ko.replace("모두", "{:.0%}".format(unf["below_trend_share"]))
    return {
        "target_year": target,
        "verdict": verdict,
        "verdict_ko": LABELS_KO[verdict],
        "score": score,
        "reason_ko": reason,
        "season_observed_share": round(observed, 2),
        "indicators": items,
        "history_ko": history_ko,
        "applied_to_forecast": False,
        "note_ko": "판정은 참고용이며 예측치(추세)에는 반영하지 않는다.",
    }


if __name__ == "__main__":
    if sys.argv[1:] == ["backtest"]:
        out = backtest()
        print(json.dumps(out["classes"], indent=2))
