import numpy as np
import pandas as pd

from .regions import POINTS
from .train import _prepare


def test_regional_weights_match_rounded_ecta_total():
    assert np.isclose(sum(p["weight"] for p in POINTS), 0.995)


def test_lag2_is_detrended_without_mutating_frame():
    frame = pd.DataFrame({"yield_lag2_kg_ha": [500.0], "area_growth_lag2": [0.02]})
    trend = np.poly1d([0.0, np.log(400.0)])
    result = _prepare(frame, ["yield_lag2_kg_ha", "area_growth_lag2"], np.array([2020.0]), trend)
    assert np.isclose(result[0, 0], np.log(500.0) - np.log(400.0))
    assert frame.iloc[0, 0] == 500.0
