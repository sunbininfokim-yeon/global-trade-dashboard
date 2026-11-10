"""Public filing totals transcribed into OpenDART response shape, no live API."""
import unittest

from test_pe_cr import bundle
from dart_kfa.entity_policy import classify_entity
from dart_kfa.pe_cr import build_pe_cr
from dart_kfa.pe_cr_dart_schedules import INSTRUMENTS


def record(entity, as_of, receipt, instrument, amounts, *, dash_means_zero=True):
    endpoint, label, specs = INSTRUMENTS[instrument]
    row = {"corp_code": entity, "stlm_dt": as_of, "rcept_no": receipt,
           "remndr_exprtn1": "미상환 잔액", "remndr_exprtn2": "합계",
           **{field: str(amount) for (field, _, _), amount in zip(specs, amounts)},
           "sm": str(sum(x for x in amounts if type(x) is int))}
    if instrument == "short_term_bond":
        row.update(isu_lmt="300,000", remndr_lmt="190,000")
    return {"endpoint": endpoint, "as_of": as_of, "receipt": receipt, "scope": "issuer_only", "currency": "KRW",
            "scale": 1_000_000, "scope_evidence": f"증권의 발행을 통한 자금조달 / {label} 미상환 잔액 / 합계",
            "dash_means_zero": dash_means_zero, "response": {"status": "000", "list": [row]}}


def funding(entity, as_of, packets):
    return dict(schema_version="kfa-funding-disclosure/1", entity_id=entity, as_of=as_of,
                fs_div="CFS", currency="KRW", scale=1, dart_instruments=packets)


def instruments(result):
    profile = result["disclosure_profile"]["instrument_maturity"]
    return profile["issuer_type"], {row["instrument"]: row for row in profile["rows"]}


class FundingInstrumentsTests(unittest.TestCase):
    def test_uamco_2025_q3_instruments_preserve_original_day_boundaries(self):
        entity, end, receipt = "00819268", "2025-09-30", "20251114001364"
        packets = {k: record(entity, end, receipt, k, amounts) for k, amounts in {
            "commercial_paper": ["-", 320000, 590000, 120000, 830000, "-", "-", "-"],
            "short_term_bond": ["-", 80000, 30000, "-", "-"],
            "corporate_bond": [490000, 1070000, 1130000, 290000, 220000, "-", "-"],
        }.items()}
        result = build_pe_cr({**bundle(), "entity_id": entity}, selected_period="Q3", funding=funding(entity, end, packets))
        issuer, rows = instruments(result)
        self.assertEqual(issuer["id"], "npl_asset_management")
        cp, short, bond = (rows[k] for k in ("commercial_paper", "short_term_bond", "corporate_bond"))
        self.assertEqual(cp["cumulative"]["90d"]["value"], 910_000_000_000)
        self.assertEqual(cp["cumulative"]["180d"]["value"], 1_030_000_000_000)
        self.assertEqual(cp["cumulative"]["1y"]["value"], 1_860_000_000_000)
        self.assertEqual(short["cumulative"]["90d"]["value"], 110_000_000_000)
        self.assertEqual(short["outstanding"], 110_000_000_000)  # excludes issuance limit
        self.assertEqual(bond["cumulative"]["90d"], {"value": None, "reason": "missing:exact_reported_boundary"})
        self.assertEqual(bond["cumulative"]["1y"]["value"], 490_000_000_000)
        self.assertEqual(bond["scope"], "issuer_only")  # not the CFS principal schedule
        self.assertIsNone(result["cards"]["debt_due_within_1y"]["value"])
        self.assertEqual(result["cards"]["fcf"]["reason"], "not_applicable:financial_entity")

    def test_korea_capital_fy2025_cp_and_missing_short_term_bonds_are_separate(self):
        entity, end, receipt = "00149594", "2025-12-31", "20260312000997"
        cp = record(entity, end, receipt, "commercial_paper", ["-", "-", "-", "-", 60000, "-", "-", "-"])
        short = record(entity, end, receipt, "short_term_bond", ["-"] * 5, dash_means_zero=False)
        short["response"]["list"][0]["sm"] = "-"
        bond = record(entity, end, receipt, "corporate_bond", [1795000, 1700000, 0, 0, 0, 0, 0])
        for name, amounts in (("공모", [1670000, 1550000, 0, 0, 0, 0, 0]), ("사모", [1250000, 150000, 0, 0, 0, 0, 0])):
            detail = record(entity, end, receipt, "corporate_bond", amounts)["response"]["list"][0]
            detail["remndr_exprtn2"] = name
            if name == "사모":
                detail["sm"] = "275000"  # source row conflicts with its first bucket
            bond["response"]["list"].append(detail)
        result = build_pe_cr({**bundle(), "entity_id": entity}, funding=funding(entity, end, {
            "commercial_paper": cp, "short_term_bond": short, "corporate_bond": bond}))
        issuer, rows = instruments(result)
        self.assertEqual(issuer["id"], "specialized_credit_finance")
        self.assertEqual(rows["commercial_paper"]["outstanding"], 60_000_000_000)
        self.assertEqual(rows["commercial_paper"]["cumulative"]["90d"]["value"], 0)
        self.assertIsNone(rows["short_term_bond"]["outstanding"])
        self.assertEqual(rows["short_term_bond"]["status"], "unavailable")
        self.assertEqual(rows["corporate_bond"]["reason"], "conflict:dart_instrument_placement_total")
        self.assertEqual(classify_entity({"induty_code": "64913"})["entity_class"], "specialized_credit_finance")
        self.assertNotEqual(classify_entity({"induty_code": "64999"})["entity_class"], "npl_asset_management")

    def test_wrong_layout_receipt_scope_and_total_do_not_become_reported(self):
        entity, end, receipt = "00149594", "2025-12-31", "20260312000997"
        b = {**bundle(), "entity_id": entity}
        for change, reason in (
            (lambda p, r: p.update(endpoint="wrong"), "incompatible:dart_instrument_endpoint"),
            (lambda p, r: p.update(scope="OFS"), "incompatible:dart_instrument_scope_currency_or_date"),
            (lambda p, r: r.update(corp_code="00819268"), "incompatible:dart_schedule_entity_receipt_or_date"),
            (lambda p, r: r.update(sm="5"), "conflict:dart_instrument_bucket_total"),
            (lambda p, r: r.update(isu_lmt="5"), "incompatible:dart_instrument_bucket_layout"),
            (lambda p, r: p["response"]["list"].append(dict(r)), "missing_or_conflict:dart_instrument_exact_scope_row"),
            (lambda p, r: p.update(response={"status": "013"}), "missing:opendart_no_data"),
        ):
            with self.subTest(reason=reason):
                cp = record(entity, end, receipt, "commercial_paper", [1] * 8)
                change(cp, cp["response"]["list"][0])
                row = instruments(build_pe_cr(b, funding=funding(entity, end, {"commercial_paper": cp})))[1]["commercial_paper"]
                self.assertEqual(row["reason"], reason)
                self.assertIsNone(row["outstanding"])


if __name__ == "__main__":
    unittest.main()
