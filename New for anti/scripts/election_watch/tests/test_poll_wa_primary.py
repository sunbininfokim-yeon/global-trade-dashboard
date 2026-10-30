"""WA official field, initial/leaner questions and exact finance identities."""
from tests.poll_config_fixture import SNAPSHOT_DAY, PUBLIC_SNAPSHOT_DAY, PINNED_FINANCE_NATIONAL
import copy
import json
from pathlib import Path
import unittest

from election_watch.ballot_wa import parse_general
from election_watch.governor_matchups import apply_matchups
from election_watch.live_polls import normalize, summarize
from election_watch.polls import read
from election_watch.poll_targets import apply_targets
from election_watch.state_evidence import build_state, load_finance
from publish_state_packets import rebuild
from tests.poll_config_fixture import SNAPSHOT_DAY

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT/'config/usa_polls'
PUBLIC = ROOT.parent.parent/'public/data'
DAY = '2026-10-13'


class WashingtonEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = read(PUBLIC/'usa_election_poll_release_reviews/2026/WA-primary-20261013.json')
        cls.raw = cls.audit['records'][0]['provider_record']
        cls.ballots = read(CONFIG/'ballot_reviews_2026.json')
        cls.federal = read(ROOT/'config/federal_matchups/2026.json')
        cls.governors = read(ROOT/'config/governor_matchups/2026.json')
        cls.catalog = read(CONFIG/'targets_2026.json')
        cls.policy = apply_targets(apply_matchups(read(CONFIG/'live_2026.json'), cls.governors, SNAPSHOT_DAY),
            cls.catalog, cls.ballots, SNAPSHOT_DAY)
        cls.policy['quality_reviews'] = read(CONFIG/'quality_reviews_2026.json')['reviews']

    def fixture(self):
        rows = []
        for rid, candidates in self.audit['official_candidates'].items():
            for c in candidates:
                cells = ['Congressional', f'Congressional District {int(rid[-2:])}',
                    'U.S. Representative', 'Regular', '2', c['name'], '', '', '', '',
                    'DEMOCRATIC' if c['party'] == 'DEM' else 'REPUBLICAN', 'Active', '',
                    str(c['ballot_order'])]
                rows.append('<tr>' + ''.join(f'<td>{v}</td>' for v in cells) + '</tr>')
        return ('<select id="ddlElection"><option value="899" selected>GENERAL 2026</option></select>'
                '<select id="ddlCounty"><option value="99" selected>State</option></select>'
                '<table>' + ''.join(rows) + '</table>')

    def test_official_ten_districts_and_twenty_names(self):
        parsed = parse_general(self.fixture())
        self.assertEqual(parsed, self.audit['official_candidates'])
        self.assertEqual(len(parsed), 10)
        self.assertEqual(sum(map(len, parsed.values())), 20)
        for rid in parsed:
            race = self.federal['races'][rid]
            self.assertEqual(race['source_role'], 'state_election_agency')
            self.assertEqual(race['coverage'], 'complete_active_agency_listing')
            self.assertEqual(self.policy['races'][rid]['general_from'], '2026-08-05')
            self.assertFalse(self.policy['races'][rid]['ballot_competition']['general_unopposed'])

    def test_primary_county_subset_changed_field_never_promoted(self):
        original = self.fixture()
        for altered in [original.replace('value="899"', 'value="898"'),
                        original.replace('value="99"', 'value="04"'),
                        original.replace('Active', 'Withdrawn', 1),
                        original.replace('REPUBLICAN', 'UNREVIEWED PARTY', 1),
                        original.replace('Congressional District 10', 'Congressional District 11')]:
            with self.assertRaises(ValueError): parse_general(altered)

    def test_state_legislature_not_federal_district(self):
        additional = '<tr><td>Legislative</td><td>Legislative District 3</td><td>State Senator</td></tr>'
        self.assertEqual(parse_general(self.fixture()+additional), self.audit['official_candidates'])

    def test_valid_leaner_values_preserved_while_initial_question_selected(self):
        original = copy.deepcopy(self.raw)
        observations, rejected = normalize([self.raw], self.policy, DAY)
        self.assertFalse(rejected)
        self.assertEqual(self.raw, original)
        self.assertEqual([a['pct'] for a in observations[0]['answers']], [44, 46])
        correction = observations[0]['provider_answer_correction']
        self.assertEqual(correction['provider_values'], {'Marie Gluesenkamp Perez': 47, 'John Braun': 48})
        disclosure = observations[0]['source_quality']['disclosure_review']
        self.assertTrue(disclosure['provider_values_are_valid_different_question'])
        self.assertEqual(disclosure['selected_question'], 'Q21 initial congressional ballot')
        self.assertEqual(disclosure['combined_leaner_toplines']['dont_know'], 5)
        self.assertEqual(disclosure['non_candidate_responses']['dont_know_pct'], 11)

    def test_lv_not_rv_and_no_accuracy_or_unprimed_claim(self):
        observations, _ = normalize([self.raw], self.policy, DAY)
        row = observations[0]; disclosure = row['source_quality']['disclosure_review']
        self.assertEqual((row['population'], row['sample_n']), ('lv', 543))
        self.assertEqual(disclosure['RV_initial_separate_not_imported']['sample_n'], 600)
        self.assertTrue(disclosure['candidate_favorability_precedes_ballot'])
        self.assertTrue(disclosure['initial_ballot_unprimed_not_claimed'])
        self.assertIsNone(row['source_quality']['accuracy_grade'])

    def test_old_wave_retained_but_not_a_current_winner(self):
        observations, _ = normalize([self.raw], self.policy, DAY)
        self.assertEqual(observations[0]['field_end'], '2026-09-27')
        for days in [7, 14]:
            summary = summarize(observations, self.policy['races']['USA:WA:house:03'], DAY, days)
            self.assertEqual(summary['pollster_count'], 0)
            self.assertIsNone(summary['party'])

    def test_changed_reviewed_record_does_not_inherit_selection(self):
        for field, value in [('sample_size', 544), ('end_date', '2026-09-28'),
                             ('sponsors', ['new commissioner'])]:
            raw = copy.deepcopy(self.raw); raw[field] = value
            self.assertFalse(normalize([raw], self.policy, DAY)[0])

    def test_future_poll_in_unpolled_district_joins_reviewed_names(self):
        raw = copy.deepcopy(self.raw)
        raw.update(id='future-wa08-fixture', subject='2026 WA-08', seat_name='WA-08',
                   start_date='2026-10-11', end_date='2026-10-12', created_at=DAY,
                   url='https://www.opb.org/article/2026/10/13/wa08-fixture-survey/',
                   answers=[{'choice': 'Kim Schrier', 'pct': 50}, {'choice': 'Spencer Meline', 'pct': 45}])
        observations, rejected = normalize([raw], self.policy, DAY)
        self.assertFalse(rejected)
        self.assertEqual(observations[0]['race_id'], 'USA:WA:house:08')
        self.assertEqual(observations[0]['source_quality']['verification_level'], 'partial')
        raw['answers'][1]['choice'] = 'Carmen Goers'
        self.assertFalse(normalize([raw], self.policy, DAY)[0])

    def test_preprimary_and_missing_sample_held(self):
        rows = self.audit['provider_records_reviewed']
        for rid in ['us-202emeae4416eb', 'us-202vot41d1f9d5']:
            self.assertFalse(normalize([next(r for r in rows if r['id'] == rid)], self.policy, DAY)[0])

    def test_no_senate_governor_election_or_invented_unopposed_winner(self):
        self.assertNotIn('USA:WA:senate', self.policy['races'])
        self.assertNotIn('USA:WA:governor', self.policy['races'])
        self.assertFalse(self.audit['official_ballot']['unopposed_verified_races'])

    def test_finance_identity_and_actual_money_are_separate(self):
        packet = read(ROOT/'config/state_evidence/2026/WA.json')
        old = read(PUBLIC/'usa_election_live_polls_v1.json')
        board, _ = rebuild(old, read(PUBLIC/'usa_election_poll_history_2026.json'), [packet], PUBLIC)
        finance = load_finance(PUBLIC/'usa_election_finance_index_v1.json', 2026, national_file=PINNED_FINANCE_NATIONAL)
        state = build_state('WA', 'C', read(CONFIG/'state_evidence_plan_2026.json'), self.catalog,
            self.federal, self.governors, board, finance,
            read(ROOT/'config/usa_state_campaign_finance_sources_v1.json'), PUBLIC_SNAPSHOT_DAY,
            read(CONFIG/'state_finance_identities_2026.json'))
        self.assertEqual(state['office_coverage']['house']['candidate_id_links'], 20)
        self.assertEqual(state['office_coverage']['house']['with_observed_current_candidate_spending'], 10)
        ninth = next(r for r in state['races'] if r['district'] == '09')
        smith = next(c for c in ninth['candidates'] if c['name'] == 'Adam Smith')
        self.assertEqual(smith['candidate_id'], 'H6WA09025')
        self.assertEqual(smith['finance']['reported_names'], ['SMITH, D. ADAM'])
        self.assertEqual(smith['finance']['all_reported_election_types']['support_cents'], 1000)
        self.assertFalse(self.audit['finance_review']['FEC_recollected'])
        self.assertEqual(state['source_dates']['federal_last_success_at'],
                         finance['source_status']['federal']['last_success_at'])
        # A later main collection may supersede the reviewed capture. Linking
        # an identity must retain that actual source date, never roll it back.
        self.assertGreaterEqual(state['source_dates']['federal_last_success_at'],
                                self.audit['finance_review']['existing_last_success_at'])


if __name__ == '__main__': unittest.main()
