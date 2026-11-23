import numpy as np

from brazil import enso_analog as E


def _series(n=30, hit=-0.12):
    years = np.arange(1995, 1995 + n, dtype=float)
    n34 = np.where(np.arange(n) % 7 == 0, 1.8, 0.0)
    yields = 2000 * np.exp(0.02 * (years - 1995) + np.where(n34 > 1, hit, 0.01))
    return years, yields, n34


def test_neutral_year_has_almost_no_shift():
    y, Y, n = _series()
    shift, _ = E.direct_adjust(y, Y, n, 0.0)
    assert abs(shift) < 0.03


def test_el_nino_year_shifts_down():
    y, Y, n = _series()
    shift, info = E.direct_adjust(y, Y, n, 1.8)
    assert shift < -0.08
    assert info["analogs"][0]["departure_pct"] < 0


def test_too_few_seasons():
    y, Y, n = _series(n=10)
    assert E.direct_adjust(y, Y, n, 1.8) == (None, None)


def test_switch_matches_committed_backtest():
    import json
    with open(E.OUT, encoding="utf-8") as f:
        direct = json.load(f)["direct"]["regions"]
    for key, r in direct.items():
        assert r["earns_switch"] == (key in E.DIRECT_ON)
