import importlib.util
from pathlib import Path
from datetime import date
import unittest
import json
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('collect', Path(__file__).resolve().parents[1] / 'collect.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ContractTests(unittest.TestCase):
    def test_null_not_zero(self):
        self.assertIsNone(m.number(''))
        self.assertEqual(m.number('0'), 0)
        for value in ('NaN', 'Infinity', '-1'):
            with self.assertRaises(m.SourceError):
                m.stock(value)

    def test_gap_not_weekly_change(self):
        r = m.series('x', 'eia', 'US', 'x', 'underground', 'Bcf', 'weekly', 'test',
                     [{'period': '2026-08-07', 'value': 10}, {'period': '2026-08-28', 'value': 20}])
        self.assertIsNone(m.finalize(r, {}, date(2026, 9, 9))['change'])

    def test_error_retains_date_and_status(self):
        old = m.series('x', 'eia', 'US', 'x', 'underground', 'Bcf', 'weekly', 'test',
                       [{'period': '2026-08-28', 'value': 20}])
        new = {**old, 'status': 'error', 'observations': []}
        result = m.finalize(new, {'x': old}, date(2026, 9, 9))
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['latest']['period'], '2026-08-28')
        self.assertTrue(result['retained_previous_observations'])

    def test_gie_auth_error_is_not_empty_success(self):
        with self.assertRaises(m.SourceError):
            m.parse_gie({'error': 'access denied', 'data': []}, 'agsi', 'DE')

    def test_agsi_no_data_and_alsi_units(self):
        row = {'code': 'DE', 'gasDayStart': '2026-09-08', 'gasInStorage': '0', 'status': 'N'}
        self.assertIsNone(m.parse_gie({'data': [row]}, 'agsi', 'DE')['observations'][0]['value'])
        lng = {'code': 'BE', 'gasDayStart': '2026-09-08', 'inventory': {'lng': '80', 'gwh': '500'}, 'dtmi': {'lng': '100', 'gwh': '625'}}
        result = m.parse_gie({'data': [lng]}, 'alsi', 'BE')
        self.assertEqual(result['unit'], 'thousand_m3_LNG')
        self.assertEqual(result['observations'][0]['fill_pct'], 80)


    def test_rehden_requires_facility_identity(self):
        row = {'code': '21Z000000000271O', 'gasDayStart': '2026-09-07',
               'gasInStorage': '3.2801', 'status': 'C'}
        good = m.parse_gie({'data': [row]}, 'agsi', 'REHDEN', '21Z000000000271O')
        self.assertEqual(good['country'], 'DE')
        self.assertEqual(good['observations'][0]['value'], 3.2801)
        row['code'] = 'DE'
        with self.assertRaises(m.SourceError):
            m.parse_gie({'data': [row]}, 'agsi', 'REHDEN', '21Z000000000271O')

    def test_henry_spot_and_safe_failure(self):
        row = {'series':'RNGWHHD','period':'2026-09-01','value':'2.9','units':'$/MMBTU'}
        def fetch(url):
            self.assertIn('/natural-gas/pri/fut/data/', url)
            return json.dumps({'response':{'data':[row]}}).encode()
        with patch.dict(m.os.environ, {'EIA_API_KEY':'TEST_SECRET'}):
            good = m.collect_benchmarks(fetch, {}, date(2026,9,9))
            self.assertEqual(good[0]['status'], 'ok')
            self.assertNotIn('TEST_SECRET', json.dumps(good))
            row['units'] = 'EUR/MWh'
            failed = m.collect_benchmarks(fetch, {'benchmarks':good}, date(2026,9,10))[0]
            self.assertEqual(failed['status'], 'error')
            self.assertEqual(failed['latest'], good[0]['latest'])

if __name__ == '__main__':
    unittest.main()
