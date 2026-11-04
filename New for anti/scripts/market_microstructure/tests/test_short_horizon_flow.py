import copy
import sys
import unittest

import importlib.util
if any(importlib.util.find_spec(p) is None for p in ['numpy','pandas','scipy','sklearn','exchange_calendars']):
    raise unittest.SkipTest('install requirements-us-kr-preopen.txt for optional direction tests')

from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research_short_horizon_flow import components, targets
from option_direction_model import calendar
from research_direction_diagnostics import ReviewedCalendar


class ShortHorizonTests(unittest.TestCase):
    def setUp(self):
        self.row = {'quality':'observed',
                    'foreign':{'buy_krw':100,'sell_krw':60,'net_krw':40},
                    'market_total':{'buy_krw':200,'sell_krw':200}}

    def test_accounting_decomposition(self):
        v=components(self.row)
        self.assertAlmostEqual(v['net_share'],2*v['imbalance']*v['participation'])
        self.assertAlmostEqual(v['participation'],.4)

    def test_invalid_observations_are_missing(self):
        for field,val in [('buy_krw',None),('net_krw',41.1),('sell_krw',-1),('buy_krw',float('nan'))]:
            bad=copy.deepcopy(self.row);bad['foreign'][field]=val
            self.assertIsNone(components(bad))
        self.row['quality']='carried_forward'
        self.assertIsNone(components(self.row))

    def test_no_activity_is_not_zero_imbalance(self):
        self.row['foreign']={k:0 for k in self.row['foreign']}
        self.assertIsNone(components(self.row))

    def test_missing_next_session_never_skipped(self):
        cal=ReviewedCalendar(calendar())
        prices={'2026-10-30':{'open':100,'close':101},
                '2026-11-03':{'open':200,'close':202}}
        t=targets('2026-10-30',prices,cal)
        self.assertIsNone(t['day1_intraday'])
        self.assertIsNone(t['hold2'])
        self.assertAlmostEqual(t['day2_intraday'],.01)


if __name__=='__main__':
    unittest.main()
