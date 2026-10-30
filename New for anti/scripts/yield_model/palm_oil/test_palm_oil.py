"""Offline checks for palm_oil: synthetic weather and PSD, no network.

Run: cd "New for anti/scripts/yield_model" && python3 -m pytest palm_oil -q
"""

from datetime import date

import numpy as np
import pandas as pd

from palm_oil import conditions as K
from palm_oil import forecast, psd
from palm_oil.producers import ALL, MALAYSIA


def _daily(drought_years, seed=0):
    rng = np.random.default_rng(seed)
    days = pd.date_range("1984-01-01", "2026-10-25", freq="D")
    rain = rng.gamma(0.6, 12.0, len(days))
    soil = np.full(len(days), 0.8)
    for y in drought_years:
        dry = (days >= pd.Timestamp(y, 2, 1)) & (days <= pd.Timestamp(y, 7, 31))
        rain[dry] = 0.0
        soil[dry] = 0.5
    return pd.DataFrame({"date": days, "precip": rain, "soil": soil})


def test_windows_follow_marketing_year():
    assert K.window(2027, 1) == (pd.Timestamp(2025, 10, 1), pd.Timestamp(2026, 9, 30))
    assert K.window(2027, 2) == (pd.Timestamp(2024, 10, 1), pd.Timestamp(2025, 9, 30))
    assert K.season_label(2027, 1) == "2025/26"


def test_point_features_need_a_full_window():
    d = _daily([])
    assert "water_deficit_lag1" in K.point_features(d, 2027)
    assert "water_deficit_lag1" not in K.point_features(d, 2028)


def test_drought_reads_unfavourable():
    droughts = [1998, 2005, 2010, 2016, 2020, 2024]
    dailies = {p["name"]: _daily(droughts, i) for i, p in enumerate(MALAYSIA.points)}
    nino = {f"{y}-{m:02d}": (1.5 if y in droughts else 0.0)
            for y in range(1982, 2027) for m in range(1, 13)}
    frame = K.feature_frame(MALAYSIA, dailies, nino, 2027)
    z = K.z_frame(frame)
    row = z[z.year == 2025].iloc[0]          # window Oct 2023 - Sep 2024
    items, score, verdict = K.classify(row)
    assert verdict == "unfavorable" and score <= -2
    quiet = z[z.year == 2023].iloc[0]
    assert K.classify(quiet)[2] == "neutral"


def test_backtest_and_region(tmp_path, monkeypatch):
    droughts = [1998, 2005, 2010, 2016, 2020, 2024]
    dailies = {p["name"]: _daily(droughts, i) for i, p in enumerate(MALAYSIA.points)}
    nino = {f"{y}-{m:02d}": (1.5 if y in droughts else 0.0)
            for y in range(1982, 2027) for m in range(1, 13)}
    frame = K.feature_frame(MALAYSIA, dailies, nino, 2027)

    years = np.arange(1980, 2027)
    prod = 5000 * np.exp(0.04 * (years - 1980))
    prod = np.where(np.isin(years, [d + 1 for d in droughts]), prod * 0.9, prod)
    rows = [{"Country_Name": p.psd_name, "Market_Year": y - 1, "Calendar_Year": 2026,
             "Month": 10, "Attribute_Description": "Production",
             "Unit_Description": "(1000 MT)", "Value": v}
            for p in ALL for y, v in zip(years, prod)]
    rows.append({"Country_Name": "Malaysia", "Market_Year": 2026, "Calendar_Year": 2026,
                 "Month": 10, "Attribute_Description": "Production",
                 "Unit_Description": "(1000 MT)", "Value": 31000.0})
    csv = tmp_path / "psd_palm.csv"
    pd.DataFrame(rows).to_csv(csv, index=False)
    monkeypatch.setattr(psd, "PSD_CSV", str(csv))
    labels = psd.labels(MALAYSIA)
    assert labels.year.max() == 2027

    result = K.backtest(MALAYSIA, frame, labels)
    assert result["classes"]["unfavorable"]["mean_residual_pct"] < 0
    assert result["unfavorable_supported"]

    monkeypatch.setattr(K, "TRAINING", str(tmp_path))
    frame.to_csv(K.features_path(MALAYSIA), index=False)
    import json
    with open(K.backtest_path(MALAYSIA), "w") as f:
        json.dump(result, f)
    entry = forecast.region(MALAYSIA, today=date(2026, 10, 30))
    assert entry["season"] == 2027
    assert entry["usda_estimate"] == 31000.0
    assert entry["point_basis"] == "trend" and entry["weather_effect_pct"] == 0.0
    wc = entry["weather_conditions"]
    assert wc["target_year"] == 2027 and wc["applied_to_forecast"] is False
    assert wc["indicators"][0]["season"] == "2025/26"
