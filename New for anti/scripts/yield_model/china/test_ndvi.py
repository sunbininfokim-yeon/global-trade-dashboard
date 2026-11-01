"""Offline tests for china/ndvi.py (no network)."""

import numpy as np
import pandas as pd

from australia import ndvi as N
from china import ndvi as C
from china.regions import BY_KEY


def test_sites_and_windows():
    country = C.china()
    assert [c.key for c in country.configs] == list(C.WINDOWS)
    sites = country.sites()
    # every weather point of the four configs is collected, cities moved
    for cfg in country.configs:
        for p in cfg.points:
            assert p["name"] in sites
    assert sites["Zhengzhou"][2] == frozenset({3, 4, 5})
    assert sites["Harbin"][2] == frozenset({7, 8})
    assert sites["Wuhan"][:2] == C.SITES["Wuhan"]


def test_trend_base_uses_only_earlier_seasons():
    base, operational = C.trend_base(BY_KEY["northeast_soy"])
    assert operational is False
    assert min(base) >= 2001
    frame = pd.read_csv(f"{C.os.path.dirname(C.__file__)}/training/northeast_soy.csv")
    truth = dict(zip(frame.year, frame.target))
    for y, (t, p) in base.items():
        assert t == truth[y]
        assert p > 0


def test_switch_on_against_trend(monkeypatch):
    """Synthetic NDVI that explains the trend error switches the window on;
    noise leaves it off."""
    country = C.china()
    cfg = BY_KEY["northeast_soy"]
    base, _ = C.trend_base(cfg)
    rng = np.random.default_rng(0)

    def frame(signal):
        rows = []
        for y, (t, p) in base.items():
            v = 0.7 + (np.log(t / p) * 3 if signal else rng.normal(0, 0.05))
            for p_ in cfg.points:
                for d in pd.date_range(f"{y}-07-04", f"{y}-08-28", freq="16D"):
                    rows.append({"point": p_["name"], "date": d,
                                 "ndvi_p75": v, "ndvi_median": v - 0.02})
        return pd.DataFrame(rows)

    on = N.score(country, cfg, frame(True))
    assert on["base"] == "trend"
    assert on["live"]["full"]["enabled"]
    off = N.score(country, cfg, frame(False))
    assert not off["live"]["full"]["enabled"]


def test_apply_recentres_on_trend():
    row = {"trend": 2000.0, "point": 2200.0,
           "range_68": [1900.0, 2300.0], "range_95": [1700.0, 2500.0],
           "presentation": "trend extrapolation"}
    adj = {"log_adjustment": float(np.log(1.05)), "adjustment_pct": 5.0}
    C.apply(row, adj)
    assert row["point"] == 2100.0          # 2000 x 1.05: the weather effect is replaced
    assert row["range_68"] == [1800.0, 2200.0]
    assert row["range_95"] == [1600.0, 2400.0]
    assert row["presentation"] == "trend x NDVI"
    assert row["ndvi"] is adj
    assert C.apply({"point": 1.0}, None) == {"point": 1.0}
