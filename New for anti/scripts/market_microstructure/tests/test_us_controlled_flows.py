import copy
import importlib.util
import sys
import unittest
from pathlib import Path

if any(importlib.util.find_spec(p) is None for p in ['numpy', 'pandas', 'scipy', 'sklearn', 'statsmodels', 'exchange_calendars']):
    raise unittest.SkipTest('install requirements-flow-horizons-research.txt for optional research')

import exchange_calendars as xc
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import research_us_controlled_flows as study


class USControlledTests(unittest.TestCase):
    def option_fixture(self):
        cal = study.ReviewedCalendar(study.calendar())
        days = [d for d in cal.sessions.strftime('%Y-%m-%d') if d >= '2026-01-05'][:24]
        def row(d, amount):
            return dict(date=d, quality='observed', foreign=dict(buy_krw=10, sell_krw=5, net_krw=5),
                        market_total=dict(buy_krw=amount, sell_krw=amount))
        products = {s: {d: row(d, 100) for d in days} for s in ['call', 'put']}
        products['put'][days[20]] = row(days[20], 200)
        return products, cal, days

    def test_activity_uses_only_prior20_and_current_single_side_market_value(self):
        p, cal, days = self.option_fixture()
        x = study.activity_vector(p, cal, days[20])
        self.assertAlmostEqual(x[0], 0);self.assertAlmostEqual(x[1], np.log(2));self.assertAlmostEqual(x[2], 2/3)
        p['call'][days[21]]['market_total'] = dict(buy_krw=1e9, sell_krw=1e9)
        self.assertEqual(x, study.activity_vector(p, cal, days[20]))

    def test_missing_or_invalid_option_session_never_zero_filled(self):
        p, cal, days = self.option_fixture();del p['put'][days[10]]
        with self.assertRaises(ValueError): study.activity_vector(p, cal, days[20])
        p, cal, days = self.option_fixture();p['call'][days[20]]['market_total']['sell_krw'] = 95
        with self.assertRaises(ValueError): study.activity_vector(p, cal, days[20])

    def us_fixture(self):
        c = xc.get_calendar('XNYS', start='2018-01-01', end='2027-12-31')
        data = {s: {'2026-10-29': dict(close=100), '2026-10-30': dict(close=110),
                    '2026-11-02': dict(close=500)} for s in study.SYMBOLS}
        return data, c

    def test_us_alignment_keeps_first_preopen_and_ignores_future_us_close(self):
        data, cal = self.us_fixture();x, meta = study.align_us(data, cal, '2026-11-02')
        self.assertEqual(meta['US_session'], '2026-10-30')
        self.assertAlmostEqual(x[0], .1)
        data['QQQ']['2026-11-02']['close'] = 10000
        self.assertEqual(x, study.align_us(data, cal, '2026-11-02')[0])

    def test_missing_expected_or_nonobserved_us_price_is_not_stale_filled(self):
        data, cal = self.us_fixture();del data['QQQ']['2026-10-30']
        with self.assertRaises(ValueError): study.align_us(data, cal, '2026-11-02')
        data, cal = self.us_fixture();data['QQQ']['2026-10-30']['quality'] = 'carried_forward'
        with self.assertRaises(ValueError): study.align_us(data, cal, '2026-11-02')

    def test_reviewed_january9_closure_is_not_missing_price_or_a_zero_return(self):
        cal = study.ReviewedUSCalendar(xc.get_calendar('XNYS', start='2018-01-01', end='2027-12-31'))
        self.assertNotIn('2025-01-09', cal.sessions)
        data = {s: {'2025-01-07': dict(close=100), '2025-01-08': dict(close=110), '2025-01-10': dict(close=121)} for s in study.SYMBOLS}
        x, a = study.align_us(data, cal, '2025-01-10')
        self.assertEqual(a['US_session'], '2025-01-08');self.assertAlmostEqual(x[0], .1)
        x, a = study.align_us(data, cal, '2025-01-13')
        self.assertEqual(a['US_session'], '2025-01-10');self.assertAlmostEqual(x[0], .1)

    def rows(self, n=390):
        c = study.ReviewedCalendar(study.calendar());days = [d for d in c.sessions.strftime('%Y-%m-%d') if d >= '2024-01-05']
        rng = np.random.default_rng(18);rows = []
        for i in range(n):
            b = rng.normal(size=20).tolist()
            rows.append({'source_date': days[i], 'last_target_date': days[i+5], 'first_target_date': days[i+1],
                         'base': b, 'foreign': [b[0]*.2+b[18]*.1, b[1]*.1+b[19]*.2],
                         'ownership': [40+i/100, .01, .05], 'activity': [.1, .2, .6],
                         'binary': {h: 'UP' if (i+j) % 3 else 'DOWN' for j, h in enumerate(study.HEADS)},
                         'target_dates': {h: days[i+int(h[-1])] for h in study.HEADS},
                         'volatility': {h: abs(b[j])+1 for j, h in enumerate(study.VOLS)}})
        return rows

    def test_folds_require250_and_purge_both_five_day_boundaries(self):
        self.assertEqual(study.folds(self.rows(280)), [])
        fs = study.folds(self.rows());self.assertTrue(fs)
        for tr, ca, te in fs:
            self.assertGreaterEqual(len(tr), 250);self.assertEqual(len(ca), 60)
            self.assertLess(max(r['last_target_date'] for r in tr), ca[0]['source_date'])
            self.assertLess(max(r['last_target_date'] for r in ca), te[0]['source_date'])

    def test_residualizer_uses_train_price_and_volume_not_future_us_or_stock_labels(self):
        rows = self.rows();tr, ca, te = study.folds(rows)[0]
        model = study.residualizer(tr);before = [a.copy() for a in model[:2]];coef = model[2].coef_.copy()
        for r in ca+te:
            r['base'] = [1e8]*20;r['foreign'] = [99, 99]
        again = study.residualizer(tr)
        self.assertTrue(np.array_equal(before[0], again[0]));self.assertTrue(np.array_equal(before[1], again[1]))
        self.assertTrue(np.array_equal(coef, again[2].coef_))
        r = copy.deepcopy(tr[-1]);v = study.vector(r, 'us_residual_flow', model)
        expected = study.ridge_predict(model, [[r['base'][i] for i in study.RESIDUAL_CONTROLS]])[0]
        self.assertTrue(np.allclose(v[-2:], np.array(r['foreign'])-expected))
        r['base'][10:18] = [1e7]*8
        self.assertTrue(np.allclose(v[-2:], study.vector(r, 'us_residual_flow', model)[-2:]))

    def test_family_dimensions_and_no_input_mutation(self):
        rows = self.rows(260);before = copy.deepcopy(rows);nuisance = study.residualizer(rows)
        expected = dict(domestic_controls=12, us_controls=20, us_flow=22, us_ownership=23,
                        us_flow_ownership=25, us_residual_flow=22, us_activity=23, us_flow_activity=25)
        self.assertEqual({f: len(study.vector(rows[0], f, nuisance)) for f in study.FAMILIES}, expected)
        self.assertEqual(rows, before)

    def test_paired_direction_uses_same_date_label_and_target(self):
        base = [dict(kind='direction', source_date='2026-01-05', target_date='2026-01-06', y=1, p_up=.5)]
        candidate = [{**base[0], 'p_up': .7}]
        out = study.paired(candidate, base, True)
        self.assertAlmostEqual(out['mean_loss_difference'], -.16);self.assertIsNone(out['p_value'])
        for changed in [dict(target_date='2026-01-07'), dict(y=0)]:
            with self.assertRaises(ValueError): study.paired([{**candidate[0], **changed}], base, True)
        with self.assertRaises(ValueError): study.paired(candidate+candidate, base, True)

    def test_magnitude_metrics_are_sizes_and_recent_mean_skill(self):
        rows = [dict(source_date=str(i), predicted=p, actual=y) for i, (p, y) in enumerate([(1., 1.), (2., 3.)])]
        reference = {str(i): dict(predicted=2.) for i in range(2)}
        s = study.magnitude_metrics(rows, reference)
        self.assertAlmostEqual(s['mae'], .5);self.assertAlmostEqual(s['rmse'], np.sqrt(.5))
        self.assertAlmostEqual(s['skill_vs_recent_mean'], .5)

    def test_primary_family_has36_and_missing_results_cannot_be_significant(self):
        summary = study.summarize([])
        t = {'a': {'results': copy.deepcopy(summary)}, 'b': {'results': copy.deepcopy(summary)}}
        study.adjust_primary(t)
        tests = [p for v in t.values() for p in v['results']['paired'].values() if p['primary']]
        self.assertEqual(len(tests), 36)
        self.assertTrue(all(p['holm_p_primary36'] == 1 for p in tests))
        with self.assertRaises(ValueError): study.adjust_primary({'a': t['a']})

    def test_constant_loss_difference_is_not_reported_as_certain_significance(self):
        base = [dict(kind='direction', source_date=str(i).zfill(3), target_date=str(i), y=1, p_up=.5) for i in range(60)]
        candidate = [{**r, 'p_up': .7} for r in base]
        s = study.paired(candidate, base, True)
        self.assertEqual(s['p_value'], 1);self.assertEqual(s['status'], 'degenerate_loss_difference')

    def test_hac_and_holm_use_entire_family_not_the_best_result(self):
        a = study.summarize([]);b = copy.deepcopy(a)
        tests = [p for d in [a, b] for p in d['paired'].values() if p['primary']]
        tests[0]['p_value'] = .01
        study.adjust_primary({'a': {'results': a}, 'b': {'results': b}})
        self.assertAlmostEqual(tests[0]['holm_p_primary36'], .36)

    def test_full_evaluation_has_matching_dates_and_each_head_flat_is_separate(self):
        rows = self.rows(360);fs = study.folds(rows);source = fs[0][2][2]['source_date']
        next(r for r in rows if r['source_date'] == source)['binary']['closing5'] = 'FLAT'
        original = copy.deepcopy(rows);records, audit = study.evaluate(rows)
        self.assertEqual(rows, original);self.assertTrue(audit)
        self.assertTrue(any(r['kind'] == 'direction' and r['head'] == 'opening1' and r['source_date'] == source for r in records))
        self.assertFalse(any(r['kind'] == 'direction' and r['head'] == 'closing5' and r['source_date'] == source for r in records))
        for h in study.HEADS:
            sets = [{r['source_date'] for r in records if r['kind'] == 'direction' and r['head'] == h and r['family'] == f}
                    for f in study.FAMILIES+['recent_frequency']]
            self.assertTrue(all(s == sets[0] for s in sets))
        self.assertTrue(all(abs(r['p_up']+r['p_down']-1) < 1e-12 for r in records if r['kind'] == 'direction'))
        self.assertTrue(all(r['predicted'] >= 0 for r in records if r['kind'] == 'magnitude'))
        self.assertTrue(all(r['eligible_for_prospective_evaluation'] is False and r['research_only'] for r in records))


if __name__ == '__main__':
    unittest.main()
