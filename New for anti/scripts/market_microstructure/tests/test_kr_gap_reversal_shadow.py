import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

if any(importlib.util.find_spec(p) is None for p in ('pandas', 'numpy', 'scipy', 'sklearn', 'exchange_calendars')):
    raise unittest.SkipTest('install requirements-us-kr-preopen.txt')

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kr_gap_reversal_shadow as reversal


class GapReversalShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact = reversal.read(reversal.DEFAULT_MODEL)

    def test_preopen_replay_uses_only_matching_size_forecast(self):
        target = '2026-11-23'
        as_of = target + 'T07:00:00+09:00'
        forecast = {
            'schema': reversal.SIZE_SCHEMA, 'model_id': self.artifact['gap_size_model_id'],
            'target_date': target, 'generated_at': as_of, 'status': 'retrospective_replay',
            'KR_source_date': '2026-11-20', 'US_source_date': '2026-11-20',
            'results': {'KOSPI': {'median_abs_gap': .025}},
        }
        result = reversal.infer(self.artifact, target, as_of, 'preopen', gap=forecast, replay=True)
        self.assertEqual(result['gap_size_band'], 'high')
        self.assertAlmostEqual(result['probability_reversal'] + result['probability_continuation'], 1.)
        for key, value in [('target_date', '2026-11-20'), ('model_id', 'another-size-model'),
                           ('US_source_date', '2026-11-19'), ('generated_at', target + 'T07:01:00+09:00'),
                           ('results', {})]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                reversal.infer(self.artifact, target, as_of, 'preopen', gap={**forecast, key: value}, replay=True)

    def test_first_hour_uses_prior_closes_and_closed_first_bar(self):
        target = '2026-11-24'
        day = pd.Timestamp(target)
        cal = reversal.calendar(day - pd.Timedelta(days=65), day)
        idx = reversal.ReviewedCalendar(cal).sessions[reversal.ReviewedCalendar(cal).sessions < day][-21:]
        daily = pd.DataFrame({'close': 100 + np.sin(np.arange(21))})
        daily.index = idx
        hourly = pd.DataFrame({'open': [98., 100.], 'close': [101., 1.]},
                              index=pd.date_range(target + 'T09:00', periods=2, freq='h', tz=reversal.SEOUL))
        with patch.object(reversal, 'daily_series', return_value=daily) as daily_load, patch.object(
            reversal, 'yahoo_frame', return_value=hourly
        ):
            with self.assertRaisesRegex(ValueError, 'closed'):
                reversal.infer(self.artifact, target, target + 'T09:59:59+09:00', 'first_hour', replay=True)
            result = reversal.infer(self.artifact, target, target + 'T10:00:00+09:00', 'first_hour', replay=True)
        self.assertEqual(daily_load.call_args.args[1], idx[-1])
        self.assertEqual(result['first_hour_close'], 101.)
        self.assertEqual(result['probability_close_up_vs_previous_close'], result['probability_reversal'])
        self.assertAlmostEqual(result['probability_close_up_vs_previous_close']
                               + result['probability_close_down_vs_previous_close'], 1.)

    def test_both_reversal_directions_and_flat_cases(self):
        daily = pd.DataFrame({'open': [102, 98, 102, 98, 100, 98], 'close': [99, 101, 101, 99, 101, 100]})
        labels = reversal.reversal_labels(daily, pd.Series([100] * 6))
        self.assertEqual(labels.head(4).tolist(), [1., 1., 0., 0.])
        self.assertTrue(labels.tail(2).isna().all())
