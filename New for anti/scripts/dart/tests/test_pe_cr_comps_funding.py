"""Synthetic checks for valuation, peer compatibility and filing schedules."""
import unittest
from copy import deepcopy

from test_pe_cr import VALUES, bundle
from test_pe_cr_evidence import reviewed
from dart_kfa.pe_cr import build_pe_cr
from dart_kfa.pe_cr_dart_schedules import BOND_BUCKETS


SOURCE = {"filing_id": "synthetic", "url": "https://example.com/synthetic", "table": "synthetic source"}
END = "2025-12-31"
VALUES_PLUS = {**VALUES, "pretax_income": 80, "parent_income": 60, "total_income": 65, "assets": 1000,
               "equity": 500, "parent_equity": 400, "liabilities": 500}


def quote(entity_id="test", as_of="2026-03-31"):
    part = dict(price_date=as_of, shares_date="2025-12-31", share_basis="outstanding_excluding_treasury",
                price_source="synthetic exchange", shares_source="synthetic filing", currency="KRW", corporate_actions_checked=True)
    return {"is_listed": True, "entity_id": entity_id, "as_of": as_of, "fundamentals_available_date": "2026-03-10",
            "currency": "KRW", "coverage": "all_ordinary_share_classes",
            "classes": [{**part, "id": "A", "price": 4, "shares_out": 100}, {**part, "id": "B", "price": 10, "shares_out": 10}],
            "preferred_equity": {"value": 20, "as_of": as_of, "currency": "KRW", "source": "synthetic exchange"}}


def evidence(b):
    return reviewed(b, dict(PPE_DEPRECIATION=10, INTANGIBLE_AMORTIZATION=5, interest_income=5,
                            financing_debt=200, unrestricted_cash=60, principal_due_1y=100,
                            maintenance_capex=11, preferred_dividends=10, preferred_book_value=50, noncontrolling_value=30))


def packet(b, kind, **kwargs):
    return {**{k: b[k] for k in ("entity_id", "fs_div", "currency")}, "as_of": END,
            "schema_version": f"kfa-{kind}-disclosure/1", "scale": 1, **kwargs}


class ValuationFundingTests(unittest.TestCase):
    def test_market_financial_and_cash_cards(self):
        b = bundle(values=VALUES_PLUS)
        prior = bundle(2024, {**VALUES_PLUS, "assets": 800, "parent_equity": 350,
                              "receivables": 80, "inventory": 100, "payables": 40})
        c = build_pe_cr(b, history=[prior], reviewed_disclosures=evidence(b), market=quote(), corp={"accounting_basis": "K-IFRS"})["cards"]
        expected = dict(market_cap=500, per=10, pbr=500/350, roe=.16, roa=65/900, debt_ratio=1,
                        current_ratio=2, current_liabilities_share=.4, working_capital=200, operating_nwc=160, operating_nwc_change=20,
                        operating_income=100, ebit=95, ebitda=115, net_debt=140, ev=690, ev_to_ebitda=6,
                        ev_to_ebit=690/95, ev_to_sales=.69, debt_due_within_1y=100, liquidity_coverage_1y=.6,
                        owner_earnings_proxy=139)
        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertAlmostEqual(c[key]["value"], value)

    def test_loss_unlisted_and_currency_gate(self):
        b = bundle(values={**VALUES_PLUS, "parent_income": -60})
        self.assertIsNone(build_pe_cr(b, reviewed_disclosures=evidence(b), market=quote())["cards"]["per"]["value"])
        for raw in ({**quote(), "is_listed": False}, {**quote(), "currency": "USD"}, {**quote(), "coverage": "single_class"}):
            c = build_pe_cr(b, reviewed_disclosures=evidence(b), market=raw)["cards"]
            self.assertIsNone(c["market_cap"]["value"])
            self.assertIsNone(c["ev"]["value"])
        unchecked = quote()
        unchecked["classes"][0]["corporate_actions_checked"] = False
        self.assertEqual(build_pe_cr(b, market=unchecked)["cards"]["market_cap"]["reason"], "requires:share_count_corporate_actions_check")
        c = build_pe_cr(b, reviewed_disclosures=evidence(b), market={**quote(), "fundamentals_available_date": "2026-04-01"})["cards"]
        self.assertEqual(c["market_cap"]["value"], 500)
        self.assertEqual(c["ev"]["reason"], "incompatible:filing_not_public_at_market_date")
        b["series"]["PECR_parent_income"]["annual"]["provenance"]["filing_id"] = "20260312000001"
        c = build_pe_cr(b, reviewed_disclosures=evidence(b), market=quote())["cards"]
        self.assertEqual(c["ev"]["reason"], "incompatible:fact_filed_after_declared_public_date")

    def test_no_unverified_preferred_or_nci_zero_and_no_capex_proxy(self):
        b = bundle(values=VALUES_PLUS)
        c = build_pe_cr(b, market={**quote(), "preferred_equity": None}, reviewed_disclosures=evidence(b))["cards"]
        self.assertEqual(c["ev"]["reason"], "missing:dated_preferred_equity_value_or_explicit_zero")
        c = build_pe_cr(b, market=quote(), reviewed_disclosures=reviewed(b, {"financing_debt": 200, "unrestricted_cash": 60}))["cards"]
        self.assertEqual(c["ev"]["reason"], "missing:reviewed_noncontrolling_value")
        self.assertIsNone(c["owner_earnings_proxy"]["value"])
        self.assertIsNone(c["debt_due_within_1y"]["value"])

    def test_quarter_pbr_but_not_per(self):
        b = bundle(values=VALUES_PLUS)
        for s in b["series"].values():
            f = deepcopy(s["annual"])
            if f["nature"] == "flow":
                f["period_start"] = "2025-10-01"
            s["quarters"]["Q4"] = f
        c = build_pe_cr(b, selected_period="Q4", reviewed_disclosures=evidence(b), market=quote())["cards"]
        self.assertAlmostEqual(c["pbr"]["value"], 500/350)
        self.assertIsNone(c["per"]["value"])
        self.assertIsNone(c["ev_to_ebitda"]["value"])

    def test_peers_exclude_mixed_dates_groups_and_target(self):
        def company(eid, *, group="machinery:test", as_of="2026-03-31", profit=60, peers=()):
            b = {**bundle(values={**VALUES_PLUS, "parent_income": profit}), "entity_id": eid}
            return build_pe_cr(b, industry="machinery", market=quote(eid, as_of), reviewed_disclosures=evidence(b), corp={"accounting_basis": "K-IFRS"},
                               peer_group=group, peers=peers)

        peers = [company("p1"), company("p2", profit=110), company("p3", group="other"), company("p4", as_of="2026-03-30"), company("target")]
        out = company("target", peers=peers)["peer_comparison"]
        self.assertEqual(out["summary"]["per"]["median"], 7.5)
        self.assertEqual(out["summary"]["per"]["count"], 2)
        self.assertEqual(len(out["excluded"]), 2)
        dated = next(row for row in out["included"] if row["entity_id"] == "p4")
        self.assertEqual(dated["cells"]["per"]["reason"], "incompatible:peer_market_date")
        self.assertIsNone(company("target", peers=peers[:1])["peer_comparison"]["summary"]["per"]["median"])

    def test_financial_profile_separates_issuer_maturity_and_bond_duration(self):
        b = {**bundle(values=VALUES_PLUS), "entity_id": "00688996"}
        broad = dict(id="liabs", group="liabilities", side="liability", measure="undiscounted_contractual_cash_flow", source=SOURCE,
                     buckets=[{"from_month": 0, "to_month": 6, "amount": 100}, {"from_month": 6, "to_month": 18, "amount": 200}])
        bond = dict(id="bond-1", side="liability", fixed_non_callable=True, complete_schedule=True, source=SOURCE,
                    annual_effective_ytm=.05, yield_source="synthetic yield", yield_as_of=END, remaining_principal=100,
                    cashflows=[{"date": "2026-12-31", "coupon": 5, "principal": 0}, {"date": "2027-12-31", "coupon": 5, "principal": 100}])
        groups = packet(b, "funding", tables=[broad], bonds=[bond, {**bond, "id": "bond-2", "fixed_non_callable": False}])
        seg = packet(b, "segment", period_start="2025-01-01", rows=[dict(id="npl", name="NPL", kind="portfolio_category",
                                                                        assets=dict(value=90, basis="carrying amount", source=SOURCE))])
        r = build_pe_cr(b, funding=groups, segments=seg)
        c, d = r["cards"], r["disclosure_profile"]
        self.assertIsNone(c["fcf"]["value"])
        self.assertIsNone(c["ev"]["value"])
        self.assertIsNone(c["debt_due_within_1y"]["value"])
        self.assertIsNone(d["maturity"]["tables"][0]["within_12_months"])
        self.assertAlmostEqual(d["duration"]["bonds"][0]["macaulay_years"], 1.95238095238)
        self.assertAlmostEqual(d["duration"]["bonds"][0]["modified_years"], 1.95238095238/1.05)
        self.assertIsNone(d["duration"]["bonds"][1]["macaulay_years"])
        self.assertEqual(d["segments"]["rows"][0]["metrics"]["assets"]["value"], 90)

    def test_dart_bond_bucket_adapter_keeps_issuer_bonds_separate(self):
        b = {**bundle(), "entity_id": "00126380"}
        row = {"corp_code": "00126380", "stlm_dt": END, "rcept_no": "20260310000001", "remndr_exprtn1": "연결", "remndr_exprtn2": "합계",
               **{k: "1,000" if lo == 0 else "0" for k, lo, _ in BOND_BUCKETS}, "sm": "1,000"}
        data = dict(as_of=END, receipt=row["rcept_no"], fs_div="CFS", currency="KRW", scale=1000000, scope_evidence="synthetic verified table",
                    row_selector={"remndr_exprtn1": "연결", "remndr_exprtn2": "합계"}, response={"status": "000", "list": [row]})
        r = build_pe_cr(b, dart_bonds=data)
        t = r["disclosure_profile"]["maturity"]["tables"][0]
        self.assertEqual(t["within_12_months"], 1000000000)
        self.assertEqual(t["measure"], "reported_corporate_bond_outstanding")
        self.assertIsNone(r["cards"]["debt_due_within_1y"]["value"])
        row["sm"] = "999"
        with self.assertRaisesRegex(ValueError, "conflict:dart_bond_bucket_total"):
            build_pe_cr(b, dart_bonds=data)

    def test_dart_share_classes_and_receipt_time_reconcile(self):
        b = {**bundle(values=VALUES_PLUS), "entity_id": "00126380"}
        q = quote(b["entity_id"])
        q["classes"] = [{k: v for k, v in q["classes"][0].items() if k != "shares_out"}]
        q["classes"][0]["dart_security_type"] = "보통주"
        row = {"corp_code": b["entity_id"], "rcept_no": "20260310000001", "stlm_dt": END, "se": "보통주",
               "istc_totqy": "1,000", "tesstk_co": "100", "distb_stock_co": "900"}
        data = dict(as_of=END, receipt=row["rcept_no"], response={"status": "000", "list": [row]})
        self.assertEqual(build_pe_cr(b, market=q, dart_shares=data)["cards"]["market_cap"]["value"], 3600)
        row["distb_stock_co"] = "999"
        with self.assertRaisesRegex(ValueError, "conflict:dart_outstanding_share_reconciliation"):
            build_pe_cr(b, market=q, dart_shares=data)

    def test_funding_and_segments_scope_gates(self):
        b = bundle()
        with self.assertRaisesRegex(ValueError, "incompatible:disclosure_entity_scope_currency_or_date"):
            build_pe_cr(b, funding={**packet(b, "funding"), "currency": "USD"})
        with self.assertRaisesRegex(ValueError, "incompatible:segment_period_start"):
            build_pe_cr(b, segments=packet(b, "segment", period_start="2025-10-01"))

    def test_funding_gap_and_short_term_principal_require_matching_schedules(self):
        b = bundle(values=VALUES_PLUS)
        def table(key, side, buckets):
            return {"id": key, "side": side, "group": key, "measure": "principal", "source": SOURCE,
                    "buckets": [{"from_month": a, "to_month": z, "amount": amount} for a, z, amount in buckets]}
        liability = table("debt", "liability", [(0, 12, 100), (12, None, 300)])
        asset = table("assets", "asset", [(0, 12, 40), (12, None, 370)])
        data = packet(b, "funding", tables=[liability, asset],
                      principal_profile={"table_id": "debt", "coverage": "complete_financing_principal_including_leases", "source": SOURCE},
                      matched_gap={"asset_table_id": "assets", "liability_table_id": "debt", "coverage": "comparable_contractual_funding_cashflows", "source": SOURCE})
        r = build_pe_cr(b, funding=data, reviewed_disclosures=reviewed(b, {"unrestricted_cash": 70}))
        self.assertEqual(r["cards"]["debt_due_within_1y"]["value"], 100)
        self.assertEqual(r["cards"]["liquidity_coverage_1y"]["value"], .7)
        self.assertEqual(r["cards"]["financing_principal_due_1y_share"]["value"], .25)
        gap = r["disclosure_profile"]["contractual_funding_gap"]["rows"]
        self.assertEqual([row["gap"] for row in gap], [-60, 70])
        self.assertEqual(gap[-1]["cumulative_gap"], 10)
        conflict = build_pe_cr(b, funding=data, reviewed_disclosures=reviewed(b, {"principal_due_1y": 90}))["cards"]
        self.assertIsNone(conflict["debt_due_within_1y"]["value"])
        self.assertIsNone(conflict["financing_principal_due_1y_share"]["value"])
        liability["measure"] = "undiscounted_contractual_cash_flow"
        r = build_pe_cr(b, funding=data)
        self.assertEqual(r["disclosure_profile"]["contractual_funding_gap"]["reason"], "incompatible:asset_liability_measure_or_side")
        self.assertIsNone(r["cards"]["financing_principal_due_1y_share"]["value"])

    def test_selected_peer_order_and_missing_reason(self):
        b = bundle(values=VALUES_PLUS)
        p = {**b, "entity_id": "peer"}
        metadata = {"accounting_basis": "K-IFRS"}
        peer = build_pe_cr(p, peer_group="machinery", corp={**metadata, "name": "Peer A"}, industry="machinery")
        r = build_pe_cr(b, peer_group="machinery", corp=metadata, industry="machinery", peers=[peer], peer_ids=["missing", "peer"])
        comp = r["peer_comparison"]
        self.assertEqual(comp["selection"]["peer_ids"], ["missing", "peer"])
        self.assertEqual(comp["target"]["entity_id"], "test")
        self.assertEqual(comp["included"][0]["label"], "Peer A")
        self.assertEqual(comp["excluded"][0]["reason"], "missing:resolved_peer_snapshot")
        self.assertEqual(comp["columns"][0]["display"], "multiple")


if __name__ == "__main__":
    unittest.main()
