"""us_cpi_contrib: weight table parsing, the hierarchy (and its repair), contributions that add up."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_monitor import us_cpi_contrib as uc  # noqa: E402

RI_HTML = """<table>
<tr><th>Item and Group</th><th>CPI-U</th><th>CPI-W</th></tr>
<tr><td>All items</td><td>100.000</td><td>100.000</td></tr>
<tr><td><p class="sub1">Food</p></td><td>40.000</td><td>1</td></tr>
<tr><td><p class="sub2">Bread</p></td><td>30.000</td><td>1</td></tr>
<tr><td><p class="sub2">Milk</p></td><td>10.000</td><td>1</td></tr>
<tr><td><p class="sub1">Fuel</p></td><td>60.000</td><td>1</td></tr>
<tr><td>Special aggregate indexes</td><td></td><td></td></tr>
<tr><td>All items less food</td><td>60.000</td><td>1</td></tr>
</table>"""
ITEMS = "item_code\titem_name\tdisplay_level\tselectable\tsort_sequence\n" \
        "SA0\tAll items\t0\tT\t1\nF\tFood\t0\tT\t2\nB\tBread\t1\tT\t3\nM\tMilk\t1\tT\t4\nE\tFuel\t0\tT\t5\n"


def series(code, values, sa=False):
    months = ["2025-12", "2026-01", "2026-02"]
    return {f"{'CUSR' if sa else 'CUUR'}0000{code}": dict(zip(months, values))}


class Parse(unittest.TestCase):
    def test_weights_stop_at_the_special_aggregates(self):
        rows = uc.parse_relative_importance(RI_HTML)
        self.assertEqual([r["name"] for r in rows], ["All items", "Food", "Bread", "Milk", "Fuel"])
        self.assertEqual(rows[2]["ri"], 30.0)

    def test_catalog_levels(self):
        self.assertEqual(uc.parse_items(ITEMS)["bread"], ["B", 1])

    def test_contact_is_required(self):
        old = os.environ.pop("BLS_CONTACT_EMAIL", None)
        try:
            with self.assertRaises(RuntimeError):
                uc.user_agent()
        finally:
            if old is not None:
                os.environ["BLS_CONTACT_EMAIL"] = old


class Api(unittest.TestCase):
    def test_missing_series_and_months_are_left_out_and_batches_follow_the_key(self):
        import io
        import json
        sent = []

        def opener(req, timeout):
            body = json.loads(req.data)
            sent.append(body)
            series = [{"seriesID": sid, "data": [{"year": "2026", "period": "M01", "value": "101.5"},
                                                 {"year": "2025", "period": "M10", "value": "-"},
                                                 {"year": "2025", "period": "M13", "value": "100"}]}
                      for sid in body["seriesid"] if not sid.startswith("CUSR")]
            return io.BytesIO(json.dumps({"status": "REQUEST_SUCCEEDED",
                                          "Results": {"series": series}}).encode())

        ids = [f"CUUR0000X{i}" for i in range(60)] + ["CUSR0000X0"]
        got = uc.api_data(ids, 2023, 2026, key="k", opener=opener)
        self.assertEqual([len(b["seriesid"]) for b in sent], [50, 11])
        self.assertEqual(sent[0]["registrationkey"], "k")
        self.assertEqual(got["CUUR0000X1"], {"2026-01": 101.5})
        self.assertNotIn("CUSR0000X0", got)
        sent.clear()
        uc.api_data(ids, 2023, 2026, key="", opener=opener)
        self.assertEqual([len(b["seriesid"]) for b in sent], [25, 25, 11])
        self.assertNotIn("registrationkey", sent[0])


class Tree(unittest.TestCase):
    def test_depth_from_the_catalog(self):
        nodes = uc.build_tree(uc.parse_relative_importance(RI_HTML), uc.parse_items(ITEMS))
        self.assertEqual([n["level"] for n in nodes], [0, 1, 2, 2, 1])
        self.assertEqual(uc.tree_gaps(nodes), [])

    def test_a_sibling_put_one_level_too_deep_is_moved_back_by_the_weights(self):
        items = uc.parse_items(ITEMS.replace("E\tFuel\t0", "E\tFuel\t1"))     # catalog says Fuel is under Food
        nodes = uc.build_tree(uc.parse_relative_importance(RI_HTML), items)
        self.assertEqual(nodes[4]["parent"], 0)
        self.assertEqual(uc.tree_gaps(nodes), [])


class Contributions(unittest.TestCase):
    def setUp(self):
        self.nodes = uc.build_tree(uc.parse_relative_importance(RI_HTML), uc.parse_items(ITEMS))
        ri = {2025: self.nodes}
        self.ri = ri
        # Bread +10%, Milk 0, Fuel -5% in January; the all-items index is what those weights imply.
        self.data = {**series("B", [100, 110, 110]), **series("M", [100, 100, 100]), **series("E", [100, 95, 95]),
                     **series("SA0", [100, 100.0, 100.0])}

    def test_parts_add_up_and_parents_are_their_children(self):
        got = uc.contributions(self.nodes, self.ri, self.data, "2026-01", "mom")
        rows = got["by_node"]
        self.assertAlmostEqual(rows[2][1], 3.0)          # 30 x 10%
        self.assertAlmostEqual(rows[4][1], -3.0)         # 60 x -5%
        self.assertAlmostEqual(rows[1][1], 3.0)          # Food = Bread + Milk
        self.assertAlmostEqual(got["sum_pp"], 0.0)

    def test_excluded_subtree_rescales_to_its_own_basket(self):
        got = uc.contributions(self.nodes, self.ri, self.data, "2026-01", "mom", exclude=("Food",))
        self.assertAlmostEqual(got["by_node"][4][1], -5.0)   # Fuel is the whole "core": its own -5%
        self.assertNotIn(2, got["by_node"])

    def test_a_leaf_without_an_index_follows_its_parent(self):
        data = {k: v for k, v in self.data.items() if "0000M" not in k}
        data.update(series("F", [100, 107.5, 107.5]))
        got = uc.contributions(self.nodes, self.ri, data, "2026-01", "mom")
        self.assertAlmostEqual(got["by_node"][3][1], 0.75)  # Milk's 10 x Food's 7.5%
        self.assertIsNone(got["by_node"][3][0])             # but no change of its own to show


if __name__ == "__main__":
    unittest.main()
