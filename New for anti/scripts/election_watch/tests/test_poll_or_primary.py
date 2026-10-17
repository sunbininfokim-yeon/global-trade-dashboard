"""Oregon official lists, primary ballot question and bounded future discovery."""
from copy import deepcopy
import hashlib
import io
from pathlib import Path
import unittest

from election_watch.ballot_or import merge_lists, parse_list_page
from election_watch.governor_matchups import apply_matchups
from election_watch.live_polls import apply_watchlist, normalize, summarize
from election_watch.poll_targets import apply_targets
from election_watch.poll_primary_supplements import merge_primary_supplements
from election_watch.polls import read
from election_watch.state_evidence import build_state, load_finance
from publish_state_packets import rebuild
from tests.poll_config_fixture import SNAPSHOT_DAY, PUBLIC_SNAPSHOT_DAY

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'config/usa_polls'
PUBLIC = ROOT.parents[1] / 'public/data'
DAY = '2026-10-14'


class OregonEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = read(PUBLIC / 'usa_election_poll_release_reviews/2026/OR-primary-20261014.json')
        cls.pages = cls.audit['official_candidate_list_pages']
        cls.policy = apply_targets(apply_matchups(apply_watchlist(read(CONFIG / 'live_2026.json'),
            read(CONFIG / 'watchlist_2026.json')), read(ROOT / 'config/governor_matchups/2026.json'), SNAPSHOT_DAY),
            read(CONFIG / 'targets_2026.json'), read(CONFIG / 'ballot_reviews_2026.json'), SNAPSHOT_DAY)
        cls.policy['quality_reviews'] = read(CONFIG / 'quality_reviews_2026.json')['reviews']
        cls.packet = read(ROOT / 'config/state_evidence/2026/OR.json')
        cls.raw = cls.packet['capture']['primary_records'][0]
        cls.entry = next(e for e in read(CONFIG / 'primary_supplements_2026.json')['records'] if e['state'] == 'OR')

    def test_four_official_books_cover_six_house_districts_and_21_nominees(self):
        result = merge_lists(self.pages)
        self.assertEqual(result, self.audit['official_candidates'])
        self.assertEqual(len(result), 8)
        self.assertEqual(sum(map(len, result.values())), 21)
        self.assertEqual(len(result['USA:OR:senate']), 4)
        self.assertEqual(len(result['USA:OR:governor']), 3)
        for rid in result:
            self.assertEqual(self.policy['races'][rid]['ballot_review']['source_role'], 'state_election_agency')
            self.assertFalse(self.policy['races'][rid]['ballot_competition']['general_unopposed'])

    def test_county_subset_conflicting_books_and_wrong_year_require_review(self):
        with self.assertRaisesRegex(ValueError, 'Incomplete'): merge_lists(self.pages[:1])
        changed = deepcopy(self.pages)
        changed[1]['text'] = changed[1]['text'].replace('Jeff Merkley', 'Different Nominee')
        with self.assertRaisesRegex(ValueError, 'Conflicting'): merge_lists(changed)
        for text, url in [(self.pages[0]['text'].replace('November 3, 2026', 'May 19, 2026'), self.pages[0]['source_url']),
                          (self.pages[0]['text'], self.pages[0]['source_url'].replace('VP_G26', 'VP_P26'))]:
            with self.assertRaises(ValueError): parse_list_page(text, url)

    def test_optional_statement_and_cross_nomination_do_not_remove_or_duplicate_names(self):
        result = merge_lists(self.pages)
        dye = next(c for c in result['USA:OR:senate'] if c['name'] == 'Gary Lyndon Dye')
        self.assertFalse(dye['pamphlet_statement_submitted'])
        drazan = next(c for c in result['USA:OR:governor'] if c['name'] == 'Christine Drazan')
        self.assertEqual(drazan['reported_party'], 'Republican, Libertarian')
        self.assertEqual(drazan['party'], 'REP')
        self.assertFalse(any(c['name'] == 'Greg Smith' for candidates in result.values() for c in candidates))

    def test_initial_question_preserves_third_candidate_rv_and_leaners_separately(self):
        observations, held = normalize([self.raw], self.policy, DAY)
        self.assertFalse(held)
        row = observations[0]
        self.assertEqual((row['population'], row['sample_n']), ('lv', 915))
        self.assertEqual({a['name']: a['pct'] for a in row['answers']},
                         {'Tina Kotek': 44, 'Christine Drazan': 46, 'Brett Smith': 3})
        self.assertEqual(next(a for a in row['answers'] if a['name'] == 'Brett Smith')['party'], 'GRE')
        facts = row['source_quality']['disclosure_review']
        self.assertEqual(facts['RV_initial_separate_not_imported']['sample_n'], 1000)
        self.assertEqual(facts['combined_leaner_toplines_not_imported']['Christine Drazan'], 47)
        self.assertTrue(facts['candidate_favorability_precedes_ballot'])
        self.assertIsNone(row['source_quality']['accuracy_grade'])

    def test_real_provider_discoveries_remain_held_without_fabricated_methods(self):
        rows = self.audit['provider_records_reviewed']
        accepted, held = normalize(rows, self.policy, DAY)
        self.assertFalse(accepted)
        self.assertEqual(len(held), 3)
        self.assertTrue(any('detailed_question_methodology' in r['reason'] for r in held))
        self.assertEqual(next(r for r in rows if r['id'] == 'gov202dhm2140107e')['end_date'], '2026-10-01')

    def test_expired_primary_wave_retained_without_recent_winner(self):
        observations, _ = normalize([self.raw], self.policy, DAY)
        for window in (7, 14):
            row = summarize(observations, self.policy['races']['USA:OR:governor'], DAY, window)
            self.assertEqual(row['pollster_count'], 0)
            self.assertIsNone(row['party'])
        self.assertEqual(observations[0]['field_end'], '2026-09-27')

    def test_new_verified_source_api_poll_can_join_unpolled_or05(self):
        raw = deepcopy(self.audit['records'][0]['provider_record'])
        raw.update(id='or05-future-test-fixture', subject='2026 OR-05', poll_type='us-representative',
            start_date='2026-10-12', end_date='2026-10-13', created_at=DAY,
            url='https://www.opb.org/article/2026/10/14/or05-fixture/',
            answers=[{'choice': 'Janelle Bynum', 'pct': 50}, {'choice': 'Patti Adair', 'pct': 45}])
        observations, rejected = normalize([raw], self.policy, DAY)
        self.assertFalse(rejected)
        self.assertEqual(observations[0]['race_id'], 'USA:OR:house:05')
        self.assertEqual(observations[0]['source_quality']['verification_level'], 'partial')
        raw['answers'][1]['choice'] = 'Lori Chavez-DeRemer'
        self.assertFalse(normalize([raw], self.policy, DAY)[0])

    def merge(self, providers=(), body=b'%PDF-reviewed'):
        entry = deepcopy(self.entry)
        entry['documents'][0]['sha256'] = hashlib.sha256(body).hexdigest()
        class Response(io.BytesIO):
            status = 200
            def geturl(self): return entry['documents'][0]['url']
        snapshot = read(CONFIG / 'primary_supplements_2026.json')
        snapshot['records'] = [entry]
        return merge_primary_supplements(list(providers), snapshot, DAY, ['OR'],
            lambda req, timeout: Response(body), reviewed_entries=[entry])

    def test_later_matching_api_wave_counts_once_and_changed_question_holds(self):
        later = deepcopy(self.entry['record']); later['id'] = 'later-or-api-fixture'
        rows, receipts = self.merge([later])
        self.assertEqual(len(rows), 1)
        self.assertEqual(receipts[0]['provider_duplicate_ids'], [later['id']])
        later['answers'][0]['pct'] = 46
        later['answers'][1]['pct'] = 47
        with self.assertRaisesRegex(ValueError, 'primary_and_provider_wave_conflict'): self.merge([later])

    def test_changed_document_loses_signal_without_redating_wave(self):
        raw = deepcopy(self.raw)
        raw['primary_source_capture']['status'] = 'carried_forward_reference_only'
        raw['primary_source_capture']['documents'][0]['status'] = 'changed_review_required'
        raw['primary_source_capture']['documents'][0]['sha256'] = '0' * 64
        observations, held = normalize([raw], self.policy, DAY)
        self.assertFalse(held)
        self.assertFalse(observations[0]['aggregation_eligibility']['eligible'])
        self.assertEqual(observations[0]['field_end'], '2026-09-27')

    def test_explicit_fec_id_links_do_not_turn_missing_money_into_zero(self):
        board, _ = rebuild(read(PUBLIC / 'usa_election_live_polls_v1.json'),
            read(PUBLIC / 'usa_election_poll_history_2026.json'), [self.packet], PUBLIC)
        finance = load_finance(PUBLIC / 'usa_election_finance_index_v1.json', 2026)
        state = build_state('OR', 'C', read(CONFIG / 'state_evidence_plan_2026.json'),
            read(CONFIG / 'targets_2026.json'), read(ROOT / 'config/federal_matchups/2026.json'),
            read(ROOT / 'config/governor_matchups/2026.json'), board, finance,
            read(ROOT / 'config/usa_state_campaign_finance_sources_v1.json'), PUBLIC_SNAPSHOT_DAY,
            read(CONFIG / 'state_finance_identities_2026.json'),
            governor_access={'OR': read(PUBLIC / 'usa_governor_source_access/2026/OR.json')})
        self.assertEqual(state['office_coverage']['house']['candidate_id_links'], 12)
        self.assertEqual(state['office_coverage']['senate']['candidate_id_links'], 4)
        senate = next(r for r in state['races'] if r['office'] == 'senate')
        smith = next(c for c in senate['candidates'] if c['name'] == 'David Brock Smith')
        self.assertEqual(smith['candidate_id'], 'S6OR05218')
        self.assertEqual(smith['finance']['reported_names'], ['SMITH, DAVID BROCK'])
        governor = next(r for r in state['races'] if r['office'] == 'governor')
        self.assertIsNone(governor['finance']['all_reported_candidates']['support_cents'])
        self.assertFalse(self.audit['finance_review']['FEC_recollected'])
        self.assertEqual(state['source_dates']['federal_last_success_at'], finance['source_status']['federal']['last_success_at'])
        minor = next(c for r in state['races'] for c in r['candidates'] if c['name'] == 'Andrea Townsend')
        self.assertIsNone(minor['candidate_id'])
        self.assertIsNone(minor['finance']['all_reported_election_types']['support_cents'])


if __name__ == '__main__': unittest.main()
