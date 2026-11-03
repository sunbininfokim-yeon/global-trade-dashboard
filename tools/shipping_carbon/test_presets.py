import unittest
from decimal import Decimal as D
from engine import calculate, defaults
from presets import catalog


class PresetTest(unittest.TestCase):
    def test_provisional_transactions_remain_explicit_assumptions(self):
        c = catalog({})
        self.assertEqual(c['benchmark']['status'], 'missing')
        for preset in c['presets']:
            result = calculate({**defaults({}), **preset['inputs']}, {})
            self.assertEqual(result['shipowner']['procurement_gap_eua'], D(preset['demand_eua']))
            self.assertEqual(result['dealer']['hedge_eua'], D(preset['demand_eua']))
            self.assertEqual(result['dealer']['initial_margin_eur'], D(preset['initial_margin_eur']))
            self.assertEqual(preset['quality'], 'assumed_transaction_not_firm_position')

    def test_benchmark_excludes_partial_missing_and_zero(self):
        def row(v, scope='full', kind='Container ship'):
            return {'report_scope': scope, 'ship_type': kind, 'ets_reported_co2_t': v}
        c = catalog({'reporting_year': 2025, 'records': [row('100'), row('200'), row('300'),
            row('9999','partial'), row('0'), row(None), row('8888',kind='Bulk carrier')]})
        self.assertEqual(c['benchmark']['count'], 3)
        self.assertEqual(c['benchmark']['quantiles']['0.5'], '200')
        self.assertNotEqual(c['benchmark']['unit'], 'EUA')


if __name__ == '__main__':
    unittest.main()
