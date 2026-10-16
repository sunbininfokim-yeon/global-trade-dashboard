"""NY21 exact publisher evidence, named write-in and current-window coverage."""
from copy import deepcopy
from pathlib import Path
import unittest
from election_watch.polls import read
from election_watch.live_polls import normalize,apply_watchlist,summarize
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from publish_state_packets import rebuild
from tests.poll_config_fixture import SNAPSHOT_DAY
ROOT=Path(__file__).resolve().parents[1];CFG=ROOT/'config';PUBLIC=ROOT.parents[1]/'public/data';DAY='2026-10-16';RID='USA:NY:house:21';ID='us-202sie2af2e738'
class NewYork21PrimaryTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.packet=read(CFG/'state_evidence/2026/NY.json');cls.audit=read(PUBLIC/'usa_election_poll_release_reviews/2026/NY21-primary-20261016.json')
  cls.policy=apply_targets(apply_matchups(apply_watchlist(read(CFG/'usa_polls/live_2026.json'),read(CFG/'usa_polls/watchlist_2026.json')),read(CFG/'governor_matchups/2026.json'),SNAPSHOT_DAY),read(CFG/'usa_polls/targets_2026.json'),read(CFG/'usa_polls/ballot_reviews_2026.json'),SNAPSHOT_DAY)
  cls.policy['quality_reviews']=read(CFG/'usa_polls/quality_reviews_2026.json')['reviews'];cls.raw=next(r for r in cls.packet['capture']['provider_records']if r['id']==ID)
 def test_exact_release_is_admitted_with_sample_and_named_writein_disclosure(self):
  obs,held=normalize([self.raw],self.policy,DAY);self.assertFalse(held);r=obs[0]
  self.assertTrue(r['aggregation_eligibility']['eligible']);self.assertEqual((r['population'],r['sample_n']),( 'lv',496))
  self.assertEqual({a['name']:a['pct']for a in r['answers']},{'Blake Gendebien':46,'Anthony Constantino':42,'Christopher Schmidt':5})
  self.assertEqual(next(a['party']for a in r['answers']if a['name']=='Christopher Schmidt'),'IND')
  self.assertEqual(r['source_quality']['verification_level'],'primary_toplines_checked')
  self.assertTrue(r['source_quality']['disclosure_review']['named_write_in_presented']);self.assertFalse(r['source_quality']['disclosure_review']['statewide_governor_poll'])
 def test_printed_candidates_and_campaign_writein_are_distinct(self):
  ballot=read(CFG/'usa_polls/ballot_reviews_2026.json')['races'][RID]
  self.assertEqual({c['name']for c in ballot['candidates']},{'Blake Gendebien','Anthony Constantino'})
  self.assertEqual(ballot['candidate_declared_write_ins'][0]['status'],'campaign_declared_not_agency_certified')
  self.assertEqual(set(self.policy['races'][RID]['required_candidates']),{'Blake Gendebien','Anthony Constantino'})
  self.assertFalse(self.policy['races'][RID]['ballot_competition']['confirmed_winner'])
 def test_seven_day_absence_and_fourteen_day_count_use_fieldwork_not_release(self):
  obs,_=normalize([self.raw],self.policy,DAY);r=self.policy['races'][RID]
  self.assertEqual(summarize(obs,r,DAY,7)['pollster_count'],0)
  window=summarize(obs+[deepcopy(obs[0])],r,DAY,14)
  self.assertEqual(window['pollster_count'],1);self.assertEqual(window['party'],'DEM')
  self.assertEqual(obs[0]['field_end'],'2026-10-06');self.assertEqual(obs[0]['source_quality']['reported_precision']['half_width_pp'],4.6)
 def test_changed_sponsor_sample_or_link_is_not_inherited_approval(self):
  for change in ({'sponsors':['Campaign']},{'sample_size':600},{'url':'https://www.mynbc5.com/another-release'}):
   raw=deepcopy(self.raw);raw.update(change);obs,held=normalize([raw],self.policy,DAY)
   self.assertFalse(obs);self.assertEqual(held[0]['reason'],'primary_review_provider_metadata_changed')
 def test_new_original_publisher_two_candidate_release_can_connect_but_new_commissioner_link_is_held(self):
  raw=deepcopy(self.raw);raw.update(id='synthetic-test-only-ny21',url='https://sri.siena.edu/test-fixture-only/',start_date='2026-10-14',end_date='2026-10-15',created_at=DAY,answers=self.raw['answers'][:2])
  obs,held=normalize([raw],self.policy,DAY);self.assertFalse(held);self.assertTrue(obs[0]['aggregation_eligibility']['eligible'])
  raw['url']='https://www.mynbc5.com/test-fixture-only/';obs,held=normalize([raw],self.policy,DAY)
  self.assertFalse(obs);self.assertEqual(held[0]['reason'],'unregistered_primary_host')
 def test_state_replay_keeps_every_other_state_dates_and_focus(self):
  old=read(PUBLIC/'usa_election_live_polls_v1.json');archive=read(PUBLIC/'usa_election_poll_history_2026.json');board,history=rebuild(old,archive,[self.packet],PUBLIC)
  for rid,r in old['races'].items():
   if r['state']!='NY':self.assertEqual(board['races'][rid],r)
  for rid,r in archive['races'].items():
   if not rid.startswith('USA:NY:'):self.assertEqual(history['races'][rid],r)
  for k in ('as_of','fetched_at'):self.assertEqual(board[k],old[k])
  self.assertEqual(board['house_poll_focus']['race_count'],104);self.assertEqual(board['state_captures']['NY'],self.packet['capture']['receipt'])
  r=board['races'][RID];self.assertEqual(r['windows']['14']['included_ids'],[ID]);self.assertFalse(r['windows']['7']['included_ids'])
if __name__=='__main__':unittest.main()
