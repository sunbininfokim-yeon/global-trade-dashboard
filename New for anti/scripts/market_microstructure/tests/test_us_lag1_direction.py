import sys
import unittest

import importlib.util
if any(importlib.util.find_spec(p) is None for p in ['numpy','pandas','scipy','sklearn','exchange_calendars']):
    raise unittest.SkipTest('install requirements-us-kr-preopen.txt for optional direction tests')

from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import exchange_calendars as xc
from research_us_lag1_direction import previous_us_session, us_vector, SYMBOLS


class USLagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cal=xc.get_calendar('XNYS',start='2018-01-01',end='2027-12-31')

    def test_weekend_uses_friday_once(self):
        d,_,_=previous_us_session(self.cal,'2026-11-02')
        self.assertEqual(d,'2026-10-30')

    def test_DST_closing_clock_is_not_fixed_UTC(self):
        _,summer,_=previous_us_session(self.cal,'2026-03-10')
        _,winter,_=previous_us_session(self.cal,'2026-11-03')
        self.assertIn('20:00:00',summer)
        self.assertIn('21:00:00',winter)

    def test_US_holiday_not_synthetic_row(self):
        d,_,_=previous_us_session(self.cal,'2026-07-06')
        self.assertEqual(d,'2026-07-02')

    def data(self):
        return {s:{'2026-03-06':{'close':100},'2026-03-09':{'close':110},
                   '2026-03-10':{'close':999999}} for s in SYMBOLS}

    def test_same_US_calendar_day_future_bar_is_not_used(self):
        data=self.data();v,m=us_vector(data,self.cal,'2026-03-10')
        self.assertEqual(m['US_session'],'2026-03-09')
        self.assertAlmostEqual(v[0][0],.1)
        data['QQQ']['2026-03-10']['close']=1
        self.assertEqual(v,us_vector(data,self.cal,'2026-03-10')[0])

    def test_missing_expected_session_is_not_stale_fallback(self):
        data=self.data();del data['QQQ']['2026-03-09']
        v,meta=us_vector(data,self.cal,'2026-03-10')
        self.assertIsNone(v)
        self.assertEqual(meta['reason'],'missing_expected_US_session')


if __name__=='__main__':unittest.main()
