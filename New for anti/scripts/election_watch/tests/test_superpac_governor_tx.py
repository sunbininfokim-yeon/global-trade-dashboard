import csv
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch
import build_governor_finance

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
        self.assertEqual([r['party'] for r in payload['unclassified_spending']], ['REP', 'UNKNOWN'])
        self.assertEqual(payload['unclassified_spending'][0]['candidate_id'], roster[0]['candidate_id'])

    def test_single_governor_beneficiary_is_audit_only_without_direction(self):
        payload = normalize(2026, lines(candidate()), 'etag')
        self.assertEqual(payload['status'], 'needs_direction_review')
        self.assertEqual(payload['quality']['included_records'], 1)
        row = payload['unclassified_spending'][0]
        self.assertEqual(row['amount_cents'], 10025)
        self.assertIsNone(row['direction'])
        self.assertNotIn('support_cents', row)
        self.assertEqual(payload['spending'], [])
        self.assertEqual(row['party'], 'UNKNOWN')
        self.assertEqual(row['candidate_identity_status'], 'reported_name_only_unverified')
        self.assertEqual(row['monthly']['2026-09']['amount_cents'], 10025)

    def test_multiple_targets_are_not_double_counted(self):
        payload = normalize(2026, lines(candidate(), candidate(**{'25': 'Taylor'})), 'etag')
        self.assertEqual(payload['unclassified_spending'], [])
        self.assertEqual(payload['quality']['excluded_records']['multi_target_or_duplicate_expenditure'], 2)

    def test_corrections_office_and_cycle_are_excluded(self):
        payload = normalize(2026, lines(candidate(**{'5': 'Y'}), candidate(**{'9': '457', '34': 'STATESEN'}),
                                        candidate(**{'9': '458', '11': '20240101'})), 'etag')
        self.assertEqual(payload['unclassified_spending'], [])
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

    def test_audit_payload_cannot_replace_public_finance_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'usa_governor_finance/2026/TX.json'
            path.parent.mkdir(parents=True)
            path.write_text('existing validated snapshot')
            audit = normalize(2026, lines(candidate()), 'etag')
            args = ['build_governor_finance.py', '--cycle', '2026', '--state', 'TX', '--public', str(root)]
            with patch('sys.argv', args), patch('build_governor_finance.collect_tx', return_value=audit), redirect_stdout(io.StringIO()):
                self.assertEqual(build_governor_finance.main(), 1)
            self.assertEqual(path.read_text(), 'existing validated snapshot')


if __name__ == '__main__':
    unittest.main()
