from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from macro_monitor import cpi_items as ci  # noqa: E402

JP_CSV = """類・品目,総合,食料,米類
Group/Item,All items,Food,Rice
類・品目符号(Group/Item code),0001,0002,0004
含類総連番(Serial number),001,002,004
ウエイト(Weight),3543757090,975803165,35742127
ウエイト１万分比(Weight per 10000),10000,2754,101
202508,101.0,102.0,110.0
202509,101.5,102.4,
202609,104.0,105.0,88.0
"""


def _monthly(start_year: int, start_month: int, values: list[float]) -> list[tuple[str, float]]:
    out, y, m = [], start_year, start_month
    for v in values:
        out.append((f"{y:04d}-{m:02d}-01", v))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


TOY = ci.Country("XXX", ("cpi_yoy",), "테스트청", "test:src", ("https://example/",), tuple(
    ci.Item(f"i{n}", f"품목{n}", lambda r: []) for n in range(6)))


class JapanCsv(unittest.TestCase):
    def test_items_by_code_and_blank_cells_skipped(self):
        got = ci.parse_jp_stat_items(JP_CSV, ("0001", "0004", "9999"))
        self.assertEqual(got["0001"][-1], ("2026-09-01", 104.0))
        self.assertEqual([d for d, _ in got["0004"]], ["2025-08-01", "2026-09-01"])
        self.assertEqual(got["9999"], [])


class Rates(unittest.TestCase):
    def test_mom_and_yoy_need_both_ends(self):
        pts = _monthly(2025, 9, [100.0] + [101.0] * 11 + [103.02, 104.05])
        r = ci.rates_from_index(pts)
        self.assertNotIn("2025-09-01", r)                                   # nothing before it
        self.assertAlmostEqual(r["2026-09-01"]["mom"], 2.0)
        self.assertAlmostEqual(r["2026-09-01"]["yoy"], 3.02)
        self.assertAlmostEqual(r["2026-10-01"]["yoy"], (104.05 / 101.0 - 1) * 100)

    def test_published_rates_are_taken_as_they_are(self):
        r = ci.rates_published([("2026-09-01", 0.83)], [("2026-09-01", 5.1), ("2026-08-01", 5.0)])
        self.assertEqual(r["2026-09-01"], {"mom": 0.83, "yoy": 5.1})
        self.assertEqual(r["2026-08-01"], {"yoy": 5.0})


class Movers(unittest.TestCase):
    def stored(self, last_moves: list[float | None]) -> dict:
        out = {}
        for n, mv in enumerate(last_moves):
            base = [100.0] * 13
            if mv is not None:
                base.append(100.0 * (1 + mv / 100))
            out[f"i{n}"] = [[d, v] for d, v in _monthly(2025, 8, base)]
        return out

    def test_ranked_by_own_mom_top_and_bottom_three(self):
        mv = ci.movers(TOY, self.stored([1.0, -2.0, 0.5, 3.0, -0.1, 0.0]))
        self.assertEqual(mv["reference_period"], "2026-09")
        self.assertEqual([r["id"] for r in mv["up"]], ["i3", "i0", "i2"])
        self.assertEqual([r["id"] for r in mv["down"]], ["i1", "i4", "i5"])
        self.assertEqual(mv["basis"], "item_mom_percent_change_unweighted")
        self.assertEqual(mv["items_ranked"], 6)

    def test_a_late_month_with_few_items_does_not_move_the_panel(self):
        st = self.stored([1.0, -2.0, 0.5, 3.0, -0.1, 0.0])
        st["i0"].append(["2026-10-01", 120.0])                             # one early item for October
        self.assertEqual(ci.movers(TOY, st)["reference_period"], "2026-09")

    def test_falls_back_to_the_last_month_most_items_share(self):
        mv = ci.movers(TOY, self.stored([1.0, 2.0, None, None, None, None]))
        self.assertEqual(mv["reference_period"], "2026-08")

    def test_too_few_items_gives_nothing(self):
        st = {k: v for k, v in self.stored([1.0, 2.0, 0, 0, 0, 0]).items() if k in ("i0", "i1")}
        self.assertIsNone(ci.movers(TOY, st))


class CollectAndAttach(unittest.TestCase):
    def test_failed_item_keeps_stored_observations(self):
        def boom(_r):
            raise RuntimeError("down")
        c = ci.Country("XXX", ("cpi_yoy",), "p", "s", ("u",), (
            ci.Item("ok", "ok", lambda r: [("2026-09-01", 1.0)]), ci.Item("bad", "bad", boom)))
        items, errors = ci.collect(c, None, {"bad": [["2026-08-01", 9.0]]})
        self.assertEqual(items["ok"], [["2026-09-01", 1.0]])
        self.assertEqual(items["bad"], [["2026-08-01", 9.0]])
        self.assertEqual(len(errors), 1)

    def test_attach_puts_movers_on_every_target(self):
        orig = dict(ci.COUNTRIES)
        try:
            ci.COUNTRIES.clear()
            ci.COUNTRIES["XXX"] = TOY
            st = Movers().stored([1.0, -2.0, 0.5, 3.0, -0.1, 0.0])
            pack = {"countries": [{"iso3": "XXX", "indicators": [{"id": "cpi_yoy"}, {"id": "gdp"}]}]}
            done = ci.attach(pack, {"countries": {"XXX": {"items": st}}})
            self.assertEqual(done, {"XXX": "2026-09"})
            inds = pack["countries"][0]["indicators"]
            self.assertIn("movers", inds[0])
            self.assertNotIn("movers", inds[1])
        finally:
            ci.COUNTRIES.clear()
            ci.COUNTRIES.update(orig)

    def test_country_lists_are_well_formed(self):
        for c in ci.COUNTRIES.values():
            ids = [i.id for i in c.items]
            self.assertEqual(len(ids), len(set(ids)), c.iso3)
            self.assertGreaterEqual(len(ids), 6, c.iso3)


if __name__ == "__main__":
    unittest.main()
