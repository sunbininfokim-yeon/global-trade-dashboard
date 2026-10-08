import copy,json,unittest
from pathlib import Path
from election_watch.live_polls import normalize,summarize
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.poll_primary_supplements import merge_primary_supplements
ROOT=Path(__file__).resolve().parents[1];CONFIG=ROOT/'config/usa_polls';PUBLIC=ROOT.parent.parent/'public/data';DAY='2026-10-08'
read=lambda p:json.loads(p.read_text())
class TexasPrimaryTests(unittest.TestCase):
 def setUp(self):
  self.audit=read(PUBLIC/'usa_election_poll_release_reviews/2026/TX-primary-20261009.json')
  self.p=apply_targets(apply_matchups(read(CONFIG/'live_2026.json'),read(ROOT/'config/governor_matchups/2026.json'),DAY),read(CONFIG/'targets_2026.json'),read(CONFIG/'ballot_reviews_2026.json'),DAY)
  self.p['quality_reviews']=read(CONFIG/'quality_reviews_2026.json')['reviews']
 def test_corrected_house_waves_are_august_not_july_or_recent(self):
  rows=[x['provider_record'] for x in self.audit['records'] if x['provider_record']['id'].startswith('primary-')]
  obs,rejected=normalize(rows,self.p,DAY);self.assertFalse(rejected);self.assertEqual(len(obs),3)
  self.assertEqual(sorted(o['sample_n'] for o in obs),[600,700,700])
  for o in obs:
   self.assertEqual((o['field_start'],o['field_end']),('2026-08-18','2026-08-22'))
   self.assertEqual(summarize([o],self.p['races'][o['race_id']],DAY,14)['pollster_count'],0)
   self.assertTrue(o['source_quality']['disclosure_review']['new_2026_district_boundaries_checked'])
 def test_original_wrong_date_api_is_held(self):
  rows=[x['provider_record'] for x in self.audit['held_records'] if x['reason']=='primary_provider_field_dates_conflict']
  obs,rejected=normalize(rows,self.p,DAY);self.assertFalse(obs);self.assertEqual(len(rejected),3)
 def test_statewide_and_district_subsamples_are_not_mixed(self):
  rows=[x['provider_record'] for x in self.audit['records'] if not x['provider_record']['id'].startswith('primary-')]
  obs,rejected=normalize(rows,self.p,DAY);self.assertFalse(rejected);self.assertEqual(len(obs),4)
  self.assertEqual(sorted(o['sample_n'] for o in obs),[850,850,1800,1800])
  for o in obs:
   self.assertFalse(o['source_quality']['accuracy_grade'])
   if o['sample_n']==850:self.assertEqual(o['source_quality']['disclosure_review']['sampling_method'],'non_probability_sample_matching')
 def test_ballot_minor_candidates_and_exact_reviewed_aliases(self):
  for suffix,count in [('house:15',2),('house:28',3),('house:34',4),('senate',3),('governor',3)]:
   r=self.p['races']['USA:TX:'+suffix];self.assertEqual(r['ballot_competition']['candidate_count'],count);self.assertFalse(r['ballot_competition']['general_unopposed']);self.assertFalse(r['ballot_competition']['confirmed_winner'])
  r=self.p['races']['USA:TX:house:34'];self.assertEqual(r['candidates']['Vicente Gonzalez']['canonical_name'],'Vicente González');self.assertEqual(r['candidates']['Chris Royal']['party'],'LIB')
 def test_governor_aliases_do_not_cross_party_candidates(self):
  candidates=read(ROOT/'config/governor_matchups/2026.json')['contests']['TX']['candidates']
  d=next(c for c in candidates if c['name']=='Pat Dixon');self.assertEqual(d['reported_name_aliases'],['Pat Dixon'])
 def test_tec_does_not_publish_misspelled_beneficiary_or_direction(self):
  audit=read(PUBLIC/'usa_governor_finance_audits/2026/TX.json');raw=audit['raw_audit'];self.assertEqual(raw['quality']['input_records'],253873);self.assertEqual(raw['quality']['included_records'],1);self.assertFalse(raw['spending']);self.assertIsNone(audit['support_cents']);self.assertIsNone(audit['oppose_cents'])
  row=raw['unclassified_spending'][0];self.assertEqual(row['candidate_name'],'Greg Abbot');self.assertEqual(row['candidate_identity_status'],'reported_name_only_unverified');self.assertIsNone(row['direction']);self.assertEqual(row['party'],'UNKNOWN')
 def test_reviewed_values_change_requires_new_review(self):
  row=copy.deepcopy(next(x['provider_record'] for x in self.audit['records'] if x['provider_record']['id']=='us-202unic8d0412d'));row['answers'][0]['pct']+=1
  obs,rejected=normalize([row],self.p,DAY);self.assertFalse(obs);self.assertTrue(rejected)
if __name__=='__main__':unittest.main()
