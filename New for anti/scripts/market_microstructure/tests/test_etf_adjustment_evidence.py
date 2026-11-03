import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_etf_adjustment_evidence import adjustment_events, collect_prices
from build_kospi200_price_panel import apply_etf_definition


class EvidenceTests(unittest.TestCase):
    def test_cash_inverse_and_no_false_constant_ratio_event(self):
        adjusted = {"2024-01-29": 90, "2024-01-30": 100, "2024-01-31": 101}
        raw = {"2024-01-29": 100, "2024-01-30": 100, "2024-01-31": 101}
        events = adjustment_events(adjusted, raw, "2024-01-30", "2024-01-31")
        self.assertEqual(len(events), 1)
        self.assertAlmostEqual(events[0]["inferred_D_krw"], 10)
        self.assertFalse(events[0]["issuer_cash_verified"])

    def test_missing_previous_date_rejected(self):
        with self.assertRaises(ValueError):
            adjustment_events({"2024-01-29": 90, "2024-01-30": 100},
                              {"2024-01-30": 100}, "2024-01-30", "2024-01-30")

    def test_pagination_requires_predecessor_not_just_start(self):
        batches = [[{"localTradedAt": day, "closePrice": "100"}]
                   for day in ("2024-01-30", "2024-01-29")]
        with patch("build_etf_adjustment_evidence._get", side_effect=map(json.dumps, batches)) as get:
            rows, receipts = collect_prices("069500", "2024-01-30", 2)
        self.assertEqual(get.call_count, 2)
        self.assertEqual(len(receipts), 2)
        self.assertIn("2024-01-29", rows)
        with patch("build_etf_adjustment_evidence._get", return_value=json.dumps(batches[0])):
            with self.assertRaises(ValueError):
                collect_prices("069500", "2024-01-30", 1)

    def test_note_overwrites_stale_unknown_and_is_idempotent(self):
        doc = {"adjustment_note_ko": "수정주가·분배금 반영 여부는 unknown이다", "candidates": []}
        apply_etf_definition(doc, collected_at="fixed")
        self.assertIn("069500·102110", doc["adjustment_note_ko"])
        self.assertIn("나머지 10개", doc["adjustment_note_ko"])
        before = json.dumps(doc, sort_keys=True)
        apply_etf_definition(doc, collected_at="fixed")
        self.assertEqual(before, json.dumps(doc, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
