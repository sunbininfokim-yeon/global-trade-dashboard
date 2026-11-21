import unittest

import numpy as np
import pandas as pd

import affordability as A


def prices(years, rng):
    rows = []
    for y in years:
        u, m, s = rng.uniform(150, 500), rng.uniform(100, 250), rng.uniform(250, 450)
        for mo in range(1, 13):
            rows.append({"month": f"{y}-{mo:02d}", "urea": u, "maize": m, "soybeans": s})
    return pd.DataFrame(rows)


class AffordabilityTest(unittest.TestCase):
    def test_detects_dear_nitrogen_cutting_corn(self):
        rng = np.random.default_rng(1)
        p = prices(range(1979, 2027), rng)
        win = A.window_means(p)
        full = win[win.months == 6]
        share = 55 - 8 * np.log(full.urea_corn) + 4 * np.log(1 / full.soy_corn) + rng.normal(0, 0.3, len(full))
        corn = share * 10
        area = pd.DataFrame({"year": full.index, "corn_kha": corn.values, "soy_kha": (1000 - corn).values})
        bt = A.backtest(win, area)
        self.assertTrue(bt["passed"])
        self.assertLess(bt["coef_share_pp_per_10pct"], 0)

    def test_noise_does_not_pass(self):
        rng = np.random.default_rng(2)
        p = prices(range(1979, 2027), rng)
        win = A.window_means(p)
        full = win[win.months == 6]
        corn = 500 + rng.normal(0, 20, len(full))
        area = pd.DataFrame({"year": full.index, "corn_kha": corn, "soy_kha": 1000 - corn})
        self.assertFalse(A.backtest(win, area)["passed"])

    def test_window_spans_new_year(self):
        p = pd.DataFrame([{"month": "2025-09", "urea": 400, "maize": 200, "soybeans": 400},
                          {"month": "2026-02", "urea": 300, "maize": 200, "soybeans": 400},
                          {"month": "2026-05", "urea": 999, "maize": 200, "soybeans": 400}])
        w = A.window_means(p)
        self.assertEqual(list(w.index), [2026])
        self.assertAlmostEqual(w.loc[2026].urea_corn, 1.75)


if __name__ == "__main__":
    unittest.main()
