import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

if any(importlib.util.find_spec(p) is None for p in ('pandas', 'numpy', 'scipy', 'sklearn', 'exchange_calendars')):
    raise unittest.SkipTest('install requirements-us-kr-preopen.txt')

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kr_gap_size_shadow as shadow


class GapSizeShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact = json.loads(shadow.DEFAULT_MODEL.read_text())

    def test_replay_only_returns_validated_heads_and_survives_model_key_order(self):
        artifact = json.loads(json.dumps(self.artifact, sort_keys=True))
        vector = dict.fromkeys(shadow.FEATURES, .01)
        with patch.object(shadow, 'features_for_day', return_value=[('KOSPI', vector)]):
            result = shadow.infer(None, artifact, '2026-11-23', '2026-11-23T07:00:00+09:00', True)
        scores = result['results']['KOSPI']
        self.assertEqual(result['status'], 'retrospective_replay')
        self.assertEqual(set(scores), set(shadow.HEADS['KOSPI']))
        self.assertGreaterEqual(scores['median_abs_gap'], 0)
        self.assertLessEqual(scores['probability_abs_gap_gt_1pct'], 1)

    def test_rejects_post_cutoff_replay_and_past_model_creation_for_live(self):
        with self.assertRaisesRegex(ValueError, 'precedes model creation'):
            shadow.infer(None, self.artifact, '2026-11-23', '2026-11-23T07:00:00+09:00', False)
        with self.assertRaisesRegex(ValueError, '08:30'):
            shadow.infer(None, self.artifact, '2026-11-23', '2026-11-23T08:31:00+09:00', True)

    def test_holiday_never_reuses_us_input(self):
        with self.assertRaisesRegex(ValueError, 'no new US close'):
            shadow.infer(None, self.artifact, '2026-11-27', '2026-11-27T07:00:00+09:00', True)
