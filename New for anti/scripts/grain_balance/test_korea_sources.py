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

    def test_mirror_used_when_korea_months_lag(self):
        months = [f"2025{m:02d}" for m in range(11, 13)] + [f"2026{m:02d}" for m in range(1, 11)]
        mirror = {"_reporters": {ym: ["36", "842"] for ym in months},
                  "wheat": {ym: {"842": 60, "36": 40} for ym in months}}
        # A month the US did not report would read as the US vanishing: skip it.
        mirror["_reporters"]["202510"] = ["36"]
        mirror["wheat"]["202510"] = {"36": 100}
        imports = {"wheat": {"year": 2025, "rows": {"842": 530, "36": 330, "124": 50}}, "mirror": mirror,
                   "monthly": {"wheat": {"202512": {"842": 1}}}}
        b = K.block("wheat", imports, {"regions": {}}, {})
        self.assertEqual(b["basis"], "mirror")
        self.assertEqual(b["period"], {"from": "202511", "to": "202610"})
        self.assertEqual(b["partners"][0]["share_pct"], 60.0)
        # Canada sent nothing in the window, so the US change is against 530/860.
        self.assertEqual(b["partners"][0]["change_pp"], -1.6)

    def test_missing_crop(self):
        self.assertIsNone(K.block("wheat", {}, {}, {}))


class ComexStatTest(unittest.TestCase):
    def test_parse_and_merge(self):
        import comexstat as C
        body = {"data": {"list": [
            {"year": "2026", "monthNumber": "07", "country": "South Korea", "headingCode": "1201", "metricKG": "60900000"},
            {"year": "2026", "monthNumber": "07", "country": "North Korea", "headingCode": "1201", "metricKG": "5000"},
            {"year": "2026", "monthNumber": "06", "country": "China", "headingCode": "1201", "metricKG": "9000000000"},
        ]}}
        got = C.parse(body)
        self.assertEqual(got["202607"]["soybeans"], 60900)
        self.assertEqual(got["202606"]["soybeans"], 0)
        mirror = {"_reporters": {"202606": ["124", "842"], "202607": ["842"]},
                  "soybeans": {"202606": {"842": 4306}}}
        C.merge(mirror, {**got, "202605": {"soybeans": 1}})
        self.assertIn("76", mirror["_reporters"]["202606"])
        self.assertNotIn("76", mirror["soybeans"]["202606"])
        self.assertEqual(mirror["soybeans"]["202607"]["76"], 60900)
        self.assertNotIn("202605", mirror["_reporters"])


if __name__ == "__main__":
    unittest.main()
