import copy
import json
from pathlib import Path
import unittest

from election_watch.live_polls import normalize, summarize
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'config/usa_polls'
PUBLIC=ROOT.parent.parent/'public/data'


class GeorgiaPrimaryReviewTests(unittest.TestCase):
    def setUp(self):
        read=lambda p:json.loads(p.read_text())
        policy=apply_matchups(read(CONFIG/'live_2026.json'),read(ROOT/'config/governor_matchups/2026.json'),'2026-10-08')
        policy=apply_targets(policy,read(CONFIG/'targets_2026.json'),read(CONFIG/'ballot_reviews_2026.json'),'2026-10-08')
        policy['quality_reviews']=read(CONFIG/'quality_reviews_2026.json')['reviews']
        self.policy=policy
        self.rows=[r['provider_record'] for r in read(PUBLIC/'usa_election_poll_release_reviews/2026/GA-primary-20261008.json')['records']]

    def test_initial_ballot_replaces_leaner_measure_without_double_counting(self):
        accepted,rejected=normalize(self.rows,self.policy,'2026-10-08')
        self.assertFalse(rejected);self.assertEqual(len(accepted),6)
        byid={r['id']:r for r in accepted}
        for ident,partyvalue in [('us-202bigbe8a8854',52.2),('gov202bigf56bfd9a',48.7)]:
            poll=byid[ident];self.assertEqual(poll['answers'][0]['pct'],partyvalue)
            self.assertIn('provider_values',poll['provider_answer_correction'])
            self.assertEqual(poll['source_quality']['ballot_format'],'initial_vote_intention')
        for rid in ('USA:GA:senate','USA:GA:governor'):
            polls=[r for r in accepted if r['race_id']==rid]
            self.assertEqual(len(polls),3)
            self.assertFalse(next(r for r in polls if r['pollster']=='Wick')['aggregation_eligibility']['eligible'])
            self.assertEqual(summarize(polls,self.policy['races'][rid],'2026-10-08',14)['pollster_count'],0)

    def test_changed_reviewed_api_values_are_held(self):
        for original in self.rows:
            row=copy.deepcopy(original);row['answers'][0]['pct']+=1
            accepted,rejected=normalize([row],self.policy,'2026-10-08')
            self.assertFalse(accepted);self.assertEqual(len(rejected),1)

    def test_new_registered_release_stays_partial_and_new_sponsor_is_held(self):
        raw=copy.deepcopy(next(r for r in self.rows if r['pollster']=='InsiderAdvantage'))
        raw.update(id='synthetic-new-ga-test',start_date='2026-10-05',end_date='2026-10-06',created_at='2026-10-07')
        raw['url']='https://insideradvantage.com/synthetic-test-release/'
        accepted,rejected=normalize([raw],self.policy,'2026-10-08')
        self.assertFalse(rejected);self.assertEqual(accepted[0]['source_quality']['verification_level'],'partial')
        self.assertIsNone(accepted[0]['source_quality']['accuracy_grade'])
        raw['sponsors']=['Unreviewed commissioner']
        accepted,rejected=normalize([raw],self.policy,'2026-10-08')
        self.assertFalse(accepted);self.assertEqual(rejected[0]['reason'],'commissioner_not_reviewed')
