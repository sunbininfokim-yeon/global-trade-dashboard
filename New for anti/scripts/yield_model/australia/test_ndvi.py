"""Offline checks for the Australian/Canadian NDVI channel: synthetic NDVI, no network.

Run: cd "New for anti/scripts/yield_model" && python3 -m pytest australia/test_ndvi.py -q
"""

import json

import numpy as np
import pandas as pd
import pytest

from australia import ndvi as N
from canada import ndvi as C


def _synthetic(country, cfg, base, signal, seed=0):
    rng = np.random.default_rng(seed)
    (m0, d0), (m1, d1) = country.window
    rows = []
    for y in range(2001, 2026):
        err = np.log(base[y][0] / base[y][1]) if y in base else 0.0
        for d in pd.date_range(pd.Timestamp(y, m0, d0), pd.Timestamp(y, m1, d1), freq="16D"):
            for p in cfg.points:
                v = 0.6 + signal * err + rng.normal(0, 0.02)
                rows.append({"point": p["name"], "date": d,
                             "ndvi_p75": v, "ndvi_median": v - 0.05})
    return pd.DataFrame(rows)


@pytest.mark.parametrize("make,key", [(N.australia, "wa_wheat"), (N.australia, "sa_barley"),
                                      (C.canada, "sad_sk_canola_palliser")])
def test_backtest_switches_on_for_signal_and_off_for_noise(make, key):
    country = make()
    cfg = next(c for c in country.configs if c.key == key)
    base, _ = N.base_forecasts(country, cfg)
    on = N.score(country, cfg, _synthetic(country, cfg, base, 2.0))
    assert on["live"]["full"]["enabled"] and on["full"]["skill_vs_base"] > 0.3
    off = N.score(country, cfg, _synthetic(country, cfg, base, 0.0, seed=1))
    assert not off["live"]["full"]["enabled"]


def test_adjustment_applies_only_a_live_window(tmp_path):
    country = N.australia()
    country.cond, country.out = str(tmp_path), str(tmp_path / "ndvi_points.csv")
    cfg = next(c for c in country.configs if c.key == "wa_wheat")
    base, _ = N.base_forecasts(country, cfg)
    nd = _synthetic(country, cfg, base, 2.0)
    nd.to_csv(country.out, index=False)
    report = {cfg.key: N.score(country, cfg, nd)}
    (tmp_path / "ndvi_backtest.json").write_text(json.dumps(report))
    assert N.adjustment(country, cfg, 2024)["window"] == "full"
    assert N.adjustment(country, cfg, 2030) is None
    report[cfg.key]["live"] = {"full": {"enabled": False}, "half": {"enabled": False}}
    (tmp_path / "ndvi_backtest.json").write_text(json.dumps(report))
    assert N.adjustment(country, cfg, 2024) is None


def test_sites_move_only_the_listed_points():
    a, c = N.australia().sites(), C.canada().sites()
    assert a["Esperance"][:2] == N.SITES["Esperance"] and a["Merredin"][:2] == (-31.48, 118.28)
    assert a["Merredin"][2] == {7, 8, 9}
    assert c["Winnipeg"][:2] == C.SITES["Winnipeg"] and c["Yorkton"][:2] == (51.21, -102.46)
    assert c["Yorkton"][2] == {7, 8}


def test_apply_scales_point_and_ranges():
    row = {"point": 1000.0, "range_68": [900.0, 1100.0], "range_95": [800.0, 1200.0]}
    adj = {"log_adjustment": float(np.log(1.1)), "adjustment_pct": 10.0}
    out = N.apply(row, adj)
    assert out["point"] == pytest.approx(1100.0)
    assert out["range_68"] == pytest.approx([990.0, 1210.0])
    assert out["ndvi"] is adj
    assert N.apply({"point": 5.0}, None) == {"point": 5.0}


def test_half_window_needs_the_full_window_not_to_hurt():
    good = {"skill_vs_base": 0.2}
    entry = {"half": good, "half_median": good, "full": {"skill_vs_base": -0.1},
             "full_median": {"skill_vs_base": -0.1}}
    assert not N.switched_on(entry, "half", 0.05)
    entry["full"] = {"skill_vs_base": 0.01}
    assert N.switched_on(entry, "half", 0.05)
    assert not N.switched_on(entry, "full", 0.05)
