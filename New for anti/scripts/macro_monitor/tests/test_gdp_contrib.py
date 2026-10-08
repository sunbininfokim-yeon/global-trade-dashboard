"""gdp_contrib: expenditure contributions to real GDP growth (no network)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macro_monitor import gdp_contrib as gc  # noqa: E402

Q = ["2026-01-01", "2026-04-01"]


def reader(series):
    return lambda kind, key: series[key]


class Build(unittest.TestCase):
    def test_usa_parts_total_and_residual(self):
        s = {"A191RL1Q225SBEA": list(zip(Q, [2.5, 2.2])), "DPCERY2Q224SBEA": list(zip(Q, [0.49, 2.51])),
             "A006RY2Q224SBEA": list(zip(Q, [1.25, 0.82])), "A822RY2Q224SBEA": list(zip(Q, [0.80, -0.01])),
             "A019RY2Q224SBEA": list(zip(Q, [-0.04, -1.10]))}
        c = gc.build("USA", reader(s))
        self.assertEqual(c["periods"], ["2026Q1", "2026Q2"])
        self.assertEqual([p["values"][-1] for p in c["parts"]], [2.51, 0.82, -0.01, -1.10])
        self.assertEqual(c["latest"], {"period": "2026Q2", "total": 2.2, "sum_parts": 2.22, "residual": -0.02})

    def test_only_quarters_with_every_part(self):
        s = {"A191RL1Q225SBEA": list(zip(Q, [2.5, 2.2])), "DPCERY2Q224SBEA": list(zip(Q, [0.49, 2.51])),
             "A006RY2Q224SBEA": list(zip(Q[:1], [1.25])), "A822RY2Q224SBEA": list(zip(Q, [0.80, -0.01])),
             "A019RY2Q224SBEA": list(zip(Q, [-0.04, -1.10]))}
        self.assertEqual(gc.build("USA", reader(s))["periods"], ["2026Q1"])


class Apply(unittest.TestCase):
    def test_attaches_and_drops_the_fixture_components(self):
        country = {"indicators": [{"id": "gdp", "components": [{"id": "pce", "contrib_pp": 1.6}]}]}
        contrib = {"parts": [], "latest": {}}
        self.assertTrue(gc.apply(country, contrib))
        self.assertNotIn("components", country["indicators"][0])
        self.assertFalse(gc.apply(country, contrib))


if __name__ == "__main__":
    unittest.main()
