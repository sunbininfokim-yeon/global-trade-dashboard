"""An open governor election is not a missing election or an unverified winner."""
from pathlib import Path
from copy import deepcopy
import json,unittest
from election_watch.governor_context import build_context,parse_nga
C=Path(__file__).resolve().parents[1]/'config'
class GovernorContextTests(unittest.TestCase):
 def setUp(self):
  self.inputs=json.loads((C/'usa_polls/governor_context_2026.json').read_text());self.catalog=json.loads((C/'usa_polls/targets_2026.json').read_text());gov={r['state']:r for r in json.loads((C/'extracted/usa_governors.json').read_text())['governors']};self.cards=[{'id':st,'governor':gov[x['name']]}for st,x in self.catalog['states'].items()]
 def test_50_states_36_elections_15_term_limits_retirements_and_primary_loss_are_separate(self):
  d=build_context(self.inputs,self.catalog,self.cards,'2026-10-19');self.assertEqual([d['counts'][k]for k in('all_states','contested','not_contested','term_limited_reported')],[50,36,14,15]);self.assertIsNone(d['states']['NC']['race_id']);self.assertIsNone(d['states']['NC']['election_date']);self.assertTrue(d['states']['OH']['election_in_cycle']);self.assertEqual(d['states']['OH']['incumbent_ballot_status'],'term_limited_reported');self.assertEqual(d['states']['WI']['incumbent_ballot_status'],'not_seeking_reelection_reported');self.assertEqual(d['states']['RI']['incumbent_ballot_status'],'primary_defeated_reported');self.assertNotIn('GU',d['states']);self.assertEqual(d['counts']['by_incumbent_status']['running_reported'],17);self.assertNotIn('incumbent_identity_conflict',d['counts']['by_incumbent_status'])
 def test_current_incumbent_conflict_does_not_transfer_predecessor_term_limit(self):
  cards=deepcopy(self.cards);next(c for c in cards if c['id']=='OH')['governor']['name']='A different governor';r=build_context(self.inputs,self.catalog,cards,'2026-10-19')['states']['OH'];self.assertEqual(r['incumbent_ballot_status'],'incumbent_identity_conflict');self.assertIsNone(r['term_limited_reported'])
 def test_future_review_or_missing_state_is_not_silently_a_new_calendar(self):
  with self.assertRaises(ValueError):build_context(self.inputs,self.catalog,self.cards,'2026-10-18')
  x=deepcopy(self.inputs);del x['contests']['CA']
  with self.assertRaises(ValueError):build_context(x,self.catalog,self.cards,'2026-10-19')
 def test_network_recheck_changes_receipt_not_human_review_date_and_rejects_lost_flag(self):
  rows=[]
  for st,r in self.inputs['contests'].items():
   listing = '' if r['incumbent_listed_as_candidate'] is None else '<p>General Election Candidates</p><ul><li>'+('Gov. '+r['incumbent_name'] if r['incumbent_listed_as_candidate'] else 'Other candidate')+' (R)</li></ul>'
   rows.append(f'<div data-original-id="US-{st}"><h3><a href="gubernatorial_election,_2026">State</a></h3>Incumbent:</strong> <a href="https://www.nga.org/governors/fixture/">Gov. {r["incumbent_name"]}</a>'+listing+'Length of Regular Terms:4'+(' * Term Limited' if r['term_limited_reported'] else '')+'</div>')
  # A territory and a past result are not state-election panels.
  rows+=['<div data-original-id="US-GU"><h3>gubernatorial_election,_2026</h3>not a state</div>','<div data-original-id="US-OH"><h3>gubernatorial_election,_2022</h3>past</div>']
  s=''.join(rows);r=parse_nga(s,self.inputs,self.catalog,'2026-10-20T00:00:00Z');self.assertEqual(r['reviewed_on'],'2026-10-19');self.assertEqual(r['source']['captured_at'],'2026-10-20T00:00:00Z')
  with self.assertRaises(ValueError):parse_nga(s.replace('* Term Limited','',1),self.inputs,self.catalog,'2026-10-20T00:00:00Z')
