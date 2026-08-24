"""Currency display policy regressions."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dart_kfa.currency import (  # noqa: E402
    build_currency_contract,
    convert_currency_value,
    convert_monetary_input_to_calculation_currency,
)


class CurrencyPolicyTest(unittest.TestCase):
    def test_dart_is_krw_only(self):
        got = build_currency_contract(source_adapter="opendart", source_currency="KRW", display_currency="USD")
        self.assertEqual(got["status"], "not_allowed")
        self.assertEqual(got["display_currency"], "KRW")

    def test_sec_krw_conversion_requires_auditable_fx(self):
        missing = build_currency_contract(source_adapter="sec_companyfacts", source_currency="USD", display_currency="KRW")
        self.assertEqual(missing["status"], "inputs_required")
        self.assertEqual(convert_currency_value(10, missing), 10)

        ready = build_currency_contract(
            source_adapter="sec_companyfacts",
            source_currency="USD",
            display_currency="KRW",
            fx_input={"rate": 1350, "source": "official_fx_snapshot", "as_of": "2026-08-20"},
        )
        self.assertEqual(ready["status"], "ready")
        self.assertEqual(convert_currency_value(10, ready), 13500)
        self.assertEqual(ready["provenance"]["pair"], "USD/KRW")

    def test_external_money_requires_currency_and_converts_only_via_same_fx_contract(self):
        contract = build_currency_contract(
            source_adapter="sec_companyfacts",
            source_currency="USD",
            display_currency="KRW",
            fx_input={"rate": 1350, "source": "official_fx_snapshot", "as_of": "2026-08-20"},
        )
        self.assertEqual(contract["calculation_currency"], "USD")
        self.assertEqual(contract["model_currency_policy"], "filing_currency_only")
        self.assertEqual(
            convert_monetary_input_to_calculation_currency(135000, input_currency="KRW", contract=contract),
            (100.0, None),
        )
        value, reason = convert_monetary_input_to_calculation_currency(100, input_currency=None, contract=contract)
        self.assertIsNone(value)
        self.assertEqual(reason, "missing:monetary_input_currency")


if __name__ == "__main__":
    unittest.main()
