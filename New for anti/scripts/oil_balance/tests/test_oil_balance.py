from __future__ import annotations

import math
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oil_balance import forecast as fc  # noqa: E402


def months(y0: int, y1: int) -> list[str]:
    return [f"{y}-{m:02d}" for y in range(y0, y1 + 1) for m in range(1, 13)]


def synthetic(seed: int = 3, rho: float = 0.7):
    """Brent generated from the model's own structure with AR(1) residuals."""
    rng = random.Random(seed)
    ms = months(2003, 2027)
    stocks = {m: 2700 + 120 * math.sin(i / 9) + rng.gauss(0, 15) for i, m in enumerate(ms)}
    demand = {m: 46.0 for m in ms}
    spare = {m: 3 + 1.5 * math.cos(i / 13) for i, m in enumerate(ms)}
    dxy = {m: 100 * math.exp(0.08 * math.sin(i / 17)) for i, m in enumerate(ms)}
    X = fc.features(stocks, demand, spare, dxy)
    beta = [8.0, -0.002, -0.05, -0.8]
    r, price = 0.0, {}
    for m in ms:
        if m in X["dev_mb"] and m <= "2026-11":
            r = rho * r + rng.gauss(0, 0.05)
            price[m] = math.exp(fc.log_fv(beta, fc.SPEC, X, m) + r)
    return ms, stocks, spare, dxy, X, price, beta


class Shaping(unittest.TestCase):
    def test_dev5_is_against_the_same_month_five_years_back(self):
        x = {m: 60.0 + (2.0 if m == "2021-03" else 0.0) for m in months(2015, 2021)}
        d = fc.dev5(x)
        self.assertNotIn("2019-03", d)
        self.assertEqual(d["2021-03"], 2.0)
        self.assertEqual(d["2021-04"], 0.0)

    def test_next_month(self):
        self.assertEqual(fc.next_month("2026-11", 2), "2027-01")
        self.assertEqual(fc.next_month("2027-01", -1), "2026-12")

    def test_outside_oecd_is_the_identity_residual(self):
        stocks = {"2026-01": 2800.0, "2026-02": 2800.0 + 0.5 * fc.MONTH_DAYS}
        out = fc.outside_oecd({"2026-02": 105.0}, {"2026-02": 103.0}, stocks)
        self.assertAlmostEqual(out["2026-02"], 1.5)          # 2.0 surplus, 0.5 into OECD tanks


class Estimation(unittest.TestCase):
    def test_fit_recovers_coefficients_and_newey_west_widens_errors(self):
        _, _, _, _, X, price, beta = synthetic()
        c = fc.fit(price, X, fc.SPEC, "2008-01", "2025-12")
        for got, want in zip(c["beta"][1:], beta[1:]):
            self.assertAlmostEqual(got, want, delta=abs(want) * 0.35 + 1e-4)
        plain = fc.ols([math.log(price[m]) for m in c["months"]], [[X[v][m] for v in fc.SPEC] for m in c["months"]], lags=0)
        self.assertGreater(c["se"][1], plain["se"][1])

    def test_ar1_half_life(self):
        _, _, _, _, X, price, _ = synthetic(rho=0.8)
        c = fc.fit(price, X)
        a = fc.ar1(list(c["resid"].values()))
        self.assertAlmostEqual(a["rho"], 0.8, delta=0.1)
        self.assertAlmostEqual(a["half_life"], math.log(0.5) / math.log(a["rho"]))

    def test_stability_flags(self):
        full = {"vars": ["a", "b", "c"], "beta": [0, -1.0, -1.0, -1.0]}
        wins = [{"beta": {"a": -0.9, "b": -1.1, "c": -1.2}}, {"beta": {"a": -1.0, "b": -0.3, "c": 0.4}}]
        self.assertEqual(fc.stability_flags(full, wins), {"a": "stable", "b": "weakening", "c": "flipped"})

    def test_compete_ranks_on_shared_out_of_sample_years(self):
        _, _, _, _, X, price, _ = synthetic()
        rows, common = fc.compete(price, X, list(range(2016, 2026)))
        self.assertEqual(len(rows), 16)
        self.assertTrue(all(str(y) in r["oos"] for r in rows for y in common))
        self.assertEqual(rows, sorted(rows, key=lambda r: r["oos_mae"]))
        self.assertIn("spare", rows[0]["vars"])                # the true structure has spare capacity


class Engine(unittest.TestCase):
    def setUp(self):
        ms, stocks, spare, dxy, X, price, _ = synthetic()
        self.c = fc.fit(price, X)
        self.eng = fc.build_engine(self.c, X, price, stocks, spare, {m: 105.0 for m in ms}, {m: 103.0 for m in ms},
                                   dxy, "2026-11", "2027-12")
        self.inp = {"oecd_mode": "eia", "oecd_build": 0.4, "supply_delta": 0.0, "demand_delta": 0.0, "china_build": 0.7,
                    "other_build": 0.5, "spare_mode": "eia", "spare": 3.0, "dxy_pct": 0.0, "half_life": 3.0}

    def test_premium_decays_by_half_life(self):
        p = fc.project(self.eng, self.inp)
        prem = [math.log(x["price"] / x["fv"]) for x in p]
        self.assertAlmostEqual(prem[2] / self.eng["r0"], 0.5, places=6)   # three months after the anchor

    def test_identity_mode_matches_a_flat_rate(self):
        ident = dict(self.inp, oecd_mode="identity")                     # 105 - 103 - 0.7 - 0.5 = 0.8
        flat = dict(self.inp, oecd_mode="value", oecd_build=0.8)
        for a, b in zip(fc.project(self.eng, ident), fc.project(self.eng, flat)):
            self.assertAlmostEqual(a["price"], b["price"])

    def test_faster_stock_build_lowers_fair_value(self):
        lo = fc.project(self.eng, dict(self.inp, oecd_mode="value", oecd_build=0.0))
        hi = fc.project(self.eng, dict(self.inp, oecd_mode="value", oecd_build=1.5))
        self.assertLess(hi[-1]["fv"], lo[-1]["fv"])

    def test_scenario_window_and_premium(self):
        sc = {"start": 2, "months": 3, "oecd_add": -3.0, "spare_add": -1.0, "premium_pct": 20}
        base, shock = fc.project(self.eng, self.inp), fc.project(self.eng, self.inp, sc)
        self.assertAlmostEqual(base[1]["price"], shock[1]["price"])
        self.assertAlmostEqual(shock[4]["stocks"] - base[4]["stocks"], -3.0 * 3 * fc.MONTH_DAYS)
        self.assertAlmostEqual(shock[-1]["stocks"] - base[-1]["stocks"], -3.0 * 3 * fc.MONTH_DAYS)   # drawn stocks stay drawn
        self.assertGreater(shock[2]["price"], base[2]["price"])

    def test_simulate_quantiles_bracket_the_central_path(self):
        sim = fc.simulate(self.eng, self.inp, [{"id": "base", "prob": 1}], {"oecd_build": 0.3, "dxy_pct": 5}, n=600)
        cen = fc.project(self.eng, self.inp)
        for i in range(len(cen)):
            self.assertLessEqual(sim["p10"][i], sim["p50"][i])
            self.assertLessEqual(sim["p50"][i], sim["p90"][i])
            self.assertLess(abs(math.log(sim["p50"][i] / cen[i]["price"])), 0.12)
        self.assertIn("2027", sim["annual"])
        self.assertIn("2026", sim["annual"])                    # eleven known months + December

    def test_score_log(self):
        e = {"steo": "2026-11-05", "made": "2026-11-25", "anchor_price": 90.0,
             "p10": {"2026-12": 70.0}, "p50": {"2026-12": 80.0}, "p90": {"2026-12": 95.0}, "eia": {"2026-12": 85.0}}
        s = fc.score_log([e], {"2026-12": 84.0}, "2026-12")[0]
        self.assertEqual((s["mae_model"], s["mae_rw"], s["mae_eia"], s["coverage"]), (4.0, 6.0, 1.0, 1.0))
        self.assertEqual(fc.score_log([e], {}, "2026-11")[0]["months"], 0)


if __name__ == "__main__":
    unittest.main()
