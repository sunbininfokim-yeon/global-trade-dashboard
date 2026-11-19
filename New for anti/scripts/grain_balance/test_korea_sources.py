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

    def test_recent_twelve_months_lead_with_change_vs_annual(self):
        months = {f"2025{m:02d}": {"842": 100} for m in range(9, 13)}
        months.update({f"2026{m:02d}": {"842": 50, "804": 50} for m in range(1, 9)})
        months["202501"] = {"842": 999}          # outside the window
        imports = {"corn": {"year": 2025, "rows": {"842": 900, "804": 100}}, "monthly": {"corn": months}}
        b = K.block("corn", imports, {"regions": {}}, {})
        self.assertEqual(b["period"], {"from": "202509", "to": "202608"})
        us = b["partners"][0]
        self.assertEqual(us["share_pct"], 66.7)
        self.assertEqual(us["change_pp"], -23.3)

    def test_gap_falls_back_to_annual(self):
        months = {f"2026{m:02d}": {"842": 10} for m in range(1, 9) if m != 4}
        imports = {"corn": {"year": 2025, "rows": {"842": 1}}, "monthly": {"corn": months}}
        b = K.block("corn", imports, {"regions": {}}, {})
        self.assertIsNone(b["period"])
        self.assertIsNone(b["partners"][0]["change_pp"])

    def test_missing_crop(self):
        self.assertIsNone(K.block("wheat", {}, {}, {}))


if __name__ == "__main__":
    unittest.main()
