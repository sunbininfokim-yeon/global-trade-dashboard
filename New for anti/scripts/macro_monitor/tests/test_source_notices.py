"""apply_source_notices.py: per-country source/licence footnotes."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import apply_source_notices as asn  # noqa: E402


class SourceNotices(unittest.TestCase):
    def test_writes_once_and_leaves_unlisted_countries_alone(self):
        pack = {"countries": [{"iso3": "SGP"}, {"iso3": "IDN", "source_notices": [{"text": "이 서비스는 BPS API를 사용합니다"}]}]}
        notices = {"SGP": [{"text": "ODL", "url": "https://data.gov.sg/open-data-licence"}]}
        self.assertEqual(asn.apply(pack, notices), ["SGP"])
        self.assertEqual(asn.apply(pack, notices), [])
        self.assertEqual(pack["countries"][1]["source_notices"][0]["text"], "이 서비스는 BPS API를 사용합니다")

    def test_config_is_well_formed(self):
        cfg = json.loads(asn.NOTICES.read_text(encoding="utf-8"))
        for iso3, rows in cfg.items():
            if iso3.startswith("_"):
                continue
            for n in rows:
                self.assertTrue(n["text"])
                self.assertTrue(n.get("url", "https://").startswith("https://"))
        self.assertIn("Singapore Open Data Licence", cfg["SGP"][0]["text"])


if __name__ == "__main__":
    unittest.main()
