from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_monthly import (  # noqa: E402
    _last_monthly_periods,
    _parse_comtrade_reporters,
    _validate_monthly_contract,
    align_sector_to_board,
    build_energy,
    overlay_comtrade_monthly,
)
from country_codes import iso2_to_iso3  # noqa: E402


class CountryCodeTests(unittest.TestCase):
    def test_jodi_iso2_codes_are_converted_to_iso3(self) -> None:
        self.assertEqual(iso2_to_iso3("AL"), "ALB")
        self.assertEqual(iso2_to_iso3("TH"), "THA")
        self.assertEqual(iso2_to_iso3("us"), "USA")
        self.assertIsNone(iso2_to_iso3("ZZ"))

    def test_energy_builder_never_emits_iso2_as_iso3(self) -> None:
        oil = {
            "available": True,
            "series": {
                "crude_oil": {
                    "AL": [{"month": "2026-01", "value": 1, "unit": "KTONS"}],
                    "US": [{"month": "2026-01", "value": 2, "unit": "KTONS"}],
                }
            },
        }
        gas = {"available": False, "series": {}}
        with patch("build_monthly.jodi_oil.load_export_series", return_value=oil), patch(
            "build_monthly.jodi_gas.load_lng_export_series", return_value=gas
        ):
            countries = build_energy(Path("/unused"))["commodities"]["crude_oil"]["countries"]
        self.assertEqual(set(countries), {"ALB", "USA"})


class ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.board = {"sectors": [{"id": "energy", "commodities": ["crude_oil", "coal"]}]}

    def test_missing_board_product_is_explicit_placeholder(self) -> None:
        payload = {"sector": "energy", "commodities": {"crude_oil": {"countries": {}}}}
        aligned = align_sector_to_board("energy", payload, self.board)
        self.assertEqual(set(aligned["commodities"]), {"crude_oil", "coal"})
        self.assertEqual(aligned["commodities"]["coal"]["stage2_status"], "monthly_planned")

    def test_extra_product_is_preserved_outside_ui_contract(self) -> None:
        payload = {"sector": "energy", "commodities": {"crude_oil": {}, "other": {"raw": True}}}
        aligned = align_sector_to_board("energy", payload, self.board)
        self.assertNotIn("other", aligned["commodities"])
        self.assertEqual(aligned["supplemental_commodities"]["other"], {"raw": True})

    def test_invalid_iso3_fails_closed(self) -> None:
        payload = {
            "sectors": {
                "energy": {
                    "commodities": {
                        "crude_oil": {
                            "countries": {"TH": {"points": [{"month": "2026-01", "unit": "KTONS"}]}}
                        },
                        "coal": {"countries": {}},
                    }
                }
            }
        }
        with self.assertRaisesRegex(ValueError, "invalid iso3"):
            _validate_monthly_contract(payload, self.board)


class ComtradeInputTests(unittest.TestCase):
    def test_reporters_and_periods_are_bounded_and_explicit(self) -> None:
        self.assertEqual(_parse_comtrade_reporters("USA=842,CHN=156"), {"USA": "842", "CHN": "156"})
        self.assertEqual(_last_monthly_periods("2026-02", 3), "202512,202601,202602")
        with self.assertRaises(ValueError):
            _parse_comtrade_reporters("USA-842")

    def test_comtrade_overlay_is_explicit_and_quota_capped(self) -> None:
        sectors = {
            "energy": {
                "commodities": {
                    "crude_oil": {
                        "hs_stems": ["2709"],
                        "stage2_status": "monthly_planned",
                        "countries": {},
                    }
                }
            }
        }
        response = {
            "available": True,
            "series": [{"month": "2026-01", "value": 3, "unit": "kg", "source": "comtrade"}],
        }
        with patch("build_monthly.comtrade.fetch_monthly", return_value=response) as fetch:
            result = overlay_comtrade_monthly(
                sectors, reporters={"USA": "842"}, periods="202601", max_requests=1
            )
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(result["loaded"], 1)
        product = sectors["energy"]["commodities"]["crude_oil"]
        self.assertEqual(product["stage2_status"], "monthly_partial")
        self.assertEqual(product["countries"]["USA"]["point_count"], 1)


if __name__ == "__main__":
    unittest.main()
