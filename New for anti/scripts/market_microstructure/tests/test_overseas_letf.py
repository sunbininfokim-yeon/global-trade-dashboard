import copy
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_microstructure.overseas_letf import (
    build_board, implied_rebalance, leverage_on, normalize_bars, number,
    parse_themes_holdings, parse_leverage_shares, strict_sum, upsert_history, usd_rate,
)

ROOT = Path(__file__).resolve().parents[1]


class OverseasLetfTests(unittest.TestCase):
    def setUp(self):
        self.registry = json.loads((ROOT / 'config/overseas_letf_universe.json').read_text())
        self.p = copy.deepcopy(next(p for p in self.registry['products'] if p['product_id'] == 'SKHX'))

    def board(self, p, observations, aums=None, returns=None):
        return build_board(dict(products=[p], coverage='test'), observations, [], aums or [], {}, [], returns or [], as_of='2026-09-04')

    def bar(self, p, d='2026-09-04', **kw):
        return normalize_bars(p, p['listings'][0], [dict(date=d, close=10, volume=100, **kw)], {}, as_of='2026-09-04')[0]

    def test_registry_ids_and_listing_ids_unique(self):
        ps = self.registry['products']
        self.assertEqual(len(ps), len({p['product_id'] for p in ps}))
        ls = [l['listing_id'] for p in ps for l in p['listings']]
        self.assertEqual(len(ls), len(set(ls)))
        self.assertTrue(all(p['source_urls'] for p in ps))

    def test_missing_is_not_zero(self):
        self.assertIsNone(strict_sum([None, 10]))
        self.assertEqual(strict_sum([0, 10]), 10)
        for n in (float('nan'), float('inf'), True, ''):
            self.assertIsNone(number(n))

    def test_pence_fx_and_date_alignment(self):
        fx = {'2026-09-04': {'GBP': 1.3}}
        self.assertAlmostEqual(usd_rate('GBp', '2026-09-04', fx), .013)
        self.assertIsNone(usd_rate('GBp', '2026-09-03', fx))
        self.assertIsNone(usd_rate('HKD', '2026-09-04', fx))

    def test_flexible_cap_is_not_actual_leverage(self):
        p = self.registry['products'][0]
        self.assertEqual(leverage_on(p, '2026-08-02'), 2)
        self.assertIsNone(leverage_on(p, '2026-08-03'))

    def test_rebalance_sign_and_changing_target(self):
        self.assertAlmostEqual(implied_rebalance(100, 2, 2, .1), 20)
        self.assertAlmostEqual(implied_rebalance(100, -2, -2, -.1), -60)
        self.assertAlmostEqual(implied_rebalance(100, 2, 1.1, 0), -90)
        self.assertIsNone(implied_rebalance(100, None, 2, .1))
        self.assertIsNone(implied_rebalance(100, 2, 2, -.6))

    def test_no_future_or_after_counter_delisting(self):
        l = dict(self.p['listings'][0], last_trade_date='2026-09-03')
        bars = [dict(date=d, close=10, volume=0) for d in ['2026-09-03', '2026-09-04', '2026-09-08']]
        out = normalize_bars(self.p, l, bars, {}, as_of='2026-09-04')
        self.assertEqual([r['date'] for r in out], ['2026-09-03'])
        self.assertEqual(out[0]['trading_value_usd'], 0)

    def test_same_bar_proxy_and_observed_turnover_override(self):
        r = self.bar(self.p)
        self.assertEqual(r['trading_value_usd'], 1000)
        self.assertEqual(r['trading_value_quality'], 'proxy')
        self.assertEqual(self.bar(self.p, trading_value_native=950)['trading_value_usd'], 950)

    def test_aum_is_not_duplicated_by_currency_counters(self):
        p = copy.deepcopy(self.p)
        p['listings'].append(dict(p['listings'][0], listing_id='uk:TEST', ticker='TEST'))
        aums = [dict(date='2026-09-04', product_id='SKHX', aum_native=100, currency='USD', quality='observed')]
        row = self.bar(p)
        board, history = self.board(p, [row, dict(row, listing_id='uk:TEST')], aums)
        self.assertEqual(history[0]['aum_usd'], 100)
        self.assertEqual(history[0]['trading_value_usd'], 2000)
        _, partial = self.board(p, [row], aums)
        self.assertIsNone(partial[0]['trading_value_usd'])
        self.assertEqual(partial[0]['covered_trading_value_usd'], 1000)

    def test_unstamped_or_current_aum_cannot_backfill_previous(self):
        rows = [self.bar(self.p, '2026-09-03'), self.bar(self.p)]
        a = dict(date='2026-09-04', product_id='SKHX', aum_native=100, currency='USD', quality='observed')
        r = dict(date='2026-09-04', previous_date='2026-09-03', reference='SKHY', currency='USD', **{'return': .1})
        _, history = self.board(self.p, rows, [a], [r])
        self.assertIsNone(history[-1]['implied_rebalance_usd'])
        _, history = self.board(self.p, rows, [dict(a, date='2026-09-03')], [r])
        self.assertAlmostEqual(history[-1]['implied_rebalance_usd'], 20)
        _, history = self.board(self.p, rows, [dict(a, date='2026-09-03')], [dict(r, reference='000660.KS')])
        self.assertIsNone(history[-1]['implied_rebalance_usd'])

    def test_missing_fx_preserves_covered_subtotal_but_not_complete_total(self):
        p = copy.deepcopy(self.p)
        p['listings'].append(dict(p['listings'][0], listing_id='eu:EUR', ticker='EUR'))
        row = self.bar(p)
        _, history = self.board(p, [row, dict(row, listing_id='eu:EUR', trading_value_usd=None)])
        self.assertEqual(history[0]['covered_trading_value_usd'], 1000)
        self.assertIsNone(history[0]['trading_value_usd'])
        self.assertFalse(history[0]['coverage_complete'])
        self.assertEqual(history[0]['valued_listing_count'], 1)

    def test_holdings_negative_cash_and_future_rejection(self):
        header = 'Date,Account,StockTicker,SecurityName,Shares,MarketValue,Weightings,NetAssets\n'
        csv = header + '09/03/2026,SKHX,SWAP1,SK HYNIX SWAP,20,200,200%,100\n09/03/2026,SKHX,CASH,Cash & Other,-100,-100,-100%,100\n'
        hs, a, reject = parse_themes_holdings(csv, self.p, '2026-09-04')
        self.assertEqual([h['weight_pct'] for h in hs], [200, -100])
        self.assertEqual(len(a), 1)
        hs, a, reject = parse_themes_holdings(csv, self.p, '2026-09-02')
        self.assertFalse(hs)
        self.assertEqual(reject[0]['reason'], 'future_dated_holdings')
        with self.assertRaises(ValueError):
            parse_themes_holdings(csv.replace('SKHX', 'WRONG'), self.p, '2026-09-04')

    def test_upsert_idempotence_and_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'history.jsonl.gz'
            rows = [dict(date='2026-09-03', ticker='A', v=10), dict(date='2026-09-04', ticker='A', v=20)]
            m = upsert_history(p, rows, ('date', 'ticker'))
            old = p.read_bytes()
            self.assertEqual(m['date_count'], 2)
            upsert_history(p, rows, ('date', 'ticker'))
            self.assertEqual(old, p.read_bytes())
            upsert_history(p, [dict(rows[-1], v=30)], ('date', 'ticker'))
            with gzip.open(p, 'rt') as f:
                data = [json.loads(l) for l in f]
            self.assertEqual([r['v'] for r in data], [10, 30])

    def test_issuer_aum_units_and_simulated_history(self):
        p = next(p for p in self.registry['products'] if p['product_id'] == 'XS3388190301')
        info = dict(Isin=p['product_id'], date='04 Sep 2026', value_underlying_assets='300', liabilities='200',
                    etp_securities_issued='100', Underlying_holding='KRX futures', Leverage='3')
        rows = [dict(date='03/09/2026', IsSimulated='1', etp_securities_issued='90', price='9'),
                dict(date='04/09/2026', IsSimulated='0', etp_securities_issued='100', price='10')]
        aums, capital = parse_leverage_shares(dict(Etp=[info], Usd=rows), p, '2026-09-04')
        self.assertEqual(len(aums), 1)
        self.assertEqual(aums[0]['aum_native'], 100)
        self.assertEqual(capital['structure'], 'futures')
        with self.assertRaises(ValueError):
            parse_leverage_shares(dict(Etp=[dict(info, liabilities='190')], Usd=rows), p, '2026-09-04')

    def test_aum_dates_are_not_changed_by_observation_dates(self):
        rows = [self.bar(self.p)]
        aum = dict(date='2026-08-24', product_id='SKHX', aum_native=100, currency='USD', quality='observed')
        b, h = self.board(self.p, rows, [aum])
        self.assertIsNone(h[0]['aum_usd'])
        self.assertEqual(b['products'][0]['latest_aum']['date'], '2026-08-24')
        self.assertFalse(b['products'][0]['line_chart_available'])

    def test_primary_volume_does_not_switch_to_alphabetical_counter(self):
        p = copy.deepcopy(self.p)
        p['listings'].append(dict(p['listings'][0], listing_id='aa:counter', ticker='COUNTER'))
        primary = self.bar(p)
        other = dict(primary, listing_id='aa:counter', volume=777)
        _, history = self.board(p, [other, primary])
        self.assertEqual(history[0]['primary_volume'], 100)
        _, history = self.board(p, [other])
        self.assertIsNone(history[0]['primary_volume'])

    def test_revised_holdings_replace_snapshot_but_empty_failure_preserves_it(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'holdings.jsonl.gz'
            keys = ('date', 'product_id', 'holding_id')
            rows = [dict(date='2026-09-03', product_id='X', holding_id=h) for h in ['a', 'b']]
            prior = dict(date='2026-09-02', product_id='X', holding_id='prior')
            upsert_history(path, [prior] + rows, keys)
            upsert_history(path, rows[:1], keys, replace_groups=('date', 'product_id'))
            before = path.read_bytes()
            upsert_history(path, [], keys, replace_groups=('date', 'product_id'))
            self.assertEqual(before, path.read_bytes())
            with gzip.open(path, 'rt') as f:
                self.assertEqual([json.loads(l)['holding_id'] for l in f], ['prior', 'a'])


if __name__ == '__main__':
    unittest.main()
