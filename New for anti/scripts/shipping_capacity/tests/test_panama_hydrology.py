"""Pure-unit contracts for the Panama hydrology research benchmark."""

from __future__ import annotations

import unittest
from datetime import date, timedelta

from shipping_capacity.panama_hydrology import (
    ResearchDataBoundaryError,
    _make_dataset,
    fetch_acp_history,
)


class PanamaHydrologyTests(unittest.TestCase):
    def test_acp_fetch_requires_explicit_research_boundary(self) -> None:
        with self.assertRaises(ResearchDataBoundaryError):
            fetch_acp_history(allow_research_fetch=False)

    def test_open_model_does_not_require_observed_lake_state(self) -> None:
        start = date(2010, 1, 1)
        weather = {}
        levels = {}
        for offset in range(365 * 6):
            day = start + timedelta(days=offset)
            weather[day] = {
                "PRECTOTCORR": 5.0,
                "T2M": 27.0,
                "RH2M": 80.0,
                "WS2M": 2.0,
            }
            if offset % 17:
                levels[day] = 85.0
        features, targets, anchors = _make_dataset(
            levels, weather, 7, include_observed_acp_state=False
        )
        self.assertGreater(len(features), 365 * 5)
        self.assertEqual(len(features), len(targets))
        self.assertEqual(len(features), len(anchors))
        with_state, _, _ = _make_dataset(
            levels, weather, 7, include_observed_acp_state=True
        )
        self.assertLess(len(with_state), len(features))


if __name__ == "__main__":
    unittest.main()
