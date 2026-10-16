from pathlib import Path
import unittest
from election_watch.polls import read
from publish_state_packets import rebuild
ROOT=Path(__file__).resolve().parents[1]; PUBLIC=ROOT.parents[1]/'public/data'
class MontanaEvidenceTests(unittest.TestCase):
 def test_official_four_way_senate_and_separate_writein(self):
  r=read(ROOT/'config/federal_matchups/2026.json')['races']['USA:MT:senate']
  self.assertEqual({c['name']:c['party'] for c in r['candidates']},{'Kurt Alme':'REP','Kyle Austin':'LIB','Alani Bankhead':'DEM','Seth Bodnar':'IND'})
  self.assertEqual(len(r['declared_write_ins']),1)
  self.assertEqual(r['declared_write_ins'][0]['name'],'Jami Dee Woodman')
  self.assertTrue(all(c['candidate_id'] is None for c in r['candidates']))
 def test_house_universe_and_no_governor_contest(self):
  rs=read(ROOT/'config/usa_polls/ballot_reviews_2026.json')['races']
  mt=[r for r in rs.values() if r['state']=='MT']
  self.assertEqual(len(mt),3); self.assertEqual(sum(len(r['candidates']) for r in mt),11)
  self.assertNotIn('USA:MT:governor',rs)
 def test_state_replay_keeps_other_states_and_global_dates(self):
  old=read(PUBLIC/'usa_election_live_polls_v1.json');hist=read(PUBLIC/'usa_election_poll_history_2026.json');p=read(ROOT/'config/state_evidence/2026/MT.json')
  new,archive=rebuild(old,hist,[p],PUBLIC)
  for rid,r in old['races'].items():
   if r['state']!='MT':self.assertEqual(new['races'][rid],r)
  for key in ('as_of','fetched_at'):self.assertEqual(old[key],new[key])
  for rid,r in hist['races'].items():
   if not rid.startswith('USA:MT:'):self.assertEqual(archive['races'][rid],r)
