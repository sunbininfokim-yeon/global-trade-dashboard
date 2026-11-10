"""Offline cross-source machinery and unlisted OFS filing regressions."""
import unittest

from build_pe_cr import build, prepare_filings
from dart_kfa.canonical_facts import adapt_dart_filings, adapt_sec_companyfacts, default_dart_account_specs
from dart_kfa.pe_cr import build_pe_cr
from test_pe_cr import bundle
from test_pe_cr_evidence import payload, reviewed, saved_report


K_SHIP = "00109453"
CAT = "0000018230"
HDCE = "01205842"


def dart_report(entity, values, *, scope="CFS"):
    raw = saved_report(values, corp=entity)
    raw["request"]["fs_div"] = scope
    return {**payload(raw), "entity_id": entity, "fs_div": scope}


def cat(inventory=18_135_000_000):
    data = {"facts": {"us-gaap": {"InventoryNet": {"units": {"USD": [
        {"end": "2025-12-31", "val": inventory, "fp": "FY", "form": "10-K", "accn": "0000018230-26-000008"}
    ]}}}}}
    return adapt_sec_companyfacts(data, fiscal_year_end="2025-12-31", entity_id=CAT)


class MachineryAndKShipbuildingTests(unittest.TestCase):
    def test_k_shipbuilding_annual_public_ofs_statement(self):
        values = {k: v * 1_000_000 for k, v in {"revenue": 1256302, "op": 145427, "cfo": -29569}.items()}
        p = dart_report(K_SHIP, values, scope="OFS")
        result = build({**p, "corp": {"induty_code": "3111"}})
        self.assertEqual(result["industry"], "shipbuilding")
        canonical = adapt_dart_filings(prepare_filings(p), account_specs=default_dart_account_specs(),
                                       fiscal_year_end="2025-12-31", entity_id=K_SHIP, fs_div="OFS")
        self.assertEqual(canonical["series"]["PECR_revenue"]["annual"]["value"], 1_256_302_000_000)
        self.assertEqual(canonical["series"]["PECR_op"]["annual"]["value"], 145_427_000_000)
        self.assertEqual(canonical["series"]["PECR_cfo"]["annual"]["value"], -29_569_000_000)
        note = result["industry_note_metrics"]
        book, rg = note["shipbuilding_orderbook"], note["shipbuilding_rg"]
        self.assertEqual(book["rows"][0]["closing"], 866_539_000_000)
        self.assertEqual(book["rows"][0]["new_contracts_reported"], 630_697_000_000)
        self.assertEqual(book["rows"][0]["other_movement"], 2_770_000_000)
        self.assertEqual(rg["portfolios"][0]["reported_guaranteed_total"]["amount"], 570_471_000)

    def test_k_shipbuilding_interim_guaranteed_amount_is_not_limit_and_scope_not_copied(self):
        b = {**bundle(2026, scope="OFS"), "entity_id": K_SHIP}
        p = build_pe_cr(b, selected_period="Q2", industry="shipbuilding")["industry_note_metrics"]
        book, pool = p["shipbuilding_orderbook"], p["shipbuilding_rg"]["portfolios"][0]
        self.assertEqual(book["source_window"], "half_year_ytd")
        self.assertEqual(book["rows"][0]["closing"], 1_197_080_000_000)
        self.assertEqual(book["rows"][0]["new_contracts_reported"], 802_679_000_000)
        self.assertEqual(pool["reported_guaranteed_total"]["amount"], 688_070_000)
        self.assertEqual(pool["rows"][0]["reported_guaranteed_amount"], 450_000_000)
        self.assertTrue(all(r["limit"] is None and r["outstanding"] is None and r["utilization"] is None for r in pool["rows"]))
        cfs = build_pe_cr({**b, "fs_div": "CFS"}, selected_period="Q2", industry="shipbuilding")["industry_note_metrics"]
        self.assertEqual(cfs["shipbuilding_rg"]["portfolios"], [])
        self.assertEqual(cfs["shipbuilding_orderbook"]["rows"], [])

    def test_caterpillar_exact_inventory_and_approximate_backlog(self):
        result = build_pe_cr(cat())
        self.assertEqual(result["industry"], "machinery")
        c = result["cards"]
        self.assertAlmostEqual(c["wip_to_inventory"]["value"], 1598 / 18135)
        self.assertAlmostEqual(c["raw_materials_to_inventory"]["value"], 7434 / 18135)
        self.assertEqual(c["order_backlog"]["value"], 51_200_000_000)
        self.assertIsNone(c["new_orders"]["value"])
        mismatched = build_pe_cr(cat(19_000_000_000))
        self.assertEqual(mismatched["cards"]["wip_to_inventory"]["reason"], "conflict_or_missing:canonical_net_inventory_control")
        self.assertEqual(mismatched["cards"]["order_backlog"]["value"], 51_200_000_000)

    def test_hd_equipment_inventory_reconciles_with_reported_unit_and_never_fills_backlog(self):
        p = dart_report(HDCE, {"inventory": 1_084_094_488_000})
        result = build({**p, "corp": {"induty_code": "29241"}})
        c = result["cards"]
        self.assertAlmostEqual(c["wip_to_inventory"]["value"], 67209 / 1084094)
        self.assertAlmostEqual(c["raw_materials_to_inventory"]["value"], 212624 / 1084094)
        self.assertIsNone(c["order_backlog"]["value"])
        self.assertEqual(c["wip_to_inventory"]["inputs"][1]["evidence"]["provider"], "KRX_KIND")
        p["filings"]["FY"]["response"]["list"][0]["thstrm_amount"] = "1084095000000"
        self.assertIsNone(build(p)["cards"]["raw_materials_to_inventory"]["value"])

    def test_explicit_reviewed_inventory_is_not_silently_combined_with_builtin_rows(self):
        b = cat()
        packet = reviewed(b, {"wip_inventory": 1})
        self.assertIsNone(build_pe_cr(b, reviewed_disclosures=packet)["cards"]["wip_to_inventory"]["value"])
