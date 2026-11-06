"""kr_cpi_contrib: the hierarchy, the price-reference year, contributions that add up to the published change."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_monitor import kr_cpi_contrib as kc  # noqa: E402

ITEMS = [
    {"ITEM_CODE": "0", "ITEM_NAME": "총지수", "P_ITEM_CODE": None, "CYCLE": "M"},
    {"ITEM_CODE": "A", "ITEM_NAME": "식료품", "P_ITEM_CODE": "0", "CYCLE": "M"},
    {"ITEM_CODE": "A1", "ITEM_NAME": "쌀", "P_ITEM_CODE": "A", "CYCLE": "M"},
    {"ITEM_CODE": "A2", "ITEM_NAME": "사과", "P_ITEM_CODE": "A", "CYCLE": "M"},
    {"ITEM_CODE": "B", "ITEM_NAME": "휘발유", "P_ITEM_CODE": "0", "CYCLE": "M"},
]
W = {"0": 1000.0, "A": 600.0, "A1": 400.0, "A2": 200.0, "B": 400.0}
ANNUAL = {"A1": {"2022": 110.0, "2021": 100.0}, "A2": {"2022": 120.0, "2021": 100.0},
          "B": {"2022": 130.0, "2021": 100.0}}


def total(levels: dict[str, float], ref: str = "2022") -> float:
    """What the published total would be under the Korean formula, price reference `ref`."""
    a0 = 1000.0 / sum(W[c] / ANNUAL[c][ref] for c in ("A1", "A2", "B"))     # the total's annual level
    return a0 * sum(W[c] * levels[c] / ANNUAL[c][ref] for c in levels) / 1000.0


def data() -> tuple[kc.Index, kc.Index]:
    months = {"2025-09": {"A1": 120.0, "A2": 130.0, "B": 140.0},
              "2026-09": {"A1": 126.0, "A2": 117.0, "B": 154.0},
              "2026-10": {"A1": 127.0, "A2": 120.0, "B": 150.0}}
    monthly: kc.Index = {c: {} for c in ("0", "A", "A1", "A2", "B")}
    for m, lv in months.items():
        for c, v in lv.items():
            monthly[c][m] = v
        monthly["0"][m] = total(lv)
        monthly["A"][m] = (W["A1"] * lv["A1"] / 110 + W["A2"] * lv["A2"] / 120) / 600 * 112.0
    annual = {**ANNUAL, "0": {"2022": total({c: ANNUAL[c]["2022"] for c in ANNUAL}),
                             "2021": 100.0}}
    return monthly, annual


class Tree(unittest.TestCase):
    def test_depth_first_with_parents(self):
        nodes = kc.build_nodes(ITEMS, W)
        self.assertEqual([n["code"] for n in nodes], ["0", "A", "A1", "A2", "B"])
        self.assertEqual([n["parent"] for n in nodes], [None, 0, 1, 1, 0])
        self.assertEqual(kc.leaves(nodes), [2, 3, 4])


class Arithmetic(unittest.TestCase):
    def setUp(self):
        self.nodes = kc.build_nodes(ITEMS, W)
        self.monthly, self.annual = data()

    def test_reference_year_is_the_one_that_reproduces_the_total(self):
        ref, miss = kc.reference_year(self.nodes, self.monthly, self.annual, ["2026-09", "2026-10"])
        self.assertEqual(ref, "2022")
        self.assertLess(miss, 1e-9)

    def test_parts_add_up_to_the_published_change(self):
        for lag, month in ((1, "2026-10"), (12, "2026-09")):
            got = kc.contributions(self.nodes, self.monthly, self.annual, "2022", month, lag)
            pub = kc.published(self.monthly["0"], month, lag)
            self.assertAlmostEqual(got["sum_pp"], pub, places=3)
            rows = got["by_node"]
            self.assertAlmostEqual(rows[1][1], rows[2][1] + rows[3][1], places=2)   # parent = its children (rows rounded)
            self.assertAlmostEqual(rows[0][1], got["sum_pp"], places=2)
            self.assertAlmostEqual(sum(rows[k][2] for k in (2, 3, 4)), 100.0, places=1)

    def test_core_basket_is_rescaled_to_its_own_weight(self):
        members = kc.core_members(self.nodes, frozenset({"사과", "휘발유"}))
        self.assertEqual(members, {2})
        got = kc.contributions(self.nodes, self.monthly, self.annual, "2022", "2026-10", 1, members)
        self.assertAlmostEqual(got["sum_pp"], (127 / 126 - 1) * 100, places=3)     # rice alone
        self.assertNotIn(4, got["by_node"])

    def test_a_core_basket_that_no_longer_matches_is_withheld(self):
        members = kc.core_members(self.nodes, frozenset({"휘발유"}))
        ok, why = kc.core_check(self.nodes, members, self.monthly, self.annual, "2022",
                                {"2026-09": 100.0, "2026-10": 100.0}, 600.0, ["2026-10"])
        self.assertFalse(ok)
        self.assertIn("misses", why)

    def test_a_missing_month_gives_nothing_rather_than_a_partial_sum(self):
        del self.monthly["A2"]["2026-10"]
        self.assertIsNone(kc.contributions(self.nodes, self.monthly, self.annual, "2022", "2026-10", 1))


if __name__ == "__main__":
    unittest.main()
