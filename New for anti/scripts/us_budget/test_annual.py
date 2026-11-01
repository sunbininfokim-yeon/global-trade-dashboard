import unittest

import annual as a


class AnnualTests(unittest.TestCase):
    def test_discovery_uses_all_six_official_links_in_same_vintage(self):
        links = ''.join(f'<a href="/wp-content/uploads/2027/02/{prefix}_fy2028.xlsx">table</a>'
                        for prefix in a.PATTERNS.values())
        result = a.discover(lambda _: links.encode())
        self.assertEqual(result['proposal_fy'], 2028)
        self.assertEqual(result['publication'], '2027/02')  # No guessed April URL.
        self.assertEqual(len(result['urls']), 6)

    def test_newest_partial_vintage_cannot_fall_back_to_old_complete_set(self):
        links = ''.join(f'<a href="https://www.whitehouse.gov/wp-content/uploads/2026/04/{prefix}_fy2027.xlsx">x</a>'
                        for prefix in a.PATTERNS.values())
        links += '<a href="/wp-content/uploads/2027/03/hist01z1_fy2028.xlsx">new</a>'
        with self.assertRaisesRegex(a.AnnualError, 'incomplete'):
            a.discover(lambda _: links.encode())

    def test_nonofficial_or_midsession_links_are_not_a_government_proposal(self):
        links = b'<a href="https://example.com/wp-content/uploads/2027/02/hist01z1_fy2028.xlsx">x</a>'
        with self.assertRaises(a.AnnualError): a.discover(lambda _: links)

    def test_missing_amounts_are_not_zero_and_negative_amounts_are_kept(self):
        for value in [None, '..........', '*', 'NaN', float('nan'), True]:
            with self.assertRaises(a.AnnualError): a.money(value)
        self.assertEqual(a.money(-7), -7000000)
        self.assertEqual(a.money(0), 0)
        self.assertEqual(a.money(1, a.THOUSAND), 1000)

    def test_actual_and_estimate_years_never_share_a_lookup(self):
        rows = [('title',), ('units',), ('Category', '2026', '2027 estimate')]
        self.assertEqual(a.column(rows, 2026, False), 1)
        with self.assertRaises(a.AnnualError): a.column(rows, 2026, True)
        rows.append(('2026 estimate', 10))
        self.assertTrue(a.dated_rows(rows)[2026][1])

    def test_layout_drift_and_incomplete_detail_rollups_fail(self):
        with self.assertRaises(a.AnnualError): a.row_at([('New row',)], 0, 'Old row')
        with self.assertRaises(a.AnnualError):
            a.tree_check(dict(value=10, prior=9, children=[dict(value=8, prior=9, children=[])]))

    def test_receipts_keep_the_same_taxonomy_across_years_and_sources(self):
        rows = [dict(name=name, value=1) for name in ['Individual Income Taxes', 'Social Insurance and Retirement Receipts:',
                'Corporation Income Taxes', 'Excise Taxes', 'Estate and Gift Taxes', 'Customs Duties', 'Miscellaneous Receipts']]
        groups = a.receipt_groups(rows)
        self.assertEqual(len(groups), 5)
        self.assertEqual(groups[0]['name'], '개인소득세')
        self.assertEqual(groups[-1]['value'], 3)
        with self.assertRaises(a.AnnualError): a.receipt_groups(rows[:-1])

    def test_same_account_number_in_distinct_treasury_agencies_is_not_merged(self):
        header=['Agency Code','Agency Name','Bureau Code','Bureau Name','Account Code','Account Name',
                'Treasury Agency Code','CGAC Agency Code','BEA Category','2026','2027']
        rows=[header,['902','Offsets','00','Offsets','977120','Trust interest','75','075','Net interest',-3,-4],
              ['902','Offsets','00','Offsets','977120','Worker compensation interest','16','016','Net interest',0,-2]]
        details=a.agency_accounts(rows,2027,True)
        leaves=details['interest'][0]['children'][0]['children']
        self.assertEqual(len(leaves),2)
        self.assertNotEqual(leaves[0]['id'],leaves[1]['id'])
        self.assertEqual(details['totals']['interest'],-6000)
        self.assertEqual(details['baseline_status'],'estimate')


if __name__ == '__main__': unittest.main()
