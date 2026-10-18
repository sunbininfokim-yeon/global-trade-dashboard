"""MI primary decimals, separate partisan tracking waves and censored holds."""
from copy import deepcopy
from pathlib import Path
import unittest
from election_watch.polls import read
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.live_polls import normalize,summarize
ROOT=Path(__file__).resolve().parents[1];C=ROOT/'config';DAY='2026-10-18'
class MIPrimaryExpansionTests(unittest.TestCase):
    def setUp(self):
        self.audit=read(ROOT.parent.parent/'public/data/usa_election_poll_release_reviews/2026/MI-source-expansion-20261019.json');self.rows=[r['provider_record']for r in self.audit['records']]
        self.policy=apply_targets(apply_matchups(read(C/'usa_polls/live_2026.json'),read(C/'governor_matchups/2026.json'),DAY),read(C/'usa_polls/targets_2026.json'),read(C/'usa_polls/ballot_reviews_2026.json'),DAY);self.policy['quality_reviews']=read(C/'usa_polls/quality_reviews_2026.json')['reviews']
    def test_party_references_never_vote_in_leads(self):
        obs,held=normalize(self.rows,self.policy,DAY);self.assertFalse(held);self.assertEqual(len(obs),3)
        self.assertTrue(all(not o['aggregation_eligibility']['eligible']for o in obs))
        self.assertIsNone(summarize(obs,self.policy['races']['USA:MI:senate'],DAY,14)['party'])
        self.assertEqual({o['field_end']for o in obs},{'2026-09-27','2026-09-30','2026-10-08'})
    def test_primary_minor_decimals_are_not_zero_filled(self):
        obs,_=normalize(self.rows,self.policy,DAY);r=next(o for o in obs if o['pollster_group']=='trafalgar')
        values={a['name']:a['pct']for a in r['answers']}
        self.assertEqual(values['Walter P. Kristy'],0.3);self.assertEqual(values['Douglas P. Marsh'],0.1)
        self.assertEqual(r['provider_answer_correction']['provider_values']['Douglas P. Marsh'],0)
    def test_changed_source_row_cannot_inherit_correction_or_individual_review(self):
        for row in self.rows:
            altered=deepcopy(row);altered['sample_size']+=1;self.assertFalse(normalize([altered],self.policy,DAY)[0])
    def test_censored_questions_stay_held_and_no_money_claim(self):
        self.assertEqual(len(self.audit['held_source_records']),2)
        self.assertTrue(all(not r['eligible']for r in self.audit['held_source_records']))
        self.assertFalse(self.audit['new_provider_collection']);self.assertFalse(self.audit['finance_recollected'])
