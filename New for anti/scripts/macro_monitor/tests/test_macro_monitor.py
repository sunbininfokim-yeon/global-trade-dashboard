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
            "br_cds_5y",
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
        self.assertEqual(by_id["nfrk_assets"]["display"], "62B")
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
            "usdkrw",
            "bok_base_rate",
            "household_credit",
            "pf_delinquency",
            "us_kr_rate_gap",
            "kospi",
            "vkospi",
        ):
            self.assertIn(sid, by_id)
        self.assertEqual(by_id["bok_base_rate"]["display"], "2.50%")
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
        self.assertIn("boj_etf", by_id)
        self.assertIn("boj_jgb_share", by_id)
        self.assertIn("shunto_wage", by_id)
        self.assertIn("core_core_cpi", by_id)
        self.assertAlmostEqual(
            by_id["spread_30y10y"]["value"],
            (by_id["bond_30y"]["value"] - by_id["bond_10y"]["value"]) * 100.0,
            places=2,
        )
        self.assertEqual(len(jpn["limitations"]["items"]), 3)
        self.assertEqual(by_id["bond_10y"]["display"], "1.15%")

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
            "household_inf_exp",
        ):
            self.assertIn(sid, by_id)
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
            "za_cds_5y",
            "gold_price",
            "jse_top40",
        ):
            self.assertIn(sid, by_id)
        self.assertEqual(by_id["sarb_repo"]["display"], "7.50%")
        self.assertEqual(len(zaf["limitations"]["items"]), 3)

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
