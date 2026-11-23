import unittest

import korea_urea as K


class KoreaUreaTest(unittest.TestCase):
    def test_summary_shares_trend_and_ytd(self):
        data = {"annual": {"2021": {"156": 600, "682": 400}, "2025": {"156": 200, "682": 500, "360": 300}},
                "china_monthly": {"202501": 10_000, "202502": 20_000, "202503": 5_000,
                                  "202601": 15_000, "202602": 30_000}}
        s = K.summarize(data)
        self.assertEqual(s["year"], 2025)
        self.assertEqual(s["partners"][0]["country_ko"], "사우디아라비아")
        self.assertEqual(s["china_pct"], 20.0)
        self.assertEqual(s["hhi"], 20 ** 2 + 50 ** 2 + 30 ** 2)
        self.assertEqual([t["china_pct"] for t in s["trend"]], [60.0, 20.0])
        # Two months of 2026 vs the same two months of 2025, not the whole year.
        self.assertEqual(s["china_ytd"]["change_pct"], 50.0)

    def test_empty(self):
        self.assertIsNone(K.summarize({}))


if __name__ == "__main__":
    unittest.main()
