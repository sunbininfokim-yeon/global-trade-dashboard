import copy
import importlib.util
import sys
import unittest
from pathlib import Path

if any(importlib.util.find_spec(p) is None for p in ['numpy', 'pandas', 'scipy', 'sklearn', 'exchange_calendars']):
    raise unittest.SkipTest('install requirements-us-kr-preopen.txt for optional direction research')

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import research_foreign_flow_direction as research


class ForeignFlowTests(unittest.TestCase):
    def fixtures(self):
        days = [('2026-10-30', 100, 100), ('2026-11-02', 100, 101),
                ('2026-11-03', 102, 99), ('2026-11-04', 98, 97), ('2026-11-05', 98, 99)]
        bars = [dict(date=d, open=o, high=110, low=80, close=c, volume=100, quality='observed') for d, o, c in days]
        flows = [dict(date=d, close=c, foreign_net_shares=n, foreign_net_krw=999999999999)
                 for (d, _, c), n in zip(days[1:4], [10, -20, 15])]
        return ({'tickers': {'005930': {'quality': 'observed', 'net_shares_quality': 'observed', 'days': flows}}},
                {'candidates': [{'ticker': '005930', 'source': 'independent price fixture', 'rows': bars}]})

    def test_exact_next_session_and_quantity_ratio_not_estimated_money(self):
        flows, prices = self.fixtures();rows, audit = research.assemble(flows, prices, '005930')
        self.assertEqual(rows[0]['source_date'], '2026-11-02');self.assertEqual(rows[0]['target_date'], '2026-11-03')
        self.assertEqual(rows[0]['foreign_net_share_of_volume'], .1)
        self.assertEqual(rows[0]['opening_up'], 1);self.assertEqual(rows[0]['closing_up'], 0)
        self.assertEqual(rows[0]['same_day_close_direction'], 'UP');self.assertEqual(audit['n_eligible_pairs'], 3)
        self.assertNotIn('foreign_net_krw', rows[0])

    def test_missing_next_session_is_not_replaced_by_later_observation(self):
        flows, prices = self.fixtures()
        prices['candidates'][0]['rows'] = [r for r in prices['candidates'][0]['rows'] if r['date'] != '2026-11-03']
        rows, audit = research.assemble(flows, prices, '005930')
        self.assertFalse(any(r['source_date'] == '2026-11-02' for r in rows))
        self.assertEqual(audit['exclusions']['missing_or_invalid_exact_next_session_price'], 1)

    def test_non_observed_or_estimated_flow_source_rejected(self):
        flows, prices = self.fixtures();flows['tickers']['005930']['net_shares_quality'] = 'estimated'
        with self.assertRaises(ValueError): research.assemble(flows, prices, '005930')

    def test_price_basis_mismatch_and_impossible_quantity_excluded(self):
        flows, prices = self.fixtures();days = flows['tickers']['005930']['days']
        days[0]['close'] = 500;days[1]['foreign_net_shares'] = 200
        rows, audit = research.assemble(flows, prices, '005930')
        self.assertEqual(len(rows), 1)
        self.assertEqual(audit['exclusions']['price_basis_mismatch'], 1)
        self.assertEqual(audit['exclusions']['invalid_or_incompatible_volume'], 1)

    def test_flat_boundaries_are_audited_not_forced_to_down(self):
        flows, prices = self.fixtures();prices['candidates'][0]['rows'][2]['open'] = 101
        rows, _ = research.assemble(flows, prices, '005930');out = research.frequencies(rows[:1])
        self.assertEqual(out['events']['opening_up']['flat_excluded'], 1)
        self.assertEqual(out['events']['opening_up']['n'], 0)
        self.assertIsNone(out['events']['opening_up']['event_rate'])
        self.assertEqual(out['events']['closing_up']['n'], 1)

    def test_streak_uses_only_current_and_two_previous_sessions(self):
        flows, prices = self.fixtures()
        for r in flows['tickers']['005930']['days']: r['foreign_net_shares'] = 10
        out = research.analyze(flows, prices, '005930')
        self.assertIsNone(out['pair_audit'][0]['three_session_flow'])
        self.assertEqual(out['pair_audit'][-1]['three_session_flow'], 'BUY_3')
        self.assertEqual(out['groups']['buy_3_sessions']['n_pairs'], 1)
        original = copy.deepcopy(out['pair_audit'])
        prices['candidates'][0]['rows'][-1]['close'] = 80
        rows, _ = research.assemble(flows, prices, '005930')
        for a, b in zip(rows, original):
            self.assertEqual(a['three_session_flow'], b['three_session_flow'])
            self.assertEqual(a['flow_side'], b['flow_side'])

    def test_missing_net_quantity_and_carried_price_not_zero_filled(self):
        flows, prices = self.fixtures();flows['tickers']['005930']['days'][0]['foreign_net_shares'] = None
        prices['candidates'][0]['rows'][2]['quality'] = 'carried_forward'
        rows, audit = research.assemble(flows, prices, '005930')
        self.assertEqual(len(rows), 1)
        self.assertEqual(audit['exclusions']['invalid_foreign_net_shares'], 1)
        self.assertEqual(audit['exclusions']['missing_or_invalid_source_price'], 1)


if __name__ == '__main__':
    unittest.main()
