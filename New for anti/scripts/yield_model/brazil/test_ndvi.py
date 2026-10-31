"""Offline checks for the Brazil NDVI channel: no network, synthetic NDVI.

Run: cd "New for anti/scripts/yield_model" && python3 -m pytest brazil/test_ndvi.py -q
"""

import json

import numpy as np
import pandas as pd
import pytest

from brazil import ndvi as N
from brazil import ndvi_backtest as B
from brazil import ndvi_blend
from brazil.regions import BY_KEY


def test_windows_are_the_first_run_of_the_critical_window():
    want = {
        "mato_grosso_soja": ((11, 1, -1), (2, 28, 0)),
        "mato_grosso_milho": ((3, 1, 0), (6, 30, 0)),
        "parana_soja": ((12, 1, -1), (2, 28, 0)),
        "parana_milho": ((11, 1, -1), (1, 31, 0)),
        "parana_trigo": ((8, 1, 0), (11, 30, 0)),
        "matopiba_soja": ((12, 1, -1), (2, 28, 0)),
        "matopiba_algodao": ((2, 1, 0), (4, 30, 0)),
        "sp_cana": ((10, 1, -1), (3, 31, 0)),
        "sp_cafe": ((9, 1, -1), (10, 31, -1)),
        "sp_laranja": ((9, 1, -1), (2, 28, 0)),
    }
    for key, w in want.items():
        assert B.window(BY_KEY[key]) == w, key


def test_runs_split_at_gaps_and_at_the_api_limit():
    every = [f"A2020{d:03d}" for d in range(1, 366, 16)]
    want = set(every[0:3]) | set(every[5:17])
    chunks = N.runs(every, want, limit=10)
    assert chunks == [every[0:3], every[5:15], every[15:17]]


def test_sites_move_only_the_valley_towns_and_union_the_months():
    s = N.sites()
    assert len(s) == 19
    assert s["Ribeirao Preto"][:2] == N.SITES["Ribeirao Preto"]
    assert s["Barreiras"][:2] == N.SITES["Barreiras"]
    assert s["Pedro Afonso"][:2] == (-8.97, -48.17)
    # Barreiras serves soy (Dec-Feb) and cotton (Feb-Apr).
    assert s["Barreiras"][2] == {12, 1, 2, 3, 4}
    assert s["Patrocinio"][2] == {9, 10}


def _synthetic_ndvi(cfg, base, signal, seed=0):
    """Composites at every site whose window mean tracks the forecast error."""
    rng = np.random.default_rng(seed)
    (m0, d0, o0), (m1, d1, o1) = B.window(cfg)
    rows = []
    for y in range(2001, 2026):
        err = np.log(base[y][0] / base[y][1]) if y in base else 0.0
        a = pd.Timestamp(y + o0, m0, d0)
        b = pd.Timestamp(y + o1, m1, d1)
        for d in pd.date_range(a, b, freq="16D"):
            for p in cfg.points:
                v = 0.7 + signal * err + rng.normal(0, 0.02)
                rows.append({"point": p["name"], "date": d,
                             "ndvi_p75": v, "ndvi_median": v - 0.05})
    return pd.DataFrame(rows)


@pytest.mark.parametrize("key", ["parana_soja", "mato_grosso_soja"])
def test_backtest_switches_on_for_signal_and_off_for_noise(key):
    cfg = BY_KEY[key]
    base, _ = B.base_forecasts(cfg)
    on = B.score(cfg, _synthetic_ndvi(cfg, base, signal=2.0))
    assert on["live"]["full"]["enabled"] and on["full"]["skill_vs_base"] > 0.3
    off = B.score(cfg, _synthetic_ndvi(cfg, base, signal=0.0, seed=1))
    assert not off["live"]["full"]["enabled"]
    assert on["sites"][cfg.points[0]["name"]]["seasons"] >= 20


def test_blend_applies_only_a_live_window(tmp_path, monkeypatch):
    cfg = BY_KEY["parana_soja"]
    base, _ = B.base_forecasts(cfg)
    nd = _synthetic_ndvi(cfg, base, signal=2.0)
    report = {cfg.key: B.score(cfg, nd)}
    nd.to_csv(tmp_path / "ndvi_points.csv", index=False)
    with open(tmp_path / "ndvi_backtest.json", "w") as f:
        json.dump(report, f)
    monkeypatch.setattr(ndvi_blend, "COND", str(tmp_path))
    adj = ndvi_blend.adjustment(cfg, 2024)
    assert adj is not None and adj["window"] == "full"
    assert ndvi_blend.adjustment(cfg, 2030) is None
    report[cfg.key]["live"] = {"full": {"enabled": False}, "half": {"enabled": False}}
    with open(tmp_path / "ndvi_backtest.json", "w") as f:
        json.dump(report, f)
    assert ndvi_blend.adjustment(cfg, 2024) is None


def test_merge_drops_rows_from_a_moved_site(tmp_path, monkeypatch):
    out = tmp_path / "ndvi_points.csv"
    monkeypatch.setattr(N, "OUT", str(out))
    old = pd.DataFrame([
        {"point": "Barreiras", "modis_date": "A2020001", "date": "2020-01-01",
         "lat": -12.15, "lon": -45.0, "ndvi_median": 0.4, "ndvi_p75": 0.5,
         "n_good": 1, "n_pixels": 1},
        {"point": "Sorriso", "modis_date": "A2020001", "date": "2020-01-01",
         "lat": -12.55, "lon": -55.72, "ndvi_median": 0.8, "ndvi_p75": 0.85,
         "n_good": 1, "n_pixels": 1}])
    old.to_csv(out, index=False)
    shard = tmp_path / "s0.csv"
    new = old.iloc[[0]].assign(lat=N.SITES["Barreiras"][0], lon=N.SITES["Barreiras"][1])
    new.to_csv(shard, index=False)
    empty = tmp_path / "s1.csv"
    pd.DataFrame(columns=N.COLUMNS).to_csv(empty, index=False)
    N.merge([str(shard), str(empty)])
    got = pd.read_csv(out)
    assert len(got) == 2
    assert got[got.point == "Barreiras"].lat.iloc[0] == N.SITES["Barreiras"][0]
