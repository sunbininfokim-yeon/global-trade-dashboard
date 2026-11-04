import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import build_personnel_public as build  # noqa: E402


class PersonnelPublicTest(unittest.TestCase):
    def test_sources_validate_and_published_copies_are_current(self):
        outputs, errors = build.build()
        self.assertEqual(errors, [])
        self.assertGreaterEqual(len(outputs) - 1, 30)
        result = subprocess.run([sys.executable, str(HERE / "build_personnel_public.py"), "--check"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_wrong_country_and_bad_url(self):
        data = {"schema": "fra_personnel_v1", "country": "DEU", "as_of": "2026-11-04",
                "president": {"name": "x", "source_url": "ftp://x"}}
        errors = build.validate("fra", data)
        self.assertTrue(any("country" in e for e in errors))
        self.assertTrue(any("not an http(s) URL" in e for e in errors))


if __name__ == "__main__":
    unittest.main()


class PersonnelBoardCountriesTest(unittest.TestCase):
    ROSTER_ONLY = ["ARM", "AZE", "EGY", "ESP", "GEO", "GRC", "IRQ", "KWT", "LBN", "LBY", "MAR", "PAN", "QAT", "YEM"]

    def test_roster_countries_are_published_on_the_board(self):
        result = subprocess.run([sys.executable, str(HERE / "upsert_board_countries.py"), "--check", *self.ROSTER_ONLY],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_divided_countries_name_their_sides(self):
        import json
        for iso in ("LBY", "YEM"):
            profile = json.loads((HERE / "config" / "profiles" / f"{iso.lower()}.json").read_text(encoding="utf-8"))
            self.assertEqual(profile["mode"], "divided_authority")
            self.assertGreaterEqual(len(profile["authorities"]), 2)
            self.assertNotIn("head", profile, "a divided country has no single head on the board")
