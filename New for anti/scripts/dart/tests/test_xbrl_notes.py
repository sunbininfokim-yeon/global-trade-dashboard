"""XBRL note extraction. The instance below copies the context layout of the
Samsung Electronics FY2025 original XBRL (receipt 20260310002820) with its
actual values for the facts the extractor reads, plus decoys it must ignore."""
import io
import json
import unittest
import zipfile
from pathlib import Path

from dart_kfa.pe_cr_evidence import reviewed_facts
from dart_kfa.xbrl_notes import instance_from_zip, merge_packs, note_bundle

AX = "ifrs-full:ConsolidatedAndSeparateFinancialStatementsAxis"


def ctx(cid, start, end, **dims):
    members = "".join(f'<xbrldi:explicitMember dimension="{a}">{m}</xbrldi:explicitMember>' for a, m in dims.items())
    seg = f"<xbrli:segment>{members}</xbrli:segment>" if members else ""
    return (f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="x">00126380</xbrli:identifier>{seg}'
            f'</xbrli:entity><xbrli:period><xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate>'
            f'</xbrli:period></xbrli:context>')


def instance(facts, contexts):
    body = "".join(contexts) + "".join(
        f'<{c} contextRef="{r}" unitRef="KRW" decimals="-6">{v}</{c}>' for c, r, v in facts)
    return ('<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" '
            'xmlns:ifrs-full="http://xbrl.ifrs.org/taxonomy/2023-03-23/ifrs-full" xmlns:dart="http://dart.fss.or.kr/taxonomy">'
            + body + "</xbrli:xbrl>").encode()


Y = ("2025-01-01", "2025-12-31")
CONTEXTS = [
    ctx("cons_total", *Y, **{AX: "ifrs-full:ConsolidatedMember",
                             "ifrs-full:CarryingAmountAccumulatedDepreciationAmortisationAndImpairmentAndGrossCarryingAmountAxis": "dart:ReportedAmountMember"}),
    ctx("cons", *Y, **{AX: "ifrs-full:ConsolidatedMember"}),
    ctx("cons_fl", *Y, **{AX: "ifrs-full:ConsolidatedMember", "ifrs-full:AssetsAndLiabilitiesAxis": "ifrs-full:FinancialLiabilitiesCategoryMember"}),
    ctx("cons_fl_amortised", *Y, **{AX: "ifrs-full:ConsolidatedMember",
                                   "ifrs-full:AssetsAndLiabilitiesAxis": "ifrs-full:FinancialLiabilitiesAtAmortisedCostCategoryMember"}),
    ctx("cons_segment", *Y, **{AX: "ifrs-full:ConsolidatedMember", "ifrs-full:SegmentsAxis": "x:DsDivision"}),
    ctx("sep", *Y, **{AX: "ifrs-full:SeparateMember"}),
    ctx("cons_prior", "2024-01-01", "2024-12-31", **{AX: "ifrs-full:ConsolidatedMember"}),
]
FACTS = [
    ("ifrs-full:AdjustmentsForDepreciationExpense", "cons_total", "43605740000000"),
    ("ifrs-full:DepreciationExpense", "cons", "43605740000000"),
    ("ifrs-full:DepreciationExpense", "cons_segment", "37957308000000"),     # segment: ignored
    ("ifrs-full:DepreciationExpense", "sep", "35291428000000"),              # separate: ignored for CFS
    ("ifrs-full:DepreciationExpense", "cons_prior", "39000000000000"),       # prior year: ignored
    ("ifrs-full:AdjustmentsForAmortisationExpense", "cons_total", "3320852000000"),
    ("dart:InterestExpenseFinanceExpense", "cons_fl", "605783000000"),
    ("dart:InterestExpenseFinanceExpense", "cons_fl_amortised", "43052000000"),  # sub-category: ignored
    ("dart:InterestExpenseFinanceExpense", "cons_total", "605783000000"),
]


class XbrlNotes(unittest.TestCase):
    def bundle(self, facts=FACTS, fs_div="CFS"):
        return note_bundle(instance(facts, CONTEXTS), entity_id="00126380", fs_div=fs_div,
                           fiscal_year_end="2025-12-31", receipt="20260310002820")

    def test_reproduces_the_hand_reviewed_samsung_rows(self):
        got = {r["key"]: r["amount"] for r in self.bundle()["rows"]}
        manual = json.loads((Path(__file__).resolve().parents[1] / "config/pe_cr_reviewed/samsung_00126380_2025_cfs.json").read_text())
        for row in manual["rows"]:
            self.assertEqual(got[row["key"]], row["amount"] * row["scale"], row["key"])

    def test_separate_scope_reads_separate_contexts_only(self):
        rows = {r["key"]: r["amount"] for r in self.bundle(fs_div="OFS")["rows"]}
        self.assertEqual(rows, {"PPE_DEPRECIATION": 35291428000000})

    def test_disagreeing_contexts_leave_the_key_out(self):
        facts = FACTS + [("ifrs-full:AdjustmentsForAmortisationExpense", "cons", "1")]
        keys = {r["key"] for r in self.bundle(facts)["rows"]}
        # the concept disagrees across contexts and no lower-priority concept exists
        self.assertNotIn("INTANGIBLE_AMORTIZATION", keys)

    def test_rows_pass_the_engine_validator(self):
        from test_pe_cr import bundle as canonical_bundle
        pack = self.bundle()
        facts = reviewed_facts(pack, {**canonical_bundle(), "entity_id": "00126380"})
        self.assertEqual(facts[("interest", "2025-01-01", "2025-12-31")]["value"], 605783000000)
        self.assertIn("fnlttXbrl", facts[("interest", "2025-01-01", "2025-12-31")]["provenance"]["document"])

    def test_hand_reviewed_rows_win_in_merge(self):
        manual = {"schema_version": "kfa-pe-cr-reviewed/1", "rows": [
            {"key": "interest", "period_start": "2025-01-01", "period_end": "2025-12-31", "amount": 1, "scale": 1}]}
        merged = merge_packs(manual, self.bundle())
        interest = [r for r in merged["rows"] if r["key"] == "interest"]
        self.assertEqual([r["amount"] for r in interest], [1])
        self.assertEqual({r["key"] for r in merged["rows"]}, {"interest", "PPE_DEPRECIATION", "INTANGIBLE_AMORTIZATION"})

    def test_zip_with_one_instance(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("entity00126380_2025-12-31.xbrl", instance(FACTS, CONTEXTS))
            z.writestr("entity00126380_2025-12-31.xsd", "<x/>")
        self.assertTrue(instance_from_zip(buf.getvalue()).startswith(b"<xbrli:xbrl"))


if __name__ == "__main__":
    unittest.main()
