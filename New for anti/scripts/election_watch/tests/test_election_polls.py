"""Regression checks for false evidence, misleading denominators and publication."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from election_watch.polls import read, validate, build
from monitor_election_polls import check_document, fingerprint


class PollContractTests(unittest.TestCase):
    def setUp(self):
        self.data = read(ROOT / 'config/usa_polls/2026.json')
        self.tmp = tempfile.TemporaryDirectory()
        self.public = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def race(self, rid, day='2026-09-10', monitor=None):
        national = build(self.data, self.public, day, monitor)
        state = read(self.public / national['states'][rid.split(':')[1]]['path'])
        return read(self.public / state['races'][rid]['path'])

    def test_empty_is_not_zero_or_no_election(self):
        r = self.race('USA:TN:governor')
        self.assertEqual(r['status'], 'no_verified_poll')
        self.assertEqual(r['observations'], [])
        self.assertIsNone(r['poll_average_pct'])
        self.assertEqual(r['election_schedule_status'], 'not_verified_by_this_dataset')

    def test_question_denominators_rounding_and_hypotheticals(self):
        rows = self.race('USA:FL:senate')['observations']
        r = next(p for p in rows if 'vindman' in p['id'])
        self.assertEqual((r['sample_n'], r['question_n']), (786, 772))
        self.assertEqual(r['uncertainty']['scope'], 'survey')
        self.assertEqual(r['answer_total_pct'], 101)
        self.assertFalse(r['headline_eligible'])
        self.assertEqual(self.race('USA:GA:senate')['independent_survey_count'], 1)

    def test_population_subsets_are_one_survey(self):
        r = self.race('USA:WI:governor')
        self.assertEqual(r['independent_survey_count'], 1)
        self.assertEqual(len(r['observations']), 2)
        self.assertEqual(len(r['headline_observation_ids']), 1)
        self.assertEqual({p['question_n'] for p in r['observations']}, {738, 891})

    def test_refresh_does_not_make_old_poll_new(self):
        r = self.race('USA:NY:governor', '2026-12-01')
        self.assertEqual(r['headline_observation_ids'], [])
        self.assertEqual(r['observations'][0]['freshness'], 'stale')
        self.assertEqual(r['observations'][0]['field_end'], '2026-08-06')

    def test_changed_source_keeps_evidence_but_blocks_headline(self):
        r = self.race('USA:NY:governor', monitor={'sources': {'ny': {'status': 'changed'}}})
        self.assertEqual(len(r['observations']), 1)
        self.assertEqual(r['headline_observation_ids'], [])

    def test_invalid_input_preserves_last_good_index(self):
        self.race('USA:NY:governor')
        before = (self.public / 'usa_election_polls_index_v1.json').read_bytes()
        self.data['observations'][0]['answers'][0]['pct'] = float('nan')
        with self.assertRaises(ValueError):
            build(self.data, self.public, '2026-09-10')
        self.assertEqual(before, (self.public / 'usa_election_polls_index_v1.json').read_bytes())

    def test_rejects_future_duplicate_unreviewed_and_wrong_n(self):
        changes = [lambda d: d['observations'].append(copy.deepcopy(d['observations'][0])),
                   lambda d: d['observations'][0].update(published_on='2027-01-01'),
                   lambda d: d['observations'][0].update(question_n=9999),
                   lambda d: d['observations'][0]['review'].update(status='pending'),
                   lambda d: d['observations'][0].update(question_wording_verified=False),
                   lambda d: d['observations'][0]['answers'].pop(),
                   lambda d: d['observations'][0]['answers'][0].update(candidate_id='guessed')]
        for change in changes:
            with self.subTest(change=change):
                d = copy.deepcopy(self.data)
                change(d)
                with self.assertRaises(ValueError):
                    validate(d, '2026-09-10')

    def test_small_candidate_not_erased_by_headline_rounding(self):
        r = self.race('USA:NC:house:01')['observations'][0]
        a = next(a for a in r['answers'] if a['label'] == 'Ashley-Nicole Russell')
        self.assertEqual(a['pct'], 0.5)
        self.assertFalse(r['headline_eligible'])

    def test_idempotent_build_and_old_cycles_survive(self):
        self.race('USA:NY:governor')
        before = {str(p): p.read_bytes() for p in self.public.rglob('*.json')}
        self.race('USA:NY:governor')
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.public.rglob('*.json')})
        index_path = self.public / 'usa_election_polls_index_v1.json'
        index = read(index_path)
        index['cycles']['2024'] = {'path': 'preserved-historical-index.json'}
        index_path.write_text(json.dumps(index))
        self.race('USA:NY:governor')
        self.assertIn('2024', read(index_path)['cycles'])

    def test_network_error_and_persistent_changed_baseline(self):
        entry = {'url': 'https://example.org/poll.pdf', 'format': 'pdf',
                 'reviewed_fingerprint': fingerprint(b'old', 'pdf')}
        def fail(_):
            raise TimeoutError('private error details')
        self.assertEqual(check_document(entry, fail)['status'], 'error')
        self.assertNotIn('private', str(check_document(entry, fail)))
        for _ in range(2):
            self.assertEqual(check_document(entry, lambda _: b'new')['status'], 'changed')
        self.assertEqual(check_document(entry, lambda _: b'old')['status'], 'unchanged')

    def test_article_monitor_ignores_random_related_posts_but_not_poll_edits(self):
        a = b'<div class="entry-content clr"><p>Candidate 49</p><div>n=811</div></div><aside>Old post</aside>'
        b = a.replace(b'Old post', b'Random post')
        self.assertEqual(fingerprint(a, 'html_article'), fingerprint(b, 'html_article'))
        self.assertNotEqual(fingerprint(a, 'html_article'), fingerprint(a.replace(b'49', b'48'), 'html_article'))
        with self.assertRaises(ValueError):
            fingerprint(b'<html>layout no longer supported</html>', 'html_article')


if __name__ == '__main__':
    unittest.main()
