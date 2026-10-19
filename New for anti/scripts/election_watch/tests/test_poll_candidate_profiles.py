"""A public candidate biography cannot be inferred from name, picture or missing fields."""
from copy import deepcopy
from pathlib import Path
import unittest
from election_watch.candidate_profiles import validate_profiles,attach_profiles
from election_watch.governor_matchups import attach_state_matchups
from election_watch.polls import read
from election_watch.review_clock import validation_day

def profile():
 missing={'value':None,'status':'not_verified'}
 person={'office':'senate','name':'Fixture Candidate','party':'DEM',**{k:deepcopy(missing)for k in('birth_date','race_ethnicity','military_service','career')}}
 person['birth_date']={'value':'1952-11-09','status':'verified','precision':'day','source_url':'https://official.example/bio','reviewed_on':'2026-10-19','evidence_locator':'Birth paragraph'}
 return {'schema':'usa_candidate_profiles_v1','state':'OH','cycle':2026,'reviewed_on':'2026-10-19','people':[person]}
class CandidateProfileTests(unittest.TestCase):
 def test_governor_roster_is_attached_before_profile_join_without_erasing_senators(self):
  root=Path(__file__).resolve().parents[1]
  snapshot=read(root/'config/governor_matchups/2026.json');checked=validation_day('2026-10-19',snapshot);cards=self.cards();result=attach_state_matchups(cards,snapshot,checked);race=result[0]['election_matchups']['USA:OH:governor'];self.assertEqual(race['office'],'governor');self.assertGreaterEqual(len(race['candidates']),2);self.assertIn('USA:OH:senate',result[0]['election_matchups']);self.assertNotIn('USA:OH:governor',cards[0]['election_matchups'])
  d=profile();d['people'][0].update(office='governor',name=race['candidates'][0]['name'],party=race['candidates'][0]['party']);out=attach_profiles(result,[{'state':'OH','candidate_profiles':d}],'2026-10-19');self.assertEqual(out[0]['candidate_profile_coverage']['linked_people'],1)
 def cards(self):return [{'id':'OH','election_matchups':{'USA:OH:senate':{'candidates':[{'name':'Fixture Candidate','party':'DEM','candidate_id':'fixture-id'}]}}}]
 def test_age_uses_birthday_and_unknown_military_is_not_false(self):
  p={'state':'OH','candidate_profiles':profile()};before=self.cards();out=attach_profiles(before,[p],'2026-10-19');r=out[0]['election_matchups']['USA:OH:senate']['candidates'][0]['biography'];self.assertEqual(r['age']['value'],73);self.assertIsNone(r['military_service']['value']);self.assertNotIn('biography',before[0]['election_matchups']['USA:OH:senate']['candidates'][0]);self.assertEqual(attach_profiles(self.cards(),[p],'2026-11-09')[0]['election_matchups']['USA:OH:senate']['candidates'][0]['biography']['age']['value'],74)
 def test_different_roster_name_party_or_candidate_id_does_not_inherit_profile(self):
  for change in ({'name':'Different name'},{'party':'REP'},{'candidate_id':'different-id'}):
   d=profile();d['people'][0].update(change);out=attach_profiles(self.cards(),[{'state':'OH','candidate_profiles':d}],'2026-10-19');self.assertEqual(out[0]['candidate_profile_coverage']['linked_people'],0)
 def test_race_requires_explicit_identity_and_unknown_or_year_only_birth_is_not_invented(self):
  d=profile();d['people'][0]['race_ethnicity']={'value':'not a real identity','status':'verified','source_url':'https://official.example/bio','reviewed_on':'2026-10-19','evidence_locator':'Image color inference'}
  with self.assertRaises(ValueError):validate_profiles(d,'OH','2026-10-19')
  d=profile();d['people'][0]['birth_date']['precision']='year'
  with self.assertRaises(ValueError):validate_profiles(d,'OH','2026-10-19')
 def test_other_state_and_future_reviews_are_not_accepted(self):
  with self.assertRaises(ValueError):validate_profiles(profile(),'NY','2026-10-19')
  with self.assertRaises(ValueError):validate_profiles(profile(),'OH','2026-10-18')
 def test_verified_fact_needs_source_and_locator_and_unknown_age_stays_null(self):
  d=profile();d['people'][0]['birth_date']={'value':None,'status':'not_verified'};r=attach_profiles(self.cards(),[{'state':'OH','candidate_profiles':d}],'2026-10-19')[0]['election_matchups']['USA:OH:senate']['candidates'][0]['biography'];self.assertIsNone(r['age']['value'])
  d=profile();del d['people'][0]['birth_date']['source_url']
  with self.assertRaises((ValueError,KeyError)):validate_profiles(d,'OH','2026-10-19')
