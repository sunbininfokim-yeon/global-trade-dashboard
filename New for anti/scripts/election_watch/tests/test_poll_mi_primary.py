from tests.poll_config_fixture import SNAPSHOT_DAY
import copy,json,unittest
from pathlib import Path
from urllib.error import URLError
from election_watch.live_polls import normalize,summarize
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
from election_watch.governor_source_access import collect_access
from election_watch.state_evidence import build_state,load_finance
from test_poll_state_source_access import Response

ROOT=Path(__file__).resolve().parents[1];CONFIG=ROOT/'config/usa_polls';PUBLIC=ROOT.parent.parent/'public/data'

class MichiganPrimaryTests(unittest.TestCase):
    def setUp(self):
        read=lambda p:json.loads(p.read_text())
        self.policy=apply_targets(apply_matchups(read(CONFIG/'live_2026.json'),read(ROOT/'config/governor_matchups/2026.json'),SNAPSHOT_DAY),read(CONFIG/'targets_2026.json'),read(CONFIG/'ballot_reviews_2026.json'),SNAPSHOT_DAY)
        self.policy['quality_reviews']=read(CONFIG/'quality_reviews_2026.json')['reviews']
        self.rows=[r['provider_record'] for r in read(PUBLIC/'usa_election_poll_release_reviews/2026/MI-primary-20261008.json')['records']]

    def test_decimal_error_is_corrected_without_rescaling_third_parties(self):
        a,r=normalize(self.rows,self.policy,'2026-10-08');self.assertFalse(r);self.assertEqual(len(a),9)
        row=next(p for p in a if p['id']=='us-202eme99d02ce6')
        self.assertEqual(next(x['pct'] for x in row['answers'] if x['name']=='Douglas P. Marsh'),.3)
        self.assertEqual(row['provider_answer_correction']['provider_values']['Douglas P. Marsh'],3)
        self.assertEqual(next(x['pct'] for x in row['answers'] if x['name']=='Abdul El-Sayed'),48.2)

    def test_metadata_changes_require_new_review_including_correction(self):
        for raw in self.rows:
            for key,value in [('sample_size',999),('sponsors',['Unreviewed campaign'])]:
                a,r=normalize([{**raw,key:value}],self.policy,'2026-10-08')
                self.assertFalse(a);self.assertEqual(len(r),1)

    def test_fox_uses_michigan_method_and_rv_lv_samples_are_separate(self):
        a,r=normalize(self.rows,self.policy,'2026-10-08')
        for row in a:
            if row['pollster_group']=='beacon_shaw':
                self.assertIn('michigan_topline',row['methodology_url'])
                self.assertEqual(row['sample_n'],1028)
                self.assertEqual(row['source_quality']['disclosure_review']['overall_registered_sample_n'],1203)
                self.assertEqual(row['source_quality']['reported_precision']['scope'],'1028_LV')

    def test_forced_and_initial_question_context_is_not_two_polls(self):
        a,r=normalize(self.rows,self.policy,'2026-10-08')
        row=next(x for x in a if x['id']=='us-202co/b838141c')
        self.assertEqual([x['pct'] for x in row['answers']],[50,50])
        self.assertEqual(row['source_quality']['ballot_format'],'forced_two_candidate_ballot')
        s=summarize([row],self.policy['races'][row['race_id']],'2026-09-24',7)
        self.assertEqual(s['pollster_count'],1);self.assertEqual(s['tie_count'],1)
        self.assertEqual(len(s['included_ids']),1)

    def test_old_poll_is_not_fresh_and_suffolk_second_preference_is_excluded(self):
        a,r=normalize(self.rows,self.policy,'2026-10-08')
        for rid in ['USA:MI:senate','USA:MI:governor']:
            self.assertEqual(summarize([x for x in a if x['race_id']==rid],self.policy['races'][rid],'2026-10-08',7)['pollster_count'],0)
        for row in a:
            if row['pollster_group']=='suffolk':
                self.assertEqual(row['source_quality']['question_sample_n'],500)
                self.assertTrue(row['source_quality']['disclosure_review']['second_preference_excluded'])

    def test_export_reachability_cannot_mask_current_search_timeout(self):
        agency=json.loads((ROOT/'config/usa_state_campaign_finance_sources_v1.json').read_text())['states']['MI']
        current=agency['public_source_review']['endpoints'][0]['url']
        def opener(req,timeout):
            if req.full_url==current:raise URLError('synthetic source timeout')
            return Response(b'0 matching records found.',url=req.full_url)
        row=collect_access('MI',2026,agency,'2026-10-08T12:00:00+00:00',opener=opener)
        self.assertEqual(row['status'],'source_unavailable')
        self.assertFalse(row['candidate_amounts_available']);self.assertFalse(row['financial_data_collected'])
        self.assertEqual(row['endpoints'][1]['role'],'current_public_export')

    def state_inputs(self):
        read=lambda p:json.loads(p.read_text())
        return [read(CONFIG/'state_evidence_plan_2026.json'),read(CONFIG/'targets_2026.json'),
                read(ROOT/'config/federal_matchups/2026.json'),read(ROOT/'config/governor_matchups/2026.json'),
                read(PUBLIC/'usa_election_live_polls_v1.json'),load_finance(PUBLIC/'usa_election_finance_index_v1.json',2026),
                read(ROOT/'config/usa_state_campaign_finance_sources_v1.json')],read(CONFIG/'state_finance_identities_2026.json')

    def test_reviewed_nickname_links_existing_fec_records_and_keeps_primary_separate(self):
        inputs,identities=self.state_inputs()
        state=build_state('MI','A',*inputs,'2026-10-08',identity_reviews=identities)
        row=next(r for r in state['races'] if r['race_id']=='USA:MI:house:01')
        c=next(c for c in row['candidates'] if c['name']=='Jack Bergman')
        self.assertEqual(c['finance_candidate_id'],'H6MI01226')
        self.assertEqual(c['finance']['all_reported_election_types']['support_cents'],27900)
        self.assertEqual(c['finance']['by_election_type']['P2026']['support_cents'],27900)
        self.assertNotIn('G2026',c['finance']['by_election_type'])
        self.assertEqual(state['office_coverage']['house']['with_observed_current_candidate_spending'],13)

    def test_changed_agency_id_or_fec_identity_requires_review(self):
        for field,value in [('reported_fec_id','H00000001'),('reported_name','Changed, Person'),('source_url','https://example.org/changed')]:
            inputs,ids=self.state_inputs();c=next(c for c in inputs[2]['races']['USA:MI:house:01']['candidates'] if c['name']=='Jack Bergman');c[field]=value
            with self.assertRaisesRegex(ValueError,'changed House finance identity'):build_state('MI','A',*inputs,'2026-10-08',identity_reviews=ids)
        inputs,ids=self.state_inputs();c=next(c for c in inputs[5]['races']['USA:MI:house:01']['candidates'] if c['candidate_id']=='H6MI01226');c['reported_parties']=['DEM']
        with self.assertRaisesRegex(ValueError,'House finance source identity changed'):build_state('MI','A',*inputs,'2026-10-08',identity_reviews=ids)
