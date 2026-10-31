"""Frozen reported-count contracts, independent of the next production update."""
import copy
import hashlib
import json
import unittest
from pathlib import Path
from election_watch.israel_results import validate_results

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / 'tests/fixtures/israel/2026-10-31/post_election.json').read_text())
KNOWN = {v['list_id'] for v in DATA['result_record']['values']}


class IsraelResultsTests(unittest.TestCase):
    def test_reported_count_is_partial_and_totals_120(self):
        self.assertEqual(validate_results(copy.deepcopy(DATA), KNOWN), DATA)
        self.assertEqual(DATA['result_record']['values'][0]['seats'], 27)

    def test_rejects_invalid_counts_and_unsupported_certification(self):
        mutations = [
            lambda d: d['result_record']['values'][0].update(seats=28),
            lambda d: d['result_record']['values'].append(d['result_record']['values'][0]),
            lambda d: d['result_record']['values'][0].update(list_id='unknown'),
            lambda d: d['result_record']['votes'].update(valid=1),
            lambda d: d['result_record']['bloc_as_published'].update(arab=18),
            lambda d: d.update(official_table_verified=True),
            lambda d: d.update(government_formed=False),
            lambda d: d.update(mandate_holder='unverified winner'),
            lambda d: d['result_record'].update(review_status='accepted'),
            lambda d: d['steps'][1].update(date='2026-11-11'),
            lambda d: d['steps'][0].update(source_ids=['cec-table']),
        ]
        for mutation in mutations:
            data = copy.deepcopy(DATA)
            mutation(data)
            with self.subTest(data=data), self.assertRaises(ValueError):
                validate_results(data, KNOWN)

    def test_current_result_is_identical_to_preserved_research_record(self):
        current = json.loads((ROOT / 'config/israel/2026/post_election.json').read_text())
        repo = ROOT.parents[2]
        raw = repo / current['upstream']['path']
        self.assertEqual(hashlib.sha256(raw.read_bytes()).hexdigest(), current['upstream']['sha256'])
        row = next(r for r in map(json.loads, raw.read_text().splitlines())
                   if r.get('poll_id') == current['upstream']['poll_id'])
        self.assertEqual(current['result_record'], row)
