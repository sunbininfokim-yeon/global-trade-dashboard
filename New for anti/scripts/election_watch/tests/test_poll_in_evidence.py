"""Indiana discovery coverage and preservation boundaries."""
from copy import deepcopy
from pathlib import Path
import unittest
from election_watch.polls import read
from election_watch.live_polls import apply_watchlist,normalize
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from publish_state_packets import rebuild
from tests.poll_config_fixture import SNAPSHOT_DAY
ROOT=Path(__file__).resolve().parents[1]; PUBLIC=ROOT.parents[1]/'public/data'; CFG=ROOT/'config/usa_polls'; DAY='2026-10-16'

class IndianaEvidenceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.audit=read(PUBLIC/'usa_election_poll_release_reviews/2026/IN-source-20261016.json')
  cls.packet=read(ROOT/'config/state_evidence/2026/IN.json')
  cls.policy=apply_targets(apply_matchups(apply_watchlist(read(CFG/'live_2026.json'),read(CFG/'watchlist_2026.json')),read(ROOT/'config/governor_matchups/2026.json'),SNAPSHOT_DAY),read(CFG/'targets_2026.json'),read(CFG/'ballot_reviews_2026.json'),SNAPSHOT_DAY)
  cls.policy['quality_reviews']=read(CFG/'quality_reviews_2026.json')['reviews']
 def test_official_source_printed_names_and_writeins_separate(self):
  rows=self.audit['official_list']['records']
  self.assertEqual({r['district'] for r in rows},{f'{n:02d}' for n in range(1,10)})
  self.assertEqual(sum(not r['write_in'] for r in rows),21)
  self.assertEqual(sum(r['write_in'] for r in rows),5)
 def test_new_registered_api_poll_can_join_every_house_slot(self):
  base=read(PUBLIC/'usa_election_poll_release_reviews/2026/OR-primary-20261014.json')['records'][0]['provider_record']
  races={rid:r for rid,r in self.policy['races'].items() if r['state']=='IN'}
  self.assertEqual(len(races),9)
  for rid,race in races.items():
   raw=deepcopy(base);names=race['required_candidates'];self.assertEqual(len(names),2)
   raw.update(id='synthetic-test-only-'+rid,subject=race['subject'],poll_type='us-representative',seat_name='IN-'+race['district'],start_date='2026-10-14',end_date='2026-10-15',created_at=DAY,url='https://www.opb.org/article/2026/10/16/test-fixture-only/',answers=[{'choice':names[0],'pct':49},{'choice':names[1],'pct':45}])
   obs,held=normalize([raw],self.policy,DAY)
   self.assertFalse(held,rid);self.assertEqual(obs[0]['race_id'],rid)
   self.assertEqual(obs[0]['source_quality']['verification_level'],'partial')
   raw['answers'][1]['choice']='Wrong Former Nominee'
   self.assertFalse(normalize([raw],self.policy,DAY)[0],rid)
 def test_discovery_is_not_an_approved_provider_observation(self):
  self.assertEqual(self.packet['capture']['provider_records'],[])
  self.assertEqual(self.packet['capture']['primary_records'],[])
  held=self.audit['discovered_held_releases'][0]
  self.assertEqual(held['race_id'],'USA:IN:house:05')
  self.assertFalse(held['aggregation_eligible']);self.assertFalse(held['toplines_imported']);self.assertIsNone(held['sample_n'])
 def test_replay_preserves_other_states_and_missing_evidence(self):
  old=read(PUBLIC/'usa_election_live_polls_v1.json');history=read(PUBLIC/'usa_election_poll_history_2026.json')
  board,archive=rebuild(old,history,[self.packet],PUBLIC)
  rows=[r for r in board['races'].values() if r['state']=='IN']
  self.assertEqual(len(rows),9);self.assertTrue(all(r['office']=='house' for r in rows))
  for r in rows:
   self.assertFalse(r['observations'])
   for w in ('7','14'):self.assertIsNone(r['windows'][w]['party'])
  for rid,r in old['races'].items():
   if r['state']!='IN':self.assertEqual(board['races'][rid],r)
  for rid,r in history['races'].items():
   if not rid.startswith('USA:IN:'):self.assertEqual(archive['races'][rid],r)
  for k in ('as_of','fetched_at'):self.assertEqual(board[k],old[k])
  self.assertEqual(board['state_captures']['IN'],self.packet['capture']['receipt'])
