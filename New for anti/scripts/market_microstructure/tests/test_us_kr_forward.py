import copy
import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

if any(importlib.util.find_spec(p) is None for p in ['numpy', 'pandas', 'scipy', 'sklearn', 'exchange_calendars']):
    raise unittest.SkipTest('install requirements-us-kr-preopen.txt for optional direction tests')

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evaluate_us_kr_forward as evaluation
import us_kr_comparison as comparison
from option_direction_model import read, write
from run_us_kr_preopen import archive_forecast, record_attempt, timing
from us_kr_direction_engine import FEATURES, TICKERS
from research_stock_open_close_direction import TARGETS


class ForwardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.primary = read(Path(__file__).resolve().parents[1]/'models/shadow/us_kr_preopen_20261022_v1.json')
        cls.comparison = read(comparison.DEFAULT_MODEL)

    def forecast(self, day='2026-11-06', with_comparisons=True):
        generated = day+'T07:00:00+09:00'
        gate = timing(day, datetime.fromisoformat(generated))
        score = {'probability': .6, 'information_state': 'model_score_with_calibration'}
        results = {t: {'scores': {name: copy.deepcopy(score) for name in TARGETS},
                       'feature_values': dict.fromkeys(FEATURES, 0.0)} for t in TICKERS}
        forecast = {'status': 'research_preopen_forecast', 'generated_at': generated,
                    'target_date': day, 'model_id': self.primary['model_id'],
                    'trained_through': self.primary['trained_through'], 'input_hashes': {'fixture': day},
                    'KR_source_date': gate['source'], 'required_US_session': gate['us_source'],
                    'forecast_cutoff_KST': gate['cutoff'], 'results': results,
                    'eligible_for_prospective_evaluation': True, 'reasons': []}
        if with_comparisons:
            forecast['comparisons'] = comparison.predict(self.comparison, self.primary, forecast)
        return forecast

    def prices(self):
        return {'candidates': [{'ticker': t, 'rows': [dict(date=d, open=o, high=110, low=90, close=c,
                                                         quality='observed')
                for d, o, c in [('2026-11-05', 100, 100), ('2026-11-06', 101, 102),
                                ('2026-11-09', 103, 104), ('2026-11-10', 105, 106)]]} for t in TICKERS]}

    def evaluate(self, root, prices=None, now='2026-11-10T17:00:00+09:00', end='2026-11-10'):
        return evaluation.evaluate(root, self.primary, self.comparison, prices or self.prices(),
                                   '2026-11-06', end, now=now)

    def test_denominator_includes_uninvoked_and_failed_days(self):
        with tempfile.TemporaryDirectory() as root:
            archive_forecast(self.forecast(), root)
            failed = self.forecast('2026-11-09');failed.update(status='unavailable', reasons=['source missing'])
            record_attempt(failed, root)
            out = self.evaluate(root)
        self.assertEqual(out['issuance']['expected_sessions_past_cutoff'], 3)
        self.assertEqual(out['issuance']['issued_sessions'], 1)
        self.assertEqual(out['issuance']['issuance_rate'], 1/3)
        self.assertEqual(out['days'][1]['reason'], 'no_valid_first_forecast')
        self.assertEqual(out['days'][1]['last_attempt_reasons'], ['source missing'])
        self.assertEqual(out['days'][2]['reason'], 'no_recorded_attempt')

    def test_revisions_and_replay_are_never_scored(self):
        with tempfile.TemporaryDirectory() as root:
            f = self.forecast();_, first = archive_forecast(f, root)
            f['input_hashes'] = {'changed': True};f['results']['KOSPI']['scores']['opening_up']['probability'] = .9
            archive_forecast(f, root)
            out = self.evaluate(root)
            self.assertAlmostEqual(out['all']['KOSPI']['opening_up']['primary']['brier'], .16)
            tampered = read(first);tampered['status'] = 'retrospective_replay';write(first, tampered)
            out = self.evaluate(root)
            self.assertEqual(out['issuance']['issued_sessions'], 0)

    def test_timing_source_and_model_identity_rechecked(self):
        mutations = [{'generated_at': '2026-11-06T08:31:00+09:00'},
                     {'generated_at': '2026-11-04T01:00:00+09:00'},
                     {'KR_source_date': '2026-11-04'}, {'required_US_session': '2026-11-04'},
                     {'model_id': 'b'*64}, {'eligible_for_prospective_evaluation': False}]
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as root:
                _, first = archive_forecast(self.forecast(), root)
                f = read(first);f.update(mutation);write(first, f)
                self.assertEqual(self.evaluate(root)['issuance']['issued_sessions'], 0)

    def test_no_scoring_before_close_and_no_future_denominator(self):
        with tempfile.TemporaryDirectory() as root:
            archive_forecast(self.forecast(), root)
            report = self.evaluate(root, now='2026-11-06T10:00:00+09:00')
            self.assertEqual(report['issuance']['expected_sessions_past_cutoff'], 1)
            self.assertEqual(report['issuance']['matured_sessions'], 0)
            self.assertEqual(report['all']['KOSPI']['opening_up']['primary']['n'], 0)
            before = self.evaluate(root, now='2026-11-06T08:00:00+09:00')
            self.assertIsNone(before['issuance']['issuance_rate'])

    def test_missing_or_carried_outcome_is_not_zero_filled(self):
        for mode in ['missing', 'carried_forward']:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as root:
                archive_forecast(self.forecast(), root);prices = self.prices()
                c = next(c for c in prices['candidates'] if c['ticker'] == 'KOSPI')
                if mode == 'missing': c['rows'] = c['rows'][1:]
                else: c['rows'][1]['quality'] = mode
                out = self.evaluate(root, prices=prices)
                self.assertEqual(out['issuance']['issued_sessions'], 1)
                self.assertEqual(out['all']['KOSPI']['opening_up']['primary']['n'], 0)
                self.assertEqual(out['days'][0]['tickers']['KOSPI']['status'], 'outcome_unavailable')

    def test_flat_audited_and_excluded_from_all_common_heads(self):
        with tempfile.TemporaryDirectory() as root:
            archive_forecast(self.forecast(), root);prices = self.prices()
            prices['candidates'][0]['rows'][1]['open'] = 100
            out = self.evaluate(root, prices=prices)
        self.assertEqual(out['days'][0]['tickers']['005930']['status'], 'flat_excluded')
        self.assertEqual(out['days'][0]['tickers']['005930']['labels']['opening_direction'], 'FLAT')
        self.assertTrue(all(out['all']['005930'][t]['primary']['n'] == 0 for t in TARGETS))

    def test_comparisons_only_on_shared_dates(self):
        with tempfile.TemporaryDirectory() as root:
            archive_forecast(self.forecast(), root)
            archive_forecast(self.forecast('2026-11-09', with_comparisons=False), root)
            out = self.evaluate(root)
        result = out['all']['KOSPI']['opening_up']
        self.assertEqual(result['primary']['n'], 2)
        self.assertEqual(result['price_us']['n'], 1)
        self.assertEqual(result['paired_comparisons']['primary_vs_price_us']['n_common'], 1)
        expected = .16 - (1-result['price_us']['mean_probability'])**2
        self.assertAlmostEqual(result['paired_comparisons']['primary_vs_price_us']['mean_brier_difference'], expected)

    def test_reference_only_and_neutral_not_direction_signals(self):
        rows = [{'p': .7, 'y': 1, 'information_state': 'recent_base_rate_only'},
                {'p': .5, 'y': 0, 'information_state': 'model_score_with_calibration'},
                {'p': .6, 'y': 1, 'information_state': 'model_score_with_calibration'}]
        out = evaluation.metrics(rows)
        self.assertEqual(out['n'], 3);self.assertEqual(out['n_model_signal'], 1)
        self.assertEqual(out['n_reference_only'], 1);self.assertEqual(out['n_neutral'], 1)
        self.assertEqual(sum(b['n'] for b in out['reliability']), 3)
        self.assertEqual(out['signal_accuracy'], 1)
        self.assertLess(out['signal_accuracy_wilson95'][0], .5)
        self.assertEqual(out['status'], 'small_sample')

    def test_malformed_probabilities_and_prices_are_rejected(self):
        for p in [float('nan'), -1, 1.1, True, None]:
            with self.assertRaises(ValueError): evaluation.valid_probability({'probability': p})
        prices = self.prices()['candidates'][0]['rows'];bars = {r['date']: r for r in prices}
        bars['2026-11-06']['high'] = 100
        with self.assertRaises(ValueError): evaluation.actual_labels(bars, '2026-11-05', '2026-11-06')

    def test_frozen_comparison_integrity_and_no_parameter_mutation(self):
        before = copy.deepcopy(self.comparison);primary = copy.deepcopy(self.primary)
        forecast = self.forecast()
        self.assertEqual(set(forecast['comparisons']['results']), set(TICKERS))
        self.assertEqual(self.comparison, before);self.assertEqual(self.primary, primary)
        tampered = copy.deepcopy(self.comparison);tampered['trained_through'] = '2026-11-05'
        with self.assertRaises(ValueError): comparison.validate(tampered, self.primary)
        with self.assertRaises(ValueError): comparison.train(self.primary, {}, {}, {}, {})

    def test_comparison_cannot_be_added_to_old_forecast_as_if_preissued(self):
        forecast = self.forecast()
        artifact = copy.deepcopy(self.comparison);artifact['created_at'] = '2026-11-07T00:00:00+09:00'
        with self.assertRaises(ValueError): evaluation.comparison_scores(forecast, artifact)

    def test_outcome_collection_uses_closed_dates_only_and_records_provider_failure(self):
        with patch.object(evaluation, 'fetch_naver_chart') as fetch:
            p = evaluation.collect_outcomes('2026-11-06', '2026-11-10', now='2026-11-06T10:00:00+09:00')
            fetch.assert_not_called();self.assertEqual(p['candidates'], [])
        with patch.object(evaluation, 'fetch_naver_chart', side_effect=OSError('offline')):
            p = evaluation.collect_outcomes('2026-11-06', '2026-11-10', now='2026-11-06T17:00:00+09:00')
            self.assertEqual(len(p['errors']), 3);self.assertEqual(p['candidates'], [])
        bar = dict(open=100, high=110, low=90, close=101)
        with patch.object(evaluation, 'fetch_naver_chart', return_value={'2026-11-05': bar}) as fetch:
            p = evaluation.collect_outcomes('2026-11-06', '2026-11-10', now='2026-11-06T17:00:00+09:00')
            self.assertEqual(fetch.call_args.args[-1], '20261106')
            self.assertEqual(p['candidates'][0]['missing_sessions'], ['2026-11-06'])
            self.assertEqual(len(p['candidates'][0]['rows']), 1)


if __name__ == '__main__':
    unittest.main()
