import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_monitor import cb_balance as cb  # noqa: E402
import wire_cb_balance_sheets as wcb  # noqa: E402
import wire_kr_money_debt as wkr  # noqa: E402


class Block(unittest.TestCase):
    def setUp(self):
        d = ["2026-01-31", "2026-02-28", "2026-03-31"]
        self.total = list(zip(d, [10.0, 11.0, 12.0]))
        self.series = {"a": list(zip(d, [6.0, 6.0, 7.0])), "l": list(zip(d, [4.0, 5.0, 5.0]))}

    def build(self, **kw):
        return cb.block(total=self.total, assets=[{"id": "a", "label_ko": "A", "color": "#000"}],
                        liabilities=[{"id": "l", "label_ko": "L", "color": "#000"}], series=self.series,
                        asset_residual={"id": "ra", "label_ko": "RA", "color": "#111"},
                        liability_residual={"id": "rl", "label_ko": "RL", "color": "#111"},
                        since="2026-01-01", meta={"unit_suffix": "조"}, **kw)

    def test_residual_closes_each_side(self):
        bs = self.build()
        self.assertEqual(cb.latest_check(bs), [])
        assets = next(s for s in bs["sides"] if s["id"] == "assets")
        self.assertEqual(assets["layers"][-1]["values"], [4.0, 5.0, 5.0])

    def test_missing_layer_gets_no_residual(self):
        self.series["a"] = self.series["a"][:2]
        bs = self.build()
        assets = next(s for s in bs["sides"] if s["id"] == "assets")
        self.assertIsNone(assets["layers"][-1]["values"][-1])
        self.assertTrue(cb.latest_check(bs))

    def test_thinning_keeps_last(self):
        self.assertEqual(cb.thin(["a", "b", "c", "d"], 2), [0, 2, 3])
        bs = self.build(step=2)
        self.assertEqual(bs["dates"], ["2026-01-31", "2026-03-31"])


class Pboc(unittest.TestCase):
    HTML = ("<table><tr><td>项目 Item</td><td>2026.08</td><td>2026.09</td></tr>"
            "<tr><td>外汇 Foreign Exchange</td><td>217247.55</td><td>217236.41</td></tr>"
            "<tr><td>总资产 Total Assets</td><td>498567.28</td><td>505003.29</td></tr>"
            "<tr><td>其他存款性公司存款 Deposits</td><td>223278.85</td><td></td></tr></table>")

    def test_gbk_and_units(self):
        out = wcb.parse_pbc_table(self.HTML.encode("gbk"))
        self.assertEqual(out["total"][-1][0], "2026-09-30")
        self.assertAlmostEqual(out["total"][-1][1], 50.500329)
        self.assertEqual(len(out["reserves"]), 1)              # an empty cell is skipped

    def test_utf8(self):
        self.assertIn("fx", wcb.parse_pbc_table(self.HTML.encode("utf-8")))


class Korea(unittest.TestCase):
    def test_money_stack_bands_add_to_l(self):
        d = "2026-08-31"
        st = wkr.money_stack([(d, 1.0)], [(d, 3.0)], [(d, 5.0)], [(d, 8.0)])
        bands = [l["values"][0] for l in st["sides"][0]["layers"]]
        self.assertEqual(bands, [1.0, 2.0, 2.0, 3.0])
        self.assertEqual(sum(bands), st["total"]["values"][0])

    def test_benchmark_gap(self):
        months = [f"2019-{m:02d}-01" for m in range(1, 13)] + [f"2020-{m:02d}-01" for m in range(1, 13)]
        kr = [(d, 100.0 * (1.01 ** i)) for i, d in enumerate(months)]
        us = [(d, 100.0) for d in months]
        b = wkr.benchmark(kr, us, base="2019-12-01", since="2019-01-01")
        cum = b["modes"]["cum"]
        self.assertAlmostEqual(cum["gap"][-1], cum["kr"][-1] - cum["us"][-1], places=2)
        self.assertEqual(cum["us"][-1], 0.0)

    def test_enara_table(self):
        html = ("<table><tr><th>2024</th><th>2025</th><th>2026</th></tr>"
                "<tr><td>국가채무(1+2)</td><td>1,175.0</td><td>1,305.2</td><td>-</td></tr>"
                "<tr><td>부채</td><td>합계</td><td>741.5</td><td>768.6</td><td>-</td></tr>"
                "<tr><td>공기업</td><td>537.3</td><td>550.4</td><td>-</td></tr>"
                "<tr><td>준정부기관</td><td>170.0</td><td>181.3</td><td>-</td></tr>"
                "<tr><td>기타공공기관</td><td>34.2</td><td>37.0</td><td>-</td></tr></table>")
        years, rows = wkr.parse_enara(html)
        self.assertEqual(years, [2024, 2025, 2026])
        self.assertEqual(wkr.pick(rows, "국가채무(1+2)"), [1175.0, 1305.2, None])
        self.assertEqual([r["value"] for r in wkr.debt_breakdown(rows, 1)], [550.4, 181.3, 37.0])


if __name__ == "__main__":
    unittest.main()
