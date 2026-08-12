"""Unit tests for Macro Monitor engine (USA benchmark kit)."""

from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))

from macro_monitor.engine import build_universe, resolve_country  # noqa: E402
from macro_monitor.series import month_ends  # noqa: E402


class TestUsMacroKit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        countries = json.loads((ROOT / "config" / "countries.json").read_text(encoding="utf-8"))
        series = json.loads((ROOT / "config" / "series.spec.json").read_text(encoding="utf-8"))
        cls.doc = build_universe(
            countries,
            series,
            asof=date(2026, 8, 1),
            generated_at="2026-08-01T00:00:00Z",
        )

    def test_usa_is_benchmark(self):
        usa = resolve_country(self.doc, "United States")
        self.assertIsNotNone(usa)
        assert usa is not None
        self.assertTrue(usa["benchmark"])
        self.assertEqual(usa["kit"], "us_macro_benchmark_v1")
        self.assertEqual(
            usa["active_categories"],
            ["liquidity", "rates", "fx", "equity", "growth", "inflation"],
        )

    def test_net_liquidity_derived(self):
        usa = resolve_country(self.doc, "USA")
        assert usa is not None
        by_id = {i["id"]: i for i in usa["indicators"]}
        self.assertIn("net_liquidity", by_id)
        fed = by_id["fed_total_assets"]["value"]
        tga = by_id["tga"]["value"]
        rrp = by_id["on_rrp"]["value"]
        net = by_id["net_liquidity"]["value"]
        expected = fed - tga / 1000.0 - rrp / 1000.0
        self.assertAlmostEqual(net, expected, places=4)
        self.assertEqual(by_id["bond_10y"]["display"], "4.70%")

    def test_usa_us_tuning_contract(self):
        usa = resolve_country(self.doc, "USA")
        assert usa is not None
        by_id = {i["id"]: i for i in usa["indicators"]}
        self.assertEqual(self.doc["engine_version"], "0.31.0")
        self.assertEqual(self.doc["source"]["kind"], "fixture_synth")
        self.assertEqual(self.doc["source"].get("quality"), "demo_not_live")
        self.assertIn("refresh_policy", self.doc)

        # SOMA holdings composite (not market yields)
        self.assertIn("fed_ust_holdings", by_id)
        self.assertEqual(by_id["fed_ust_holdings"]["chart_type"], "stack")
        self.assertIn("SOMA", by_id["fed_ust_holdings"]["label_ko"])
        self.assertAlmostEqual(
            by_id["fed_ust_holdings"]["value"],
            sum(by_id[m]["value"] for m in (
                "fed_ust_le_1y", "fed_ust_1_5y", "fed_ust_5_10y", "fed_ust_gt_10y"
            )),
            places=2,
        )
        chip_ids = {c["id"] for cat in usa["categories"].values() for c in cat}
        self.assertIn("fed_ust_holdings", chip_ids)
        self.assertNotIn("fed_ust_le_1y", chip_ids)

        # Market yields include 3M
        self.assertIn("bond_3m", by_id)
        self.assertEqual(by_id["hy_oas"]["label_ko"], "High Yield OAS")

        # FedWatch structured
        self.assertIn("fedwatch", by_id)
        self.assertNotIn("fedwatch_cut_prob", by_id)
        self.assertEqual(by_id["fedwatch"]["display"], "25bp 인상 57%")
        self.assertEqual(by_id["fedwatch"]["chart_type"], "bar")
        self.assertGreaterEqual(len(by_id["fedwatch"]["outcomes"]), 3)

        # GDP dual (not SAAR)
        self.assertIn("gdp", by_id)
        self.assertNotIn("gdp_qoq_saar", by_id)
        self.assertIn("|", by_id["gdp"]["display_chip"])
        self.assertEqual(by_id["gdp"]["ui"]["dual"], ["yoy", "qoq"])

        # Inflation story
        self.assertIn("trimmed_mean_cpi", by_id)
        self.assertNotIn("bei_5y", by_id)
        self.assertTrue((by_id["core_pce_yoy"].get("ui") or {}).get("chip") is False)
        self.assertTrue(by_id["cpi_yoy"].get("components"))

        # Equity MA5 + NFP caveat + news stub (no fake articles)
        self.assertIn("ma5", by_id["spx"]["history"]["5y"])
        self.assertIn("개정", by_id["nfp"]["note_ko"])
        uref = by_id["unemployment"].get("reference") or {}
        self.assertEqual(uref.get("level"), 4.2)
        self.assertIn("analog_ko", by_id["unemployment"])
        self.assertIn("news_query", by_id["nfp"])
        self.assertIsNone(by_id["nfp"]["news"])

        # QRA maturity bars
        self.assertIn("qra_issuance", by_id)
        self.assertEqual(by_id["qra_issuance"]["chart_type"], "bar")
        self.assertGreaterEqual(len(by_id["qra_issuance"]["components"]), 6)
        # QRA click compare: prior actual / prior forecast / current
        cmp = by_id["qra_issuance"].get("compare") or {}
        self.assertTrue(cmp.get("series"))
        self.assertEqual(by_id["qra_issuance"].get("ui", {}).get("click_view"), "compare_bar_table")

        # Headlines prefer core CPI over PCE
        hl = {h["id"] for h in usa["headlines"]}
        self.assertIn("core_cpi_yoy", hl)
        self.assertNotIn("core_pce_yoy", hl)

        # Trade prices + GDP components
        self.assertIn("export_price_yoy", by_id)
        self.assertIn("import_price_yoy", by_id)
        self.assertTrue(by_id["gdp"].get("components"))
        self.assertGreaterEqual(len(by_id["gdp"]["components"]), 3)

    def test_officials_central_bank_and_finance(self):
        usa = resolve_country(self.doc, "USA")
        assert usa is not None
        off = usa.get("officials") or {}
        self.assertEqual(off["central_bank"]["name_en"], "Kevin Warsh")
        self.assertEqual(off["central_bank"]["appointed"], "2026-05-22")
        self.assertEqual(off["finance"]["name_en"], "Scott Bessent")
        self.assertEqual(off["finance"]["appointed"], "2025-01-28")

        kor = resolve_country(self.doc, "KOR")
        assert kor is not None
        koff = kor.get("officials") or {}
        self.assertEqual(koff["central_bank"]["name_en"], "Hyun Song Shin")
        self.assertEqual(koff["central_bank"]["appointed"], "2026-04-21")
        self.assertEqual(koff["finance"]["name_en"], "Koo Yoon-cheol")
        self.assertEqual(koff["finance"]["appointed"], "2026-01-02")
        self.assertIn("재정경제부", koff["finance"]["institution_ko"])
        self.assertIn("korea_rule_ko", koff)

        chn = resolve_country(self.doc, "CHN")
        assert chn is not None
        coff = chn.get("officials") or {}
        cb_set = coff["central_bank"]["set"]
        self.assertEqual(len(cb_set), 2)
        self.assertEqual(cb_set[0]["title_ko"], "당위서기")
        self.assertEqual(cb_set[0]["appointed"], "2023-07-01")
        self.assertEqual(cb_set[1]["title_ko"], "행장")
        self.assertEqual(cb_set[1]["appointed"], "2023-07-25")
        fin_set = coff["finance"]["set"]
        self.assertEqual(fin_set[0]["title_ko"], "당조서기")
        self.assertEqual(fin_set[0]["appointed"], "2023-09-28")
        self.assertEqual(fin_set[1]["title_ko"], "부장")
        self.assertEqual(fin_set[1]["appointed"], "2023-10-24")

        from macro_monitor.engine import _official_has_name  # noqa: WPS433

        for pack in self.doc["countries"]:
            o = pack.get("officials")
            self.assertIsNotNone(o, pack["iso3"])
            assert o is not None
            self.assertTrue(_official_has_name(o["central_bank"]), pack["iso3"])
            self.assertTrue(_official_has_name(o["finance"]), pack["iso3"])

    def test_electricity_generation_energy_mix(self):
        usa = resolve_country(self.doc, "USA")
        assert usa is not None
        by_id = {i["id"]: i for i in usa["indicators"]}
        self.assertIn("electricity_generation", by_id)
        elec = by_id["electricity_generation"]
        self.assertEqual(elec["category"], "growth")
        self.assertGreater(elec["value"], 1000)
        self.assertIn("TWh", elec["display"])
        self.assertEqual(elec.get("ui", {}).get("click_view"), "energy_mix")
        mix = elec.get("energy_mix") or {}
        self.assertGreaterEqual(len(mix.get("series") or []), 4)
        self.assertAlmostEqual(
            sum(s["value"] for s in mix["series"]),
            100.0,
            delta=2.0,
        )
        chip_ids = {c["id"] for c in usa["categories"]["growth"]}
        self.assertIn("electricity_generation", chip_ids)
        for pack in self.doc["countries"]:
            ids = {i["id"] for i in pack["indicators"]}
            self.assertIn("electricity_generation", ids, pack["iso3"])

    def test_history_windows(self):
        usa = resolve_country(self.doc, "US")
        assert usa is not None
        bond = next(i for i in usa["indicators"] if i["id"] == "bond_10y")
        self.assertIn("5y", bond["history"])
        self.assertIn("10y", bond["history"])
        self.assertEqual(len(bond["history"]["5y"]["values"]), 60)
        self.assertEqual(len(bond["history"]["10y"]["values"]), 120)

    def test_limitations_present(self):
        self.assertGreaterEqual(len(self.doc["limitations"]["items"]), 3)

    def test_provenance_contract_is_explicit_and_propagated_to_chips(self):
        """A fixture value must never arrive at the UI without its data state."""
        allowed = {
            "live",
            "live_latest",
            "official_snapshot",
            "delayed_official",
            "demo",
            "unknown",
        }
        self.assertIn("demo", self.doc["data_status_legend"])
        for pack in self.doc["countries"]:
            self.assertTrue(pack.get("data_status_summary"), pack["iso3"])
            by_id = {i["id"]: i for i in pack["indicators"]}
            for ind in by_id.values():
                self.assertIn(ind.get("data_status"), allowed, ind["id"])
                self.assertIn("observed_at", ind, ind["id"])
                self.assertIn("retrieved_at", ind, ind["id"])
            for chips in pack["categories"].values():
                for chip in chips:
                    ind = by_id[chip["id"]]
                    self.assertEqual(chip["data_status"], ind["data_status"])
                    self.assertEqual(chip["observed_at"], ind["observed_at"])

        usa = resolve_country(self.doc, "USA")
        assert usa is not None
        cpi = next(i for i in usa["indicators"] if i["id"] == "cpi_yoy")
        self.assertEqual(cpi["data_status"], "demo")
        self.assertIsNone(cpi["observed_at"])
        self.assertTrue(cpi["snapshot_asof"])
        qra = next(i for i in usa["indicators"] if i["id"] == "qra_issuance")
        self.assertEqual(qra["data_status"], "official_snapshot")
        self.assertIsNone(qra["observed_at"])
        self.assertIn("current_quarter", qra["qra_details"])
        self.assertIn("next_quarter", qra["qra_details"])
        self.assertEqual(qra["qra_details"]["bill_stance"], "maintain")
        self.assertEqual(qra["qra_details"]["coupon_stance"], "change_bias")

    def test_month_end_builder_never_labels_an_unfinished_month_as_observed(self):
        self.assertEqual(month_ends(date(2026, 8, 12), 2), ["2026-06-30", "2026-07-31"])

    def test_brazil_full_kit(self):
        bra = resolve_country(self.doc, "Brazil")
        self.assertIsNotNone(bra)
        assert bra is not None
        self.assertEqual(bra["kit"], "br_macro_v1")
        self.assertTrue(bra["featured"])
        by_id = {i["id"]: i for i in bra["indicators"]}
        for sid in (
            "primary_fiscal_balance",
            "debt_to_gdp",
            "selic_rate",
            "sovereign_cds_5y",
            "sovereign_ratings",
            "usdbrl",
            "iron_ore",
            "soybeans",
            "crude_oil",
            "ibovespa",
            "ibc_br",
            "ipca",
            "ipca_15",
        ):
            self.assertIn(sid, by_id)
        self.assertEqual(by_id["selic_rate"]["display"], "13.25%")
        self.assertEqual(by_id["usdbrl"]["display"], "5.550")
        self.assertEqual(len(bra["limitations"]["items"]), 3)

    def test_vietnam_full_kit(self):
        vnm = resolve_country(self.doc, "Vietnam")
        self.assertIsNotNone(vnm)
        assert vnm is not None
        self.assertEqual(vnm["kit"], "vn_macro_v1")
        self.assertTrue(vnm["featured"])
        by_id = {i["id"]: i for i in vnm["indicators"]}
        for sid in (
            "usdvnd",
            "fx_reserves",
            "fdi_registered",
            "fdi_disbursed",
            "vnindex",
            "credit_growth_quota",
            "sbv_refinancing",
            "export_yoy_vn",
            "pmi_mfg_vn",
            "ip_yoy",
        ):
            self.assertIn(sid, by_id)
        self.assertEqual(by_id["usdvnd"]["display"], "25,450")
        self.assertEqual(by_id["sbv_refinancing"]["display"], "4.50%")
        self.assertEqual(by_id["credit_growth_quota"]["display"], "15.0%")
        self.assertEqual(len(vnm["limitations"]["items"]), 3)

    def test_kazakhstan_full_kit(self):
        kaz = resolve_country(self.doc, "Kazakhstan")
        self.assertIsNotNone(kaz)
        assert kaz is not None
        self.assertEqual(kaz["kit"], "kz_macro_v1")
        self.assertTrue(kaz["featured"])
        by_id = {i["id"]: i for i in kaz["indicators"]}
        for sid in (
            "nfrk_assets",
            "usdkzt",
            "rubkzt",
            "crude_oil",
            "cpc_blend",
            "uranium",
            "nbk_base_rate",
            "kase_index",
            "mining_ip_yoy",
            "mfg_ip_yoy",
        ):
            self.assertIn(sid, by_id)
        self.assertEqual(by_id["nbk_base_rate"]["display"], "14.25%")
        self.assertEqual(by_id["usdkzt"]["display"], "485")
        self.assertEqual(by_id["nfrk_assets"]["display"], "+62B")
        self.assertEqual(len(kaz["limitations"]["items"]), 3)

    def test_taiwan_full_kit(self):
        twn = resolve_country(self.doc, "Taiwan")
        self.assertIsNotNone(twn)
        assert twn is not None
        self.assertEqual(twn["kit"], "tw_macro_v1")
        self.assertTrue(twn["featured"])
        by_id = {i["id"]: i for i in twn["indicators"]}
        for sid in (
            "usdtwd",
            "life_fx_assets",
            "hedge_ratio",
            "excess_savings",
            "cbc_discount",
            "taiex",
            "export_orders_yoy",
            "fii_flow_tw",
            "core_cpi_yoy",
        ):
            self.assertIn(sid, by_id)
        self.assertEqual(by_id["cbc_discount"]["display"], "2.00%")
        self.assertEqual(by_id["hedge_ratio"]["display"], "55.0%")
        self.assertEqual(len(twn["limitations"]["items"]), 4)

    def test_korea_full_kit(self):
        kor = resolve_country(self.doc, "한국")
        self.assertIsNotNone(kor)
        assert kor is not None
        self.assertEqual(kor["kit"], "kr_macro_v1")
        self.assertTrue(kor["featured"])
        by_id = {i["id"]: i for i in kor["indicators"]}
        for sid in (
            "semi_export_yoy",
            "export_yoy_kr",
            "usdkrw",
            "bok_base_rate",
            "household_credit",
            "pf_delinquency",
            "us_kr_rate_gap",
            "kospi",
            "vkospi",
            "current_account",
            "us_fx_watch",
        ):
            self.assertIn(sid, by_id)
        self.assertNotIn("bok_inf_exp", by_id)
        self.assertEqual(by_id["bok_base_rate"]["display"], "2.50%")
        self.assertEqual(by_id["kospi"]["display"], "6,250")
        self.assertEqual(by_id["us_fx_watch"]["display"], "관찰대상")
        growth_ids = [c["id"] for c in kor["categories"]["growth"]]
        self.assertLess(growth_ids.index("export_yoy_kr"), growth_ids.index("semi_export_yoy"))
        self.assertEqual(len(kor["limitations"]["items"]), 3)

    def test_canada_full_kit(self):
        can = resolve_country(self.doc, "Canada")
        self.assertIsNotNone(can)
        assert can is not None
        self.assertEqual(can["kit"], "ca_macro_v1")
        self.assertTrue(can["featured"])
        by_id = {i["id"]: i for i in can["indicators"]}
        for sid in (
            "hh_debt_income",
            "boc_overnight",
            "usdcad",
            "wcs_oil",
            "wcs_wti_spread",
            "teranet_hpi",
            "gdp_per_capita_yoy",
            "cpi_trim",
            "cpi_median",
        ):
            self.assertIn(sid, by_id)
        self.assertEqual(by_id["boc_overnight"]["display"], "2.75%")
        self.assertEqual(by_id["hh_debt_income"]["display"], "175%")
        self.assertEqual(len(can["limitations"]["items"]), 3)

    def test_australia_full_kit(self):
        aus = resolve_country(self.doc, "Australia")
        self.assertIsNotNone(aus)
        assert aus is not None
        self.assertEqual(aus["kit"], "au_macro_v1")
        self.assertTrue(aus["featured"])
        by_id = {i["id"]: i for i in aus["indicators"]}
        for sid in (
            "iron_ore",
            "coking_coal",
            "hh_debt_income",
            "rba_cash_rate",
            "audusd",
            "corelogic_hpi",
            "building_approvals",
            "gdp_per_capita_yoy",
            "trimmed_mean_cpi",
            "monthly_cpi",
        ):
            self.assertIn(sid, by_id)
        self.assertEqual(by_id["rba_cash_rate"]["display"], "3.85%")
        self.assertEqual(by_id["hh_debt_income"]["display"], "185%")
        self.assertEqual(len(aus["limitations"]["items"]), 3)

    def test_switzerland_full_kit(self):
        che = resolve_country(self.doc, "Switzerland")
        self.assertIsNotNone(che)
        assert che is not None
        self.assertEqual(che["kit"], "ch_macro_v1")
        self.assertTrue(che["featured"])
        by_id = {i["id"]: i for i in che["indicators"]}
        for sid in (
            "eurchf",
            "usdchf",
            "sight_deposits",
            "snb_total_assets",
            "snb_policy_rate",
            "ch_bund_10y_spread",
            "smi",
            "kof_barometer",
            "procure_pmi",
        ):
            self.assertIn(sid, by_id)
        self.assertEqual(by_id["snb_policy_rate"]["display"], "1.00%")
        self.assertEqual(by_id["eurchf"]["display"], "0.940")
        self.assertEqual(len(che["limitations"]["items"]), 3)

    def test_japan_full_kit(self):
        jpn = resolve_country(self.doc, "Japan")
        self.assertIsNotNone(jpn)
        assert jpn is not None
        self.assertEqual(jpn["kit"], "jp_macro_v1")
        self.assertTrue(jpn["featured"])
        self.assertEqual(
            jpn["active_categories"],
            ["liquidity", "rates", "fx", "equity", "growth", "inflation"],
        )
        by_id = {i["id"]: i for i in jpn["indicators"]}
        self.assertIn("boj_etf_holdings", by_id)
        self.assertEqual(by_id["boj_etf_holdings"]["chart_type"], "bar")
        self.assertTrue((by_id["boj_etf"].get("ui") or {}).get("chip") is False)
        self.assertIn("boj_jgb_ops", by_id)
        self.assertEqual(by_id["boj_jgb_ops"]["chart_type"], "bar")
        self.assertGreaterEqual(len(by_id["boj_jgb_ops"]["components"]), 4)
        self.assertIn("boj_jgb_share", by_id)
        self.assertNotIn("boj_current_account", by_id)
        self.assertNotIn("m2_yoy", by_id)
        self.assertNotIn("eurjpy", by_id)
        self.assertNotIn("yen_reer", by_id)
        self.assertIn("yen_imm_net", by_id)
        self.assertIn("fx_intervention", by_id)
        self.assertIn("shunto_wage", by_id)
        self.assertIn("core_core_cpi", by_id)
        # Growth: GDP first, PMI surveys last
        growth_ids = [c["id"] for c in jpn["categories"]["growth"]]
        self.assertEqual(growth_ids[0], "gdp")
        self.assertTrue(growth_ids.index("ism_mfg") > growth_ids.index("shunto_wage"))
        self.assertAlmostEqual(
            by_id["spread_30y10y"]["value"],
            (by_id["bond_30y"]["value"] - by_id["bond_10y"]["value"]) * 100.0,
            places=2,
        )
        self.assertEqual(len(jpn["limitations"]["items"]), 3)
        self.assertEqual(by_id["bond_10y"]["display"], "1.15%")

    def test_rates_order_and_spreads(self):
        """Policy → MM → curve 3M→10Y→30Y → curve spreads → credit; cull weak CDS."""
        usa = resolve_country(self.doc, "USA")
        assert usa is not None
        ids = [c["id"] for c in usa["categories"]["rates"]]
        self.assertEqual(
            ids,
            [
                "effr",
                "fedwatch",
                "sofr",
                "bond_3m",
                "bond_2y",
                "bond_10y",
                "tips_10y",
                "spread_10y3m",
                "spread_10y2y",
                "hy_oas",
                "sovereign_ratings",
            ],
        )
        self.assertNotIn("sovereign_cds_5y", ids)

        jpn = resolve_country(self.doc, "Japan")
        assert jpn is not None
        jids = [c["id"] for c in jpn["categories"]["rates"]]
        self.assertEqual(jids[0], "call_rate")
        self.assertLess(jids.index("bond_2y"), jids.index("bond_10y"))
        self.assertLess(jids.index("bond_10y"), jids.index("bond_30y"))
        self.assertLess(jids.index("spread_10y2y"), jids.index("spread_30y10y"))
        self.assertNotIn("sovereign_cds_5y", jids)

        kor = resolve_country(self.doc, "Korea")
        assert kor is not None
        kids = [c["id"] for c in kor["categories"]["rates"]]
        self.assertEqual(kids[0], "bok_base_rate")
        self.assertEqual(kids[1], "us_kr_rate_gap")
        self.assertLess(kids.index("ktb_3y"), kids.index("bond_10y"))
        self.assertLess(kids.index("corp_spread_aa"), kids.index("cp_spread"))
        self.assertNotIn("sovereign_cds_5y", kids)

        emu = resolve_country(self.doc, "Eurozone")
        assert emu is not None
        eids = [c["id"] for c in emu["categories"]["rates"]]
        self.assertLess(eids.index("deposit_facility"), eids.index("mro_rate"))
        self.assertLess(eids.index("bund_10y"), eids.index("btp_10y"))
        self.assertLess(eids.index("btp_10y"), eids.index("btp_bund_spread"))
        self.assertIn("sovereign_cds_5y", eids)

    def test_growth_chip_order_surveys_last(self):
        usa = resolve_country(self.doc, "USA")
        assert usa is not None
        ids = [c["id"] for c in usa["categories"]["growth"]]
        self.assertEqual(ids[0], "gdpnow")
        self.assertLess(ids.index("nfp"), ids.index("ism_mfg"))
        self.assertEqual(ids[-2:], ["ism_mfg", "ism_services"])

    def test_uk_full_kit(self):
        gbr = resolve_country(self.doc, "United Kingdom")
        self.assertIsNotNone(gbr)
        assert gbr is not None
        self.assertEqual(gbr["kit"], "uk_macro_v1")
        self.assertTrue(gbr["featured"])
        by_id = {i["id"]: i for i in gbr["indicators"]}
        for sid in (
            "bond_30y",
            "gilt_bund_10y",
            "sovereign_cds_5y",
            "rpi_yoy",
            "apf_balance",
            "m4_vs_2019",
            "sonia",
            "ftse250",
            "awe_ex_bonus",
            "services_cpi",
        ):
            self.assertIn(sid, by_id)
        self.assertEqual(len(gbr["limitations"]["items"]), 3)
        self.assertEqual(by_id["bond_30y"]["display"], "5.05%")
        rids = [c["id"] for c in gbr["categories"]["rates"]]
        self.assertLess(rids.index("bond_2y"), rids.index("bond_10y"))
        self.assertLess(rids.index("bond_10y"), rids.index("bond_30y"))
        self.assertLess(rids.index("spread_10y2y"), rids.index("gilt_bund_10y"))

    def test_china_full_kit(self):
        chn = resolve_country(self.doc, "China")
        self.assertIsNotNone(chn)
        assert chn is not None
        self.assertEqual(chn["kit"], "cn_macro_v1")
        self.assertTrue(chn["featured"])
        by_id = {i["id"]: i for i in chn["indicators"]}
        for sid in (
            "tsf_yoy",
            "rrr",
            "m1_m2_spread",
            "lpr_5y",
            "usdcnh",
            "ppi_yoy",
            "lgfv_spread",
            "li_keqiang",
        ):
            self.assertIn(sid, by_id)
        self.assertAlmostEqual(
            by_id["m1_m2_spread"]["value"],
            by_id["m1_yoy"]["value"] - by_id["m2_yoy"]["value"],
            places=4,
        )
        self.assertEqual(len(chn["limitations"]["items"]), 4)
        self.assertEqual(by_id["ppi_yoy"]["display"], "-2.5%")
        # A주 → H주 → Connect flows (B주 칩 없음)
        eids = [c["id"] for c in chn["categories"]["equity"]]
        self.assertEqual(
            eids,
            ["sse_composite", "csi300", "hscei", "northbound_flow", "southbound_flow"],
        )
        self.assertIn("A주", by_id["csi300"]["label_ko"])
        self.assertIn("H주", by_id["hscei"]["label_ko"])
        self.assertNotIn("b_share", by_id)

    def test_eurozone_full_kit(self):
        emu = resolve_country(self.doc, "Germany")
        self.assertIsNotNone(emu)
        assert emu is not None
        self.assertEqual(emu["iso3"], "EMU")
        self.assertEqual(emu["kit"], "ez_macro_v1")
        self.assertTrue(emu["featured"])
        by_id = {i["id"]: i for i in emu["indicators"]}
        for sid in (
            "btp_bund_spread",
            "deposit_facility",
            "app_balance",
            "pepp_balance",
            "eurusd",
            "hcob_pmi_mfg",
            "hicp_yoy",
            "tpi_active",
        ):
            self.assertIn(sid, by_id)
        self.assertAlmostEqual(
            by_id["btp_bund_spread"]["value"],
            (by_id["btp_10y"]["value"] - by_id["bund_10y"]["value"]) * 100.0,
            places=2,
        )
        self.assertEqual(by_id["tpi_active"]["display"], "미가동")
        self.assertEqual(len(emu["limitations"]["items"]), 3)

    def test_russia_full_kit(self):
        rus = resolve_country(self.doc, "Russia")
        self.assertIsNotNone(rus)
        assert rus is not None
        self.assertEqual(rus["kit"], "ru_macro_v1")
        self.assertTrue(rus["featured"])
        by_id = {i["id"]: i for i in rus["indicators"]}
        for sid in (
            "nwf_liquid",
            "cbr_key_rate",
            "ofz_auction_cover",
            "cnyrub",
            "urals_brent_spread",
            "rtsi",
            "labor_shortage",
        ):
            self.assertIn(sid, by_id)
        self.assertNotIn("household_inf_exp", by_id)
        self.assertEqual(by_id["cbr_key_rate"]["display"], "21.00%")
        self.assertEqual(len(rus["limitations"]["items"]), 3)

    def test_hongkong_full_kit(self):
        hkg = resolve_country(self.doc, "Hong Kong")
        self.assertIsNotNone(hkg)
        assert hkg is not None
        self.assertEqual(hkg["kit"], "hk_macro_v1")
        self.assertTrue(hkg["featured"])
        by_id = {i["id"]: i for i in hkg["indicators"]}
        for sid in (
            "aggregate_balance",
            "usdhkd",
            "hibor_3m",
            "hibor_sofr_spread",
            "hsi",
            "hscei",
            "ccl_index",
            "retail_sales_yoy",
        ):
            self.assertIn(sid, by_id)
        self.assertEqual(by_id["usdhkd"]["display"], "7.8120")
        self.assertEqual(len(hkg["limitations"]["items"]), 3)
        # LERS weak-side proximity check (demo level inside band)
        self.assertGreater(by_id["usdhkd"]["value"], 7.75)
        self.assertLess(by_id["usdhkd"]["value"], 7.85)

    def test_singapore_full_kit(self):
        sgp = resolve_country(self.doc, "Singapore")
        self.assertIsNotNone(sgp)
        assert sgp is not None
        self.assertEqual(sgp["kit"], "sg_macro_v1")
        self.assertTrue(sgp["featured"])
        by_id = {i["id"]: i for i in sgp["indicators"]}
        for sid in (
            "sgd_neer",
            "neer_slope",
            "nodx_yoy",
            "sora",
            "mas_core_infl",
            "sti",
            "sreit_index",
            "sofr_sora_spread",
        ):
            self.assertIn(sid, by_id)
        self.assertEqual(by_id["sora"]["display"], "3.10%")
        self.assertEqual(len(sgp["limitations"]["items"]), 3)

    def test_south_africa_full_kit(self):
        zaf = resolve_country(self.doc, "South Africa")
        self.assertIsNotNone(zaf)
        assert zaf is not None
        self.assertEqual(zaf["kit"], "za_macro_v1")
        self.assertTrue(zaf["featured"])
        by_id = {i["id"]: i for i in zaf["indicators"]}
        for sid in (
            "load_shedding_hours",
            "debt_to_gdp",
            "sarb_repo",
            "usdzar",
            "sagb_10y",
            "sovereign_cds_5y",
            "sovereign_ratings",
            "gold_price",
            "jse_top40",
        ):
            self.assertIn(sid, by_id)
        self.assertEqual(by_id["sarb_repo"]["display"], "7.50%")
        self.assertEqual(len(zaf["limitations"]["items"]), 3)

    def test_israel_full_kit(self):
        isr = resolve_country(self.doc, "Israel")
        self.assertIsNotNone(isr)
        assert isr is not None
        self.assertEqual(isr["kit"], "il_macro_v1")
        self.assertTrue(isr["featured"])
        by_id = {i["id"]: i for i in isr["indicators"]}
        for sid in (
            "boi_rate",
            "usdils",
            "sovereign_cds_5y",
            "ta125",
            "high_tech_export_yoy",
            "fiscal_deficit_gdp",
            "cpi_yoy",
        ):
            self.assertIn(sid, by_id)
        self.assertEqual(len(isr["limitations"]["items"]), 4)
        rids = [c["id"] for c in isr["categories"]["rates"]]
        self.assertEqual(rids[0], "boi_rate")
        self.assertIn("sovereign_cds_5y", rids)
        self.assertLess(rids.index("bond_2y"), rids.index("bond_10y"))
        gids = [c["id"] for c in isr["categories"]["growth"]]
        self.assertIn("high_tech_export_yoy", gids)
        self.assertLess(gids.index("gdp"), gids.index("high_tech_export_yoy"))
        self.assertLess(gids.index("high_tech_export_yoy"), gids.index("ism_mfg"))
        hl = [h["id"] for h in isr["headlines"]]
        self.assertEqual(hl[0], "sovereign_cds_5y")

    def test_india_full_kit(self):
        ind = resolve_country(self.doc, "India")
        self.assertIsNotNone(ind)
        assert ind is not None
        self.assertEqual(ind["kit"], "in_macro_v1")
        self.assertTrue(ind["featured"])
        by_id = {i["id"]: i for i in ind["indicators"]}
        for sid in (
            "cad_gdp",
            "rbi_repo",
            "usdinr",
            "crr",
            "laf_balance",
            "nifty50",
            "fpi_flow",
            "two_wheeler_sales",
            "wpi_yoy",
        ):
            self.assertIn(sid, by_id)
        self.assertEqual(by_id["rbi_repo"]["display"], "6.50%")
        self.assertEqual(len(ind["limitations"]["items"]), 3)

    def test_no_nonfinite_history_values(self):
        """Signed / zero-crossing series must not emit Inf/NaN (breaks JSON.parse)."""
        import math

        bad: list[tuple[str, str, str]] = []
        for c in self.doc["countries"]:
            for ind in c["indicators"]:
                for win, hist in ind.get("history", {}).items():
                    for v in hist.get("values") or []:
                        if isinstance(v, float) and not math.isfinite(v):
                            bad.append((c["iso3"], ind["id"], win))
                            break
                for key in ("value", "change_1m_pct", "change_1y_pct"):
                    v = ind.get(key)
                    if isinstance(v, float) and not math.isfinite(v):
                        bad.append((c["iso3"], ind["id"], key))
        self.assertEqual(bad, [], msg=f"non-finite values: {bad[:20]}")

    def test_json_allow_nan_false_roundtrip(self):
        """Standard JSON — Node/Workers must parse; Python allow_nan=False must succeed."""
        payload = json.dumps(self.doc, allow_nan=False)
        self.assertNotIn("Infinity", payload)
        self.assertNotIn("NaN", payload)
        json.loads(payload)


if __name__ == "__main__":
    unittest.main()
