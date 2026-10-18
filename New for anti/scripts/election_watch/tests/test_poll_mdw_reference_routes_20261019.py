"""Future publisher imports are references; an institution route is not release approval."""
from pathlib import Path
from copy import deepcopy
import unittest
from election_watch.polls import read
from election_watch.poll_reference_sources import reference_source
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.live_polls import normalize
C=Path(__file__).resolve().parents[1]/'config';DAY='2026-10-18'
class MDWRouteTests(unittest.TestCase):
 def setUp(self):
  self.p=apply_targets(apply_matchups(read(C/'usa_polls/live_2026.json'),read(C/'governor_matchups/2026.json'),DAY),read(C/'usa_polls/targets_2026.json'),read(C/'usa_polls/ballot_reviews_2026.json'),DAY)
  self.p['quality_reviews']=read(C/'usa_polls/quality_reviews_2026.json')['reviews']
  self.raw={'id':'synthetic-unreviewed-mdw-wave','subject':'2026 Florida','poll_type':'governor','pollster':'MDW Communications','url':'https://www.mdwcomm.com/media/florida-statewide-poll-october-2026.html','created_at':'2026-10-15','start_date':'2026-10-04','end_date':'2026-10-10','population':'lv','sample_size':500,'answers':[{'choice':'Byron Donalds','pct':46},{'choice':'David Jolly','pct':44}],'sponsors':['EDGE Communications'],'internal':False,'partisan':None,'seat_name':None}
 def test_both_api_spellings_share_a_single_publisher_group(self):
  for name in ('MDW','MDW Communications'):
   row={**self.raw,'pollster':name};self.assertEqual(reference_source(row,self.p,DAY)['group'],'mdw_edge')
 def test_url_scope_rejects_unrelated_page_or_impersonation(self):
  for url in ('http://www.mdwcomm.com/media/florida-statewide-poll-october-2026.html','https://www.mdwcomm.com.evil.test/media/florida-statewide-poll-october-2026.html','https://www.mdwcomm.com/media/unrelated.html','https://www.mdwcomm.com:8443/media/florida-statewide-poll-october-2026.html','https://u@www.mdwcomm.com/media/florida-statewide-poll-october-2026.html'):
   self.assertIsNone(reference_source({**self.raw,'url':url},self.p,DAY))
 def test_future_api_import_is_automatically_reference_only(self):
  obs,held=normalize([self.raw],self.p,DAY);self.assertFalse(held);self.assertFalse(obs[0]['aggregation_eligibility']['eligible'])
  self.assertEqual(obs[0]['source_quality']['verification_level'],'partial');self.assertIsNone(obs[0]['source_quality']['accuracy_grade'])
 def test_internal_flag_still_requires_exact_primary_review(self):
  obs,held=normalize([{**self.raw,'internal':True}],self.p,DAY);self.assertFalse(obs);self.assertTrue(held)
 def test_historical_replay_does_not_consume_later_source_approval(self):
  self.assertIsNone(reference_source(self.raw,self.p,'2026-10-17'))
