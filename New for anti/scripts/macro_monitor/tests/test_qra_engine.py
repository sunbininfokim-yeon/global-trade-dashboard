"""Unit tests for QRA engine parsers (offline fixtures)."""

from __future__ import annotations

import unittest
from pathlib import Path

from macro_monitor.qra.causal import auctions_to_issuance_components, build_causal_pack
from macro_monitor.qra.fetch import parse_year_quarter_table
from macro_monitor.qra.parse import parse_financing_estimates, parse_policy_statement
from macro_monitor.qra.tables_pdf import extract_pdf_links_from_html, parse_sources_uses_pdf, parse_tbac_financing_pdf

FIX = Path(__file__).resolve().parents[1].parent / "macro_intel" / "tests" / "fixtures" / "treasury_qra.html"
PDF_DIR = Path(__file__).resolve().parents[1] / "cache" / "qra" / "pdf"


class TestQraParse(unittest.TestCase):
    def test_financing_estimates_fixture(self):
        html = FIX.read_text()
        p = parse_financing_estimates(html, url="https://example.test/qra")
        self.assertTrue(p.parse_ok)
        est = [q for q in p.quarters if q.kind == "estimate"]
        self.assertEqual(len(est), 2)
        self.assertEqual(est[0].net_borrowing_bn, 739.0)
        self.assertEqual(est[0].end_cash_balance_bn, 950.0)
        self.assertEqual(est[0].vs_prior_bn, 68.0)
        act = [q for q in p.quarters if q.kind == "actual"]
        self.assertEqual(act[0].net_borrowing_bn, 190.0)

    def test_second_comparison_sentence_is_not_attached_to_the_next_quarter(self):
        # August 3, 2026 wording: the same release compares the current quarter
        # twice; the $87B (excluding the cash-balance effect) belongs to
        # July-September, not to October-December.
        html = """
        <html><title>Estimates</title><body>
        During the July \u2013 September 2026 quarter, Treasury expects to borrow $739 billion
        in privately-held net marketable debt, assuming an end-of-September cash balance of $950 billion.
        The borrowing estimate is $68 billion higher than announced in May 2026, primarily due to lower net cash flows.
        Excluding the higher-than-assumed beginning-of-quarter cash balance, the current quarter borrowing estimate
        is $87 billion higher than announced in May.
        During the October \u2013 December 2026 quarter, Treasury expects to borrow $628 billion
        in privately-held net marketable debt, assuming an end-of-December cash balance of $850 billion.
        </body></html>
        """
        p = parse_financing_estimates(html)
        est = [q for q in p.quarters if q.kind == "estimate"]
        self.assertEqual(est[0].vs_prior_bn, 68.0)
        self.assertIsNone(est[1].vs_prior_bn)

    def test_policy_stance_and_auctions(self):
        html = """
        <html><title>Policy Statement</title><body>
        The securities are: A 3-year note in the amount of $58 billion;
        A 10-year note in the amount of $42 billion; and
        A 30-year bond in the amount of $25 billion.
        Treasury anticipates maintaining nominal coupon and FRN auction sizes for at least the next several quarters.
        Looking ahead, Treasury continues to evaluate potential future changes to nominal coupon and FRN auction sizes.
        Based on current forecasts, Treasury expects to maintain current auction sizes in benchmark bills in the coming weeks.
        </body></html>
        """
        p = parse_policy_statement(html, url="https://example.test/policy")
        self.assertTrue(p.parse_ok)
        self.assertEqual(p.bill_stance, "maintain")
        self.assertEqual(p.coupon_stance, "change_bias")
        self.assertEqual(len(p.auctions), 3)
        comps = auctions_to_issuance_components([a.to_dict() for a in p.auctions])
        ids = [c["id"] for c in comps]
        self.assertEqual(ids, ["c3y", "c10y", "c30y"])

    def test_legacy_wording_paydown_and_spaces(self):
        html = """
        <html><title>Estimates</title><body>
        During the January – March 2020 quarter, Treasury expects to borrow $367 billion
        in privately-held net marketable debt, assuming an end-of-March cash balance of $400 billion.
        The borrowing estimate is $22 billion lower than announced in October.
        During the April – June 2020 quarter, Treasury expects to pay down $56 billion
        in privately-held net marketable debt, assuming an end-of-June cash balance of $400 billion.
        During the July–September 2025 quarter, Treasury borrowed $1.058 trillion
        in privately-held net marketable debt and ended the quarter with a cash balance of $891 billion.
        </body></html>
        """
        p = parse_financing_estimates(html)
        self.assertTrue(p.parse_ok)
        est = [q for q in p.quarters if q.kind == "estimate"]
        self.assertEqual(est[0].net_borrowing_bn, 367.0)
        self.assertEqual(est[0].vs_prior_bn, -22.0)
        self.assertEqual(est[1].net_borrowing_bn, -56.0)
        act = [q for q in p.quarters if q.kind == "actual"]
        self.assertEqual(act[0].net_borrowing_bn, 1058.0)

    def test_causal_flags(self):
        pack = build_causal_pack(
            {
                "estimates": {
                    "quarters": [
                        {
                            "period": "July–September 2026",
                            "kind": "estimate",
                            "net_borrowing_bn": 739,
                            "end_cash_balance_bn": 950,
                            "vs_prior_bn": 68,
                        }
                    ]
                },
                "policy": {"bill_stance": "maintain", "coupon_stance": "change_bias", "stance_snippets": []},
            }
        )
        self.assertIn("net_borrowing_up_vs_prior", pack["flags"])
        self.assertIn("tga_cash_high", pack["flags"])
        self.assertTrue(pack["edges"])

    def test_archive_table_parse(self):
        html = """
        <table><thead>
        <tr><th colspan="4" id="2026">2026</th></tr>
        <tr>
          <th headers="2026">4th Quarter</th>
          <th headers="2026"><a href="/news/press-releases/sb0584">3rd Quarter</a></th>
          <th headers="2026"><a href="/news/press-releases/sb0485">2nd Quarter</a></th>
          <th headers="2026"><a href="/news/press-releases/sb0377">1st Quarter</a></th>
        </tr>
        <tr><th colspan="4" id="2020">2020</th></tr>
        <tr>
          <th headers="2020"><a href="/news/press-releases/sm1172" aria-label="4th Quarter 2020">4th Quarter</a></th>
          <th headers="2020"><a href="/news/press-releases/sm1077" aria-label="3rd Quarter 2020">3rd Quarter</a></th>
          <th headers="2020"><a href="/news/press-releases/sm997">2nd Quarter</a></th>
          <th headers="2020"><a href="/news/press-releases/sm893">1st Quarter</a></th>
        </tr>
        </thead></table>
        """
        docs = parse_year_quarter_table(html, "financing_estimates")
        self.assertEqual(len(docs), 7)
        years = {d.year for d in docs}
        self.assertEqual(years, {2026, 2020})
        self.assertTrue(any(d.year == 2020 and d.quarter == 4 for d in docs))

    def test_archive_table_parse_minified_unquoted_attributes(self):
        # Treasury now serves this page minified with unquoted attributes; the
        # regex parser found 0 docs and build_qra_engine "succeeded" empty.
        html = (
            "<table><thead><tr><th class=span colspan=4 id=2026>2026</th></tr>"
            "<tr><th headers=2026>4th Quarter</th>"
            "<th headers=2026><a href=/news/press-releases/sb0584>3rd Quarter</a></th>"
            "<th headers=2026><a href=/news/press-releases/sb0485>2nd Quarter</a></th>"
            "<th headers=2026><a aria-label=\"2026 1st Quarter\" href=/news/press-releases/sb0377>1st Quarter</a></th></tr>"
            "</thead></table>"
        )
        docs = parse_year_quarter_table(html, "financing_estimates")
        self.assertEqual(sorted(d.quarter for d in docs), [1, 2, 3])  # 4th has no link yet
        self.assertTrue(all(d.url.startswith("https://home.treasury.gov/news/press-releases/sb0") for d in docs))

    def test_rebuild_with_fewer_events_never_overwrites_the_published_file(self):
        import json
        import tempfile
        from unittest import mock

        from macro_monitor.qra import build as qra_build

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "qra_engine_v1.json"
            out.write_text(json.dumps({"events": [{"id": "2026-Q3"}, {"id": "2026-Q2"}]}))
            with mock.patch.object(qra_build, "discover_archives", return_value=[]):
                with self.assertRaises(RuntimeError):
                    qra_build.build_qra_engine(
                        cache_dir=Path(tmp) / "cache", download=False, out_path=out, fiscal=False
                    )
            self.assertEqual(len(json.loads(out.read_text())["events"]), 2)  # untouched

    def test_split_summary_uses_the_releases_own_stances(self):
        from macro_monitor.qra.compare import split_summary_ko

        compare = {"series": [
            {"id": "current", "period": "October–December 2026", "value": 700.0, "end_cash_bn": 850.0,
             "announcement_date": "November 2, 2026"},
            {"id": "next_estimate", "period": "January–March 2027", "value": 600.0, "end_cash_bn": 850.0},
        ]}
        note = split_summary_ko(compare, "increase", "maintain")
        self.assertIn("November 2, 2026 발표", note)
        self.assertIn("T-bill 스탠스=increase", note)   # not a stance carried over from August
        self.assertIn("쿠폰 스탠스=maintain", note)
        self.assertNotIn("change_bias", note)
        self.assertIsNone(split_summary_ko({"series": [compare["series"][0]]}))

    def test_pdf_links_found_in_minified_html_with_unquoted_href(self):
        html = (
            "<p><a href=/system/files/136/Sources-Uses-Public-Table-August-2026.pdf>Sources</a> "
            "<a href=\"/system/files/221/TBACRecommendedFinancingTableByRefundingQuarter-08052026.pdf\">TBAC</a></p>"
        )
        links = dict(extract_pdf_links_from_html(html))
        self.assertTrue(links["sources_uses"].endswith("Sources-Uses-Public-Table-August-2026.pdf"))
        self.assertIn("tbac_financing", links)

    @unittest.skipUnless(
        (PDF_DIR / "Sources-Uses-Public-Table-August-2026.pdf").exists(),
        "August Sources-Uses PDF not cached",
    )
    def test_sources_uses_august_2026(self):
        t = parse_sources_uses_pdf(PDF_DIR / "Sources-Uses-Public-Table-August-2026.pdf")
        self.assertTrue(t.parse_ok)
        aug = [
            r
            for r in t.rows
            if r.row_kind == "estimate"
            and "Jul" in r.period
            and r.announcement_date
            and "August" in r.announcement_date
        ]
        self.assertTrue(aug)
        self.assertEqual(aug[0].marketable_borrowing_bn, 739.0)
        self.assertEqual(aug[0].end_cash_balance_bn, 950.0)
        self.assertEqual(aug[0].financing_need_bn, 633.0)
        rev = [r for r in t.rows if r.row_kind == "revisions" and "Jul" in r.period]
        self.assertTrue(rev)
        self.assertEqual(rev[-1].marketable_borrowing_bn, 68.0)

    @unittest.skipUnless(
        (PDF_DIR / "TBACRecommendedFinancingTable-08052026.pdf").exists(),
        "TBAC Aug 2026 PDF not cached",
    )
    def test_tbac_august_2026(self):
        t = parse_tbac_financing_pdf(PDF_DIR / "TBACRecommendedFinancingTable-08052026.pdf")
        self.assertTrue(t.parse_ok)
        rec = [r for r in t.rows if r.section == "recommendations"]
        self.assertEqual([r.month for r in rec], ["Aug-26", "Sep-26", "Oct-26"])
        self.assertEqual(rec[0].values_bn["c3y"], 58.0)
        self.assertEqual(rec[0].values_bn["c10y"], 42.0)
        self.assertEqual(rec[0].values_bn["c30y"], 25.0)
        comps = t.to_dict()["qra_issuance_components"]
        by_id = {c["id"]: c["value"] for c in comps}
        self.assertEqual(by_id["c3y"], 58 * 3)
        self.assertEqual(by_id["c10y"], 42 + 39 + 39)

    def test_compare_three_way(self):
        from macro_monitor.qra.compare import build_net_borrowing_compare

        event = {
            "estimates": {
                "quarters": [
                    {
                        "period": "January–March 2025",
                        "kind": "estimate",
                        "net_borrowing_bn": 815.0,
                        "end_cash_balance_bn": 850.0,
                        "vs_prior_bn": -9.0,
                    },
                    {
                        "period": "October–December 2024",
                        "kind": "actual",
                        "net_borrowing_bn": 620.0,
                        "end_cash_balance_bn": 722.0,
                    },
                ]
            },
            "sources_uses": {
                "rows": [
                    {
                        "period": "Jan - Mar 2025",
                        "row_kind": "estimate",
                        "announcement_date": "October 28, 2024",
                        "marketable_borrowing_bn": 823.0,
                        "end_cash_balance_bn": 850.0,
                    },
                    {
                        "period": "Jan - Mar 2025",
                        "row_kind": "estimate",
                        "announcement_date": "February 3, 2025",
                        "marketable_borrowing_bn": 815.0,
                        "end_cash_balance_bn": 850.0,
                    },
                ]
            },
        }
        cmp = build_net_borrowing_compare(event)
        ids = [s["id"] for s in cmp["series"]]
        self.assertEqual(ids, ["prior_actual", "prior_forecast", "current"])
        by = {s["id"]: s["value"] for s in cmp["series"]}
        self.assertEqual(by["prior_actual"], 620.0)
        self.assertEqual(by["prior_forecast"], 823.0)
        self.assertEqual(by["current"], 815.0)
        self.assertEqual(len(cmp["table"]), 3)
        self.assertEqual(cmp["series"][2]["announcement_date"], "February 3, 2025")

    def test_august_announcement_splits_current_and_next_quarter(self):
        from macro_monitor.qra.compare import build_net_borrowing_compare

        event = {
            "estimates": {
                "quarters": [
                    {
                        "period": "July–September 2026",
                        "kind": "estimate",
                        "net_borrowing_bn": 739.0,
                        "end_cash_balance_bn": 950.0,
                        "vs_prior_bn": 68.0,
                    },
                    {
                        "period": "October–December 2026",
                        "kind": "estimate",
                        "net_borrowing_bn": 628.0,
                        "end_cash_balance_bn": 850.0,
                        "vs_prior_bn": 87.0,
                    },
                    {
                        "period": "April–June 2026",
                        "kind": "actual",
                        "net_borrowing_bn": 190.0,
                        "end_cash_balance_bn": 919.0,
                    },
                ]
            },
            "sources_uses": {
                "rows": [
                    {
                        "period": "Jul - Sep 2026",
                        "row_kind": "estimate",
                        "announcement_date": "May 4, 2026",
                        "marketable_borrowing_bn": 671.0,
                        "end_cash_balance_bn": 950.0,
                    },
                    {
                        "period": "Jul - Sep 2026",
                        "row_kind": "estimate",
                        "announcement_date": "August 3, 2026",
                        "marketable_borrowing_bn": 739.0,
                        "end_cash_balance_bn": 950.0,
                    },
                    {
                        "period": "Oct - Dec 2026",
                        "row_kind": "estimate",
                        "announcement_date": "August 3, 2026",
                        "marketable_borrowing_bn": 628.0,
                        "end_cash_balance_bn": 850.0,
                    },
                ]
            },
        }
        cmp = build_net_borrowing_compare(event)
        by = {s["id"]: s for s in cmp["series"]}
        self.assertEqual(by["current"]["value"], 739.0)
        self.assertEqual(by["current"]["announcement_date"], "August 3, 2026")
        self.assertEqual(by["current"]["end_cash_bn"], 950.0)
        self.assertEqual(by["next_estimate"]["label_ko"], "다음 분기 예상")
        self.assertEqual(by["next_estimate"]["period"], "October–December 2026")
        self.assertEqual(by["next_estimate"]["value"], 628.0)
        self.assertEqual(by["next_estimate"]["end_cash_bn"], 850.0)
        self.assertEqual(by["next_estimate"]["announcement_date"], "August 3, 2026")
        self.assertEqual(by["prior_forecast"]["value"], 671.0)
        self.assertEqual(by["prior_forecast"]["announcement_date"], "May 4, 2026")


if __name__ == "__main__":
    unittest.main()
