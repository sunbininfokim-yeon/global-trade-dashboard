from tests.poll_config_fixture import SNAPSHOT_DAY
"""CA48 exact-release admission and state-only replay."""
import copy
from pathlib import Path
import unittest
from election_watch.polls import read
from election_watch.state_inputs import packets
from election_watch.poll_targets import apply_targets
from election_watch.governor_matchups import apply_matchups
from election_watch.live_polls import normalize
from publish_state_packets import rebuild
ROOT=Path(__file__).resolve().parents[1]; PUBLIC=ROOT.parents[1]/'public/data'
class CaliforniaReleaseTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.packet=next(p for p in packets() if p['state']=='CA')
  cls.policy=apply_targets(apply_matchups(read(ROOT/'config/usa_polls/live_2026.json'),read(ROOT/'config/governor_matchups/2026.json'),SNAPSHOT_DAY),read(ROOT/'config/usa_polls/targets_2026.json'),read(ROOT/'config/usa_polls/ballot_reviews_2026.json'),SNAPSHOT_DAY)
  cls.policy['quality_reviews']=read(ROOT/'config/usa_polls/quality_reviews_2026.json')['reviews']
  cls.raw=next(r for r in cls.packet['capture']['provider_records'] if r['id']=='us-202sur70c7e750')
 def test_primary_values_question_population_and_distinct_release_dates(self):
  rows,held=normalize([self.raw],self.policy,'2026-10-16');self.assertFalse(held);row=rows[0]
  self.assertEqual({a['name']:a['pct'] for a in row['answers']},{'Marni von Wilpert':47,'Jim Desmond':38})
  self.assertEqual((row['sample_n'],row['population'],row['field_start'],row['field_end']),(518,'lv','2026-10-01','2026-10-07'))
  self.assertEqual(row['provider_record_date'],'2026-10-09')
  self.assertEqual(row['source_quality']['disclosure_review']['primary_release_date'],'2026-10-08')
  self.assertTrue(row['aggregation_eligibility']['eligible'])
  self.assertEqual(row['source_quality']['reported_precision']['kind'],'credibility_interval')
  self.assertEqual(row['source_quality']['reported_precision']['half_width_pp'],5.2)
  self.assertIsNone(row['margin_of_error_pp']);self.assertIsNone(row['source_quality']['accuracy_grade'])
 def test_changed_metadata_or_future_wave_does_not_inherit_review(self):
  for field,value in [('sample_size',519),('sponsors',['Another commissioner']),('url',self.raw['url']+'&new=1')]:
   changed=copy.deepcopy(self.raw);changed[field]=value
   rows,held=normalize([changed],self.policy,'2026-10-16')
   self.assertFalse(rows);self.assertEqual(held[0]['reason'],'primary_review_provider_metadata_changed')
  changed=copy.deepcopy(self.raw);changed['id']='unreviewed-ca48-future-wave'
  rows,held=normalize([changed],self.policy,'2026-10-16')
  self.assertFalse(rows);self.assertEqual(held[0]['reason'],'commissioner_not_reviewed')
 def test_replay_preserves_other_states_dates_focus_and_ca22_reference(self):
  old=read(PUBLIC/'usa_election_live_polls_v1.json');history=read(PUBLIC/'usa_election_poll_history_2026.json')
  new,archive=rebuild(old,history,[self.packet],PUBLIC)
  for rid,race in old['races'].items():
   if race['state']!='CA':
    self.assertEqual(new['races'][rid],race,rid)
    if rid in history['races']:self.assertEqual(archive['races'][rid],history['races'][rid],rid)
  for key in ('as_of','fetched_at'):self.assertEqual(new[key],old[key])
  for rid,race in old['house_poll_focus']['races'].items():
   if race['state']!='CA':self.assertEqual(new['house_poll_focus']['races'][rid],race,rid)
  for rid,race in old['races'].items():
   if race['state']=='CA':
    self.assertTrue({r['id'] for r in race['observations']} <= {r['id'] for r in new['races'][rid]['observations']},rid)
  self.assertEqual(new['house_poll_focus']['race_count'],104)
  self.assertEqual(new['state_captures']['CA']['captured_at'],self.packet['capture']['fetched_at'])
  self.assertEqual(new['state_packet_replays']['CA']['new_collection'],False)
  row=next(r for r in new['races']['USA:CA:house:48']['observations'] if r['id']==self.raw['id'])
  self.assertTrue(row['aggregation_eligibility']['eligible'])
  ca22=next(r for r in new['races']['USA:CA:house:22']['observations'] if r['id']=='us-202tul5fdc419c')
  self.assertFalse(ca22['aggregation_eligibility']['eligible'])
if __name__=='__main__':unittest.main()
