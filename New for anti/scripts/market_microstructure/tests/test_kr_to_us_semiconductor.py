import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

if any(importlib.util.find_spec(p) is None for p in ('pandas', 'numpy', 'scipy', 'sklearn', 'exchange_calendars')):
    raise unittest.SkipTest('install requirements-us-kr-preopen.txt')

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kr_to_us_semiconductor as eng


class ReverseDirectionTests(unittest.TestCase):
    def test_window_requires_both_sessions_and_correct_order(self):
        d = pd.Timestamp('2026-11-24')
        eng.check_window(d, pd.Timestamp('2026-11-24T16:00:00+09:00'))
        for when in ('2026-11-24T15:29:00+09:00', '2026-11-24T09:30:00-05:00'):
            with self.assertRaises(ValueError):
                eng.check_window(d, pd.Timestamp(when))
        with self.assertRaises(ValueError):
            eng.check_window(pd.Timestamp('2026-11-26'), pd.Timestamp('2026-11-26T16:00:00+09:00'))

    def test_target_us_prices_are_only_labels(self):
        idx = pd.bdate_range('2026-08-03', '2026-11-24')
        close = np.linspace(100, 110, len(idx))
        panels = {k:pd.DataFrame({'open':close+1., 'close':close},index=idx) for k in eng.SYMBOLS}
        d = idx[-1]
        with patch.object(eng, 'prices', side_effect=lambda directory, k:panels[k]):
            original = eng.panel(None,d)['mu'].loc[d]
            for k in ('nasdaq', *eng.TARGETS):
                panels[k].loc[d, ['open','close']] = [1.,999.]
            changed = eng.panel(None,d)['mu'].loc[d]
            cols = eng.features('mu')['semiconductors']
            self.assertTrue(original[cols].notna().all())
            pd.testing.assert_series_equal(original[cols],changed[cols])
            self.assertNotEqual(original.intraday,changed.intraday)
            panels['hynix'].loc[d,'close'] = np.nan
            missing = eng.panel(None,d)['mu'].loc[d]
            self.assertTrue(pd.isna(missing.hynix_relative_body))

    def test_replay_excludes_training_dates(self):
        model = eng.json.loads(eng.MODEL.read_text())
        with self.assertRaisesRegex(ValueError,'precedes'):
            eng.infer(model,None,pd.Timestamp('2026-11-20'),pd.Timestamp('2026-11-20T16:00:00+09:00'),True)
