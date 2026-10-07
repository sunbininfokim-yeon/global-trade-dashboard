"""End-to-end calculations from annual/interim canonical facts."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dart_kfa.canonical_analysis import analyze_canonical_facts  # noqa: E402
from dart_kfa.canonical_facts import adapt_dart_filings, adapt_sec_companyfacts  # noqa: E402


SPECS = {
    "REVENUE": {"nature": "flow", "statement": "IS", "source_ids": ["rev"], "sec_concepts": ["Revenues"]},
    "OPERATING_INCOME": {"nature": "flow", "statement": "IS", "source_ids": ["op"], "sec_concepts": ["OperatingIncomeLoss"]},
    "NET_INCOME": {"nature": "flow", "statement": "IS", "source_ids": ["ni"], "sec_concepts": ["NetIncomeLoss"]},
    "CFO": {"nature": "flow", "statement": "CF", "source_ids": ["cfo"], "sec_concepts": ["NetCashProvidedByUsedInOperatingActivities"]},
    "CAPEX": {"nature": "flow", "statement": "CF", "source_ids": ["capex"], "sec_concepts": ["PaymentsToAcquirePropertyPlantAndEquipment"]},
    "TOTAL_ASSETS": {"nature": "balance", "statement": "BS", "source_ids": ["assets"], "sec_concepts": ["Assets"]},
    "TOTAL_LIABILITIES": {"nature": "balance", "statement": "BS", "source_ids": ["liab"], "sec_concepts": ["Liabilities"]},
    "EQUITY": {"nature": "balance", "statement": "BS", "source_ids": ["equity"], "sec_concepts": ["StockholdersEquity"]},
    "LEASE_LIABILITIES": {"nature": "balance", "statement": "BS", "source_ids": ["lease"], "sec_concepts": ["LeaseLiability"]},
    "CONTRACT_LIABILITIES": {"nature": "balance", "statement": "BS", "source_ids": ["contract"], "sec_concepts": ["ContractWithCustomerLiability"]},
}


def dart_row(code, account, sj, amount, cumulative=None):
    row = {"reprt_code": code, "rcept_no": f"r-{code}-{account}", "bsns_year": "2025", "fs_div": "CFS", "sj_div": sj, "account_id": account, "account_nm": account, "thstrm_amount": str(amount), "currency": "KRW"}
    if cumulative is not None:
        row["thstrm_add_amount"] = str(cumulative)
    return row


class CanonicalAnalysisTest(unittest.TestCase):
    def test_p1_addon_is_present_and_combined_da_does_not_make_strict_ebitda(self):
        specs = {
            **SPECS,
            # Deliberately combined D&A: P1 must not use this as either strict
            # component without separate reported PPE/intangible facts.
            "DEPRECIATION": {"nature": "flow", "statement": "IS", "source_ids": ["combined_da"]},
        }
        filings = {
            "11011": [
                dart_row("11011", "rev", "IS", 100),
                dart_row("11011", "op", "IS", 20),
                dart_row("11011", "combined_da", "IS", 7),
            ]
        }
        canonical = adapt_dart_filings(filings, account_specs=specs, fiscal_year_end="2025-12-31")
        company = analyze_canonical_facts(canonical, corp={"name": "산업기업", "industry": "C20"})
        self.assertIn("p1_disclosures", company)
        self.assertIn("p1_models", company)
        self.assertEqual(company["p1_models"]["schema_version"], "kfa-p1-models/1")
        self.assertEqual(company["p1_disclosures"]["schema_version"], "kfa-p1-disclosures/1")
        ebitda = company["p1_disclosures"]["current"]["ebitda"]
        self.assertIsNone(ebitda["value"])
        self.assertIn("PPE_DEPRECIATION:missing:account", ebitda["reason"])
        self.assertIn("INTANGIBLE_AMORTIZATION:missing:account", ebitda["reason"])

    def test_q2_uses_half_year_minus_q1_and_blocks_interim_dcf(self):
        quarterly = {
            "rev": (10, 30, 45, 70), "op": (2, 5, 8, 12), "ni": (1, 3, 5, 8),
            "cfo": (3, 8, 12, 20), "capex": (1, 3, 5, 8),
        }
        balances = {"assets": (100, 110, 115, 120), "liab": (40, 45, 46, 48), "equity": (60, 65, 69, 72)}
        codes = ("11013", "11012", "11014", "11011")
        filings = {code: [] for code in codes}
        for account, values in quarterly.items():
            sj = "CF" if account in {"cfo", "capex"} else "IS"
            for index, code in enumerate(codes):
                filings[code].append(dart_row(code, account, sj, values[index], cumulative=None if code == "11011" else values[index]))
        for account, values in balances.items():
            for index, code in enumerate(codes):
                filings[code].append(dart_row(code, account, "BS", values[index]))
        canonical = adapt_dart_filings(filings, account_specs=SPECS, fiscal_year_end="2025-12-31")
        company = analyze_canonical_facts(canonical, corp={"name": "산업기업", "industry": "C20"}, selected_period="Q2")
        self.assertEqual(company["accounts"]["REVENUE"]["value"], 20)
        self.assertEqual(company["accounts"]["TOTAL_ASSETS"]["value"], 110)
        self.assertEqual(company["ma_metrics"]["fcf"]["value"], 3)
        self.assertEqual(company["valuation"]["reason"], "blocked_quality:valuation_requires_annual_or_ttm_base")
        self.assertEqual(company["unified_views"]["views"]["basic"]["id"], "basic")
        for model_id in ("delever_path", "fcf_yield_snapshot", "reverse_dcf", "scenario_dcf_ev_bridge"):
            self.assertNotIn(model_id, company["unified_views"]["model_registry"])

    def test_financial_entity_has_no_visible_fcf(self):
        canonical = adapt_dart_filings({}, account_specs=SPECS, fiscal_year_end="2025-12-31")
        company = analyze_canonical_facts(canonical, corp={"name": "KB금융", "corp_code": "00688996", "industry": "K64"})
        visible = company["unified_views"]
        self.assertNotIn("fcf", visible["card_registry"])
        self.assertTrue(all("fcf" not in view["card_refs"] for view in visible["views"].values()))
        self.assertEqual(company["valuation"]["status"], "not_applicable")

    def test_p2_shipping_lease_adjustment_requires_same_reported_balance_basis(self):
        filings = {
            "11011": [
                dart_row("11011", "liab", "BS", 300),
                dart_row("11011", "equity", "BS", 100),
                dart_row("11011", "lease", "BS", 80),
            ]
        }
        canonical = adapt_dart_filings(filings, account_specs=SPECS, fiscal_year_end="2025-12-31")
        company = analyze_canonical_facts(canonical, corp={"name": "해운사", "industry_kit": "shipping"})
        adjustment = company["industry"]["adjusted_metrics"]["debt_ratio_ex_lease"]
        self.assertEqual(adjustment["value"], 220)
        self.assertEqual(adjustment["basis"]["status"], "reported_balance_facts")
        self.assertEqual(adjustment["basis"]["currency"], "KRW")

        # A single currency-mixed fact must not change the reported leverage.
        canonical["series"]["LEASE_LIABILITIES"]["annual"]["unit"]["currency"] = "USD"
        blocked = analyze_canonical_facts(canonical, corp={"name": "해운사", "industry_kit": "shipping"})
        self.assertNotIn("debt_ratio_ex_lease", blocked["industry"]["adjusted_metrics"])
        self.assertEqual(
            blocked["industry"]["adjustment_status"][0]["reason"],
            "incompatible:balance_period_scope_currency_or_unit",
        )

    def test_p2_shipbuilding_backlog_uses_only_p1_structured_reported_row(self):
        canonical = adapt_dart_filings(
            {"11011": [dart_row("11011", "rev", "IS", 100)]},
            account_specs=SPECS,
            fiscal_year_end="2025-12-31",
        )
        rows = [{
            "disclosure_type": "backlog_order_book",
            "is_structured_reported": True,
            "segment_id": "yard",
            "segment_name": "조선",
            "value": 900,
            "unit": {"kind": "currency", "currency": "KRW", "scale": 1},
            "fiscal_year": 2025,
            "period_end": "2025-12-31",
            "fs_div": "CFS",
            "report_id": "receipt-11011",
            "report_type": "business_report",
            "source_table": "수주현황",
            "source_row_id": "yard-1",
        }]
        company = analyze_canonical_facts(
            canonical,
            corp={"name": "조선사", "industry_kit": "shipbuilding"},
            p1_structured_disclosures=rows,
        )
        backlog = company["industry"]["disclosures"]["backlog_order_book"]
        self.assertEqual(backlog["status"], "reported")
        self.assertEqual(backlog["value"][0]["value"], 900)
        self.assertEqual(backlog["provenance"]["acceptance"], "structured_reported_rows_only")

    def test_sec_and_dart_sign_and_period_semantics_match(self):
        codes = ("11013", "11012", "11014", "11011")
        cumulative = {
            "rev": (10, 30, 45, 70), "op": (2, 5, 8, 12), "ni": (1, 3, 5, 8),
            "cfo": (3, 8, 12, 20), "capex": (-1, -3, -5, -8),
        }
        filings = {code: [] for code in codes}
        for account, values in cumulative.items():
            sj = "CF" if account in {"cfo", "capex"} else "IS"
            for index, code in enumerate(codes):
                filings[code].append(dart_row(code, account, sj, values[index], cumulative=None if code == "11011" else values[index]))
        dart = adapt_dart_filings(filings, account_specs=SPECS, fiscal_year_end="2025-12-31")

        concept_by_account = {
            "rev": "Revenues", "op": "OperatingIncomeLoss", "ni": "NetIncomeLoss",
            "cfo": "NetCashProvidedByUsedInOperatingActivities", "capex": "PaymentsToAcquirePropertyPlantAndEquipment",
        }
        bounds = (
            ("2025-01-01", "2025-03-31", "10-Q", "Q1"),
            ("2025-01-01", "2025-06-30", "10-Q", "Q2"),
            ("2025-01-01", "2025-09-30", "10-Q", "Q3"),
            ("2025-01-01", "2025-12-31", "10-K", "FY"),
        )
        sec_gaap = {}
        for account, values in cumulative.items():
            sec_values = tuple(abs(value) for value in values) if account == "capex" else values
            sec_gaap[concept_by_account[account]] = {"units": {"USD": [
                {"start": start, "end": end, "val": sec_values[index], "form": form, "fp": fp, "filed": "2026-02-01"}
                for index, (start, end, form, fp) in enumerate(bounds)
            ]}}
        sec = adapt_sec_companyfacts(
            {"entityName": "Synthetic", "facts": {"us-gaap": sec_gaap}},
            fiscal_year_end="2025-12-31",
            account_specs=SPECS,
        )
        dart_q2 = analyze_canonical_facts(dart, corp={"name": "DART 산업기업", "industry": "C20"}, selected_period="Q2")
        sec_q2 = analyze_canonical_facts(sec, corp={"name": "SEC Industrial", "industry": "C20"}, selected_period="Q2")
        self.assertEqual(dart_q2["period"]["period_kind"], sec_q2["period"]["period_kind"])
        self.assertEqual(dart_q2["metrics"]["operating_margin"]["value"], sec_q2["metrics"]["operating_margin"]["value"])
        self.assertEqual(dart_q2["ma_metrics"]["fcf"]["value"], sec_q2["ma_metrics"]["fcf"]["value"])


if __name__ == "__main__":
    unittest.main()
