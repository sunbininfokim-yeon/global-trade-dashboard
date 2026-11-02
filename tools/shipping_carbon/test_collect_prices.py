import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import date, datetime
from collect_prices import collect, parse_eex_rows, parse_ecb


class SourcesTest(unittest.TestCase):
    def test_eex_cancelled_future_and_price_type(self):
        header = ["Date", "Auction Name", "Contract", "Status", "Auction Price €/tCO2", "Auction Volume tCO2"]
        rows = [header, [datetime(2026, 10, 30), "DE", "T3PA", "successful", 80, 1000],
                [datetime(2026, 10, 29), "EU", "T3PA", "cancelled", None, 0],
                [datetime(2026, 11, 2), "EU", "T3PA", "successful", 90, 1000]]
        records, excluded = parse_eex_rows(rows, date(2026, 11, 1))
        self.assertEqual([r["price"] for r in records], ["80"])
        self.assertEqual(excluded, {"future": 1, "unsuccessful": 1})

    def test_eex_layout_change_rejected(self):
        with self.assertRaises(ValueError):
            parse_eex_rows([["wrong", "headers"]], date(2026, 11, 1))

    def test_ecb_unit_and_missing(self):
        head = "KEY,FREQ,CURRENCY,CURRENCY_DENOM,UNIT_MULT,TIME_PERIOD,OBS_VALUE,OBS_STATUS\n"
        row = "EXR.D.KRW.EUR.SP00.A,D,KRW,EUR,0,2026-10-30,1500,A\n"
        missing = "EXR.D.KRW.EUR.SP00.A,D,KRW,EUR,0,2026-10-29,,M\n"
        records, _ = parse_ecb((head + row + missing).encode(), date(2026, 11, 1))
        self.assertEqual(len(records), 1)
        with self.assertRaises(ValueError):
            parse_ecb((head + row.replace(",KRW,", ",USD,")).encode(), date(2026, 11, 1))

    def test_fetch_failure_preserves_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "reference_prices.json"
            p.write_text('{"known_good":true}')
            with patch("collect_prices.fetch", side_effect=OSError("offline")):
                result, dest = collect(date(2026, 11, 1), Path(d))
            self.assertEqual(json.loads(p.read_text()), {"known_good": True})
            self.assertEqual(result["status"], "partial")
            self.assertEqual(dest.name, "last_failed_attempt.json")


if __name__ == "__main__":
    unittest.main()
