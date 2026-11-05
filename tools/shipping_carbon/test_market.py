import unittest
from datetime import date
from collect_market import parse_oi_rows


class OiTests(unittest.TestCase):
    def rows(self):
        return [[None, ' 10/29/2026'],
                [None, 'Contract', 'Expiry', None, 'P/C', 'Strike', 'Open Interest', 'Synthetic Net OI'],
                [None, 'FEUA', 12, 2026, None, 0, 300, 100],
                [None, 'OEUB', 12, 2026, 'C', 90, 20, 10],
                [None, 'FEUA', None, None, None, None, 300, 100]]

    def test_futures_only_no_total_double_count(self):
        s = parse_oi_rows(self.rows(), date(2026, 11, 2))
        self.assertEqual(s['observation_date'], '2026-10-29')
        self.assertEqual(len(s['records']), 1)
        self.assertEqual(s['records'][0]['gross_oi_lots'], 300)
        self.assertEqual(s['records'][0]['eex_synthetic_net_oi_lots'], 100)

    def test_future_ambiguous_date_and_duplicate_expiry_rejected(self):
        with self.assertRaises(ValueError):
            parse_oi_rows(self.rows(), date(2026, 10, 28))
        with self.assertRaises(ValueError):
            parse_oi_rows([['10/28/2026']] + self.rows(), date(2026, 11, 2))
        with self.assertRaises(ValueError):
            parse_oi_rows(self.rows() + [self.rows()[2]], date(2026, 11, 2))

    def test_invalid_lot_rejected(self):
        rows = self.rows(); rows[2][6] = -1
        with self.assertRaises(ValueError):
            parse_oi_rows(rows, date(2026, 11, 2))


if __name__ == '__main__':
    unittest.main()
