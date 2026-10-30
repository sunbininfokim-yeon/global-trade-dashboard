import copy
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from preview_quality import annotate_preview_series
from sources.comtrade import fetch_preview_month, _preview_cache_path
from validate_release import validate_preview_publication


def point(month, value, unit="kg", **extra):
    return dict(month=month, value=value, unit=unit, source="comtrade_preview", **extra)


class PublicationTests(unittest.TestCase):
    def test_drop_preserves_raw_and_is_idempotent(self):
        series = {"points": [point("2026-05", 10000), point("2026-06", 1)]}
        original = copy.deepcopy(series["points"])
        annotate_preview_series(series)
        self.assertEqual(series["publication_summary"]["latest_eligible_month"], "2026-05")
        self.assertEqual(series["points"][1]["publication"]["flags"], ["suspected_partial_month"])
        self.assertEqual([{k: v for k, v in p.items() if k != "publication"} for p in series["points"]], original)
        again = copy.deepcopy(series)
        annotate_preview_series(series)
        self.assertEqual(series, again)

    def test_different_native_units_are_not_compared(self):
        series = {"points": [point("2026-05", 10000), point("2026-06", 1, "usd")]}
        annotate_preview_series(series)
        self.assertEqual(series["publication_summary"]["held_months"], [])

    def test_shared_usd_detects_drop_despite_missing_weight(self):
        series = {"points": [point("2026-05", 10000, primary_value_usd=100000),
                             point("2026-06", 2, "usd", primary_value_usd=2)]}
        annotate_preview_series(series)
        self.assertEqual(series["points"][1]["publication"]["evidence"]["metric"], "primary_value_usd")
        self.assertEqual(series["publication_summary"]["held_months"], ["2026-06"])

    def test_national_zero_untouched(self):
        p = point("2026-06", 0, source_access="official")
        p["source"] = "jodi"
        original = copy.deepcopy(p)
        annotate_preview_series({"points": [p]})
        self.assertEqual(p, original)

    def test_sparse_history_and_zero(self):
        series = {"points": [point("2026-06", 0)]}
        annotate_preview_series(series)
        self.assertEqual(series["publication_summary"]["held_months"], [])
        series["points"].insert(0, point("2026-05", 100))
        annotate_preview_series(series)
        self.assertEqual(series["points"][1]["value"], 0)
        self.assertEqual(series["publication_summary"]["held_months"], ["2026-06"])

    def test_recovery_clears_hold_and_release_gate_detects_tampering(self):
        series = {"points": [point("2026-05", 10000), point("2026-06", 1)]}
        annotate_preview_series(series)
        payload = {"reporters": {"BRA": {"flows": {"exports": {"commodities": {"soybeans": series}}}}}}
        self.assertEqual(validate_preview_publication(payload), 1)
        series["points"][1]["value"] = 11000
        with self.assertRaises(ValueError):
            validate_preview_publication(payload)
        annotate_preview_series(series)
        self.assertEqual(validate_preview_publication(payload), 0)
        self.assertNotIn("suspected_partial_month", series["series_quality"]["flags"])

    def test_invalid_numeric_is_held(self):
        for value in [None, -1, float("nan"), float("inf"), True]:
            series = {"points": [point("2026-06", value)]}
            annotate_preview_series(series)
            self.assertFalse(series["points"][0]["publication"]["eligible_for_display"])


class CacheTests(unittest.TestCase):
    def test_stale_refresh_failure_and_offline_preserve_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            args = dict(hs_codes=["1201"], reporter_m49="76", period="202606", flow="X", cache_dir=Path(directory))
            path = _preview_cache_path(**args)
            body = {"data": [{"cmdCode": "1201", "period": "202606", "netWgt": 12}]}
            path.write_text(json.dumps(body))
            os.utime(path, (1, 1))
            saved = path.read_bytes()
            with patch("sources.comtrade.urlopen", side_effect=HTTPError("https://example.invalid", 429, "limit", None, None)) as request:
                self.assertTrue(fetch_preview_month(**args, allow_fetch=False)["cache"]["stale"])
                request.assert_not_called()
                self.assertTrue(fetch_preview_month(**args)["rate_limited"])
            self.assertEqual(path.read_bytes(), saved)
            self.assertEqual(path.stat().st_mtime, 1)
            response = MagicMock()
            response.__enter__.return_value = io.StringIO(json.dumps({"data": [{"cmdCode": "1201", "netWgt": 34}]}))
            with patch("sources.comtrade.urlopen", return_value=response):
                result = fetch_preview_month(**args)
            self.assertFalse(result["cache"]["hit"])
            self.assertEqual(result["series_by_hs"]["1201"][0]["value"], 34)

    def test_bad_response_does_not_replace_cache(self):
        for bad in [{"error": "failed", "data": []}, {}, {"data": [None]}, []]:
            with tempfile.TemporaryDirectory() as directory:
                args = dict(hs_codes=["1201"], reporter_m49="76", period="202606", flow="X", cache_dir=Path(directory))
                path = _preview_cache_path(**args)
                path.write_text('{"data": []}')
                os.utime(path, (1, 1))
                saved = path.read_bytes()
                response = MagicMock()
                response.__enter__.return_value = io.StringIO(json.dumps(bad))
                with patch("sources.comtrade.urlopen", return_value=response):
                    self.assertFalse(fetch_preview_month(**args)["available"])
                self.assertEqual(path.read_bytes(), saved)


if __name__ == "__main__":
    unittest.main()
