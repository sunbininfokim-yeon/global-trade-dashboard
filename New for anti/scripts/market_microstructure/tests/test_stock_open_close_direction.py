import sys
import unittest

import importlib.util
if any(importlib.util.find_spec(p) is None for p in ['numpy','pandas','scipy','sklearn','exchange_calendars']):
    raise unittest.SkipTest('install requirements-us-kr-preopen.txt for optional direction tests')

from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research_stock_open_close_direction import path_labels


class StockDirectionTests(unittest.TestCase):
    def test_up_start_can_persist_while_intraday_is_down(self):
        r=path_labels(100,110,105)
        self.assertEqual((r['opening_up'],r['closing_up'],r['direction_persists']),(1,1,1))
        self.assertEqual(r['intraday_direction'],'DOWN')
        self.assertEqual(r['opening_extends'],0)

    def test_down_start_can_persist_while_intraday_is_up(self):
        r=path_labels(100,90,95)
        self.assertEqual((r['opening_up'],r['closing_up'],r['direction_persists']),(0,0,1))
        self.assertEqual(r['intraday_direction'],'UP')
        self.assertEqual(r['opening_extends'],0)

    def test_both_reversals(self):
        self.assertEqual(path_labels(100,110,95)['path'],'UP_TO_DOWN')
        self.assertEqual(path_labels(100,90,105)['path'],'DOWN_TO_UP')
        self.assertEqual(path_labels(100,110,95)['direction_persists'],0)

    def test_flat_is_neutral_not_forced_down(self):
        self.assertIsNone(path_labels(100,100,105)['opening_up'])
        self.assertIsNone(path_labels(100,110,100)['closing_up'])
        self.assertIsNone(path_labels(100,110,100)['direction_persists'])
        self.assertEqual(path_labels(100,110,110)['opening_extends'],0)

    def test_initial_direction_extends(self):
        self.assertEqual(path_labels(100,105,110)['opening_extends'],1)
        self.assertEqual(path_labels(100,95,90)['opening_extends'],1)

    def test_invalid_price_fails(self):
        for v in (0,-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):path_labels(100,v,105)


if __name__=='__main__':unittest.main()
