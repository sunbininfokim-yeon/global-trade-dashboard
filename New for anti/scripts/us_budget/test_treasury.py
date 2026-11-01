"""Run: python3 tests/test_us_budget_collector.py."""
import copy
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError

import treasury as m


def publication(fys, vintage, through=12):
    rows = []
    for fy in fys:
        parent = f"fy-{fy}"
        rows.append(dict(classification_id=parent, classification_desc=f"FY {fy}", sequence_level_nbr="1"))
        for i, month in enumerate([10, 11, 12, *range(1, 10)]):
            r = dict(classification_id=f"{fy}-{month}", parent_id=parent, record_type_cd="MTH",
                     classification_desc=m.calendar.month_name[month])
            for k, v in zip(m.MONEY, ["10.01", "12.03", "2.02"]):
                r[k] = v if fy < max(fys) or i < through else "null"
            rows.append(r)
        count = 12 if fy < max(fys) else through
        rows.append(dict(classification_id=f"total-{fy}", parent_id=parent, classification_desc="Year-to-Date",
                         **dict(zip(m.MONEY, [str(Decimal(v) * count) for v in ["10.01", "12.03", "2.02"]]))))
    return [dict(r, record_date=vintage) for r in rows]


def details(vintage="2026-09-30"):
    def r(key, name, parent, current=None, prior=None, kind="D", level="2"):
        return dict(classification_id=key, classification_desc=name, parent_id=parent, line_code_nbr=key,
                    data_type_cd=kind, sequence_level_nbr=level, record_date=vintage,
                    current_fytd_rcpt_outly_amt=current, prior_fytd_rcpt_outly_amt=prior)
    return [r("r", "Budget Receipts", "null", kind="S", level="1"),
            r("tax", "Individual Income Taxes", "r", "100.00", "90.00"),
            r("social", "Social Insurance and Retirement Receipts:", "r", kind="S"),
            r("payroll", "Employment", "social", "20.12", "19.00", level="3"),
            r("rt", "Total Receipts", "r", "120.12", "109.00", kind="T"),
            r("o", "Budget Outlays", "null", kind="S", level="1"),
            r("agency", "Department", "o", "150.00", "140.00"),
            r("offset", "Offsets", "o", "-5.64", "-4.00"),
            r("allow", "Allowances", "o", "null", "null"),
            r("ot", "Total Outlays", "o", "144.36", "136.00", kind="T")]


def finance():
    return [dict(classification_id=str(i), classification_desc=name, record_date="2026-09-30", fytd_net_txn_amt=value)
            for i, (name, value) in enumerate([
                ("Total Borrowing from the Public", "26.00"), ("Federal Reserve Account", "3.00"),
                ("Total Budget and Off-Budget Federal Entities (Financing of Deficit (+) or Disposition of Surplus (-))", "24.24")])]


class CollectorTests(unittest.TestCase):
    def test_complete_feed_reconciles_and_keeps_negative_missing(self):
        pubs = {"2024-09-30": publication([2023, 2024], "2024-09-30"),
                "2026-09-30": publication([2025, 2026], "2026-09-30")}
        d = m.build(pubs, details(), finance(), "2026-09-30", [])
        self.assertEqual(d["coverage"], dict(start="2023-10", end="2026-09", months=36))
        self.assertEqual(d["fiscal_ytd"]["agencies"][1]["value"], Decimal("-5.64"))
        self.assertIsNone(d["fiscal_ytd"]["agencies"][2]["value"])
        self.assertEqual(d["fiscal_ytd"]["finance"]["other"], Decimal("1.24"))

    def test_rollover_skips_blank_future_and_excludes_ytd(self):
        rows = publication([2026, 2027], "2026-10-31", through=1)
        parsed = m.monthly_rows(rows, "2026-10-31")
        self.assertEqual(len(parsed), 13)
        self.assertEqual(parsed["2026-10"]["fy"], 2027)
        self.assertNotIn("2026-11", parsed)

    def test_latest_revision_wins_without_duplicate_months(self):
        older = publication([2024, 2025], "2025-09-30")
        newer = publication([2025, 2026], "2026-09-30")
        row = next(r for r in newer if r["classification_id"] == "2025-10")
        row[m.MONEY[1]], row[m.MONEY[2]] = "13.03", "3.02"
        result = m.rolling_months({"2025-09-30": older, "2026-09-30": newer}, "2026-09-30")
        self.assertEqual(result[12]["outlays"], Decimal("13.03"))
        self.assertEqual(len(result), 36)

    def test_bad_parent_duplicate_or_missing_observation_rejected(self):
        rows = publication([2025, 2026], "2026-09-30")
        for mutate in [lambda r: r.update(parent_id="orphan"),
                       lambda r: r.update(current_month_gross_rcpt_amt="null"),
                       lambda r: r.update(current_month_dfct_sur_amt="100")]:
            bad = copy.deepcopy(rows)
            mutate(bad[1])
            with self.assertRaises(ValueError): m.monthly_rows(bad, "2026-09-30")
        with self.assertRaises(ValueError): m.monthly_rows(rows + [rows[1]], "2026-09-30")
        with self.assertRaises(ValueError): m.rolling_months({"2026-09-30": rows}, "2026-09-30")

    def test_null_blank_nonfinite_amounts_never_become_zero(self):
        for v in [None, "null", "", "NaN", "Infinity"]:
            with self.assertRaises(ValueError): m.amount(v)
        self.assertEqual(m.amount("0.00"), 0)

    def test_pagination_is_complete_and_truncation_fails(self):
        calls = []
        def getter(url):
            calls.append(url)
            page = len(calls)
            return json.dumps(dict(data=[dict(id=page)], meta={"total-pages": 2, "total-count": 2})).encode()
        self.assertEqual(len(m.fetch_table(1, "2026-09-30", [], getter)), 2)
        self.assertIn("page%5Bnumber%5D=2", calls[1])
        with self.assertRaises(ValueError):
            m.fetch_table(1, "2026-09-30", [], lambda _: b'{"data":[{}],"meta":{"total-pages":1,"total-count":2}}')

    def test_mismatched_table_totals_fail(self):
        rows = details()
        rows[1]["current_fytd_rcpt_outly_amt"] = "101"
        with self.assertRaises(ValueError): m.detail_groups(rows, "Budget Receipts", "Total Receipts")

    def test_http_failure_leaves_previous_publication_intact(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "feed.json"
            output.write_text('{"publication_date":"2026-09-30"}')
            def fail(url): raise HTTPError(url, 429, "rate limit", {}, None)
            with self.assertRaises(HTTPError): m.publish(m.collect(fail), output)
            self.assertEqual(output.read_text(), '{"publication_date":"2026-09-30"}')
            with self.assertRaises(ValueError): m.publish({"publication_date": "2026-08-31"}, output)
            self.assertEqual(output.read_text(), '{"publication_date":"2026-09-30"}')


if __name__ == "__main__":
    unittest.main()
