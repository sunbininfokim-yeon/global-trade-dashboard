"""Reviewed annual disclosures and rejection cases; no live data calls."""
import json
import unittest
from copy import deepcopy
from unittest.mock import patch

from build_pe_cr import build
from dart_kfa.industry_note_mapping import build_industry_note_profile
from dart_kfa.shipbuilding_rg import _packets, build_shipbuilding_rg
from test_pe_cr import bundle
from test_pe_cr_evidence import payload, saved_report


END = "2025-12-31"
HANWHA = "00111704"
KSOE = "00164830"


def saved(entity):
    return {**payload(saved_report({"revenue": 1}, corp=entity)), "entity_id": entity}


def rg(profile):
    return profile["industry_note_metrics"]["shipbuilding_rg"]


class ShipbuildingRGTests(unittest.TestCase):
    def test_hanwha_by_guarantor_and_currency_stays_mixed(self):
        result = build(saved(HANWHA))
        report = rg(result)
        self.assertEqual(report["status"], "partial")
        self.assertFalse(report["rg_only_available"])
        self.assertEqual(report["reason"], "missing:rg_only_breakdown")
        pool = report["portfolios"][0]
        self.assertEqual(pool["basis"], "rg_and_other_performance")
        self.assertEqual(pool["evidence"]["filing_id"], "20260317002932")
        self.assertEqual(len(pool["rows"]), 5)
        usd, eur = pool["rows"][0], pool["rows"][2]
        self.assertEqual((usd["currency"], usd["limit"], usd["outstanding"]), ("USD", 6_300_000_000, 2_973_590_000))
        self.assertEqual(usd["limit_less_outstanding"], 3_326_410_000)
        self.assertAlmostEqual(usd["utilization"], 2973.59 / 6300)
        self.assertEqual((eur["currency"], eur["limit_less_outstanding"], eur["utilization"]), ("EUR", 0, 1))
        self.assertNotIn("total", pool)
        self.assertEqual(json.loads(json.dumps(report, allow_nan=False)), report)
        with patch("dart_kfa.shipbuilding_rg._packets", return_value=[]):
            self.assertEqual(result["cards"], build(saved(HANWHA))["cards"])

    def test_ksoe_limit_only_is_not_issuance_or_headroom(self):
        report = rg(build(saved(KSOE)))
        row = report["portfolios"][0]["rows"][0]
        self.assertEqual(row["limit"], 51_952_383_000_000)
        self.assertEqual(row["currency_basis"], "issuer_translated_period_end")
        for field in ("outstanding", "limit_less_outstanding", "utilization"):
            self.assertIsNone(row[field])

    def test_no_mixing_entities_scopes_cutoffs_or_periods(self):
        data = {**bundle(), "entity_id": HANWHA}
        before = build_industry_note_profile(data, "shipbuilding", "annual", publication_cutoff="2026-03-16")
        self.assertEqual(before["shipbuilding_rg"]["reason"], "unavailable:filing_after_publication_cutoff")
        self.assertEqual(build_shipbuilding_rg({**data, "fs_div": "OFS"}, "shipbuilding", END)["portfolios"], [])
        self.assertEqual(build_shipbuilding_rg(data, "shipbuilding", "2025-06-30")["portfolios"], [])
        self.assertEqual(build_shipbuilding_rg({**data, "entity_id": "01390344"}, "shipbuilding", END)["portfolios"], [])
        self.assertIsNone(build_shipbuilding_rg(data, "financial", END))

    def test_hanwha_interim_snapshot_uses_the_exact_dart_reporting_date(self):
        b = {**bundle(2026), "entity_id": HANWHA}
        profile = build_industry_note_profile(b, "shipbuilding", "Q2")["shipbuilding_rg"]
        pool = profile["portfolios"][0]
        self.assertEqual(pool["evidence"]["provider"], "DART")
        self.assertEqual(profile["as_of"], "2026-06-30")
        self.assertEqual(pool["rows"][0]["outstanding"], 3_953_050_000)
        self.assertAlmostEqual(pool["rows"][0]["utilization"], 3953.05 / 6300)
        self.assertFalse(profile["rg_only_available"])

    def test_ksoe_separate_limits_and_samsung_pure_insurance_do_not_become_issued_balances(self):
        separate = {**bundle(scope="OFS"), "entity_id": KSOE}
        self.assertEqual(build_shipbuilding_rg(separate, "shipbuilding", END)["portfolios"][0]["rows"][0]["limit"], 157_839_000_000)
        b = {**bundle(2026), "entity_id": "00126478"}
        result = build_shipbuilding_rg(b, "shipbuilding", "2026-06-30")
        pool = result["portfolios"][0]
        row = pool["rows"][0]
        self.assertTrue(result["rg_only_available"])
        self.assertEqual(pool["basis"], "rg_insurance_only")
        self.assertEqual((row["currency"], row["limit"]), ("USD", 11_616_000_000))
        self.assertIsNone(row["outstanding"])
        self.assertIsNone(row["utilization"])
        self.assertEqual(pool["related_collateral"][0]["amount"], 22_233_000_000)
        self.assertEqual(pool["related_collateral"][0]["currency"], "KRW")

    def test_pure_portfolio_is_distinct_and_bad_pair_does_not_calculate(self):
        b = {**bundle(), "entity_id": HANWHA}
        synthetic = deepcopy(_packets()[0])
        synthetic["basis"] = "rg_only"
        synthetic["rows"] = [{"guarantor": "검증 테스트 전용", "currency": "USD", "scale": 1, "limit": 10, "outstanding": 12}]
        with patch("dart_kfa.shipbuilding_rg._packets", return_value=[synthetic]):
            report = build_shipbuilding_rg(b, "shipbuilding", END)
            row = report["portfolios"][0]["rows"][0]
            self.assertTrue(report["rg_only_available"])
            self.assertIsNone(row["utilization"])
            self.assertEqual(row["calculation_reason"], "conflict:outstanding_exceeds_limit")
            synthetic["rows"][0]["outstanding"] = 0
            self.assertEqual(build_shipbuilding_rg(b, "shipbuilding", END)["portfolios"][0]["rows"][0]["utilization"], 0)
            synthetic["rows"].append(deepcopy(synthetic["rows"][0]))
            with self.assertRaisesRegex(ValueError, "row_or_duplicate"):
                build_shipbuilding_rg(b, "shipbuilding", END)

    def test_every_committed_registry_packet_resolves_with_its_own_scope(self):
        for packet in _packets():
            with self.subTest(issuer=packet["entity_id"], as_of=packet["as_of"], scope=packet["fs_div"]):
                b = {"source": "DART", "entity_id": packet["entity_id"], "fs_div": packet["fs_div"]}
                found = build_shipbuilding_rg(b, "shipbuilding", packet["as_of"])["portfolios"]
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0]["evidence"]["filing_id"], packet["source"]["filing_id"])


if __name__ == "__main__":
    unittest.main()
