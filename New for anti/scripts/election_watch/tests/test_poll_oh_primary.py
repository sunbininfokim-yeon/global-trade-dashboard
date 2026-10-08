import copy,hashlib,json,unittest
from pathlib import Path
from election_watch.governor_matchups import apply_matchups,validate_snapshot
from election_watch.live_polls import normalize,summarize
from election_watch.poll_targets import apply_targets
from election_watch.poll_primary_supplements import merge_primary_supplements
from election_watch.state_evidence import build_state,load_finance
from test_poll_pa_primary import Response

ROOT=Path(__file__).resolve().parents[1];CONFIG=ROOT/'config/usa_polls';PUBLIC=ROOT.parent.parent/'public/data'
read=lambda p:json.loads(p.read_text())
DAY='2026-10-08'

class OhioPrimaryTests(unittest.TestCase):
    def setUp(self):
        self.gov=read(ROOT/'config/governor_matchups/2026.json')
        self.policy=apply_targets(apply_matchups(read(CONFIG/'live_2026.json'),self.gov,DAY),read(CONFIG/'targets_2026.json'),read(CONFIG/'ballot_reviews_2026.json'),DAY)
        self.policy['quality_reviews']=read(CONFIG/'quality_reviews_2026.json')['reviews']
        self.audit=read(PUBLIC/'usa_election_poll_release_reviews/2026/OH-primary-20261008.json')
        self.rows=[e['provider_record'] for e in self.audit['records']]
        self.supp=read(CONFIG/'primary_supplements_2026.json');self.body=b'%PDF-1.7 synthetic Ohio source fixture'
        for e in self.supp['records']:
            if e['state']!='OH':continue
            for d in e['documents']:d['sha256']=hashlib.sha256(self.body).hexdigest()
            self.policy['quality_reviews'][e['record']['id']]['primary_documents']=copy.deepcopy(e['documents'])
        self.opener=lambda req,timeout:Response(req.full_url,self.body)

    def current(self,opener=None):
        rows,receipts=merge_primary_supplements([r for r in self.rows if not r['id'].startswith('primary-')],self.supp,DAY,['OH'],opener or self.opener)
        accepted,rejected=normalize(rows,self.policy,DAY)
        self.assertFalse(rejected)
        return accepted,receipts

    def test_latest_cnn_is_joined_to_special_senate_and_governor(self):
        obs,_=self.current();self.assertEqual(len(obs),7)
        for rid,values in [('USA:OH:senate',[49,43]),('USA:OH:governor',[50,42])]:
            o=next(o for o in obs if o['race_id']==rid and o['pollster_group']=='cnn_ssrs')
            self.assertEqual([a['pct'] for a in o['answers']],values)
            self.assertEqual(o['field_end'],'2026-10-05')
            self.assertEqual(o['sample_n'],760)
            self.assertIn('all760RV',o['source_quality']['disclosure_review']['lv_definition'])
            self.assertEqual(o['source_quality']['ballot_format'],'two_candidate_with_leaners')
            self.assertTrue(o['contest_id'].endswith(':special' if rid.endswith('senate') else ':regular'))
            s=summarize([p for p in obs if p['race_id']==rid],self.policy['races'][rid],DAY,7)
            self.assertEqual(s['pollster_count'],1);self.assertEqual(s['party'],'DEM')
            self.assertEqual(s['status'],'single_poll_lead')

    def test_suffolk_missing_senate_preserves_minor_party_and_unallocated_votes(self):
        obs,receipts=self.current();self.assertEqual(len(receipts),1)
        o=next(o for o in obs if o['id'].startswith('primary-suffolk'))
        self.assertEqual(o['verification'],'reviewed_primary_source_snapshot')
        self.assertEqual([a['pct'] for a in o['answers']],[46.6,44,1,2])
        self.assertEqual([a['party'] for a in o['answers']],['DEM','REP','OTH','LIB'])
        self.assertEqual(o['source_quality']['disclosure_review']['non_candidate_responses']['undecided'],6)
        self.assertLess(sum(a['pct'] for a in o['answers']),100)
        s=summarize([p for p in obs if p['race_id']=='USA:OH:senate'],self.policy['races']['USA:OH:senate'],DAY,14)
        self.assertEqual(s['population'],'lv');self.assertEqual(s['pollster_count'],2)
        self.assertNotIn('us-202mara7f1d430',s['included_ids'])

    def test_internal_primary_disclosure_corrects_provider_flag_only_as_reference(self):
        obs,_=self.current();o=next(o for o in obs if o['race_id']=='USA:OH:house:09')
        self.assertTrue(o['commissioning']['internal']);self.assertFalse(o['commissioning']['provider_internal'])
        self.assertFalse(o['aggregation_eligibility']['eligible'])
        s=summarize([o],self.policy['races'][o['race_id']],'2026-09-24',7)
        self.assertEqual(s['pollster_count'],0);self.assertIsNone(s['party'])
        ident=o['id'];self.policy['quality_reviews'][ident]['admission']['signal_eligible']=True
        raw=next(r for r in self.rows if r['id']==ident)
        self.assertEqual(normalize([raw],self.policy,DAY)[1][0]['reason'],'primary_internal_poll_requires_reference_review')

    def test_changed_provider_sponsor_or_values_requires_new_review(self):
        raw=next(r for r in self.rows if r['id']=='us-202dcc0662cb55')
        for update in [{'sponsors':['different']},{'internal':True},{'sample_size':500}]:
            self.assertFalse(normalize([{**raw,**update}],self.policy,DAY)[0])
        raw=next(r for r in self.rows if r['id']=='us-202cnna1713372');raw=copy.deepcopy(raw);raw['answers'][0]['pct']=99
        self.assertFalse(normalize([raw],self.policy,DAY)[0])

    def test_pdf_change_or_failure_carries_original_dates_as_reference(self):
        obs,receipts=self.current(lambda req,timeout:Response(req.full_url,b'%PDF-1.7 changed document'))
        o=next(o for o in obs if o['id'].startswith('primary-suffolk'))
        self.assertFalse(o['aggregation_eligibility']['eligible']);self.assertEqual(o['field_end'],'2026-09-27')
        self.assertEqual(receipts[0]['original_reviewed_on'],DAY)
        self.assertEqual(o['primary_source_capture']['status'],'carried_forward_reference_only')
        def fail(req,timeout):raise OSError('synthetic unavailable')
        self.assertFalse(next(o for o in self.current(fail)[0] if o['id'].startswith('primary-suffolk'))['aggregation_eligibility']['eligible'])

    def test_later_provider_wave_deduplicates_and_conflict_fails_capture(self):
        raw=next(copy.deepcopy(r) for r in self.rows if r['id'].startswith('primary-suffolk'));raw['id']='later-provider-id'
        rows,receipts=merge_primary_supplements([raw],self.supp,DAY,['OH'],self.opener)
        self.assertEqual(len(rows),1);self.assertEqual(receipts[0]['provider_duplicate_ids'],[raw['id']])
        raw['sample_size']=499
        with self.assertRaisesRegex(ValueError,'primary_and_provider_wave_conflict'):
            merge_primary_supplements([raw],self.supp,DAY,['OH'],self.opener)

    def test_held_house_methods_and_geographic_conflicts_stay_held(self):
        held=[e['provider_record'] for e in self.audit['held_records']]
        obs,rejected=normalize(held,self.policy,DAY);self.assertFalse(obs);self.assertEqual(len(rejected),11)
        reasons={r['id']:r['reason'] for r in rejected}
        self.assertEqual(reasons['us-202tavd2d23773'],'primary_provider_sample_mismatch')
        self.assertEqual(reasons['us-202big1f625134'],'primary_geography_methodology_conflict')
        self.assertEqual(reasons['us-202quad5474d87'],'primary_question_and_methods_not_obtained')

    def test_official_nominees_and_write_ins_are_contested_not_confirmed_winners(self):
        for rid,n in [('USA:OH:house:01',3),('USA:OH:house:08',2),('USA:OH:house:13',3),('USA:OH:senate',7),('USA:OH:governor',7)]:
            comp=self.policy['races'][rid]['ballot_competition'];self.assertEqual(comp['candidate_count'],n)
            self.assertFalse(comp['confirmed_winner']);self.assertFalse(comp['general_unopposed'])
        self.assertEqual(self.policy['races']['USA:OH:governor']['candidates']['Don Kissick']['party'],'LIB')
        self.assertEqual(self.policy['races']['USA:OH:house:09']['candidates']['Marcy Kaptur']['canonical_name'],'Marcia Carolyn "Marcy" Kaptur')
        self.assertIn('Sandeep Dixit',self.policy['races']['USA:OH:house:13']['candidates'])
        validate_snapshot(self.gov,2026,DAY)

    def test_house_identity_is_bound_to_authority_name_and_finance(self):
        federal=read(ROOT/'config/federal_matchups/2026.json');identities=read(CONFIG/'state_finance_identities_2026.json')
        finance=load_finance(PUBLIC/'usa_election_finance_index_v1.json',2026)
        args=('OH','B',read(CONFIG/'state_evidence_plan_2026.json'),read(CONFIG/'targets_2026.json'),federal,self.gov,read(PUBLIC/'usa_election_live_polls_v1.json'),finance,read(ROOT/'config/usa_state_campaign_finance_sources_v1.json'),DAY,identities)
        result=build_state(*args);c=next(c for r in result['races'] if r['race_id']=='USA:OH:house:08' for c in r['candidates'] if c['party']=='DEM')
        self.assertEqual(c['finance_candidate_id'],'H8OH08097')
        self.assertIsNone(c['finance']['all_reported_election_types']['support_cents'])
        federal['races']['USA:OH:house:08']['candidates'][0]['reported_name']='different name'
        with self.assertRaisesRegex(ValueError,'changed House finance identity'):
            build_state(*args)

    def test_new_cnn_provider_release_can_join_as_partial_without_reusing_old_review(self):
        raw=copy.deepcopy(next(r for r in self.rows if r['id']=='us-202cnna1713372'))
        raw['id']='synthetic-new-cnn-release';raw['answers'][0]['pct']=48
        obs,rejected=normalize([raw],self.policy,DAY)
        self.assertFalse(rejected);self.assertEqual(obs[0]['source_quality']['verification_level'],'partial')
        raw['sponsors']=['unreviewed commissioner']
        self.assertEqual(normalize([raw],self.policy,DAY)[1][0]['reason'],'commissioner_not_reviewed')

    def test_finite_suffolk_supplement_does_not_admit_unreviewed_pdf_hosts(self):
        for e in self.supp['records']:
            if e['state']=='OH':e['documents'][0]['url']='https://unreviewed.example/release.pdf'
        with self.assertRaisesRegex(ValueError,'unreviewed primary document'):
            merge_primary_supplements([],self.supp,DAY,['OH'],self.opener)
