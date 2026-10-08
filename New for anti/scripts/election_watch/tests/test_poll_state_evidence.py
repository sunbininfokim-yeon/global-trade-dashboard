import copy
import json
from pathlib import Path
import tempfile
import unittest

from election_watch.state_evidence import ordered_states, expected_races, amounts, candidate_finance, build_state, publish_states

ROOT = Path(__file__).resolve().parents[1]


class StateEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((ROOT/'config/usa_polls/state_evidence_plan_2026.json').read_text())

    def fixture(self, state='AK'):
        catalog = {'states': {state: {'house_seats': 1, 'name': state}},
                   'senate_states': [state], 'governor_states': [state]}
        candidates = [{'name': 'Candidate Alpha', 'party': 'DEM', 'candidate_id': 'H00000001'},
                      {'name': 'Candidate Beta', 'party': 'REP', 'candidate_id': 'H00000002'}]
        federal = {'races': {rid: {'race_id': rid, 'state': state, 'office': 'house' if ':house:' in rid else 'senate',
                   'source_url': 'https://example.org/roster', 'candidates': copy.deepcopy(candidates)}
                   for rid in expected_races(state,catalog) if not rid.endswith(':governor')}}
        governors = {'contests': {state: {'state':state,'source_url':'https://example.org/governor','candidates':candidates}}}
        races = {rid: {'race_id':rid,'state':state,'office':rid.split(':')[2],'district':'00' if ':house:' in rid else None,
                      'election_date':'2026-11-03','required_candidates':['Candidate Alpha','Candidate Beta'],
                      'schedule_status':'reported_general_matchup','phase':'pre_election','observations':[]}
                 for rid in expected_races(state,catalog)}
        polls = {'cycle':2026,'as_of':'2026-10-08','fetched_at':'2026-10-08T00:00:00+00:00',
                 'source_status':'ok','source':{'request_url':'https://example.org/polls'},'races':races}
        finance = {'cycle':2026,'races':{},'source_status':{'federal':{'last_success_at':'2026-10-02T00:00:00+00:00'}},
                   'generated_at':'2026-10-07T00:00:00+00:00','unmatched':[f'USA:{state}:house:99']}
        directory = {'states':{},'directory_url':'https://example.org/directory'}
        return catalog,federal,governors,polls,finance,directory

    def state(self,fixture,as_of='2026-10-08'):
        return build_state('AK','B',self.plan,*fixture,as_of)

    def test_fifty_states_once_in_five_ten_state_groups(self):
        order=ordered_states(self.plan,'2026-10-08')
        self.assertEqual(len(order),50);self.assertEqual(order[:2],[('A','NY'),('A','TN')])
        self.assertEqual(order[-1],('E','WY'))
        broken=copy.deepcopy(self.plan);broken['groups']['E']['states'][0]='NY'
        with self.assertRaises(ValueError):ordered_states(broken,'2026-10-08')

    def test_at_large_and_non_election_are_not_missing_seats(self):
        f=self.fixture();f[0]['senate_states']=[];f[0]['governor_states']=[]
        row=self.state(f)
        self.assertEqual([r['race_id'] for r in row['races']],['USA:AK:house:00'])
        self.assertTrue(row['office_coverage']['senate']['non_election'])
        self.assertEqual(row['governor_source_route']['status'],'non_election')

    def test_missing_and_unimplemented_finance_stay_null(self):
        row=self.state(self.fixture())
        self.assertEqual(row['governor_source_route']['status'],'adapter_or_source_review_required')
        self.assertIsNone(row['races'][0]['candidates'][0]['finance']['all_reported_election_types']['support_cents'])
        self.assertEqual(row['unmatched_reported_finance_races'],['USA:AK:house:99'])

    def test_verified_id_joins_preserve_support_oppose_and_primary(self):
        totals={'super_pac':{'records':2,'support_cents':100,'oppose_cents':500}}
        candidate={'candidate_id':'H00000001'}
        asset={'candidates':[{'candidate_id':'H00000001','totals_by_category':totals,
                            'election_types':{'P2026':{'totals_by_category':totals}}}]}
        x=candidate_finance(candidate,asset,'house')
        self.assertEqual(x['all_reported_election_types']['oppose_cents'],500)
        self.assertEqual(set(x['by_election_type']),{'P2026'})
        self.assertNotIn('G2026',x['by_election_type'])
        self.assertIsNone(candidate_finance({'candidate_id':None},asset,'house')['all_reported_election_types']['support_cents'])

    def test_state_ie_cannot_become_federal_super_pac(self):
        totals={'state_independent_spender_unclassified':{'records':1,'support_cents':300,'oppose_cents':0}}
        self.assertEqual(amounts(totals,('state_independent_spender_unclassified',))['support_cents'],300)
        self.assertIsNone(amounts(totals,('super_pac',))['support_cents'])

    def test_public_export_audit_does_not_publish_candidate_amounts(self):
        f=self.fixture();audit={'schema':'usa_governor_finance_audit_v1','state':'AK','cycle':2026,
            'status':'collected_normalization_held','captured_at':'2026-10-08T01:00:00Z'}
        f[3]['state_captures']={'AK':{'state':'AK','cycle':2026,'primary_rechecked_ids':['p'],
                                   'governor_audit_captured_at':audit['captured_at']}}
        row=build_state('AK','B',self.plan,*f,'2026-10-08',governor_audits={'AK':audit})
        self.assertEqual(row['governor_source_route']['status'],'collected_normalization_held')
        self.assertEqual(row['work_status'],'live_sources_reviewed_partial')
        self.assertIsNone(row['races'][-1]['finance']['all_reported_candidates']['support_cents'])
        f[3]['state_captures']['AK']['governor_audit_captured_at']='2026-10-07T01:00:00Z'
        self.assertEqual(build_state('AK','B',self.plan,*f,'2026-10-08',governor_audits={'AK':audit})['work_status'],
                         'baseline_join_checked')

    def test_finance_audit_wrong_state_or_future_date_is_held(self):
        for state,day in [('TN','2026-10-08'),('AK','2026-10-09')]:
            audit={'schema':'usa_governor_finance_audit_v1','state':state,'cycle':2026,
                   'status':'collected_normalization_held','captured_at':day+'T01:00:00Z'}
            with self.assertRaises(ValueError):
                build_state('AK','B',self.plan,*self.fixture(),'2026-10-08',governor_audits={'AK':audit})

    def test_changed_nominee_does_not_inherit_poll_or_lead(self):
        f=self.fixture();f[3]['races']['USA:AK:house:00']['observations']=[{'id':'old-poll','answers':[{'name':'Old Nominee','pct':60,'party':'DEM'}]}]
        row=self.state(f)['races'][0]['polling']
        self.assertEqual(row['observations'],[]);self.assertEqual(row['held_observation_ids'],['old-poll'])
        self.assertEqual(row['windows']['7']['status'],'changed_matchup_review_required')
        self.assertFalse(row['automatic_admission'])

    def test_nonmajor_or_other_answer_does_not_discard_valid_major_poll(self):
        f=self.fixture();f[3]['races']['USA:AK:house:00']['observations']=[{'id':'p',
            'field_end':'2026-10-07','population':'lv','pollster_group':'test','source_quality':{},
            'aggregation_eligibility':{'eligible':True},'answers':[{'name':'Candidate Alpha','pct':51,'party':'DEM'},
            {'name':'Candidate Beta','pct':44,'party':'REP'},{'name':'Independent','pct':5,'party':None}]}]
        r=self.state(f)['races'][0]['polling']
        self.assertEqual(len(r['observations']),1);self.assertEqual(r['held_observation_ids'],[])
        self.assertEqual(r['unmatched_nonmajor_answer_names'],['Independent'])

    def test_sourced_middle_name_and_nickname_are_same_person(self):
        f=self.fixture();f[1]['races']['USA:AK:house:00']['candidates'][0]['name']='Candidate Middle "Candidate" Alpha'
        f[3]['races']['USA:AK:house:00']['observations']=[{'id':'p','field_end':'2026-10-07',
            'population':'lv','pollster_group':'test','source_quality':{},'aggregation_eligibility':{'eligible':True},
            'answers':[{'name':'Candidate Alpha','pct':51,'party':'DEM'},{'name':'Candidate Beta','pct':49,'party':'REP'}]}]
        self.assertEqual(self.state(f)['races'][0]['polling']['held_observation_ids'],[])

    def test_senate_id_without_matching_source_snapshot_is_rejected(self):
        f=self.fixture();reviews={'races':{'USA:AK:senate':[{'candidate_name':'Candidate Alpha','party':'DEM',
            'candidate_id':'S00000001','reviewed_on':'2026-10-08','source_url':'https://example.org/x','source_sha256':'a'*64}]}}
        with self.assertRaises(ValueError):build_state('AK','B',self.plan,*f,'2026-10-08',reviews)

    def test_after_election_clears_live_polls_without_refreshing_dates(self):
        f=self.fixture();p=f[3]['races']['USA:AK:house:00'];p['observations']=[{'id':'past','answers':[{'name':'Candidate Alpha','pct':51}]}]
        row=self.state(f,'2026-11-04')['races'][0]['polling']
        self.assertEqual(row['phase'],'awaiting_certified_result');self.assertEqual(row['observations'],[])
        self.assertEqual(row['as_of'],'2026-10-08');self.assertIsNone(row['windows']['7']['party'])

    def test_source_error_or_stale_cannot_keep_lead(self):
        f=self.fixture();f[3]['source_status']='error_stale'
        row=self.state(f)['races'][0]['polling'];self.assertIsNone(row['windows']['7']['party'])
        self.assertEqual(row['windows']['7']['status'],'source_error_or_stale')
        f[3]['source_status']='ok';f[3]['fetched_at']='2026-09-01T00:00:00+00:00'
        self.assertEqual(self.state(f)['races'][0]['polling']['windows']['14']['status'],'source_error_or_stale')

    def test_wrong_state_asset_fails_instead_of_joining(self):
        f=self.fixture();f[4]['races']['USA:AK:house:00']={'race_id':'USA:AK:house:00','state_id':'NY','office':'house'}
        with self.assertRaises(ValueError):self.state(f)

    def test_individual_capture_uses_its_own_date_and_source_status(self):
        f=self.fixture();f[3]['as_of']='2026-10-01';f[3]['source_status']='error_stale'
        p=f[3]['races']['USA:AK:house:00']
        p.update(as_of='2026-10-08',fetched_at='2026-10-08T00:00:00Z',source_status='ok',
                 source_url='https://example.org/state-capture')
        row=self.state(f)['races'][0]['polling']
        self.assertEqual(row['as_of'],'2026-10-08');self.assertEqual(row['source_status'],'ok')
        self.assertEqual(row['source_url'],'https://example.org/state-capture')
        self.assertNotEqual(row['windows']['7']['status'],'source_error_or_stale')
        f[3]['source_status']='ok';p['source_status']='error_stale'
        self.assertEqual(self.state(f)['races'][0]['polling']['windows']['7']['status'],'source_error_or_stale')

    def test_future_individual_capture_cannot_hide_behind_global_date(self):
        f=self.fixture();f[3]['races']['USA:AK:house:00']['as_of']='2026-10-09'
        with self.assertRaises(ValueError):self.state(f)

    def test_receipt_does_not_certify_unrefreshed_governor(self):
        f=self.fixture();f[3]['state_captures']={'AK':{'cycle':2026,'state':'AK','primary_rechecked_ids':['p'],
                                                        'governor_last_success_at':'2026-10-08T00:00:00+00:00'}}
        self.assertEqual(self.state(f)['work_status'],'baseline_join_checked')
        f[4]['source_status']['AK_governor']={'last_success_at':'2026-10-08T00:00:00+00:00'}
        self.assertEqual(self.state(f)['work_status'],'live_sources_reviewed_partial')

    def test_state_failure_preserves_last_file_and_source_date(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);payload=self.state(self.fixture());payload['state']='NY';payload['group']='A'
            first=publish_states(p,self.plan,[('A','NY')],lambda s,g:payload,'2026-10-08T01:00:00+00:00')
            path=p/first['states']['NY']['data_file'];raw=path.read_bytes();dates=first['states']['NY']['source_dates']
            def failure(s,g):raise ValueError('source failed')
            second=publish_states(p,self.plan,[('A','NY')],failure,'2026-10-08T02:00:00+00:00')
            self.assertEqual(path.read_bytes(),raw);self.assertEqual(second['states']['NY']['source_dates'],dates)
            self.assertEqual(second['states']['NY']['status'],'carried_forward')

    def test_unchanged_state_reuses_asset_and_reports_remaining_work(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);payload=self.state(self.fixture());payload['state']='NY';payload['group']='A'
            one=publish_states(p,self.plan,[('A','NY')],lambda s,g:payload,'2026-10-08T01:00:00+00:00')
            two=publish_states(p,self.plan,[('A','NY')],lambda s,g:payload,'2026-10-08T02:00:00+00:00')
            self.assertEqual(one['states']['NY']['data_file'],two['states']['NY']['data_file'])
            self.assertEqual(two['next_state_to_review'],'NY')
            self.assertEqual(len(list((p/'usa_election_state_evidence/2026').glob('*.json'))),1)

    def test_other_state_success_does_not_erase_previous_failure(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            def failure(s,g):raise ValueError('failed')
            publish_states(p,self.plan,[('A','NY')],failure,'2026-10-08T01:00:00+00:00')
            payload=self.state(self.fixture());payload['state']='TN';payload['group']='A'
            result=publish_states(p,self.plan,[('A','TN')],lambda s,g:payload,'2026-10-08T02:00:00+00:00')
            self.assertEqual(result['errors'],{'NY':'ValueError'})
            self.assertEqual(result['next_state_to_review'],'NY')


if __name__=='__main__':unittest.main()
