import sys
import unittest

import importlib.util
if any(importlib.util.find_spec(p) is None for p in ['numpy','pandas','scipy','sklearn','exchange_calendars']):
    raise unittest.SkipTest('install requirements-us-kr-preopen.txt for optional direction tests')

from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research_mixed_option_activity import aggregate


class MixedActivityTests(unittest.TestCase):
    def row(self, side='call', **kw):
        return dict({'session':'regular','quality':'observed','expiry_or_contract_month':'202610',
                     'option_type':side,'strike':100,'collected_at':'2026-10-01T10:00:00Z',
                     'volume_contracts':10,'trading_value_krw':100,'open_interest_contracts':20,
                     'implied_volatility':25},**kw)

    def test_night_and_duplicate_not_double_counted(self):
        r=self.row();out=aggregate([r,r,self.row('put'),self.row(session='night',volume_contracts=10000)])
        self.assertEqual(out['call_volume_contracts'],10)

    def test_missing_volume_not_zero(self):
        out=aggregate([self.row(volume_contracts=None),self.row('put')])
        self.assertEqual(out['status'],'missing')

    def test_multiple_expiries_never_merged(self):
        out=aggregate([self.row(),self.row('put'),self.row(expiry_or_contract_month='202611')])
        self.assertEqual(out['status'],'missing')

    def test_same_timestamp_conflicts_rejected(self):
        out=aggregate([self.row(),self.row(volume_contracts=999),self.row('put')])
        self.assertEqual(out['reason'],'conflicting_duplicate')

    def test_zero_volume_is_observation(self):
        out=aggregate([self.row(volume_contracts=0),self.row('put')])
        self.assertEqual(out['call_volume_contracts'],0)
        self.assertEqual(out['status'],'observed_subset')


if __name__=='__main__':unittest.main()
