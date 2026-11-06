import copy
import gzip
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

if any(importlib.util.find_spec(p) is None for p in ['numpy', 'pandas', 'scipy', 'sklearn', 'statsmodels', 'exchange_calendars']):
    raise unittest.SkipTest('install requirements-flow-horizons-research.txt for optional horizon research')

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import research_flow_horizons as research
import collect_foreign_ownership_research as collector


class HorizonTests(unittest.TestCase):
    def setUp(self):
        # Small deterministic fixtures test the same splitter; actual defaults stay 250/60.
        context = patch.multiple(research, MIN_TRAIN=80, N_CAL=30)
        context.start();self.addCleanup(context.stop)

    def price_fixture(self):
        days = ['2026-11-02', '2026-11-03', '2026-11-04', '2026-11-05', '2026-11-06', '2026-11-09']
        closes = [100, 105, 103, 100, 98, 102]
        bars = {d: dict(date=d, open=101, high=110, low=90, close=c, quality='observed') for d, c in zip(days, closes)}
        return bars, days

    def rows(self, n=170):
        cal = research.ReviewedCalendar(research.calendar())
        days = [d for d in cal.sessions.strftime('%Y-%m-%d') if d >= '2026-01-05']
        rng = np.random.default_rng(7);rows = []
        for i in range(n):
            x = rng.normal(size=7).tolist()
            outcomes = {str(h): {'target_date': days[i+h], 'cumulative_close': 'UP' if (i+h) % 3 else 'DOWN',
                                  'cumulative_log_change_pct': 2*h*x[3]+3*h*x[4]+rng.normal(0, .01)} for h in research.HORIZONS}
            rows.append({'source_date': days[i], 'last_target_date': days[i+5], 'features': x,
                         'letf_exposure': None, 'rebalance_signed_share': None, 'outcomes': outcomes})
        return rows

    def test_cumulative_direction_and_delayed_daily_direction_differ(self):
        bars, days = self.price_fixture();out = research.labels(bars, days)
        self.assertEqual(out['2']['cumulative_close'], 'UP')
        self.assertEqual(out['2']['delayed_session_close'], 'DOWN')
        self.assertEqual(out['3']['cumulative_close'], 'FLAT')
        self.assertEqual(out['5']['from_first_open'], 'UP')

    def test_missing_future_session_never_skipped(self):
        bars, days = self.price_fixture();del bars[days[2]]
        with self.assertRaises(ValueError): research.labels(bars, days)

    def test_carried_future_price_not_used(self):
        bars, days = self.price_fixture();bars[days[2]]['quality'] = 'carried_forward'
        with self.assertRaises(ValueError): research.labels(bars, days)

    def test_up_down_flat_denominator_retains_flat(self):
        rows = [{'outcomes': {'1': {'cumulative_close': s}}} for s in ['UP', 'DOWN', 'FLAT']]
        d = research.distribution(rows, 1, 'cumulative_close')
        self.assertEqual(d['n'], 3);self.assertAlmostEqual(d['p_up']+d['p_down']+d['p_flat'], 1)
        self.assertAlmostEqual(d['p_down'], 1/3)

    def basket(self):
        return {'quality': 'observed', 'letf_aum_long_krw': 100, 'letf_aum_inverse_krw': 50,
                'products': [{'ticker': 'a', 'L': 2, 'aum_krw': 100, 'aum_quality': 'observed'},
                             {'ticker': 'b', 'L': -2, 'aum_krw': 50, 'aum_quality': 'observed'}]}

    def test_exposure_uses_leveraged_gross_and_preserves_inverse(self):
        r = research.exposure(self.basket())
        self.assertAlmostEqual(r['reported_long_exposure_share'], 2/3)
        self.assertAlmostEqual(r['reported_net_exposure_bias'], 1/3)

    def test_missing_aum_not_zero_filled_or_mismatched_basket_accepted(self):
        for mutation in ['missing', 'aggregate_mismatch', 'duplicate', 'quality']:
            b = self.basket()
            if mutation == 'missing': b['products'][1]['aum_krw'] = None
            if mutation == 'aggregate_mismatch': b['letf_aum_inverse_krw'] = 0
            if mutation == 'duplicate': b['products'][1]['ticker'] = 'a'
            if mutation == 'quality': b['products'][1]['aum_quality'] = 'carried_forward'
            with self.subTest(mutation=mutation): self.assertIsNone(research.exposure(b))

    def test_rebalance_requires_existing_krx_quality_gate_and_preserves_sign(self):
        r = {'quality': 'observed', 'implied_rebalance_quality': 'estimated', 'implied_rebalance_krw': -10,
             'spot_trading_value_krw': 100, 'underlying_day_return_quality': 'observed_krx'}
        self.assertEqual(research.pressure(r), -.1)
        r['underlying_day_return_quality'] = 'unknown'
        self.assertIsNone(research.pressure(r))
        r['underlying_day_return_quality'] = 'observed_krx';r['spot_trading_value_krw'] = None
        self.assertIsNone(research.pressure(r))

    def test_both_temporal_boundaries_purge_all_five_outcomes(self):
        fs = research.folds(self.rows());self.assertTrue(fs)
        for train, cal, test in fs:
            self.assertGreaterEqual(len(train), research.MIN_TRAIN)
            self.assertEqual(len(cal), research.N_CAL)
            self.assertLess(max(r['last_target_date'] for r in train), cal[0]['source_date'])
            self.assertLess(max(r['last_target_date'] for r in cal), test[0]['source_date'])
            self.assertFalse({r['source_date'] for r in train} & {r['source_date'] for r in test})

    def test_scaler_is_fit_on_train_and_future_values_do_not_change_it(self):
        rows = self.rows();train, cal, test = research.folds(rows)[0]
        f = research.fit_logit(train, [0, 1, 2], 1)
        self.assertTrue(np.allclose(f[0], np.array([r['features'][:3] for r in train]).mean(axis=0)))
        original = f[0].copy()
        for r in cal+test: r['features'][0] = 1e9
        new = research.fit_logit(train, [0, 1, 2], 1)
        self.assertTrue(np.array_equal(original, new[0]))

    def test_up_down_metrics_and_reference_only_are_separate(self):
        rows = [{'p_up': p, 'y': y, 'information_state': state} for p, y, state in
                [(.7, 1, 'model_score_with_calibration'), (.8, 0, 'recent_base_rate_only'),
                 (.2, 0, 'model_score_with_calibration'), (.3, 1, 'model_score_with_calibration'),
                 (.5, 1, 'model_score_with_calibration')]]
        d = research.binary_metrics(rows)
        self.assertEqual(d['confusion'], dict(true_up=1, false_up=1, true_down=1, false_down=1))
        self.assertEqual(d['accuracy'], .5);self.assertEqual(d['n_neutral'], 1)
        self.assertEqual(d['signal_up_precision'], 1);self.assertEqual(d['signal_down_precision'], .5)
        self.assertEqual(d['n_model_signal'], 3);self.assertEqual(d['n_reference_only'], 1)

    def test_walk_forward_same_dates_all_families_no_input_mutation(self):
        rows = self.rows(145);before = copy.deepcopy(rows)
        report, records = research.walk_forward(rows)
        self.assertTrue(records);self.assertEqual(rows, before)
        for h in research.HORIZONS:
            dates = [{r['source_date'] for r in records if r['horizon'] == h and r['family'] == family}
                     for family in list(research.FAMILIES)+['recent_frequency']]
            self.assertTrue(all(d == dates[0] for d in dates))
            self.assertTrue(all(abs(r['p_up']+r['p_down']-1) < 1e-12 for r in records))
            self.assertEqual(report['paired_brier'][str(h)]['price']['price']['mean_brier_difference'], 0)

    def test_short_verified_rebalance_history_does_not_fit_a_forecast(self):
        rows = self.rows(35)
        for r in rows:
            r['letf_exposure'] = {'reported_net_exposure_bias': .5};r['rebalance_signed_share'] = .01
        before = copy.deepcopy(rows);report, preds = research.walk_forward(rows, extra=True)
        self.assertEqual(report['status'], 'insufficient_temporal_test_history')
        self.assertEqual(preds, []);self.assertEqual(rows, before)

    def test_local_projections_recover_known_coefficients_with_hac(self):
        out = research.local_projections(self.rows(80))
        self.assertEqual(out['status'], 'conditional_association_not_causal')
        self.assertAlmostEqual(out['horizons']['1']['foreign_share1']['effect_per_plus_10pct_volume_share_pp'], .2, places=2)
        self.assertAlmostEqual(out['horizons']['5']['foreign_share5']['effect_per_plus_10pct_volume_share_pp'], 1.5, places=2)

    def test_holm_adjusts_the_whole_declared_family(self):
        values = {'x': {'local_projections': {'horizons': {'1': {'a': {'p_value': .01}, 'b': {'p_value': .04}}, '2': {'a': {'p_value': .03}}}}}}
        self.assertEqual(research.holm(values), 3)
        h = values['x']['local_projections']['horizons'];key = 'holm_p_all_stocks_horizons_flow_ratios'
        self.assertAlmostEqual(h['1']['a'][key], .03);self.assertAlmostEqual(h['1']['b'][key], .06)
        self.assertAlmostEqual(h['2']['a'][key], .06)

    def assembly_fixture(self):
        cal = research.ReviewedCalendar(research.calendar())
        days = [d for d in cal.sessions.strftime('%Y-%m-%d') if d >= '2026-01-05'][:26]
        bars = [dict(date=d, open=100+i, high=115+i, low=90+i, close=101+i, volume=100+i, quality='observed')
                for i, d in enumerate(days)]
        flow = [{'date': r['date'], 'close': r['close'], 'foreign_net_shares': i+1} for i, r in enumerate(bars[1:21])]
        report = {'tickers': {'005930': {'quality': 'observed', 'net_shares_quality': 'observed', 'days': flow}}}
        prices = {'candidates': [{'ticker': '005930', 'rows': bars}]}
        series = [dict(date=d, quality='observed', foreign=dict(buy_krw=30, sell_krw=10, net_krw=20),
                       market_total=dict(buy_krw=100, sell_krw=100)) for d in days]
        board = {'kr': {'investor_nets': {'detailed_15007': {'products': {'options_call': {'series': series}, 'options_put': {'series': series}}}}}}
        return report, prices, board, days

    def test_five_day_flow_is_volume_weighted_and_features_ignore_future_prices(self):
        report, prices, board, days = self.assembly_fixture()
        rows, _ = research.assemble(report, prices, board, [], '005930')
        r = next(r for r in rows if r['features'] is not None);index = days.index(r['source_date'])
        raw = {x['date']: x for x in report['tickers']['005930']['days']}
        v = {x['date']: x['volume'] for x in prices['candidates'][0]['rows']}
        recent = days[index-4:index+1]
        self.assertAlmostEqual(r['features'][4], sum(raw[d]['foreign_net_shares'] for d in recent)/sum(v[d] for d in recent))
        prices['candidates'][0]['rows'][index+3]['close'] *= 1.01
        new, _ = research.assemble(report, prices, board, [], '005930')
        after = next(x for x in new if x['source_date'] == r['source_date'])
        self.assertEqual(r['features'], after['features'])

    def test_missing_past_foreign_quantity_blocks_five_day_features(self):
        report, prices, board, days = self.assembly_fixture()
        rows, _ = research.assemble(report, prices, board, [], '005930')
        r = next(r for r in rows if r['features'] is not None);index = days.index(r['source_date'])
        for raw in report['tickers']['005930']['days']:
            if raw['date'] == days[index-2]: raw['foreign_net_shares'] = None
        new, _ = research.assemble(report, prices, board, [], '005930')
        self.assertIsNone(next(x for x in new if x['source_date'] == r['source_date'])['features'])

    def ownership_fixture(self, report, days):
        raw = {r['date']: r for r in report['tickers']['005930']['days']}
        return {'tickers': {'005930': [{'date': d, 'quality': 'observed', 'foreign_holding_pct': 40+.01*i,
                    'foreign_net_shares_source_check': raw.get(d, {}).get('foreign_net_shares')} for i, d in enumerate(days)]}}

    def test_holding_percent_level_and_changes_are_distinct_from_flow_share(self):
        report, prices, board, days = self.assembly_fixture();owned = self.ownership_fixture(report, days)
        rows, _ = research.assemble(report, prices, board, [], '005930', owned)
        r = next(r for r in rows if r['features'] is not None)
        i = days.index(r['source_date'])
        self.assertAlmostEqual(r['ownership_features'][0], 40+.01*i)
        self.assertAlmostEqual(r['ownership_features'][1], .01)
        self.assertAlmostEqual(r['ownership_features'][2], .05)
        self.assertNotAlmostEqual(r['ownership_features'][0], r['foreign_share1'])

    def test_missing_or_revised_ownership_is_not_a_zero_position(self):
        for kind in ['missing', 'revised']:
            report, prices, board, days = self.assembly_fixture();owned = self.ownership_fixture(report, days)
            d = days[5];r = next(r for r in owned['tickers']['005930'] if r['date'] == d)
            if kind == 'missing': r['foreign_holding_pct'] = None
            else: r['foreign_net_shares_source_check'] = -999
            rows, audit = research.assemble(report, prices, board, [], '005930', owned)
            row = next(r for r in rows if r['source_date'] == d)
            self.assertIsNone(row['ownership_features']);self.assertIsNotNone(row['features'])
            if kind == 'revised': self.assertGreater(audit['availability']['ownership_net_share_snapshot_mismatch'], 0)

    def test_percentage_parser_preserves_real_zero_and_missing(self):
        self.assertEqual(collector.holding_pct('45.96%'), 45.96)
        self.assertEqual(collector.holding_pct('0%'), 0)
        for v in [None, '', '-', 'nan%', '101%', '-1%', '45.96']:
            self.assertIsNone(collector.holding_pct(v))

    def test_ownership_normalization_retains_missing_and_rejects_duplicate_dates(self):
        rows = [{'bizdate': '20261105', 'foreignerHoldRatio': '45.96%', 'foreignerPureBuyQuant': '-1,234'},
                {'bizdate': '20261104', 'foreignerHoldRatio': None, 'foreignerPureBuyQuant': '0'}]
        out = collector.normalize(rows)
        self.assertEqual(out[0]['quality'], 'missing');self.assertIsNone(out[0]['foreign_holding_pct'])
        self.assertEqual(out[1]['foreign_net_shares_source_check'], -1234)
        with self.assertRaises(ValueError): collector.normalize(rows+rows[:1])

    def test_ownership_model_compares_same_dates_without_changing_base_features(self):
        rows = self.rows(145)
        for i, r in enumerate(rows): r['ownership_features'] = [40+i/100, .01, .05]
        before = copy.deepcopy(rows);report, preds = research.walk_forward(rows, with_ownership=True)
        self.assertEqual(rows, before);self.assertTrue(preds)
        for h in research.HORIZONS:
            scores = report['scores'][str(h)]
            self.assertEqual(scores['price']['n'], scores['price_foreign_options_ownership']['n'])

    def test_flat_at_five_days_does_not_remove_one_day_test_prediction(self):
        rows = self.rows(145);source = rows[130]['source_date']
        rows[130]['outcomes']['5']['cumulative_close'] = 'FLAT'
        report, preds = research.walk_forward(rows)
        self.assertTrue(any(r['source_date'] == source and r['horizon'] == 1 for r in preds))
        self.assertFalse(any(r['source_date'] == source and r['horizon'] == 5 for r in preds))
        self.assertTrue(any(f['heads']['5'].get('n_test_flat_excluded', 0) > 0 for f in report['folds']))

    def test_prediction_archive_is_deterministic_and_reversible(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'records.jsonl.gz';records = [{'p_up': .6, 'p_down': .4}]
            research.write_predictions(path, records);before = path.read_bytes()
            research.write_predictions(path, records)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(gzip.decompress(before).decode(), '{"p_up": 0.6, "p_down": 0.4}\n')

    def test_full_default_protocol_requires_250_training_and_60_calibration_rows(self):
        with patch.multiple(research, MIN_TRAIN=250, N_CAL=60):
            self.assertEqual(research.folds(self.rows(280)), [])
            fs = research.folds(self.rows(400));self.assertTrue(fs)
            for train, cal, test in fs:
                self.assertGreaterEqual(len(train), 250);self.assertEqual(len(cal), 60)


if __name__ == '__main__':
    unittest.main()
