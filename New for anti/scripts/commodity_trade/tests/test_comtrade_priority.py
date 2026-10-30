from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "sources"))

from build_comtrade_priority_monthly import _periods_ending_at, _parse_flows  # noqa: E402
from sources.comtrade import fetch_preview_month  # noqa: E402


class PreviewAdapterTests(unittest.TestCase):
    def test_preview_response_preserves_comtrade_quality_flags_and_caches(self) -> None:
        body = {
            "count": 1,
            "data": [
                {
                    "period": "202606",
                    "cmdCode": "1201",
                    "netWgt": 12.5,
                    "primaryValue": 100.0,
                    "isReported": False,
                    "isQtyEstimated": True,
                    "isAggregate": True,
                    "legacyEstimationFlag": 6,
                }
            ],
        }
        response = MagicMock()
        response.__enter__.return_value = io.StringIO(json.dumps(body))
        with tempfile.TemporaryDirectory() as directory, patch("sources.comtrade.urlopen", return_value=response) as request:
            first = fetch_preview_month(
                hs_codes=["1201"], reporter_m49="842", period="202606", flow="X", cache_dir=Path(directory)
            )
            second = fetch_preview_month(
                hs_codes=["1201"], reporter_m49="842", period="202606", flow="X", cache_dir=Path(directory)
            )
        self.assertEqual(request.call_count, 1)
        point = first["series_by_hs"]["1201"][0]
        self.assertEqual(point["month"], "2026-06")
        self.assertEqual(point["unit"], "kg")
        self.assertTrue(point["quality"]["is_quantity_estimated"])
        self.assertTrue(second["cache"]["hit"])

    def test_preview_requires_one_month_and_supported_flow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = fetch_preview_month(
                hs_codes=["1201"], reporter_m49="842", period="2026-06", flow="X", cache_dir=Path(directory)
            )
        self.assertFalse(result["available"])
        self.assertIn("YYYYMM", result["reason"])

    def test_preview_surfaces_rate_limit_without_retrying(self) -> None:
        error = HTTPError("https://example.invalid", 429, "Too Many Requests", hdrs=None, fp=None)
        with tempfile.TemporaryDirectory() as directory, patch("sources.comtrade.urlopen", side_effect=error):
            result = fetch_preview_month(
                hs_codes=["1201"], reporter_m49="842", period="202606", flow="X", cache_dir=Path(directory)
            )
        self.assertFalse(result["available"])
        self.assertTrue(result["rate_limited"])


class PriorityCliHelpersTests(unittest.TestCase):
    def test_newest_period_is_requested_first_and_flow_labels_are_explicit(self) -> None:
        self.assertEqual(_periods_ending_at("2026-02", 3), ["202602", "202601", "202512"])
        self.assertEqual(_parse_flows("exports,imports"), ["X", "M"])
        with self.assertRaises(ValueError):
            _parse_flows("exports,exports")


if __name__ == "__main__":
    unittest.main()
