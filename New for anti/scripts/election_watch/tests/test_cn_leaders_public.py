import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import build_cn_leaders_public as build  # noqa: E402


class CnLeadersPublicTest(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(build.SOURCE.read_text(encoding="utf-8"))

    def test_source_is_valid_and_published_copy_is_current(self):
        self.assertEqual(build.validate(self.data), [])
        result = subprocess.run([sys.executable, str(HERE / "build_cn_leaders_public.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_non_http_url(self):
        bad = copy.deepcopy(self.data)
        bad["politburo"][0]["bio_url"] = "javascript:alert(1)"
        self.assertTrue(any("not an http(s) URL" in e for e in build.validate(bad)))

    def test_rejects_acting_head_with_election(self):
        bad = copy.deepcopy(self.data)
        head = next(h for h in bad["government_heads"] if h["status"] == "acting")
        head["elected"] = {"date": "2026-11-01", "url": "https://www.news.cn/x"}
        self.assertTrue(any("carries an election event" in e for e in build.validate(bad)))

    def test_rejects_dated_event_without_source(self):
        bad = copy.deepcopy(self.data)
        bad["provincial_secretaries"][0]["central_decision"] = {"date": "2022-11-13", "url": None}
        self.assertTrue(any("without url or note_ko" in e for e in build.validate(bad)))


if __name__ == "__main__":
    unittest.main()
