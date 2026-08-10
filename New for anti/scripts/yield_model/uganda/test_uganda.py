import numpy as np
import pandas as pd

from .collect import add_causal_anomalies
from .regions import POINTS


def test_weights_sum_to_one():
    assert abs(sum(point["weight"] for point in POINTS) - 1.0) < 1e-9
    assert abs(sum(point["weight"] for point in POINTS if point["species"] == "robusta") - 0.85) < 1e-9


def test_anomaly_is_causal():
    frame = pd.DataFrame({"year": range(2000, 2013), "rain_short_rains_mm": range(13)})
    for name in ("rain_long_rains_mm", "rain_jun_jul_mm", "hot28_edd_c_days", "root_sm_long_rains", "vpd_long_rains_kpa"):
        frame[name] = range(13)
    result = add_causal_anomalies(frame, window=20, min_prior=10)
    expected = (10 - np.mean(range(10))) / np.std(range(10), ddof=1)
    assert np.isclose(result.loc[result.year == 2010, "rain_short_rains_mm_z"].iloc[0], expected)
