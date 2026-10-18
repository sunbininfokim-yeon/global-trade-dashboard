"""UT-02 candidate alias and primary RV metadata; old polls never become fresh."""
from copy import deepcopy
from pathlib import Path
import unittest
from election_watch.polls import read
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.live_polls import normalize,summarize
ROOT=Path(__file__).resolve().parents[1];C=ROOT/'config';DAY='2026-10-18'
class UTPrimaryImageTests(unittest.TestCase):
    def setUp(self):
        self.audit=read(ROOT.parent.parent/'public/data/usa_election_poll_release_reviews/2026/UT-source-expansion-20261019.json');self.raw=self.audit['records'][0]['provider_record']
        self.policy=apply_targets(apply_matchups(read(C/'usa_polls/live_2026.json'),read(C/'governor_matchups/2026.json'),DAY),read(C/'usa_polls/targets_2026.json'),read(C/'usa_polls/ballot_reviews_2026.json'),DAY);self.policy['quality_reviews']=read(C/'usa_polls/quality_reviews_2026.json')['reviews']
    def test_population_corrected_to_rv_with_original_lv_preserved(self):
        rows,held=normalize([self.raw],self.policy,DAY);self.assertFalse(held);r=rows[0]
        self.assertEqual(r['population'],'rv');self.assertEqual(r['provider_metadata_correction']['provider_values'],{'population':'lv'})
        self.assertEqual(r['sample_n'],515);self.assertTrue(r['aggregation_eligibility']['eligible'])
        self.assertEqual([a['pct']for a in r['answers']],[39,34,4.1,4.9,4.9])
    def test_original_age_outside_both_current_windows(self):
        rows,_=normalize([self.raw],self.policy,DAY);race=self.policy['races']['USA:UT:house:02']
        for days in (7,14):self.assertIsNone(summarize(rows,race,DAY,days)['party'])
        self.assertEqual(rows[0]['field_end'],'2026-09-24')
        self.assertEqual(race['candidates']['Blake Moore']['canonical_name'],'Blake David Moore')
    def test_changed_provider_population_or_sample_is_held(self):
        for k,v in (('sample_size',516),('population','rv'),('sponsors',[])):
            r={**deepcopy(self.raw),k:v};self.assertFalse(normalize([r],self.policy,DAY)[0])
    def test_no_fresh_collection_or_finance_claim(self):
        self.assertFalse(self.audit['new_provider_collection']);self.assertFalse(self.audit['finance_recollected'])
        self.assertTrue(self.audit['preserved_primary_records'])
