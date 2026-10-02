import csv
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from election_watch.governor_tx import normalize, collect
from election_watch.superpac import SourceError


def candidate(**changes):
    row = [''] * 40
    for index, value in {0: 'CAND', 1: 'DCE', 3: '900', 4: '20260930', 5: 'N',
                         6: '123', 8: 'Independent spender', 9: '456', 11: '20260920',
                         12: '100.25', 23: 'Sample', 25: 'Alex', 34: 'GOVERNOR'}.items():
        row[index] = value
    for index, value in changes.items():
        row[int(index)] = value
    return row


def lines(*rows):
    output = io.StringIO()
    csv.writer(output).writerows(rows)
    output.seek(0)
    return output


class TexasGovernorTests(unittest.TestCase):
    def test_exact_certified_general_name_assigns_party_without_guessing_others(self):
        roster = [{'candidate_id': 'TX:certified:2026:governor:greg-abbott', 'name': 'Greg Abbott',
                   'party': 'REP', 'office': 'G', 'state': 'TX', 'district': None, 'election_year': 2026}]
        payload = normalize(2026, lines(candidate(**{'25': 'Greg', '23': 'Abbott'}),
                                        candidate(**{'9': '457', '25': 'G.', '23': 'Abbott'})), 'etag', roster)
        self.assertEqual([r['party'] for r in payload['spending']], ['REP', 'UNKNOWN'])
        self.assertEqual(payload['spending'][0]['candidate_id'], roster[0]['candidate_id'])

    def test_single_governor_beneficiary_is_partial_support_only(self):
        payload = normalize(2026, lines(candidate()), 'etag')
        self.assertEqual(payload['status'], 'partial')
        self.assertEqual(payload['quality']['included_records'], 1)
        row = payload['spending'][0]
        self.assertEqual((row['support_cents'], row['oppose_cents']), (10025, 0))
        self.assertEqual(row['party'], 'UNKNOWN')
        self.assertEqual(row['candidate_identity_status'], 'reported_name_only_unverified')
        self.assertEqual(row['monthly']['2026-09']['support_cents'], 10025)

    def test_multiple_targets_are_not_double_counted(self):
        payload = normalize(2026, lines(candidate(), candidate(**{'25': 'Taylor'})), 'etag')
        self.assertEqual(payload['spending'], [])
        self.assertEqual(payload['quality']['excluded_records']['multi_target_or_duplicate_expenditure'], 2)

    def test_corrections_office_and_cycle_are_excluded(self):
        payload = normalize(2026, lines(candidate(**{'5': 'Y'}), candidate(**{'9': '457', '34': 'STATESEN'}),
                                        candidate(**{'9': '458', '11': '20240101'})), 'etag')
        self.assertEqual(payload['spending'], [])
        self.assertEqual(sum(payload['quality']['excluded_records'].values()), 3)

    def test_unknown_schema_or_flag_fails_closed(self):
        with self.assertRaises(SourceError):
            normalize(2026, lines(candidate()[:-1]), 'etag')
        with self.assertRaises(SourceError):
            normalize(2026, lines(candidate(**{'5': 'UNKNOWN'})), 'etag')

    def test_local_official_archive_path_uses_same_parser(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'TEC_CF_CSV.zip'
            output = lines(candidate()).getvalue()
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('cand.csv', output)
            payload = collect(2026, path)
            self.assertEqual(payload['quality']['included_records'], 1)
            self.assertTrue(payload['dataset_revision'].startswith('local:'))


if __name__ == '__main__':
    unittest.main()
