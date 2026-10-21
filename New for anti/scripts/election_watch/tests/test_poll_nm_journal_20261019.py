from tests.poll_config_fixture import SNAPSHOT_DAY
"""NM primary charts and explicit roster aliases; no fuzzy candidate matching."""
from copy import deepcopy
import unittest
from pathlib import Path
from election_watch.polls import read
from election_watch.live_polls import normalize,summarize
from election_watch.poll_targets import apply_targets
from election_watch.governor_matchups import apply_matchups
ROOT=Path(__file__).resolve().parents[1];C=ROOT/'config';DAY='2026-10-18'
class NMJournalReleaseTests(unittest.TestCase):
    def setUp(self):
        self.audit=read(ROOT.parent.parent/'public/data/usa_election_poll_release_reviews/2026/NM-journal-20261019.json')
        self.policy=apply_targets(apply_matchups(read(C/'usa_polls/live_2026.json'),read(C/'governor_matchups/2026.json'),SNAPSHOT_DAY),read(C/'usa_polls/targets_2026.json'),read(C/'usa_polls/ballot_reviews_2026.json'),SNAPSHOT_DAY)
        self.policy['quality_reviews']=read(C/'usa_polls/quality_reviews_2026.json')['reviews']
        self.rows=[r['provider_record']for r in self.audit['records']]
    def test_both_house_polls_admitted_with_primary_sample_and_party(self):
        obs,held=normalize(self.rows,self.policy,DAY);self.assertFalse(held);self.assertEqual(len(obs),2)
        for row in obs:
            self.assertTrue(row['aggregation_eligibility']['eligible'])
            self.assertEqual(row['source_quality']['verification_level'],'primary_toplines_checked')
            self.assertEqual([a['party']for a in row['answers']],['DEM','REP'])
            self.assertEqual(row['sample_n'],380 if row['race_id'].endswith('01')else 362)
            self.assertEqual(summarize([row],self.policy['races'][row['race_id']],DAY,14)['party'],'DEM')
            self.assertIsNone(summarize([row],self.policy['races'][row['race_id']],DAY,7)['party'])
    def test_changed_provider_values_or_metadata_require_new_review(self):
        for change in ({'sample_size':999},{'url':'https://example.org/poll'},{'sponsors':['Other']}):
            row={**deepcopy(self.rows[0]),**change}
            self.assertFalse(normalize([row],self.policy,DAY)[0])
    def test_canonical_identity_and_unrelated_names_are_not_inferred(self):
        race=self.policy['races']['USA:NM:house:01']
        self.assertEqual(race['candidates']['Melanie Stansbury']['canonical_name'],'Melanie Ann Stansbury')
        self.assertEqual(race['candidates']['Ndidiamaka Okpareke']['candidate_id'],'H6NM01129')
        row=deepcopy(self.rows[0]);row['id']='other';row['answers'][0]['choice']='Melanie Other'
        self.assertFalse(normalize([row],self.policy,DAY)[0])
    def test_old_primary_date_and_money_preserved(self):
        self.assertTrue(self.audit['prior_primary_records_preserved'])
        self.assertEqual(self.audit['prior_capture_at'],'2026-10-09T10:16:59.119404+00:00')
        self.assertFalse(self.audit['finance_recollected'])
        packet=read(C/'state_evidence/2026/NM.json')
        self.assertEqual(packet['capture']['primary_records'][0]['end_date'],'2026-09-30')
