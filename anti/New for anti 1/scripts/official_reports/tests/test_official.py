from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from official_reports.build import build_official_reports
from official_reports.fetch import RawReport
from official_reports.score import OfficialScorer, append_label, _load_learned_multipliers


def _load(name: str):
    return json.loads((ROOT / "config" / name).read_text(encoding="utf-8"))


class ScoreTests(unittest.TestCase):
    def setUp(self):
        self.scorer = OfficialScorer(_load("domains.json"), _load("series_catalog.json"))

    def test_fomc_series(self):
        r = RawReport(
            "us_fed_all",
            "USA",
            "Fed",
            "Federal Reserve issues FOMC statement",
            "https://example/fomc",
            "federal funds rate decision",
            None,
            ["finance"],
            1.2,
        )
        s = self.scorer.score(r)
        self.assertIsNotNone(s)
        self.assertEqual(s.series_id, "US_FED_FOMC")

    def test_reject_gallery(self):
        r = RawReport(
            "x", "USA", "Fed", "Photo gallery holiday hours", "https://x", "", None, ["finance"], 1.0
        )
        self.assertIsNone(self.scorer.score(r))


class BuildTests(unittest.TestCase):
    def test_fixtures(self):
        doc = build_official_reports(
            limit=20,
            fetch_live=False,
            fixture_dir=ROOT / "tests" / "fixtures",
            fetch_qra_detail=False,
        )
        self.assertEqual(doc["schema_version"], "official-reports-v1")
        self.assertGreaterEqual(doc["stats"]["selected"], 1)
        series = {i.get("series_id") for i in doc["ticker_items"]}
        self.assertTrue(series & {"US_FED_FOMC", "US_FED_BEIGE_BOOK", "US_QRA_MARKETABLE_BORROWING", "JP_BOJ_POLICY", None})


class LearnTests(unittest.TestCase):
    def test_label_roundtrip(self):
        path = ROOT / "cache" / "_test_labels.jsonl"
        if path.exists():
            path.unlink()
        append_label(path, series_id="US_FED_FOMC", url="u", title="t", label="promote")
        append_label(path, series_id="US_FED_FOMC", url="u2", title="t2", label="promote")
        m = _load_learned_multipliers(path)
        self.assertGreater(m["US_FED_FOMC"], 1.0)
        path.unlink()


if __name__ == "__main__":
    unittest.main()
