from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

from election_watch.governor_ny import collect, normalize, FIELDS, METADATA
from election_watch.superpac import SourceError
from build_superpac import atomic_json
from build_superpac_map import build


ROSTER = [{'name': 'Kathy C. Hochul', 'reported_name_aliases': ['Kathy Hochul'],
           'candidate_id': 'NY:certified:2026:governor:kathy-hochul', 'party': 'DEM'}]
FILERS = {'446033': {'name': 'Fair and Affordable New York', 'source_url': 'https://publicreporting.elections.ny.gov/'}}


def allocation(**changes):
    # Public API field names and parent linkage observed in the 2026 live data.
    row = dict(filer_id='446033', cand_comm_name='Fair and Affordable New York',
               election_year='2026', election_type='State/Local', filing_abbrev='D',
               r_amend='N', filing_sched_abbrev='R', filing_trans_id='10',
               trans_number='allocation-1', trans_mapping='payment-1',
               election_year_r='2026', office_desc='Governor',
               flng_ent_first_name='Kathy', flng_ent_last_name='Hochul',
               r_support_oppose='S', org_amt='100.25', sched_date='2026-09-04T00:00:00.000')
    return dict(row, **changes)


def payment(**changes):
    row = allocation(filing_sched_abbrev='F', trans_number='payment-1',
                     filing_trans_id='11', r_subcontractor='N', r_liability='N')
    return dict(row, **changes)


class NewYorkGovernorTests(unittest.TestCase):
    def test_unique_equal_payment_uses_explicit_direction_and_reviewed_alias(self):
        a, p = allocation(), payment()
        result = normalize(2026, [a], [a, p], 1791029456, ROSTER, FILERS)
        r = result['spending'][0]
        self.assertEqual((r['support_cents'], r['oppose_cents']), (10025, 0))
        self.assertEqual(r['party'], 'DEM')
        self.assertEqual(r['candidate_name'], 'Kathy C. Hochul')
        self.assertIsNone(r['filing_date'])
        a['r_support_oppose'] = 'O'
        r = normalize(2026, [a], [a, p], 1791029456, ROSTER, FILERS)['spending'][0]
        self.assertEqual((r['support_cents'], r['oppose_cents']), (0, 10025))

    def test_unlinked_cumulative_allocations_never_sum(self):
        rows = [allocation(trans_mapping='', org_amt='1000', filing_trans_id='1'),
                allocation(trans_mapping='', org_amt='2000', filing_trans_id='2')]
        r = normalize(2026, rows, [], 1791029456, ROSTER, FILERS)
        self.assertEqual(r['spending'], [])
        self.assertEqual(r['quality']['excluded_records']['unlinked_cumulative_allocation'], 2)

    def test_multiple_targets_duplicate_versions_and_mismatched_amounts_excluded(self):
        a, p = allocation(), payment()
        for linked in ([a, a, p], [a, p, p], [a, payment(org_amt='200')],
                       [a, payment(filing_abbrev='K')], [a, payment(r_amend='Y')]):
            self.assertEqual(normalize(2026, [a], linked, 1791029456, ROSTER, FILERS)['spending'], [])

    def test_amended_flag_is_not_a_sort_key(self):
        a, p = allocation(r_amend='Y'), payment(r_amend='Y')
        self.assertEqual(len(normalize(2026, [a], [a, p], 1791029456, ROSTER, FILERS)['spending']), 1)
        self.assertEqual(normalize(2026, [a], [a, p, payment()], 1791029456, ROSTER, FILERS)['spending'], [])

    def test_subcontracted_and_liability_payments_count_paid_amount_once(self):
        a = allocation()
        for changes in ({'r_subcontractor': 'Y'}, {'r_liability': 'Y', 'owed_amt': '100000'}):
            result = normalize(2026, [a], [a, payment(**changes)], 1791029456, ROSTER, FILERS)
            self.assertEqual(result['spending'][0]['support_cents'], 10025)

    def test_unknown_spender_candidate_and_direction_excluded(self):
        for changes in ({'filer_id': 'unknown'}, {'flng_ent_last_name': 'Other'}, {'r_support_oppose': 'Y'}):
            a = allocation(**changes)
            self.assertEqual(normalize(2026, [a], [a, payment()], 1791029456, ROSTER, FILERS)['spending'], [])

    def test_duplicate_identity_fails_closed(self):
        a = allocation()
        with self.assertRaises(SourceError):
            normalize(2026, [a, a], [a, payment()], 1791029456, ROSTER, FILERS)

    def test_revision_change_during_collection_preserves_old_snapshot(self):
        reads = 0
        def fetch(url):
            nonlocal reads
            if url == METADATA:
                reads += 1
                return {'rowsUpdatedAt': 100 + reads, 'columns': [{'fieldName': f} for f in FIELDS]}
            where = parse_qs(urlparse(url).query)['$where'][0]
            return [allocation()] if "office_desc='Governor'" in where else [allocation(), payment()]
        with self.assertRaisesRegex(SourceError, 'dataset changed'):
            collect(2026, ROSTER, {'cycle': 2026, 'verified_on': '2026-10-04',
                    'filers': [{'filer_id': key, **value} for key, value in FILERS.items()]}, fetch)

    def test_map_preserves_amounts_and_partial_coverage_without_federal_claim(self):
        roster = [dict(ROSTER[0], office='G', state='NY', district=None, election_year=2026)]
        a = allocation()
        source = normalize(2026, [a], [a, payment()], 1791029456, roster, FILERS)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            atomic_json(root / 'usa_governor_finance/2026/NY.json', source)
            catalog = build(root)
            national = json.loads((root / catalog['cycles']['2026']['national_file']).read_text())
            state = json.loads((root / national['states']['NY']['data_file']).read_text())
            summary = next(r for r in state['races'] if r['office'] == 'governor')
            race = json.loads((root / summary['data_file']).read_text())
            self.assertEqual(race['status'], 'partial')
            self.assertEqual(race['totals_by_reported_party']['DEM']['state_independent_spender_unclassified']['support_cents'], 10025)
            self.assertIsNone(race['totals_by_category']['super_pac']['support_cents'])
            self.assertEqual(race['source_limitations_ko'], source['limitations_ko'])
            self.assertEqual(race['amount_basis'], 'gross_disclosed_payments_refunds_not_netted')


if __name__ == '__main__':
    unittest.main()
