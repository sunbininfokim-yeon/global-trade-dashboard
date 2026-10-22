from tests.poll_config_fixture import SNAPSHOT_DAY
"""Primary vote support is not the separately asked expected-winner question."""
from pathlib import Path
from copy import deepcopy
import unittest
from election_watch.polls import read
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.live_polls import normalize,summarize
from election_watch.state_inputs import packets,validate_packet
from election_watch.candidate_profiles import attach_profiles
C=Path(__file__).resolve().parents[1]/'config';DAY='2026-10-19'
class OhioPrimaryContextTests(unittest.TestCase):
 def setUp(self):
  self.packet=read(C/'state_evidence/2026/OH.json');self.audit=read(C.parents[2]/'public/data/usa_election_poll_release_reviews/2026/OH-context-20261019.json');self.raw=[x['provider_record']for x in self.audit['records']]
  self.policy=apply_targets(apply_matchups(read(C/'usa_polls/live_2026.json'),read(C/'governor_matchups/2026.json'),SNAPSHOT_DAY),read(C/'usa_polls/targets_2026.json'),read(C/'usa_polls/ballot_reviews_2026.json'),SNAPSHOT_DAY);self.policy['quality_reviews']=read(C/'usa_polls/quality_reviews_2026.json')['reviews']
 def test_two_primary_major_toplines_join_14_days_but_not_7(self):
  rows,held=normalize(self.raw,self.policy,DAY);self.assertFalse(held);self.assertEqual(len(rows),2)
  for row in rows:
   self.assertTrue(row['aggregation_eligibility']['eligible']);self.assertEqual(row['sample_n'],1000);self.assertEqual(summarize([row],self.policy['races'][row['race_id']],DAY,14)['party'],'DEM');self.assertIsNone(summarize([row],self.policy['races'][row['race_id']],DAY,7)['party']);self.assertIsNone(row['source_quality']['accuracy_grade'])
 def test_expected_winner_48_48_is_not_48_42_vote_preference(self):
  raw=deepcopy(self.raw[0]);self.assertEqual(raw['poll_type'],'us-senator');raw['answers'][1]['pct']=48
  rows,held=normalize([raw],self.policy,DAY);self.assertFalse(rows);self.assertEqual(held[0]['reason'],'primary_review_provider_metadata_changed');self.assertEqual(self.audit['not_vote_support']['expected_senate_winner'],{'Sherrod Brown':48,'Jon Husted':48})
 def test_primary_recheck_scope_does_not_claim_minor_values_or_alias_verification(self):
  rows,held=normalize(self.raw,self.policy,DAY);self.assertFalse(held)
  for row in rows:
   self.assertEqual(len(row['source_quality']['primary_toplines']),2);self.assertIn('minor_candidate_values_primary_pdf_recheck',row['source_quality']['missing_fields']);self.assertIsNone(row['source_quality']['disclosure_review']['full_question_wording'])
  senate=next(x for x in rows if x['race_id'].endswith(':senate'));redpath=next(a for a in senate['answers']if a['name']=='Bill Redpath');self.assertIsNone(redpath['party'])
 def test_changed_n_dates_sponsor_or_new_id_cannot_inherit_review(self):
  for changes in ({'sample_size':999},{'start_date':'2026-09-28'},{'sponsors':['unreviewed sponsor']}):
   rows,held=normalize([{**deepcopy(self.raw[0]),**changes}],self.policy,DAY);self.assertFalse(rows);self.assertTrue(held)
  rows,held=normalize([{**deepcopy(self.raw[0]),'id':'new-unreviewed-bgsu-wave'}],self.policy,DAY)
  # A publisher route may preserve the new API item as a reference, never
  # inherit this finite release's primary verification or lead eligibility.
  self.assertTrue(held or rows)
  for row in rows:
   self.assertFalse(row['aggregation_eligibility']['eligible']);self.assertNotEqual(row['verification'],'primary_values_rechecked')
 def test_state_capture_and_existing_primary_original_dates_are_preserved(self):
  self.assertTrue(self.packet['capture']['receipt']['new_provider_collection']);self.assertEqual(self.packet['capture']['receipt']['captured_at'],self.packet['capture']['fetched_at']);names={s:d['name']for s,d in read(C/'usa_polls/targets_2026.json')['states'].items()};validate_packet(self.packet,names)
  prior=next(x for x in self.packet['capture']['primary_records']if x['id']=='primary-suffolk-oh-senate-20261002');self.assertEqual(prior['primary_source_capture']['original_reviewed_on'],'2026-10-08')
 def test_profiles_join_exact_oh_rosters_keep_unknowns_and_compute_age(self):
  races={rid:{'candidates':[{'name':p['name'],'party':p['party']}for p in self.packet['candidate_profiles']['people']if rid.endswith(':'+p['office'])]}for rid in ('USA:OH:senate','USA:OH:governor')}
  cards=attach_profiles([{'id':'OH','election_matchups':races}],[self.packet],DAY);self.assertEqual(cards[0]['candidate_profile_coverage']['linked_people'],4);byname={c['name']:c['biography']for r in cards[0]['election_matchups'].values()for c in r['candidates']};self.assertEqual(byname['Sherrod Brown']['age']['value'],73);self.assertIsNone(byname['Vivek Ramaswamy']['career']['value']);self.assertTrue(all(x['race_ethnicity']['value']is None and x['military_service']['value']is None for x in byname.values()))
