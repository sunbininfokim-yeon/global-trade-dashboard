from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from shipping_capacity.panama_acp import (
    BookingSlotWindow,
    DailyGatunLevel,
    DailySatellitePrecipitation,
    GatunDashboardSnapshot,
    MonthlyHydrologyRecord,
    MonthlyCanalOperations,
    attach_lagged_oni,
    aggregate_daily_gatun_to_monthly,
    aggregate_daily_hydrology_proxy,
    build_local_acp_report,
    compare_gpm_imerg_year_over_year,
    _gpm_window_precipitation_mm,
    hydrology_design,
    load_acp_daily_gatun_history,
    load_monthly_climate_forecast_ensemble,
    load_nasa_power_daily_meteorology,
    parse_booking_slot_windows,
    parse_gatun_dashboard_text,
    parse_monthly_operations_summary,
    parse_noaa_oni_text,
    parse_gatun_projection_csv,
    summarize_projection_month,
    summarize_gpm_imerg_monitor,
)


class PanamaACPTests(unittest.TestCase):
    def test_parses_explicit_acp_dashboard_values(self) -> None:
        text = """
        84.1 ft Official Gatun Water Level for Aug. 31, 2026
        0.45% Variable Fresh Water Surcharge for all transits that begin on Aug. 31, 2026
        Official Maximum Draft Neopanamax Panamax 48.5 ft 39.5 ft
        Gatun Water Level Projection Last projection uploaded on: Aug. 25, 2026 14:43 (GMT-5) Probable
        """
        row = parse_gatun_dashboard_text(text, source_url="https://example.test/gatun.pdf")
        self.assertEqual(row.observation_date, "2026-08-31")
        self.assertEqual(row.water_level_ft, 84.1)
        self.assertEqual(row.fresh_water_surcharge_pct, 0.45)
        self.assertEqual(row.neopanamax_max_draft_ft, 48.5)
        self.assertEqual(row.panamax_max_draft_ft, 39.5)

    def test_parses_acp_pdf_text_order_for_maximum_draft(self) -> None:
        text = """
        84.1 ft Official Gatun Water Level for Aug. 31, 2026
        Neopanamax Panamax 48.5 ft 39.5 ft Official Maximum Draft
        """
        row = parse_gatun_dashboard_text(text)
        self.assertEqual(row.neopanamax_max_draft_ft, 48.5)
        self.assertEqual(row.panamax_max_draft_ft, 39.5)

    def test_summarizes_official_projection_without_labelling_it_modelled(self) -> None:
        text = """ACP notice\nprojected_date,projected_gatun_water_level,surcharge_pcent,max_neopanamax_draft_ft,max_panamax_draft_ft
09/01/2026,83.6,0.60,48.5,39.5
09/02/2026,83.4,0.70,48.0,39.5
"""
        summary = summarize_projection_month(parse_gatun_projection_csv(text), "2026-09")
        self.assertEqual(summary["status"], "official_acp_projection_not_model_output")
        self.assertEqual(summary["mean_water_level_ft"], 83.5)
        self.assertEqual(summary["neopanamax_draft_range_ft"], [48.0, 48.5])

    def test_extracts_advisory_slot_windows_without_open_ended_invention(self) -> None:
        text = """
        Advisory To Shipping No. A-48-2023
        From November 3, 2023, to November 6, 2023, the number of booking slots will be reduced to 25.
        From November 7, 2023 to November 30, 2023, the number of booking slots will be reduced to 24.
        From February 1, 2024, until further notice, the number of booking slots will be reduced to 18.
        """
        rows = parse_booking_slot_windows(text, source_url="https://example.test/a48.pdf")
        self.assertEqual([(row.start_date, row.end_date, row.slots_per_day) for row in rows], [
            ("2023-11-03", "2023-11-06", 25),
            ("2023-11-07", "2023-11-30", 24),
            ("2024-02-01", None, 18),
        ])

    def test_parses_official_monthly_operations_without_current_month_demand_features(self) -> None:
        text = """
        Advisory To Shipping No. A-03-2023
        SUBJECT: Monthly Canal Operations Summary – JANUARY 2023
        2. Traffic Statistics: Daily Average High Low
        Arrivals 35.90 47 27
        Oceangoing Transits 36.39 41 33
        Canal Waters Time (hours) 38.91 66.01 24.47
        In-Transit Time (hours) 10.44 12.85 9.40
        Oceangoing Transits: Total Daily Average Percentage
        Neopanamax Vessels (107’ beam and over) 261 8.42 23.14
        Booking Slots: Available Used Percentage
        Neopanamax (vessels of 107’ beam and Over) 239* 214*1 89.54
        Supers (vessels of 91’ beam to under 107’ beam) 403* 383*1 95.04
        Regular Vessels (less than 91' beam) 186* 172*1 92.47
        Auctioned booking slots 167 123 98.40
        * Does not include additional auctioned booking slots
        """
        row = parse_monthly_operations_summary(text, source_url="https://example.test/jan.pdf")
        self.assertEqual(row.month, "2023-01")
        self.assertEqual(row.oceangoing_transits_daily_average, 36.39)
        self.assertEqual(row.booking_available_total, 828)
        self.assertEqual(row.booking_used_total, 769)
        self.assertEqual(row.neopanamax_transits_daily_average, 8.42)

    def test_attaches_only_lagged_noaa_oni(self) -> None:
        oni = parse_noaa_oni_text(" SEAS YR TOTAL ANOM\n DJF 2024 26.0 -0.50\n JFM 2024 26.1 -0.20\n")
        records = [MonthlyHydrologyRecord("2024-03", 84, 100, 40)]
        enriched = attach_lagged_oni(records, oni, lag_months=2)
        self.assertEqual(enriched[0].oni_lag_6w, -0.5)

    def test_preserves_each_consecutive_advisory_sentence(self) -> None:
        text = """
        Advisory To Shipping No. A-48-2023.
        From December 1 to December 31, 2023, the number of booking slots will further be reduced to 22.
        From January 1 to January 31, 2024, the number of booking slots will be reduced to 20.
        """
        rows = parse_booking_slot_windows(text, source_url="https://example.test/a48.pdf")
        self.assertEqual([(row.start_date, row.end_date, row.slots_per_day) for row in rows], [
            ("2023-12-01", "2023-12-31", 22),
            ("2024-01-01", "2024-01-31", 20),
        ])

    def test_hydrology_design_uses_trailing_12_months_and_never_imputes(self) -> None:
        records = [
            MonthlyHydrologyRecord(
                month=f"2020-{month:02d}", gatun_mean_ft=80 + month / 10,
                precipitation_mm=100 + month, evaporation_mm=40 + month,
            )
            for month in range(1, 13)
        ]
        features, target, months = hydrology_design(records)
        self.assertEqual(months, ["2020-12"])
        self.assertEqual(target, [81.2])
        self.assertEqual(features[0][2], sum(100 + month for month in range(1, 13)))
        self.assertEqual(features[0][3], sum(40 + month for month in range(1, 13)))

    def test_aggregates_official_daily_levels_only_with_complete_monthly_covariates(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "gatun.csv"
            values = "\n".join(f"2024-01-{day:02d},{80 + day / 100:.2f}" for day in range(1, 22))
            path.write_text("DATE_LOG,GATUN_LAKE_LEVEL(FEET)\n" + values + "\n", encoding="utf-8")
            levels = load_acp_daily_gatun_history(path)
        records = aggregate_daily_gatun_to_monthly(levels, [{
            "month": "2024-01", "precipitation_mm": "220.5", "evaporation_mm": "75.1",
        }])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].month, "2024-01")
        self.assertAlmostEqual(records[0].gatun_mean_ft, 80.11)

    def test_rejects_sparse_daily_level_month_instead_of_imputing(self) -> None:
        levels = [DailyGatunLevel("2024-01-01", 80.0)]
        with self.assertRaisesRegex(ValueError, "coverage below 20"):
            aggregate_daily_gatun_to_monthly(levels, [{
                "month": "2024-01", "precipitation_mm": "220", "evaporation_mm": "75",
            }])

    def test_builds_local_acp_nasa_proxy_month_without_missing_day_imputation(self) -> None:
        levels = [DailyGatunLevel(f"2024-01-{day:02d}", 80 + day / 100) for day in range(1, 22)]
        parameters = {
            "PRECTOTCORR": {f"202401{day:02d}": 2.0 for day in range(1, 22)},
            "EVLAND": {f"202401{day:02d}": 1.0 for day in range(1, 22)},
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "power.json"
            path.write_text(json.dumps({"properties": {"parameter": parameters}}), encoding="utf-8")
            weather = load_nasa_power_daily_meteorology(path)
        records = aggregate_daily_hydrology_proxy(levels, weather)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].precipitation_mm, 42.0)
        self.assertEqual(records[0].evaporation_mm, 21.0)

    def test_loads_external_monthly_climate_ensemble_with_provenance(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ensemble.csv"
            path.write_text(
                "source_id,member_id,month,precipitation_mm,evaporation_mm,oni\n"
                "c3s,m01,2026-09,250.0,95.0,1.2\n"
                "c3s,m02,2026-09,310.0,90.0,1.0\n",
                encoding="utf-8",
            )
            members = load_monthly_climate_forecast_ensemble(path)
        self.assertEqual(len(members), 2)
        self.assertEqual(members[0].source_id, "c3s")
        self.assertEqual(members[0].oni, 1.2)

    def test_reads_gpm_rectangular_monitor_with_latitude_weighting(self) -> None:
        try:
            import h5py
            import numpy as np
        except ImportError:  # pragma: no cover - requirements-ml installs h5py
            self.skipTest("h5py unavailable")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "imerg.nc4"
            with h5py.File(path, "w") as handle:
                handle.create_dataset("lat", data=np.array([8.8, 9.2]))
                handle.create_dataset("lon", data=np.array([-80.0, -79.5]))
                handle.create_dataset("precipitation", data=np.array([[[1.0, 2.0], [3.0, 4.0]]]))
            result = _gpm_window_precipitation_mm(path, (8.7, -80.1, 9.3, -79.4))
        self.assertAlmostEqual(result, 2.4997, places=3)

    def test_summarizes_observed_gpm_without_turning_it_into_a_forecast(self) -> None:
        summary = summarize_gpm_imerg_monitor([
            DailySatellitePrecipitation("2026-08-30", 4.0, "GPM_3IMERGDL.07", "https://example.test/a.nc4"),
            DailySatellitePrecipitation("2026-08-31", 6.0, "GPM_3IMERGDL.07", "https://example.test/b.nc4"),
        ])
        self.assertEqual(summary["status"], "observed_satellite_precipitation_local_only")
        self.assertEqual(summary["total_precipitation_mm"], 10.0)
        self.assertIn("not a water-level forecast", summary["interpretation"])

    def test_compares_gpm_same_calendar_days_to_previous_year(self) -> None:
        current = [
            DailySatellitePrecipitation("2026-08-25", 8.0, "GPM_3IMERGDL.07", "https://example.test/current-a.nc4"),
            DailySatellitePrecipitation("2026-08-26", 4.0, "GPM_3IMERGDL.07", "https://example.test/current-b.nc4"),
        ]
        previous = [
            DailySatellitePrecipitation("2025-08-25", 3.0, "GPM_3IMERGDL.07", "https://example.test/previous-a.nc4"),
            DailySatellitePrecipitation("2025-08-26", 5.0, "GPM_3IMERGDL.07", "https://example.test/previous-b.nc4"),
        ]
        comparison = compare_gpm_imerg_year_over_year(current, previous)
        self.assertEqual(comparison["status"], "comparable_observed_same_calendar_days")
        self.assertEqual(comparison["difference_mm"], 4.0)
        self.assertEqual(comparison["change_pct"], 50.0)

    def test_no_history_withholds_hydrology_and_traffic_forecast(self) -> None:
        dashboard = GatunDashboardSnapshot(
            observation_date="2026-08-31", water_level_ft=84.1,
            fresh_water_surcharge_pct=0.45, neopanamax_max_draft_ft=48.5,
            panamax_max_draft_ft=39.5, projection_uploaded_at=None,
            source_url="https://example.test/gatun.pdf",
        )
        report = build_local_acp_report(
            dashboard,
            advisory_windows=[BookingSlotWindow("2023-11-03", "2023-11-06", 25, "https://example.test/a48.pdf")],
        )
        self.assertEqual(report["model_layers"]["hydrology"]["forecast_use"], "withheld")
        self.assertEqual(report["model_layers"]["transits"]["forecast_use"], "withheld")
        self.assertEqual(report["model_layers"]["operations"]["windows"][0]["slots_per_day"], 25)


if __name__ == "__main__":
    unittest.main()
