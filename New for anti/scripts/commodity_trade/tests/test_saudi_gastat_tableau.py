from __future__ import annotations

import sys
import unittest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sources.saudi_gastat_tableau import SECTION_BY_CHAPTER, parse_tableau_csv, select_observed_months  # noqa: E402
from world_link import to_kg  # noqa: E402
from sources.saudi_gastat_tableau import fetch_monthly_hs_world


class SaudiGastatTableauTests(unittest.TestCase):
    def test_parse_value_and_weight_tables(self) -> None:
        value_csv = "HS Section,Year Month,Value\nMineral products.,2026 / 06,\"12,345.6\"\n"
        weight_csv = "HS Section,Year Month,Weight\nMineral products.,2026 / 06,\"7,890,000\"\n"
        import_weight_csv = "Hs Section ,Year Month,Max. Hs Chapter Cd,Value\nMineral products.,2026 / 06,27,\"7,890\"\n"
        self.assertEqual(parse_tableau_csv(value_csv, metric="value"), {"2026-06": 12345.6})
        self.assertEqual(parse_tableau_csv(weight_csv, metric="weight"), {"2026-06": 7890000.0})
        self.assertEqual(parse_tableau_csv(import_weight_csv, metric="weight"), {"2026-06": 7890.0})

    def test_priority_hs4_chapters_have_explicit_sections(self) -> None:
        for chapter in ("10", "12", "15", "17", "23", "25", "26", "27", "28", "52", "75", "76", "81"):
            self.assertIn(chapter, SECTION_BY_CHAPTER)

    def test_stale_tail_is_only_used_when_requested_months_are_absent(self) -> None:
        values = {"2025-08": 1.0, "2025-09": 2.0}
        weights = {"2025-08": 3.0, "2025-09": 4.0}
        selected, fallback = select_observed_months(
            values, weights, requested_months={"2026-06"}, fallback_latest_months=12
        )
        self.assertEqual(selected, ["2025-08", "2025-09"])
        self.assertTrue(fallback)
        selected, fallback = select_observed_months(
            values, weights, requested_months={"2025-09"}, fallback_latest_months=12
        )
        self.assertEqual(selected, ["2025-09"])
        self.assertFalse(fallback)

    def test_ktons_is_a_thousand_metric_tons(self) -> None:
        self.assertEqual(to_kg(1, "KTONS"), 1_000_000.0)

    def test_duplicate_and_nonfinite_rows_fail_closed(self):
        for rows in ('2026 / 06,1\n2026 / 06,2\n', '2026 / 06,nan\n', '2026 / 06,-1\n'):
            with self.assertRaises(ValueError):
                parse_tableau_csv('Year Month,Value\n' + rows, metric='value')

    def test_expired_cache_refreshes_and_counts_failed_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            value = cache / 'saudi_gastat_tableau_X_2709_value.csv'
            weight = cache / 'saudi_gastat_tableau_X_2709_weight.csv'
            for path in (value, weight):
                path.write_text('Year Month,Value\n2025 / 09,1\n')
                os.utime(path, (1, 1))
            args = dict(periods=['202606'], flow='X', hs_code='2709', cache_dir=cache, max_requests=2)
            with patch('sources.saudi_gastat_tableau._fetch_csv', side_effect=OSError('offline')):
                result = fetch_monthly_hs_world(**args)
            self.assertFalse(result['available'])
            self.assertEqual(result['cache']['network_requests'], 1)
            self.assertIn('2025 / 09', value.read_text())
            with patch('sources.saudi_gastat_tableau._fetch_csv', side_effect=[
                'Year Month,Value\n2026 / 06,2\n', 'Year Month,Weight\n2026 / 06,3\n'
            ]) as fetch:
                result = fetch_monthly_hs_world(**args)
            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(result['source_latest_month'], '2026-06')
            self.assertEqual(result['series_by_hs']['2709'][0]['value'], 3)

    def test_bad_second_metric_preserves_both_caches(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            paths = [cache / f'saudi_gastat_tableau_X_2709_{m}.csv' for m in ('value', 'weight')]
            for path in paths:
                path.write_text('Year Month,Value\n2025 / 09,1\n')
            with patch('sources.saudi_gastat_tableau._fetch_csv', side_effect=[
                'Year Month,Value\n2026 / 06,2\n', '<html>Error</html>'
            ]):
                result = fetch_monthly_hs_world(periods=['202606'], flow='X', hs_code='2709',
                    cache_dir=cache, cache_max_age_seconds=0, max_requests=2)
            self.assertFalse(result['available'])
            self.assertTrue(all('2025 / 09' in p.read_text() for p in paths))


if __name__ == "__main__":
    unittest.main()
