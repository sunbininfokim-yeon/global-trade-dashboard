import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build_kospi200_contract_meta import build  # noqa: E402


def write_part(root: Path, dataset: str, rows: list[dict]) -> None:
    part = root / "data/normalized" / dataset / "year=2026/month=10/part.jsonl.gz"
    part.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(part, "wt", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    manifest = root / "data/manifests" / f"{dataset}.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"missing_trading_days": []}), encoding="utf-8")


def opt(day, month, session="regular", oi=1.0):
    return {"date": day, "session": session, "expiry_or_contract_month": month, "contract_code": f"B{month}",
            "contract_name": f"코스피200 C {month}   750.0", "option_type": "call",
            "open_interest_contracts": oi, "implied_volatility": 20.0, "raw_shas": {"front_call.xlsx": "ab"}}


def fut(day, month):
    return {"date": day, "session": "regular", "expiry_or_contract_month": month, "contract_code": "A016C000",
            "contract_name": f"코스피200 F {month}", "open_interest_contracts": 1.0, "raw_shas": {}}


class ContractMetaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        cal = self.root / "calendar.json"
        days = ["2026-10-06", "2026-10-07", "2026-10-08", "2026-10-12", "2026-10-13"]
        cal.write_text(json.dumps({"rows": [{"date": d} for d in days]}), encoding="utf-8")
        self.calendar = cal

    def tearDown(self):
        self.tmp.cleanup()

    def test_closed_roll_keeps_expiry_null(self):
        write_part(self.root, "kospi200_option_oi", [
            opt("2026-10-07", "202610"), opt("2026-10-08", "202610"), opt("2026-10-08", "202611", session="night"),
            opt("2026-10-12", "202611"), opt("2026-10-13", "202611"),
        ])
        write_part(self.root, "kospi200_futures_oi", [fut("2026-10-12", "202612")])
        doc = build(self.root, self.calendar)
        oct_ = next(c for c in doc["contracts"] if c["expiry_or_contract_month"] == "202610")
        self.assertEqual(oct_["last_front_regular_date"], "2026-10-08")
        self.assertEqual(oct_["next_first_front_regular_date"], "2026-10-12")
        self.assertEqual(oct_["roll_status"], "closed")
        self.assertIsNone(oct_["expiry_date"])
        self.assertEqual(oct_["contract_type"], "standard_monthly")
        nov = next(c for c in doc["contracts"] if c["expiry_or_contract_month"] == "202611")
        self.assertEqual(nov["first_front_regular_date"], "2026-10-12")
        self.assertEqual(nov["roll_status"], "open_latest_month")

    def test_missing_day_before_roll(self):
        write_part(self.root, "kospi200_option_oi", [
            opt("2026-10-06", "202610"), opt("2026-10-12", "202611"),
        ])
        write_part(self.root, "kospi200_futures_oi", [fut("2026-10-12", "202612")])
        doc = build(self.root, self.calendar)
        oct_ = next(c for c in doc["contracts"] if c["expiry_or_contract_month"] == "202610")
        self.assertEqual(oct_["roll_status"], "missing_day_between")
        self.assertEqual(oct_["missing_trading_days_before_roll"], ["2026-10-07", "2026-10-08"])


if __name__ == "__main__":
    unittest.main()
