import unittest

import korea_sources as K


def call(crop, verdict, live=True, hist=None):
    return {"crop": crop, "season": "2026", "overall": {"verdict": verdict, "verdict_ko": verdict,
            "history_check": hist},
            "stages": [{"state": "in_progress" if live else "done"}]}


class KoreaSourcesTest(unittest.TestCase):
    def test_shares_and_exposure(self):
        imports = {"corn": {"year": 2025, "rows": {"842": 500, "76": 300, "32": 150, "710": 45, "999": 5}}}
        stage = {"regions": {
            "corn_belt": [call("corn", "unfavorable")],
            "mato_grosso_soja": [call("corn_safrinha", "unfavorable", hist="unmatched")],
            "parana_soja": [call("corn", "neutral")],
            "pampas_maiz": [call("corn", "unfavorable", live=False)],
        }}
        b = K.block("corn", imports, stage, {})
        self.assertEqual([p["country_ko"] for p in b["partners"]], ["미국", "브라질", "아르헨티나", "남아공"])
        self.assertEqual(b["partners"][0]["share_pct"], 50.0)
        # US fully exposed; Brazil's bad call is reference-only; Argentina harvested.
        self.assertEqual(b["exposed_pct"], 50.0)
        self.assertEqual(b["covered_pct"], 80.0)
        self.assertTrue(b["partners"][2]["regions"][0]["harvested"])

    def test_missing_crop(self):
        self.assertIsNone(K.block("wheat", {}, {}, {}))


if __name__ == "__main__":
    unittest.main()
