"""Note items. Contexts copy SK하이닉스 / 현대건설 FY2025 layouts."""
import unittest

from dart_kfa.note_items import note_items

SCOPE = "ifrs-full:ConsolidatedAndSeparateFinancialStatementsAxis"
CONS = {SCOPE: "ifrs-full:ConsolidatedMember"}
REP = {"ifrs-full:CarryingAmountAccumulatedDepreciationAmortisationAndImpairmentAndGrossCarryingAmountAxis": "dart:ReportedAmountMember"}


def instance(contexts, facts):
    out = []
    for cid, (period, dims) in contexts.items():
        members = "".join(f'<xbrldi:explicitMember dimension="{a}">{m}</xbrldi:explicitMember>' for a, m in dims.items())
        p = (f"<xbrli:instant>{period}</xbrli:instant>" if isinstance(period, str)
             else f"<xbrli:startDate>{period[0]}</xbrli:startDate><xbrli:endDate>{period[1]}</xbrli:endDate>")
        out.append(f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="x">e</xbrli:identifier>'
                   f'<xbrli:segment>{members}</xbrli:segment></xbrli:entity><xbrli:period>{p}</xbrli:period></xbrli:context>')
    fx = "".join(f'<x:{c} contextRef="{cid}" unitRef="KRW">{v}</x:{c}>' for c, cid, v in facts)
    return ('<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" '
            'xmlns:x="http://x">' + "".join(out) + fx + "</xbrli:xbrl>").encode()


FY = ("2025-01-01", "2025-12-31")


class NoteItems(unittest.TestCase):
    def test_rd_capitalisation_and_sbc(self):
        cap = {**CONS, "ifrs-full:ClassesOfIntangibleAssetsAndGoodwillAxis": "ifrs-full:CapitalisedDevelopmentExpenditureMember"}
        ctxs = {"rep": (FY, {**CONS, **REP}), "plain": (FY, CONS), "cap": (FY, cap),
                "sep": (FY, {SCOPE: "ifrs-full:SeparateMember"})}
        facts = [("OrdinaryDevelopmentExpenseSellingGeneralAdministrativeExpenses", "rep", "6465637000000"),
                 ("AdditionsOtherThanThroughBusinessCombinationsIntangibleAssetsOtherThanGoodwill", "cap", "266890000000"),
                 ("ExpenseFromSharebasedPaymentTransactionsWithEmployees", "plain", "216000000000"),
                 ("ExpenseFromSharebasedPaymentTransactionsWithEmployees", "sep", "1")]
        r = note_items(instance(ctxs, facts), fs_div="CFS", fiscal_year_end="2025-12-31", revenue=97_146_675e6)
        self.assertEqual((r["rd_expensed"]["value"], r["rd_capitalised"]["value"], r["sbc"]["value"]),
                         (6_465_637e6, 266_890e6, 216_000e6))
        self.assertAlmostEqual(r["capitalisation_ratio"]["value"], 266890 / (6465637 + 266890))
        self.assertAlmostEqual(r["rd_to_sales"]["value"], (6465637 + 266890) / 97146675)

    def test_provisions_by_class(self):
        cls = lambda m: ("2025-12-31", {**CONS, "ifrs-full:ClassesOfProvisionsAxis": f"ifrs-full:{m}"})  # noqa: E731
        ctxs = {"w": cls("WarrantyProvisionMember"), "o": cls("OnerousContractsProvisionMember"),
                "t": ("2025-12-31", CONS), "x": cls("RoyaltyExpensesMemberOfOtherProvisions")}
        facts = [("OtherProvisions", "w", "584676000000"), ("OtherProvisions", "o", "279820000000"),
                 ("OtherProvisions", "x", "100"), ("OtherProvisions", "t", "864676000100")]
        r = note_items(instance(ctxs, facts), fs_div="CFS", fiscal_year_end="2025-12-31",
                       labels={"RoyaltyExpensesMemberOfOtherProvisions": "기술사용료 [구성요소]"})
        p = r["provisions"]
        self.assertEqual([c["label"] for c in p["classes"]], ["판매보증", "손실부담계약(공사손실 등)", "기술사용료"])
        self.assertEqual(p["total"], 864_676_000_100)

    def test_disagreeing_contexts_are_dropped(self):
        ctxs = {"a": (FY, CONS), "b": (FY, {**CONS, **REP})}
        facts = [("ResearchAndDevelopmentExpense", "a", "10"), ("ResearchAndDevelopmentExpense", "a", "11")]
        self.assertIsNone(note_items(instance(ctxs, facts), fs_div="CFS", fiscal_year_end="2025-12-31")["rd_expensed"]["value"])


if __name__ == "__main__":
    unittest.main()
