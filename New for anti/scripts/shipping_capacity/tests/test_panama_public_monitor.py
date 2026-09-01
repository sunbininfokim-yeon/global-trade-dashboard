from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from shipping_capacity.panama_public_monitor import (
    DailySatelliteRainfall,
    build_public_monitor,
    compare_same_calendar_days,
    gpm_window_mean_mm,
)


class PanamaPublicMonitorTests(unittest.TestCase):
    def test_public_artifact_excludes_canal_operations_and_capacity(self) -> None:
        current = [DailySatelliteRainfall("2026-08-25", 8.0, "https://example.test/current.nc4")]
        prior = [DailySatelliteRainfall("2025-08-25", 4.0, "https://example.test/prior.nc4")]
        monitor = build_public_monitor(current, prior)
        self.assertEqual(monitor["status"], "public_portfolio_monitor")
        self.assertEqual(monitor["year_over_year"]["change_pct"], 100.0)
        self.assertIn("vessel_transits", monitor["not_included"])
        self.assertNotIn("acp", str(monitor["data_sources"]).lower())

    def test_comparison_with_missing_matching_date_is_withheld(self) -> None:
        comparison = compare_same_calendar_days(
            [DailySatelliteRainfall("2026-08-25", 8.0, "https://example.test/current.nc4")],
            [DailySatelliteRainfall("2025-08-24", 4.0, "https://example.test/prior.nc4")],
        )
        self.assertEqual(comparison["status"], "withheld_missing_matching_previous_year_observation")

    def test_reads_gpm_grid_without_any_canal_source(self) -> None:
        try:
            import h5py
            import numpy as np
        except ImportError:  # pragma: no cover - requirements-ml installs h5py
            self.skipTest("h5py unavailable")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "gpm.nc4"
            with h5py.File(path, "w") as handle:
                handle.create_dataset("lat", data=np.array([8.8, 9.2]))
                handle.create_dataset("lon", data=np.array([-80.0, -79.5]))
                handle.create_dataset("precipitation", data=np.array([[[1.0, 2.0], [3.0, 4.0]]]))
            value = gpm_window_mean_mm(path, (8.7, -80.1, 9.3, -79.4))
        self.assertAlmostEqual(value, 2.4997, places=3)


if __name__ == "__main__":
    unittest.main()
