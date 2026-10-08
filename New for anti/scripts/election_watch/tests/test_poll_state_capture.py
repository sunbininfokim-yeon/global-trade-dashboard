from copy import deepcopy
import unittest
from election_watch.state_poll_capture import merge_capture


class StateCaptureTests(unittest.TestCase):
    def fixture(self):
        ids={'TN':'USA:TN:house:09','NY':'USA:NY:house:17'}
        races={rid:{'state':state,'observations':[]} for state,rid in ids.items()}
        coverage={rid:{'priority':{'reasons':['requested_state']},'accepted_count':0,
                      'windows':{'7':{'pollster_count':0},'14':{'pollster_count':0}}} for rid in ids.values()}
        gaps={rid:{'office':'house','poll_observation_count':0,'recent_7d_pollsters':0,
                   'recent_14d_pollsters':0,'ballot_competition':{'status':'contested'}} for rid in ids.values()}
        previous={'schema':'usa_live_polls_v1','cycle':2026,'as_of':'2026-10-07',
            'fetched_at':'2026-10-07T01:00:00Z','source_status':'ok','races':races,
            'source':{'request_url':'https://example.org/polls'},
            'review_queue':[{'race_id':ids['TN'],'reason':'old'},{'race_id':ids['NY'],'reason':'kept'}],
            'coverage':{},'monitoring':{'race_coverage':coverage,'groups':{}},
            'data_gaps':{'races':gaps,'states':{'NY':{'original':True},'TN':{}},
                         'counts_by_office':{'house':{}},'ballot_counts':{}},
            'state_captures':{'NY':{'unchanged':True}}}
        capture=deepcopy(previous);capture.update(as_of='2026-10-08',fetched_at='2026-10-08T01:00:00Z')
        capture['races']={ids['TN']:{'state':'TN','observations':[{'aggregation_eligibility':{'eligible':False}}]}}
        capture['review_queue']=[]
        capture['monitoring']['race_coverage']={ids['TN']:deepcopy(coverage[ids['TN']])}
        capture['monitoring']['race_coverage'][ids['TN']]['accepted_count']=1
        capture['data_gaps']['races']={ids['TN']:deepcopy(gaps[ids['TN']])}
        capture['data_gaps']['races'][ids['TN']]['poll_observation_count']=1
        return previous,capture,{'state':'TN','cycle':2026}

    def test_only_selected_state_changes_and_global_source_dates_are_preserved(self):
        old,new,receipt=self.fixture();original=deepcopy(old)
        result=merge_capture(old,new,'TN',receipt)
        self.assertEqual(old,original)
        self.assertEqual(result['races']['USA:NY:house:17'],old['races']['USA:NY:house:17'])
        self.assertEqual(result['state_captures']['NY'],old['state_captures']['NY'])
        self.assertEqual(result['data_gaps']['states']['NY'],old['data_gaps']['states']['NY'])
        self.assertEqual(result['as_of'],'2026-10-07');self.assertEqual(result['fetched_at'],old['fetched_at'])
        self.assertEqual(result['races']['USA:TN:house:09']['fetched_at'],new['fetched_at'])
        self.assertEqual(result['races']['USA:TN:house:09']['source_url'],new['source']['request_url'])
        self.assertEqual(result['coverage']['reference_only_observations'],1)
        self.assertEqual(result['coverage']['aggregation_eligible_observations'],0)
        self.assertEqual(result['coverage']['exclusion_reasons'],{'kept':1})

    def test_missing_race_or_foreign_state_cannot_replace_existing_slots(self):
        for change in ('missing','foreign'):
            old,new,receipt=self.fixture()
            if change=='missing':new['races']={}
            else:new['races']['USA:TN:house:09']['state']='NY'
            with self.assertRaises(ValueError):merge_capture(old,new,'TN',receipt)

    def test_failed_source_and_wrong_receipt_cannot_publish(self):
        old,new,receipt=self.fixture();new['source_status']='error_stale'
        with self.assertRaises(ValueError):merge_capture(old,new,'TN',receipt)

    def test_real_poll_builder_contract_can_be_merged(self):
        from test_live_polls import POLICY,DAY,poll
        from election_watch.live_polls import build_live
        from election_watch.poll_priorities import attach_coverage
        from election_watch.poll_gaps import attach_gaps
        raw=[poll()];policy=deepcopy(POLICY)
        policy['races']={rid:r for rid,r in policy['races'].items() if r['state']=='NY'}
        policy['states']=['NY']
        board=build_live(raw,policy,{'schema':'usa_confirmed_results_v1','results':[]},DAY,DAY+'T00:00:00Z','test')
        finance={'races':{},'status':'loaded','generated_at':DAY}
        attach_coverage(board,raw,policy,finance);attach_gaps(board,finance)
        merged=merge_capture(board,board,'NY',{'state':'NY','cycle':2026})
        self.assertEqual(merged['coverage']['displayed_observations'],1)
        old,new,receipt=self.fixture();receipt['state']='NY'
        with self.assertRaises(ValueError):merge_capture(old,new,'TN',receipt)
