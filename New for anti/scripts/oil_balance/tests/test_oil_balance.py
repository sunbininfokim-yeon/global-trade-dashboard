from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oil_balance import model as om  # noqa: E402


def months(y0: int, y1: int) -> list[str]:
    return [f"{y}-{m:02d}" for y in range(y0, y1 + 1) for m in range(1, 13)]


class Model(unittest.TestCase):
    def test_deviation_is_against_the_same_month_five_years_back(self):
        doc = {m: 60.0 + (2.0 if m == "2021-03" else 0.0) for m in months(2015, 2021)}
        dev = om.deviation(doc)
        self.assertNotIn("2019-03", dev)                 # needs 2014-2018
        self.assertEqual(dev["2021-03"], 2.0)
        self.assertEqual(dev["2021-04"], 0.0)

    def test_fit_recovers_the_line_and_gap_stats(self):
        ms = months(2015, 2025)
        dev = {m: math.sin(i / 7) * 4 for i, m in enumerate(ms)}
        brent = {m: math.exp(4.2 - 0.045 * dev[m]) for m in ms}
        brent["2022-06"] += 30
        brent["2022-07"] += 20
        c = om.fit(dev, brent)
        self.assertAlmostEqual(c["b"], -0.045, delta=0.005)
        g = om.gap_stats(brent, om.fair_value(dev, {"a": 4.2, "b": -0.045}), "2015-01", "2025-12")
        self.assertEqual(g["max_premium_month"], "2022-06")
        self.assertEqual((g["episodes_above_band"], g["avg_months_above_band"]), (1, 2.0))

    def test_runs(self):
        self.assertEqual(om.runs([True, True, False, True]), [2, 1])


if __name__ == "__main__":
    unittest.main()
