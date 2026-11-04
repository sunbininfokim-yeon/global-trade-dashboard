import sys
import unittest

import importlib.util
if any(importlib.util.find_spec(p) is None for p in ['numpy','pandas','scipy','sklearn','exchange_calendars']):
    raise unittest.SkipTest('install requirements-us-kr-preopen.txt for optional direction tests')

from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research_short_horizon_prediction import signal, policy, holm, paired_loss


class PredictionTests(unittest.TestCase):
    def test_probability_direction_and_neutral_boundary(self):
        self.assertEqual([signal(p) for p in (.4,.5,.6)],[-1,0,1])
        self.assertEqual([signal(p,.05) for p in (.449,.45,.5,.55,.551)],[-1,0,0,0,1])
        for p in (-.1,1.1,float('nan')):
            with self.assertRaises(ValueError): signal(p)

    def test_short_pnl_and_neutral_cost(self):
        rows=[{'p':.7,'return':.01},{'p':.3,'return':-.01},{'p':.5,'return':.5}]
        r=policy(rows,0)
        self.assertEqual((r['buy'],r['sell'],r['neutral']),(1,1,1))
        self.assertAlmostEqual(r['cost_scenarios']['10']['mean_per_active_pct'],.9)
        self.assertEqual(r['direction_hit_active'],1.)

    def test_comparison_requires_same_outcomes(self):
        with self.assertRaises(ValueError):
            paired_loss([{'date':'a','target_date':'b','y':1}],
                        [{'date':'a','target_date':'c','y':1}])

    def test_base_rate_probability_can_be_neutralized(self):
        rows=[{'p':.7,'return':.01,'information_state':'recent_base_rate_only'}]
        self.assertEqual(policy(rows,0,True)['neutral'],1)
        self.assertIsNone(policy(rows,0,True)['cost_scenarios']['10']['mean_per_active_pct'])

    def test_multiple_testing_correction(self):
        c={k:{'two_sided_centered_block_p':p} for k,p in [('a',.01),('b',.03),('c',.04)]}
        holm(c)
        self.assertAlmostEqual(c['a']['holm_adjusted_p'],.03)
        self.assertAlmostEqual(c['b']['holm_adjusted_p'],.06)
        self.assertAlmostEqual(c['c']['holm_adjusted_p'],.06)


if __name__=='__main__': unittest.main()
