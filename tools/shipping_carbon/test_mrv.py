import unittest
from collect_mrv import parse_rows, quantity

HEADER = ('IMO Number', 'Name', 'Ship type', 'Reporting Period', 'IMO Number', 'Name',
          'DoC issue date', 'Total CO₂ emissions [m tonnes]',
          'CO2 emissions to be reported under Directive 2003/87/EC [m tonnes]',
          'Total fuel consumption [m tonnes]')
ROW = ('1234567', 'TEST VESSEL', 'Container ship', '2025', '7654321', 'TEST COMPANY',
       'DoC not issued', 0, 'N/A', None)


class MRVTest(unittest.TestCase):
    def test_ship_company_and_missing_values(self):
        r = parse_rows([HEADER, ROW], 'full', '2025 Full ERs')[0]
        self.assertEqual(r['imo'], '1234567')
        self.assertEqual(r['name'], 'TEST VESSEL')
        self.assertEqual(r['company'], 'TEST COMPANY')
        self.assertEqual(r['total_co2_t'], '0')
        self.assertIsNone(r['ets_reported_co2_t'])
        self.assertIsNone(r['fuel_t'])
        self.assertEqual(r['doc_issue_date'], 'DoC not issued')

    def test_full_partial_same_ship_are_distinct_records(self):
        full = parse_rows([HEADER, ROW], 'full', '2025 Full ERs')[0]
        partial = parse_rows([HEADER, ROW], 'partial', '2025 Partial ERs')[0]
        self.assertNotEqual(full['record_id'], partial['record_id'])
        self.assertEqual(partial['report_scope'], 'partial')

    def test_bad_header_and_numeric_values_rejected(self):
        with self.assertRaises(ValueError):
            parse_rows([['unknown']], 'full', 'changed')
        for value in ('NaN', '-1', 'not-a-number'):
            with self.assertRaises(ValueError):
                quantity(value)


if __name__ == '__main__':
    unittest.main()
