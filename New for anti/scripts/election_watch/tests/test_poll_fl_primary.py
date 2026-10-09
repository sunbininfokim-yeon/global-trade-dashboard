from tests.poll_config_fixture import SNAPSHOT_DAY
import copy
import json
from pathlib import Path
import unittest
from election_watch.live_polls import normalize, summarize
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.poll_quality import answer_correction_fingerprint

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'config/usa_polls'
PUBLIC=ROOT.parent.parent/'public/data'


class FloridaPrimaryReviewTests(unittest.TestCase):
    def setUp(self):
        read=lambda p:json.loads(p.read_text())
        policy=apply_matchups(read(CONFIG/'live_2026.json'),read(ROOT/'config/governor_matchups/2026.json'),SNAPSHOT_DAY)
        self.policy=apply_targets(policy,read(CONFIG/'targets_2026.json'),read(CONFIG/'ballot_reviews_2026.json'),SNAPSHOT_DAY)
        self.policy['quality_reviews']=read(CONFIG/'quality_reviews_2026.json')['reviews']
        receipt=read(PUBLIC/'usa_election_poll_release_reviews/2026/FL-primary-20261008.json')
        self.rows=[r['provider_record'] for r in receipt['records']]
        self.held=receipt['held_records'][0]['provider_record']

    def test_reference_only_new_polls_and_original_sample_limits(self):
        accepted,rejected=normalize(self.rows,self.policy,'2026-10-08')
        self.assertFalse(rejected);self.assertEqual(len(accepted),9)
        byid={r['id']:r for r in accepted}
        for ident in ['us-202tav1ccea6ab','us-202cha69e5536b','gov202cha6fdf31d1','us-202pub0bd895c4']:
            self.assertFalse(byid[ident]['aggregation_eligibility']['eligible'])
        self.assertIsNone(byid['us-202tav1ccea6ab']['source_quality']['question_sample_n'])
        for rid in ['USA:FL:governor','USA:FL:senate','USA:FL:house:16','USA:FL:house:22']:
            polls=[r for r in accepted if r['race_id']==rid]
            self.assertEqual(summarize(polls,self.policy['races'][rid],'2026-10-08',14)['pollster_count'],0)

    def test_missing_url_is_restored_with_original_provider_provenance(self):
        row=next(r for r in self.rows if r['id']=='gov202cha6fdf31d1')
        accepted,rejected=normalize([row],self.policy,'2026-10-08')
        self.assertFalse(rejected)
        record=accepted[0];self.assertEqual(record['provider_source_correction']['original_provider_url'],'[null]')
        self.assertEqual(record['provider_source_correction']['provider_snapshot_sha256'],answer_correction_fingerprint(row))
        self.assertTrue(record['source_url'].startswith('https://changeresearch.com/'))
        self.assertEqual(record['answers'][0]['pct'],47)

    def test_missing_url_correction_cannot_survive_changed_source_metadata(self):
        original=next(r for r in self.rows if r['id']=='gov202cha6fdf31d1')
        for changes in [{'url':'https://example.org/new'}, {'sample_size':1108}, {'sponsors':['Different funder']},
                        {'start_date':'2026-09-08'}, {'internal':True}, {'pollster':'Different institute'}]:
            accepted,rejected=normalize([{**original,**changes}],self.policy,'2026-10-08')
            self.assertFalse(accepted);self.assertEqual(rejected[0]['reason'],'provider_source_correction_snapshot_changed')

    def test_changed_values_are_held_even_if_missing_link_has_not_changed(self):
        for raw in self.rows:
            row=copy.deepcopy(raw);row['answers'][0]['pct']+=1
            accepted,rejected=normalize([row],self.policy,'2026-10-08')
            self.assertFalse(accepted);self.assertEqual(len(rejected),1)

    def test_primary_link_must_be_reviewed_https_not_an_arbitrary_replacement(self):
        row=next(r for r in self.rows if r['id']=='gov202cha6fdf31d1')
        policy=copy.deepcopy(self.policy);review=policy['quality_reviews'][row['id']]
        review['provider_source_correction']['primary_url']='https://example.org/unreviewed'
        accepted,rejected=normalize([row],policy,'2026-10-08')
        self.assertFalse(accepted);self.assertEqual(rejected[0]['reason'],'unverified_source_correction')

    def test_other_response_does_not_become_named_third_candidate(self):
        accepted,rejected=normalize([self.held],self.policy,'2026-10-08')
        self.assertFalse(accepted);self.assertEqual(rejected[0]['reason'],'provider_third_candidate_attribution_unverified')

    def test_single_release_review_does_not_whitelist_shared_document_host(self):
        row=copy.deepcopy(next(r for r in self.rows if r['pollster']=='Tavern Research'))
        row.update(id='synthetic-new-fl-test',start_date='2026-10-05',end_date='2026-10-06',created_at='2026-10-07')
        accepted,rejected=normalize([row],self.policy,'2026-10-08')
        self.assertFalse(accepted);self.assertEqual(rejected[0]['reason'],'pollster_not_selected')
