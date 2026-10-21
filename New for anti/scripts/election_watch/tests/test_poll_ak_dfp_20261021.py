from tests.poll_config_fixture import SNAPSHOT_DAY
"""One Alaska study, separate RCV questions, no manufactured ordinary winner."""
from copy import deepcopy
import hashlib
import io
from pathlib import Path
import unittest

from election_watch.governor_matchups import apply_matchups
from election_watch.live_polls import normalize, summarize
from election_watch.poll_primary_supplements import merge_primary_supplements
from election_watch.poll_quality import answer_correction_fingerprint
from election_watch.poll_targets import apply_targets
from election_watch.polls import read
from election_watch.state_inputs import validate_packet

ROOT = Path(__file__).resolve().parents[1]
C = ROOT/'config'
PUBLIC = ROOT.parent.parent/'public/data'
DAY = '2026-10-20'
PREFIX = 'primary-ak-dfp-20261016-q'


class AlaskaDFPTests(unittest.TestCase):
    def setUp(self):
        self.packet = read(C/'state_evidence/2026/AK.json')
        self.audit = read(PUBLIC/'usa_election_poll_release_reviews/2026/AK-dfp-20261021.json')
        self.rows = [r for r in self.packet['capture']['primary_records'] if r['id'].startswith(PREFIX)]
        self.policy = apply_targets(apply_matchups(read(C/'usa_polls/live_2026.json'),
            read(C/'governor_matchups/2026.json'), SNAPSHOT_DAY), read(C/'usa_polls/targets_2026.json'),
            read(C/'usa_polls/ballot_reviews_2026.json'), SNAPSHOT_DAY)
        self.policy['quality_reviews'] = read(C/'usa_polls/quality_reviews_2026.json')['reviews']
        self.snapshot = {'schema':'usa_reviewed_primary_poll_supplements_v1','cycle':2026,
            'records':[o['value'] for o in self.packet['config_operations']
                if o['file']=='usa_polls/primary_supplements_2026.json'
                and o['value']['record']['id'].startswith(PREFIX)]}

    def observations(self):
        obs, held = normalize(self.rows, self.policy, DAY)
        self.assertEqual(held, [])
        self.assertEqual(len(obs), 9)
        return {int(o['id'].rsplit('q',1)[1]):o for o in obs}

    def transport(self, provider=(), changed=False, conflict=False, unavailable=False):
        snapshot = deepcopy(self.snapshot)
        body = b'%PDF-synthetic-reviewed-AK-question-tables'
        for entry in snapshot['records']:
            entry['documents'][0]['sha256'] = hashlib.sha256(body).hexdigest()
        class Response(io.BytesIO):
            status = 200
            def geturl(self): return snapshot['records'][0]['documents'][0]['url']
        def opener(req, timeout):
            if unavailable:
                raise OSError('synthetic source outage')
            return Response(b'%PDF-changed' if changed else body)
        output, checks = merge_primary_supplements(list(provider), snapshot, DAY, ['AK'],
            opener=opener,
            reviewed_entries=snapshot['records'], isolate_conflicts=conflict)
        policy = deepcopy(self.policy)
        for entry in snapshot['records']:
            policy['quality_reviews'][entry['record']['id']]['primary_documents'] = entry['documents']
        return output, checks, policy

    def test_one_study_three_races_nine_question_observations(self):
        obs = self.observations()
        self.assertEqual({o['race_id'] for o in obs.values()},
                         {'USA:AK:house:00','USA:AK:senate','USA:AK:governor'})
        self.assertEqual({o['pollster_group'] for o in obs.values()}, {'dataforprogress'})
        self.assertEqual(self.audit['counts']['new_poll_waves'], 1)
        self.assertEqual(self.audit['counts']['question_observations'], 9)
        self.assertEqual({o['ballot_question']['wave_id'] for o in obs.values()},
                         {'ak-dfp-20261008-20261016'})

    def test_first_choice_keeps_whole_ballot_and_not_sure_separate(self):
        obs = self.observations()
        self.assertEqual({a['name']:a['pct'] for a in obs[20]['answers']},
            {'Nick Begich':48,'Bill Hill':42,'Eric Hafner':5,'James C. "Jim" McDermott':1})
        for q,unsure in ((10,5),(15,3),(20,4)):
            row = obs[q]
            self.assertEqual(row['ballot_question']['kind'], 'first_preference')
            self.assertEqual(len(row['answers']), 4)
            self.assertEqual(row['sample_n'], 694)
            self.assertEqual(row['source_quality']['disclosure_review']['undecided_pct'], unsure)
        # The source's rounded Senate total is 99 with Not sure, never rescaled.
        self.assertEqual(sum(a['pct'] for a in obs[15]['answers'])+3, 99)

    def test_active_round_n_and_hypothetical_transfer_n_are_not_study_n(self):
        obs = self.observations()
        for q,n in ((13,629),(14,660),(18,671),(19,675),(23,659),(24,668)):
            with self.subTest(question=q):
                row = obs[q]
                self.assertEqual(row['sample_n'], n)
                self.assertEqual(row['source_quality']['question_sample_n'], n)
                self.assertEqual(row['source_quality']['disclosure_review']['study_sample_n'], 694)
                self.assertEqual(row['ballot_question']['active_weighted_n'], n)

    def test_published_final_and_exhausted_ballot_hypothesis_remain_distinct(self):
        obs = self.observations()
        for final,hypothesis in ((18,19),(23,24)):
            self.assertFalse(obs[final]['ballot_question']['hypothetical'])
            self.assertTrue(obs[hypothesis]['ballot_question']['hypothetical'])
            self.assertEqual(sorted(a['pct'] for a in obs[final]['answers']), [49,51])
            self.assertEqual([a['pct'] for a in obs[hypothesis]['answers']], [50,50])
        self.assertFalse(obs[13]['ballot_question']['hypothetical'])
        self.assertIn('반올림', obs[13]['source_quality']['disclosure_review']['scenario_assumption'])

    def test_two_sullivans_and_independent_hill_do_not_change_party(self):
        obs = self.observations()
        parties = {a['name']:a['party'] for a in obs[15]['answers']}
        self.assertEqual(parties['Dan S. Sullivan'], 'REP')
        self.assertEqual(parties['Daniel J. Sullivan Jr.'], 'OTH')
        self.assertEqual(next(a['party'] for a in obs[20]['answers'] if a['name']=='Bill Hill'), 'IND')

    def test_recent_reference_is_visible_without_an_ordinary_lead_or_winner(self):
        obs = list(self.observations().values())
        for rid in {o['race_id'] for o in obs}:
            rows = [o for o in obs if o['race_id']==rid]
            for days in (7,14):
                summary = summarize(rows, self.policy['races'][rid], DAY, days)
                self.assertEqual(summary['reference_poll_count'], 3)
                self.assertEqual(summary['pollster_count'], 0)
                self.assertIsNone(summary['party'])
                self.assertIsNone(summary['leader'])
        self.assertTrue(all(not o['ballot_question']['election_result'] for o in obs))

    def test_missing_commissioner_and_final_round_precision_are_not_invented(self):
        for o in self.observations().values():
            quality = o['source_quality']
            self.assertIsNone(quality['accuracy_grade'])
            self.assertIsNone(quality['disclosure_review']['commissioner'])
            self.assertIsNone(quality['reported_precision']['confidence_level_pct'])
            self.assertFalse(quality['reported_precision']['applies_to_final_or_conditional_question'])
            self.assertEqual(quality['reported_precision']['half_width_pp'], 4)

    def test_source_and_provider_provenance_preserve_old_review_dates(self):
        names = {s:r['name'] for s,r in read(C/'usa_polls/targets_2026.json')['states'].items()}
        validate_packet(self.packet, names)
        receipt = self.packet['capture']['receipt']
        self.assertTrue(receipt['new_provider_collection'])
        self.assertFalse(receipt['federal_finance_recollected'])
        self.assertEqual(receipt['prior_capture_receipt']['captured_at'], '2026-10-09T04:59:12.473203+00:00')
        old = next(r for r in self.packet['capture']['primary_records'] if 'quantus' in r['id'])
        self.assertEqual(old['primary_source_capture']['original_reviewed_on'], '2026-10-09')
        self.assertEqual(old['end_date'], '2026-09-30')

    def test_same_wave_question_approvals_do_not_collapse_or_conflict(self):
        output, checks, policy = self.transport()
        self.assertEqual(len(output), 9)
        self.assertTrue(all(c['status']=='primary_documents_rechecked' for c in checks))
        obs, held = normalize(output, policy, DAY)
        self.assertEqual(len(obs), 9)
        self.assertEqual(held, [])

    def test_later_api_exact_question_deduplicates_but_other_round_is_retained(self):
        raw = deepcopy(next(r['record'] for r in self.snapshot['records'] if r['record']['id'].endswith('q20')))
        raw['id'] = 'later-dfp-house-api'
        output, checks, _ = self.transport([raw])
        self.assertEqual(len(output), 9)
        self.assertEqual(next(c for c in checks if c['id'].endswith('q20'))['provider_duplicate_ids'], [raw['id']])
        self.assertEqual(len({r['id'] for r in output}), 9)

    def test_changed_source_preserves_values_and_real_field_dates_as_reference(self):
        output, checks, policy = self.transport(changed=True)
        self.assertTrue(all(c['status']=='carried_forward_reference_only' for c in checks))
        obs, held = normalize(output, policy, DAY)
        self.assertEqual(held, [])
        self.assertEqual(len(obs), 9)
        self.assertTrue(all(o['field_end']=='2026-10-16' for o in obs))
        self.assertTrue(all('primary_source_unavailable_or_changed' in o['aggregation_eligibility']['reasons'] for o in obs))

    def test_disagreeing_later_api_wave_is_held_without_replacing_primary_values(self):
        raw = deepcopy(next(r['record'] for r in self.snapshot['records'] if r['record']['id'].endswith('q20')))
        raw['id'] = 'later-dfp-house-api'
        raw['answers'][0]['pct'] = 49
        with self.assertRaisesRegex(ValueError, 'primary_and_provider_wave_conflict'):
            self.transport([raw])
        output, checks, _ = self.transport([raw], conflict=True)
        primary = next(r for r in output if r['id'].endswith('q20'))
        self.assertEqual(primary['answers'][0]['pct'], 48)
        self.assertEqual(primary['primary_source_capture']['status'], 'primary_provider_conflict_reference_only')
        self.assertEqual(primary['primary_source_capture']['conflicting_provider_records'], [raw])
        self.assertEqual(next(c for c in checks if c['id'].endswith('q20'))['status'],
                         'primary_provider_conflict_reference_only')

    def test_source_outage_retains_original_values_and_review_day(self):
        output, checks, policy = self.transport(unavailable=True)
        obs, held = normalize(output, policy, DAY)
        self.assertEqual(held, [])
        self.assertEqual(len(obs), 9)
        self.assertTrue(all(c['status']=='carried_forward_reference_only' for c in checks))
        self.assertTrue(all(o['field_end']=='2026-10-16' and o['source_quality']['reviewed_on']==DAY for o in obs))
        self.assertEqual(next(a['pct'] for o in obs if o['id'].endswith('q20')
                              for a in o['answers'] if a['name']=='Nick Begich'), 48)

    def test_unreviewed_answer_sample_or_party_cannot_inherit_a_finite_review(self):
        raw = deepcopy(next(r for r in self.rows if r['id'].endswith('q15')))
        for key,value in (('sample_size',675),('start_date','2026-10-09'),('partisan','DEM')):
            altered = {**raw,key:value}
            obs, held = normalize([altered], self.policy, DAY)
            self.assertFalse(obs)
            self.assertEqual(held[0]['reason'], 'primary_review_provider_metadata_changed')
        raw['answers'][0]['pct'] = 50
        obs, held = normalize([raw], self.policy, DAY)
        self.assertFalse(obs)
        self.assertEqual(held[0]['reason'], 'primary_review_provider_metadata_changed')


if __name__=='__main__':
    unittest.main()
