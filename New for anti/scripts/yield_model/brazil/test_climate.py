"""Offline checks for brazil.climate: synthetic weather, no network.

Run: cd "New for anti/scripts/yield_model" && python3 -m pytest brazil/test_climate.py -q
"""

import numpy as np
import pandas as pd

from brazil import climate as C


def _daily(until):
    """Dry July-mid October, 10 mm a day from 15 Oct to 15 Apr, every year."""
    dates = pd.date_range("2024-01-01", until)
    wet = ((dates.month > 10) | (dates.month < 4)
           | ((dates.month == 10) & (dates.day >= 15))
           | ((dates.month == 4) & (dates.day <= 15)))
    return pd.DataFrame({"date": dates, "precip": np.where(wet, 10.0, 0.5)})


def _doy(ts, plant_year):
    return (pd.Timestamp(ts) - pd.Timestamp(plant_year, 1, 1)).days + 1


def test_covered_window_is_unchanged():
    daily = _daily("2027-12-31")
    start, end = pd.Timestamp(2025, 7, 1), pd.Timestamp(2026, 6, 30)
    onset, demise, _ = C.anomalous_accumulation(daily, start, end)
    assert C.onset_doy(daily, 2026) == (_doy(onset, 2025), _doy(demise, 2025))


def test_season_in_progress_has_no_demise_yet():
    # Data to 10 Nov: the rains began 15 Oct, the demise is months away.
    ors, ers = C.onset_doy(_daily("2026-11-10"), 2027)
    assert ers is None
    assert ors == _doy("2026-10-14", 2026)


def test_onset_waits_until_the_rise_is_confirmed():
    # Six days of rain is not yet an onset, and a dry-season-only window must
    # not put it at the first shower.
    assert C.onset_doy(_daily("2026-10-21"), 2027) == (None, None)
    assert C.onset_doy(_daily("2026-09-30"), 2027) == (None, None)


def test_no_complete_window_means_no_live_onset():
    daily = _daily("2026-11-10")
    assert C.onset_doy(daily[daily.date >= "2026-01-01"], 2027) == (None, None)
