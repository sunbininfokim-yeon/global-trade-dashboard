import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from election_watch.israel_analysis import build, health, read_inputs

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / 'config/israel/2026'
BUILT = '2026-10-14T12:00:00+00:00'


class IsraelAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.inputs = read_inputs(INPUT)

    def board(self):
        return build(self.inputs, '2026-10-14', BUILT)

    def seat(self):
        return next(row for row in self.inputs['poll_observations.jsonl']
                    if row.get('question_id') == 'reported_seats' and row.get('review_status') == 'accepted')

    def test_research_counts_and_original_numbers(self):
        board = self.board()
        self.assertEqual(board['coverage'], {'accepted_seat_polls': 6, 'partial_seat_polls': 3,
                         'held_seat_polls': 2, 'reported_lists': 38, 'sources': 56})
        expected = {'midgam-n12-2026-10-05': 501, 'midgam-n12-2026-10-12': 509,
                    'lazar-maariv-2026-10-07': 700, 'direct-polls-i24-2026-10-07': 518,
                    'midgam-n12-2026-09-22': 501, 'kantar-israelhayom-2026-10-07': 555}
        seats = [r for r in board['observations'] if r['question_id'] == 'reported_seats' and r['review_status'] == 'accepted']
        self.assertEqual({r['poll_id']: r['n_respondents'] for r in seats}, expected)
        self.assertTrue(all(sum(v['seats'] for v in row['values']) == 120 for row in seats))
        self.assertFalse(board['automatic_refresh'])
        self.assertIsNone(board['current_seats'])
        self.assertIsNone(board['rules']['threshold_pct'])
        self.assertEqual(board['list_review_status'], 'partial')
        self.assertEqual(board['evidence_as_of'], '2026-10-14')

    def test_inputs_and_dates_are_not_mutated_by_rebuild(self):
        original = copy.deepcopy(self.inputs)
        first = self.board()
        later = build(self.inputs, '2026-10-14', '2026-10-15T12:00:00+00:00')
        self.assertEqual(self.inputs, original)
        self.assertEqual(first['observations'], later['observations'])
        self.assertEqual(first['evidence_as_of'], later['evidence_as_of'])

    def test_rebuild_cannot_advance_evidence_date(self):
        with self.assertRaisesRegex(ValueError, 'advance research'):
            build(self.inputs, '2026-10-15', BUILT)

    def test_sum_failure_is_rejected(self):
        self.seat()['values'][0]['seats'] += 1
        with self.assertRaisesRegex(ValueError, '120'):
            self.board()

    def test_duplicate_list_and_unknown_list_are_rejected(self):
        self.seat()['values'][1]['list_id'] = self.seat()['values'][0]['list_id']
        with self.assertRaisesRegex(ValueError, 'duplicate list'):
            self.board()
        self.setUp(); self.seat()['values'][0]['list_id'] = 'unknown-list'
        with self.assertRaisesRegex(ValueError, 'unknown'):
            self.board()

    def test_missing_and_boolean_seats_are_not_zero(self):
        for bad in (None, True, -1, 1.5):
            self.setUp(); self.seat()['values'][0]['seats'] = bad
            with self.assertRaisesRegex(ValueError, 'invalid reported seat'):
                self.board()

    def test_duplicate_observation_is_rejected(self):
        self.inputs['poll_observations.jsonl'].append(copy.deepcopy(self.seat()))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.board()

    def test_wrong_cycle_and_future_fieldwork_are_rejected(self):
        self.seat()['cycle'] = 'knesset-25'
        with self.assertRaisesRegex(ValueError, 'cycle'):
            self.board()
        self.setUp(); self.seat()['field_end'] = '2026-10-15'
        with self.assertRaisesRegex(ValueError, 'after evidence'):
            self.board()

    def test_percent_zero_is_preserved_without_filling_missing_seats(self):
        board = self.board()
        share = next(r for r in board['observations'] if r['poll_id'] == 'midgam-n12-2026-10-05' and r['question_id'] == 'party_vote_share')
        self.assertEqual(share['values'][-1]['pct'], 0)
        self.assertFalse(any(v['list_id'] == 'k26:ך' for v in self.seat()['values']))

    def test_held_numbers_cannot_be_promoted(self):
        row = next(r for r in self.inputs['poll_observations.jsonl'] if r.get('review_status') == 'held' and r.get('question_id') == 'reported_seats')
        row['values'] = [{'list_id': 'k26:מחל', 'seats': 20}]
        with self.assertRaisesRegex(ValueError, 'held'):
            self.board()

    def test_url_and_averaging_policy(self):
        self.seat()['source_url'] = 'javascript:alert(1)'
        with self.assertRaisesRegex(ValueError, 'HTTPS'):
            self.board()
        self.setUp(); self.seat()['average_eligible'] = True
        with self.assertRaisesRegex(ValueError, 'averaging'):
            self.board()

    def test_broadcaster_copy_does_not_become_court_host_original(self):
        doc = self.board()['judgment_copy']
        self.assertTrue(doc['document_copy_read'])
        self.assertFalse(doc['court_host_original_opened'])
        self.assertFalse(doc['full_reasons_opened'])

    def test_health_hash_matches_serialized_board(self):
        board = self.board()
        body = json.dumps(board, ensure_ascii=False, indent=2) + '\n'
        self.assertEqual(health(board)['board_sha256'], hashlib.sha256(body.encode()).hexdigest())

    def test_failed_cli_replay_preserves_last_good_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'israel_election_analysis_v1.json'
            cmd = [sys.executable, str(ROOT/'build_israel_analysis.py'), '--output', str(out), '--built-at', BUILT]
            subprocess.run(cmd, check=True, capture_output=True)
            before = {p.name: p.read_bytes() for p in Path(tmp).iterdir()}
            failed = subprocess.run(cmd + ['--as-of', '2026-10-15'], capture_output=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(before, {p.name: p.read_bytes() for p in Path(tmp).iterdir()})


if __name__ == '__main__':
    unittest.main()
