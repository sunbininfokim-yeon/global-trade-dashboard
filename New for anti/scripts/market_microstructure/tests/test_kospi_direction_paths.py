import sys
import unittest

import importlib.util
if any(importlib.util.find_spec(p) is None for p in ['numpy','pandas','scipy','sklearn','exchange_calendars']):
    raise unittest.SkipTest('install requirements-us-kr-preopen.txt for optional direction tests')

from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research_kospi_direction_paths import cash_row_reasons


class KospiCashGateTests(unittest.TestCase):
    def row(self):
        return {'product':'kospi_cash','security_scope':'stock','quality':'observed',
                'date':'2026-10-02','market_total_buy_krw':1e13,'market_total_sell_krw':1e13}

    def test_stock_scoped_market_record_passes(self):
        self.assertEqual(cash_row_reasons(self.row()),[])

    def test_named_stock_dataset_is_not_market_total(self):
        r=self.row();r['product']='ticker_cash'
        self.assertIn('not_market_cash',cash_row_reasons(r))

    def test_missing_stock_scope_is_not_assumed(self):
        r=self.row();del r['security_scope']
        self.assertIn('stock_only_scope_not_explicit',cash_row_reasons(r))

    def test_thousandfold_side_mismatch_rejected(self):
        r=self.row();r['market_total_sell_krw']/=1000
        self.assertIn('market_buy_sell_not_balanced',cash_row_reasons(r))

    def test_missing_values_not_imputed(self):
        r=self.row();r['market_total_buy_krw']=None
        self.assertIn('missing_market_gross',cash_row_reasons(r))


if __name__=='__main__':unittest.main()
