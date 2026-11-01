import importlib.util
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location("cw", Path(__file__).resolve().parents[1] / "coal_weather.py")
cw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cw)
cw.log = lambda msg: None


def synthetic(effect, seed=0):
    rng = np.random.default_rng(seed)
    months = pd.period_range("2001-01", "2025-12", freq="M").astype(str)
    rain = pd.DataFrame({p["name"]: rng.gamma(4, 60, len(months)) for p in cw.POINTS}, index=months)
    x = cw.rain_z(rain)
    lab = months[months >= "2010-01"]
    trend = np.linspace(np.log(1.0e6), np.log(1.6e6), len(lab))
    noise = rng.normal(0, 0.05, len(lab))
    days = pd.PeriodIndex(lab, freq="M").days_in_month.values
    tonnes = pd.Series(np.exp(trend + noise + effect * x.reindex(lab).values) * days, index=lab)
    return tonnes, x


class CoalWeatherTest(unittest.TestCase):
    def test_rain_z_is_standardised(self):
        _, x = synthetic(0.0)
        base = x[(x.index >= "2001") & (x.index < "2021")]
        self.assertLess(abs(base.mean()), 0.1)

    def test_detects_a_real_rain_effect(self):
        tonnes, x = synthetic(-0.06)
        res = cw.assess(tonnes, x, None)
        self.assertTrue(res["passed"], res)
        self.assertLess(res["slope_pct_per_z"], 0)

    def test_rejects_noise(self):
        passes = sum(cw.assess(*synthetic(0.0, seed), None)["passed"] for seed in range(20))
        self.assertLessEqual(passes, 2)

    def test_excluded_months_are_dropped(self):
        tonnes, x = synthetic(0.0)
        tonnes["2022-01"] = tonnes["2022-01"] * 0.2  # export ban
        r = cw.residuals(tonnes)
        self.assertIn("2022-01", r.index)
        res = cw.assess(tonnes, x, None)
        self.assertEqual(res["n"], len(r) - len(cw.EXCLUDE & set(r.index)))

    def test_risk_levels(self):
        self.assertEqual(cw.risk_level(2.0), "high")
        self.assertEqual(cw.risk_level(1.0), "elevated")
        self.assertEqual(cw.risk_level(0.2), "normal")


if __name__ == "__main__":
    unittest.main()
