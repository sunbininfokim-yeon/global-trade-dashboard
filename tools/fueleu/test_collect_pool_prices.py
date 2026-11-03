"""Parser tests on hand-written pages shaped like the commentary (not copies of it)."""
import unittest

import collect_pool_prices as c


def page(body, published="2026-03-05"):
    return (f'<html><head><script type="application/ld+json">{{"datePublished":"{published}T08:00:00+00:00"}}</script></head>'
            f'<body><div class="oceanscore-topbar">OPX (2026) €99,10</div>'
            f'<article>Market Commentary <p>Written by Someone Posted on March 5, 2026</p>{body}'
            f'<p>Share this post</p><p>Related posts OPX falls to €1.00/tCO₂e in another month.</p></article></body></html>')


class Parse(unittest.TestCase):
    def test_two_cycles_on_one_page_and_toc_year_ignored(self):
        raw = page("Table of Contents Effects On 2026 Surplus Outlook "
                   "The OPX for Compliance Balance 2025 fell to €200 per ton of CO₂e in March. "
                   "Offers for 2025 surplus sit between €180 and €216 per ton of CO₂e . "
                   "The OPX for 2026 compliance surplus stands at €197 per ton of CO₂e .")
        obs = c.parse_page(raw, "march-2026")
        heads = {(o["compliance_year"], o["value_eur_per_tco2e"]) for o in obs if o["kind"] == "headline"}
        self.assertEqual(heads, {(2025, 200.0), (2026, 197.0)})
        cb25 = next(o for o in obs if o["compliance_year"] == 2025)
        self.assertEqual((cb25["offer_low_eur"], cb25["offer_high_eur"]), (180.0, 216.0))

    def test_prior_month_restatement_and_decimal(self):
        raw = page("The OceanScore Pool-Price Index (OPX) stands at €95.80/tCO₂e in October , "
                   "down from €108.60/tCO₂e in September. Offers range from €70 to €138/tCO₂e .", "2026-10-20")
        obs = c.parse_page(raw, "october-2026")
        head = next(o for o in obs if o["kind"] == "headline")
        prior = next(o for o in obs if o["kind"] == "prior_month")
        self.assertEqual((head["value_eur_per_tco2e"], head["compliance_year"], head["compliance_year_basis"]), (95.8, 2026, "inferred_by_cycle"))
        self.assertEqual((prior["year"], prior["month"], prior["value_eur_per_tco2e"]), (2026, 9, 108.6))
        self.assertEqual((head["offer_low_eur"], head["offer_high_eur"]), (70.0, 138.0))

    def test_value_for_other_months_is_not_this_months_headline(self):
        raw = page("After the summer the OPX touched €193 / ton of CO₂e in August and September. "
                   "The index now shows an increase to €207 / ton of CO₂e .", "2025-10-13")
        head = [o for o in c.parse_page(raw, "october-2025") if o["kind"] == "headline"]
        self.assertEqual([h["value_eur_per_tco2e"] for h in head], [207.0])
        self.assertEqual(head[0]["compliance_year"], 2025)

    def test_footer_teasers_ignored_and_missing_headline_raises(self):
        with self.assertRaises(ValueError):
            c.parse_page(page("Nothing about prices this month."), "june-2026")

    def test_series_prefers_own_page_over_restatement(self):
        obs = [
            {"kind": "prior_month", "year": 2025, "month": 10, "compliance_year": 2025, "compliance_year_basis": "inferred_by_cycle",
             "value_eur_per_tco2e": 206.67, "source_url": "u2", "published": "2025-11-06"},
            {"kind": "headline", "year": 2025, "month": 10, "compliance_year": 2025, "compliance_year_basis": "inferred_by_cycle",
             "value_eur_per_tco2e": 207.0, "source_url": "u1", "published": "2025-10-13"},
            {"kind": "prior_month", "year": 2025, "month": 12, "compliance_year": 2025, "compliance_year_basis": "inferred_by_cycle",
             "value_eur_per_tco2e": 220.0, "source_url": "u3", "published": "2026-01-05"},
        ]
        s = c.build_series(obs)["2025"]
        self.assertEqual([(p["month"], p["value_eur_per_tco2e"], p["basis"]) for p in s],
                         [("2025-10", 207.0, "monthly_commentary"), ("2025-12", 220.0, "restated_in_next_commentary")])

    def test_topbar(self):
        self.assertEqual(c.latest_topbar(page("x")), {"compliance_year": 2026, "value_eur_per_tco2e": 99.1})


if __name__ == "__main__":
    unittest.main()
