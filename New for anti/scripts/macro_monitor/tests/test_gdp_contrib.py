"""gdp_contrib: expenditure contributions to real GDP growth (no network)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from macro_monitor import gdp_contrib as gc  # noqa: E402

Q = ["2026-01-01", "2026-04-01"]


def reader(series):
    return lambda kind, key: series[key]


class Build(unittest.TestCase):
    def test_usa_parts_total_and_residual(self):
        s = {"A191RL1Q225SBEA": list(zip(Q, [2.5, 2.2])), "DPCERY2Q224SBEA": list(zip(Q, [0.49, 2.51])),
             "A006RY2Q224SBEA": list(zip(Q, [1.25, 0.82])), "A822RY2Q224SBEA": list(zip(Q, [0.80, -0.01])),
             "A019RY2Q224SBEA": list(zip(Q, [-0.04, -1.10]))}
        c = gc.build("USA", reader(s))
        self.assertEqual(c["periods"], ["2026Q1", "2026Q2"])
        self.assertEqual([p["values"][-1] for p in c["parts"]], [2.51, 0.82, -0.01, -1.10])
        self.assertEqual(c["latest"], {"period": "2026Q2", "total": 2.2, "sum_parts": 2.22, "residual": -0.02})

    def test_only_quarters_with_every_part(self):
        s = {"A191RL1Q225SBEA": list(zip(Q, [2.5, 2.2])), "DPCERY2Q224SBEA": list(zip(Q, [0.49, 2.51])),
             "A006RY2Q224SBEA": list(zip(Q[:1], [1.25])), "A822RY2Q224SBEA": list(zip(Q, [0.80, -0.01])),
             "A019RY2Q224SBEA": list(zip(Q, [-0.04, -1.10]))}
        self.assertEqual(gc.build("USA", reader(s))["periods"], ["2026Q1"])


class Apply(unittest.TestCase):
    def test_attaches_and_drops_the_fixture_components(self):
        country = {"indicators": [{"id": "gdp", "components": [{"id": "pce", "contrib_pp": 1.6}]}]}
        contrib = {"parts": [], "latest": {}}
        self.assertTrue(gc.apply(country, contrib))
        self.assertNotIn("components", country["indicators"][0])
        self.assertFalse(gc.apply(country, contrib))


class Sides(unittest.TestCase):
    def test_parts_sum_their_signed_terms(self):
        spec = {"basis_ko": "", "source": "", "source_urls": [], "total": ("t",),
                "parts": [("net_exports", "순수출", [(1, ("x",)), (-1, ("m",))])]}
        data = {("t",): list(zip(Q, [0.8, 0.82])), ("x",): list(zip(Q, [0.1, 1.17])), ("m",): list(zip(Q, [1.0, 0.09]))}
        side = gc.build_side(spec, lambda src: data[src])
        self.assertEqual(side["parts"][0]["values"], [-0.9, 1.08])

    def test_contributions_computed_from_levels(self):
        spec = {"basis_ko": "", "source": "", "source_urls": [], "computed_from_levels": True, "total": ("gdp",),
                "parts": [("pce", "소비", [(1, ("c",))])]}
        data = {("gdp",): list(zip(Q, [100.0, 101.0])), ("c",): list(zip(Q, [60.0, 60.5]))}
        side = gc.build_side(spec, lambda src: data[src])
        self.assertEqual(side["total"], [1.0])
        self.assertEqual(side["parts"][0]["values"], [0.5])           # 0.5 / 100 GDP
        self.assertTrue(side["computed"])

    def test_detail_rows_for_the_latest_quarter(self):
        spec = {"basis_ko": "", "source": "", "source_urls": [], "total": ("t",),
                "parts": [("goods", "재화", [(1, ("g",))])],
                "detail": [("53", "부동산", "services", ("d53",)), ("99", "없음", "x", ("missing",))]}
        data = {("t",): list(zip(Q, [1.0, 2.2])), ("g",): list(zip(Q, [0.3, 0.37])), ("d53",): list(zip(Q, [0.1, 0.57]))}
        side = gc.build_side(spec, lambda src: data[src])
        self.assertEqual(side["detail"], [{"id": "53", "label_ko": "부동산", "group": "services", "value": 0.57}])

    def test_apply_both_sides(self):
        country = {"indicators": [{"id": "gdp"}]}
        self.assertTrue(gc.apply(country, {"parts": []}, {"parts": [1]}))
        self.assertEqual(country["indicators"][0]["contrib_industry"], {"parts": [1]})

    def test_keys_never_in_error_messages(self):
        r = gc.Readers(fetch=object(), get=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("https://x/SECRETKEY/y")))
        import os
        os.environ["ECOS_API_KEY"] = "SECRETKEY"
        with self.assertRaises(RuntimeError) as ctx:
            r(("ecos", "200Y125", "10601"))
        self.assertNotIn("SECRETKEY", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
