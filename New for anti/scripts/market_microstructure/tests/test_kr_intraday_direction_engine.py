import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

if any(importlib.util.find_spec(p) is None for p in ('numpy', 'pandas', 'scipy', 'sklearn', 'exchange_calendars')):
    raise unittest.SkipTest('install requirements-us-kr-preopen.txt for intraday research tests')

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kr_intraday_direction_engine as engine


class IntradayDirectionTests(unittest.TestCase):
    target = '2026-11-23'
    as_of = '2026-11-23T07:52:55+09:00'

    def setUp(self):
        self.model = engine.read(engine.DEFAULT_MODEL)
        kr_dates = pd.bdate_range('2026-11-13', self.target)
        prices = pd.DataFrame({'open': 100, 'close': range(100, 100 + len(kr_dates))}, index=kr_dates)
        self.local = {ticker: prices.copy() for ticker in engine.SYMBOLS}
        self.us = pd.DataFrame({key: [.01, .02] for key in engine.US_KEYS},
                               index=pd.to_datetime(['2026-11-19', '2026-11-20']))

    def predict(self):
        with patch.object(engine, 'input_frames', return_value=(self.local, self.us)):
            return engine.predict(None, self.model, self.target, self.as_of)

    def test_two_independent_up_down_probabilities_ignore_target_prices(self):
        baseline = self.predict()
        for ticker, heads in baseline['cards'].items():
            self.assertEqual(set(heads), set(engine.HEADS), ticker)
            self.assertNotAlmostEqual(heads['first15_vs_open']['up'], heads['close_vs_open']['up'])
            for score in heads.values():
                self.assertEqual(score['status'], 'research_only')
                self.assertAlmostEqual(score['up'] + score['down'], 1)
        for prices in self.local.values():
            prices.loc[self.target, ['open', 'close']] = [1000, 2000]
        self.assertEqual(self.predict(), baseline)

    def test_missing_expected_source_is_not_replaced_by_older_data(self):
        self.us = self.us.iloc[:1]
        for heads in self.predict()['cards'].values():
            for score in heads.values():
                self.assertEqual(score, {'status': 'unavailable', 'up': None, 'down': None})

    def test_kr_hole_only_suppresses_affected_asset(self):
        self.local['005930'] = self.local['005930'].drop(index='2026-11-13')
        forecast = self.predict()['cards']
        self.assertEqual(forecast['005930']['first15_vs_open']['status'], 'unavailable')
        self.assertEqual(forecast['KOSPI']['first15_vs_open']['status'], 'research_only')

    def test_rejects_late_and_unclosed_source(self):
        for as_of in ('2026-11-23T08:31:00+09:00', '2026-11-20T14:00:00+09:00'):
            with self.subTest(as_of=as_of), self.assertRaises(ValueError):
                engine.predict(None, self.model, self.target, as_of)

    def test_reviewed_krx_holiday_is_not_predictable(self):
        with self.assertRaisesRegex(ValueError, 'reviewed KRX trading session'):
            engine.preopen_sessions('2026-07-17', pd.Timestamp('2026-07-17T07:00:00+09:00'))
