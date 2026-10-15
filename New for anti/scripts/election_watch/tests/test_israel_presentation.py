import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from election_watch.israel_analysis import build, read_inputs
from election_watch.israel_translation import collect_input_texts, input_digest, text_id, translate, validate_translations

INPUT = Path(__file__).resolve().parents[1] / 'config/israel/2026'


class IsraelPresentationTests(unittest.TestCase):
    def setUp(self):
        self.inputs = read_inputs(INPUT)
        self.context = self.inputs['coalition_context.json']
        self.items = collect_input_texts(self.inputs, self.context)
        self.doc = self.inputs['ko_translations.json']

    def build(self):
        return build(self.inputs, '2026-10-14', '2026-10-15T06:00:00+00:00')

    def test_translation_coverage_and_provenance_without_api(self):
        with patch('election_watch.israel_translation.urlopen') as api:
            validate_translations(self.doc, self.items)
        api.assert_not_called()
        self.assertEqual(len(self.items), 227)
        self.assertEqual(self.doc['provider'], 'Google Gemini API')
        self.assertTrue(all(row['model'] and row['translated_at'] for row in self.doc['translations']))

    def test_translation_source_change_or_missing_item_blocks_publication(self):
        self.context['relationships'][0]['summary'] += ' changed'
        with self.assertRaisesRegex(ValueError, 'match source'):
            self.build()
        self.setUp(); self.doc['translations'].pop()
        with self.assertRaisesRegex(ValueError, 'coverage'):
            self.build()

    def test_translation_cannot_reassign_identity_or_keep_foreign_primary_text(self):
        row = self.doc['translations'][0]
        row['source'] = 'another person'
        with self.assertRaisesRegex(ValueError, 'identity'):
            self.build()
        self.setUp(); self.doc['translations'][0]['ko'] = 'N12'
        with self.assertRaisesRegex(ValueError, 'Korean'):
            self.build()

    def test_context_needs_known_parties_safe_colors_and_sources(self):
        for key, value, error in [('list_id', 'unknown', 'unknown'), ('group', 'unknown', 'unknown'), ('source_ids', ['absent'], 'source')]:
            with self.subTest(key=key):
                self.setUp(); self.context['parties'][0][key] = value
                with self.assertRaisesRegex(ValueError, error):
                    self.build()
        self.setUp(); self.context['groups'][0]['color'] = 'red; background:url(x)'
        with self.assertRaisesRegex(ValueError, 'color'):
            self.build()

    def test_ideology_cannot_invent_a_family_or_omit_sources(self):
        for key, value, error in [('ideology_group', 'invented', 'ideology'),
                                  ('ideology_source_ids', [], 'source')]:
            with self.subTest(key=key):
                self.setUp(); self.context['parties'][0][key] = value
                with self.assertRaisesRegex(ValueError, error):
                    self.build()
        self.setUp(); self.context['ideology_groups'][0]['color'] = 'url(x)'
        with self.assertRaisesRegex(ValueError, 'color'):
            self.build()

    def test_cooperation_pair_rejects_unknown_or_cross_group_parties(self):
        self.context['cooperation_pairs'][0]['parties'] = ['k26:מחל', 'k26:ל']
        with self.assertRaisesRegex(ValueError, 'cooperation pair'):
            self.build()
        self.setUp(); self.context['cooperation_pairs'][0]['source_ids'] = ['missing']
        with self.assertRaisesRegex(ValueError, 'cooperation source'):
            self.build()

    def test_refusal_preserves_target_person_and_does_not_become_party_ban(self):
        row = next(r for r in self.context['relationships'] if r['kind'] == 'refusal')
        self.assertEqual(row['target_person'], 'Benjamin Netanyahu')
        row.pop('target_person')
        with self.assertRaisesRegex(ValueError, 'person'):
            self.build()

    def test_presentation_cannot_mutate_numeric_truth_or_promote_held_records(self):
        original = copy.deepcopy(self.inputs['poll_observations.jsonl'])
        board = self.build()
        self.assertEqual(board['observations'], [r for r in original if r.get('record_type') == 'observation'])
        self.assertEqual(board['evidence_as_of'], '2026-10-14')
        self.assertEqual(board['coalition_context']['reviewed_on'], '2026-10-15')
        self.assertIsNone(board['rules']['threshold_pct'])
        self.assertFalse(board['coverage_complete'])
        self.assertNotIn('API_KEY', json.dumps(board))

    def test_api_failure_keeps_existing_cache_and_does_not_publish_partial(self):
        before = copy.deepcopy(self.doc)
        items = self.items + [{'id': text_id('New public label'), 'text': 'New public label'}]
        with patch('election_watch.israel_translation.urlopen', side_effect=HTTPError('https://example.org', 403, 'hidden', {}, None)):
            with self.assertRaisesRegex(ValueError, 'HTTP 403'):
                translate(items, 'test-only-key', previous=self.doc)
        self.assertEqual(self.doc, before)

    def test_complete_cache_reuses_translations_without_network(self):
        with patch('election_watch.israel_translation.urlopen') as api:
            doc = translate(self.items, 'test-only-key', previous=self.doc)
        api.assert_not_called()
        self.assertEqual(doc['input_sha256'], input_digest(self.items))
        self.assertEqual(len(doc['translations']), len(self.items))


if __name__ == '__main__':
    unittest.main()
