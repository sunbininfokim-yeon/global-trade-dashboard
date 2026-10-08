import copy, hashlib, json, unittest
from pathlib import Path
from election_watch.governor_matchups import apply_matchups
from election_watch.live_polls import normalize, summarize
from election_watch.poll_targets import apply_targets
from election_watch.poll_primary_supplements import merge_primary_supplements
from election_watch.state_evidence import build_state, load_finance
from test_poll_pa_primary import Response

ROOT=Path(__file__).resolve().parents[1]; CONFIG=ROOT/'config/usa_polls'
PUBLIC=ROOT.parent.parent/'public/data'
read=lambda p:json.loads(p.read_text())

class NorthCarolinaPrimaryTests(unittest.TestCase):
    def setUp(self):
        self.policy=apply_targets(apply_matchups(read(CONFIG/'live_2026.json'),
            read(ROOT/'config/governor_matchups/2026.json'),'2026-10-08'),
            read(CONFIG/'targets_2026.json'),read(CONFIG/'ballot_reviews_2026.json'),'2026-10-08')
        self.policy['quality_reviews']=read(CONFIG/'quality_reviews_2026.json')['reviews']
        self.audit=read(PUBLIC/'usa_election_poll_release_reviews/2026/NC-primary-20261008.json')
        self.rows=[r['provider_record'] for r in self.audit['records']]
        self.snapshot=read(CONFIG/'primary_supplements_2026.json')
        self.body=b'%PDF-1.7 synthetic NC source fixture'
        digest=hashlib.sha256(self.body).hexdigest()
        for e in self.snapshot['records']:
            if e['state']!='NC':continue
            for d in e['documents']:d['sha256']=digest
            self.policy['quality_reviews'][e['record']['id']]['primary_documents']=copy.deepcopy(e['documents'])
        self.opener=lambda req,timeout:Response(req.full_url,self.body)

    def current_rows(self):
        provider=[r for r in self.rows if not r['id'].startswith('primary-')]
        return merge_primary_supplements(provider,self.snapshot,'2026-10-08',['NC'],self.opener)

    def test_source_types_and_commissioner_primary_releases_are_connected(self):
        rows,receipts=self.current_rows();a,r=normalize(rows,self.policy,'2026-10-08')
        self.assertFalse(r);self.assertEqual(len(a),8);self.assertEqual(len(receipts),2)
        cc=next(o for o in a if o['id'].startswith('primary-opinion'))
        self.assertEqual(cc['race_id'],'USA:NC:senate')
        self.assertTrue(cc['aggregation_eligibility']['eligible'])
        self.assertEqual(cc['verification'],'reviewed_primary_source_snapshot')

    def test_alias_and_general_phase_are_officially_reviewed(self):
        race=self.policy['races']['USA:NC:house:01']
        self.assertEqual(race['candidates']['Donald Davis']['canonical_name'],'Don Davis')
        self.assertEqual(race['general_from'],'2026-04-17')
        self.assertIn('Candidate_Listing_2026.csv',race['ballot_review']['source_url'])
        senate=self.policy['races']['USA:NC:senate']['candidates']
        self.assertEqual(senate['Shannon Bray']['canonical_name'],'Shannon W. Bray')
        self.assertEqual(senate['Michael Dublin']['party'],'GRN')
        self.assertNotIn('USA:NC:governor',self.policy['races'])

    def test_party_commissioned_house_reference_is_never_a_lead(self):
        rows,_=self.current_rows();a,r=normalize(rows,self.policy,'2026-10-08')
        house=[o for o in a if o['race_id']=='USA:NC:house:01']
        self.assertEqual(len(house),1);self.assertFalse(house[0]['aggregation_eligibility']['eligible'])
        self.assertEqual(house[0]['commissioning']['partisan'],'REP')
        s=summarize(house,self.policy['races']['USA:NC:house:01'],'2026-05-01',7)
        self.assertEqual(s['pollster_count'],0);self.assertIsNone(s['party'])

    def test_lv_rv_are_one_wave_and_old_sources_are_not_fresh(self):
        rows,_=self.current_rows();a,r=normalize(rows,self.policy,'2026-10-08')
        hpu=[o for o in a if o['id'] in ['us-202hig0453aa0e','us-202hig8ec8c4e5']]
        self.assertTrue(all(o['pollster_group']==self.policy['pollsters'][o['pollster']]['group'] for o in hpu))
        s=summarize(hpu,self.policy['races']['USA:NC:senate'],'2026-08-13',7)
        self.assertEqual(s['pollster_count'],1);self.assertEqual(s['included_ids'],['us-202hig0453aa0e'])
        for days in [7,14]:
            self.assertEqual(summarize(a,self.policy['races']['USA:NC:senate'],'2026-10-08',days)['pollster_count'],0)

    def test_initial_ballot_and_non_candidate_responses_are_preserved(self):
        rows,_=self.current_rows();a,r=normalize(rows,self.policy,'2026-10-08')
        o=next(o for o in a if o['id'].startswith('primary-opinion'))
        self.assertEqual([v['pct'] for v in o['answers']],[51.3,41.3])
        context=o['source_quality']['disclosure_review']
        self.assertEqual(context['non_candidate_responses']['undecided'],5.4)
        self.assertEqual(context['same_wave_context']['leaned_ballot']['Roy Cooper'],51.7)
        self.assertFalse(context['leaned_question_counted_separately'])
        elon=next(o for o in a if o['pollster_group']=='elon')
        self.assertEqual(len(elon['answers']),4);self.assertEqual(elon['source_quality']['disclosure_review']['likely_sample_n'],565)

    def test_primary_conflicts_and_missing_methods_stay_held(self):
        held=[r['provider_record'] for r in self.audit['held_records'] if 'provider_record' in r]
        a,r=normalize(held,self.policy,'2026-10-08');self.assertFalse(a)
        reasons={x['id']:x['reason'] for x in r}
        self.assertEqual(reasons['us-202bigf2db767c'],'primary_provider_candidate_values_conflict')
        self.assertEqual(reasons['us-202elo069243f3'],'primary_provider_field_dates_conflict')
        self.assertEqual(reasons['us-202nei29757f09'],'primary_methodology_not_obtained')
        self.assertEqual(reasons['us-202easa9c1ac17'],'forced_choice_question_not_comparable')

    def test_changed_metadata_requires_review_and_outage_keeps_original_reference(self):
        rows,_=self.current_rows()
        for raw in rows:
            a,r=normalize([{**raw,'sample_size':999}],self.policy,'2026-10-08')
            self.assertFalse(a);self.assertEqual(len(r),1)
        def fail(req,timeout):raise OSError('source unavailable')
        rows,receipts=merge_primary_supplements([],self.snapshot,'2026-10-08',['NC'],fail)
        a,r=normalize(rows,self.policy,'2026-10-08');self.assertFalse(r);self.assertEqual(len(a),2)
        self.assertTrue(all(not x['aggregation_eligibility']['eligible'] for x in a))
        self.assertTrue(all(x['original_reviewed_on']=='2026-10-08' for x in receipts))
        self.assertEqual(next(x for x in a if x['race_id']=='USA:NC:senate')['provider_record_date'],'2026-09-25')

    def test_later_api_duplicate_counts_once_and_conflict_fails_closed(self):
        raw=copy.deepcopy(next(e['record'] for e in self.snapshot['records'] if e['state']=='NC' and e['record']['poll_type']=='us-senator'))
        raw['id']='api-later-nc-test';rows,receipts=merge_primary_supplements([raw],self.snapshot,'2026-10-08',['NC'],self.opener)
        self.assertEqual(len(rows),2);self.assertEqual(receipts[0]['provider_duplicate_ids'],[raw['id']])
        raw['answers'][0]['pct']-=1
        with self.assertRaisesRegex(ValueError,'primary_and_provider_wave_conflict'):
            merge_primary_supplements([raw],self.snapshot,'2026-10-08',['NC'],self.opener)
        bad=copy.deepcopy(self.snapshot);next(e for e in bad['records'] if e['state']=='NC')['documents'][0]['url']='https://docs.google.com/unreviewed.pdf'
        with self.assertRaisesRegex(ValueError,'unreviewed primary document'):
            merge_primary_supplements([],bad,'2026-10-08',['NC'],self.opener)

    def test_legal_name_identity_change_is_rejected_and_primary_spending_stays_separate(self):
        inputs=[read(CONFIG/'state_evidence_plan_2026.json'),read(CONFIG/'targets_2026.json'),
            read(ROOT/'config/federal_matchups/2026.json'),read(ROOT/'config/governor_matchups/2026.json'),
            read(PUBLIC/'usa_election_live_polls_v1.json'),load_finance(PUBLIC/'usa_election_finance_index_v1.json',2026),
            read(ROOT/'config/usa_state_campaign_finance_sources_v1.json')]
        ids=read(CONFIG/'state_finance_identities_2026.json')
        state=build_state('NC','A',*inputs,'2026-10-08',identity_reviews=ids)
        murphy=next(c for r in state['races'] if r['race_id']=='USA:NC:house:03' for c in r['candidates'] if c['name']=='Greg Murphy')
        self.assertEqual(murphy['finance_candidate_id'],'H0NC03172')
        self.assertIsNone(murphy['finance']['all_reported_election_types']['support_cents'])
        hardy=next(c for r in state['races'] if r['race_id']=='USA:NC:house:07' for c in r['candidates'] if c['name']=='Kimberly Hardy')
        self.assertEqual(hardy['finance']['by_election_type']['G2026']['support_cents'],50802)
        smith=next(c for r in state['races'] if r['race_id']=='USA:NC:house:03' for c in r['candidates'] if c['name']=='Raymond Smith')
        self.assertIn('P2026',smith['finance']['by_election_type'])
        self.assertIsNone(smith['finance']['by_election_type']['P2026']['support_cents'])
        c=next(c for c in inputs[2]['races']['USA:NC:house:03']['candidates'] if c['name']=='Greg Murphy')
        c['reported_legal_name']='Unreviewed Different Candidate'
        with self.assertRaisesRegex(ValueError,'changed House finance identity'):
            build_state('NC','A',*inputs,'2026-10-08',identity_reviews=ids)

if __name__=='__main__':unittest.main()
