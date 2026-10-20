"""Research intake is durable review work, not an alternative admission path."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import unittest
from unittest.mock import patch
import sys
import discover_poll_sources as cli

from election_watch.polls import read,digest
from election_watch.poll_intake import (canonical_url,discovery_candidates,research_candidates,
                                       build_intake,attach_saved_intake,research_tasks)

C=read(Path(__file__).resolve().parents[1]/'config/usa_polls/targets_2026.json')
DAY='2026-10-21';STAMP=DAY+'T01:00:00+00:00';RID='USA:NY:governor'


def board():
    return {'as_of':DAY,'fetched_at':STAMP,'races':{
        RID:{'office':'governor','required_candidates':['Kathy Hochul','Bruce Blakeman'],
            'candidates':{'Kathy Hochul':{'party':'DEM'},'Bruce Blakeman':{'party':'REP'}},'observations':[]},
        'USA:NY:house:17':{'office':'house','observations':[]}},
        'house_poll_focus':{'races':{'USA:NY:house:17':{
            'classification':'cook_toss_up_or_lean','rating_as_of':'2026-10-16'}}}}


def discovery(url='https://pollster.example/release?releaseid=123',rid=RID):
    return {'schema':'usa_poll_source_discovery_v1','cycle':2026,'as_of':DAY,'captured_at':STAMP,'status':'ok',
        'records':[{'id':'synthetic-discovery','source':'synthetic source','source_url':url,
            'race_id':rid,'office':'governor','signal_eligible':True,'status':'claimed_approved'}],
        'source_health':{'fixture':{'status':'ok'}}}


def dossier(root):
    body=b'%PDF-synthetic test source; not an actual poll';(root/'raw.pdf').write_bytes(body)
    return {'schema':'usa_state_research_dossier_v1','cycle':2026,'state':'NY','checked_on':DAY,
        'polls':[{'id':'synthetic-research','source_url':'https://pollster.example/release?releaseid=123',
            'local_file':'raw.pdf','sha256':hashlib.sha256(body).hexdigest(),'pollster':'synthetic',
            'field_start':'2026-10-17','field_end':'2026-10-19','released_on':'2026-10-20',
            'population':'LV','sample_n':900,'mode':'synthetic test mode','weighting':'synthetic test weighting',
            'sponsor_statement':'synthetic independent commissioning disclosure',
            'questions':[{'office':'governor','stage':'general','ballot':'two_named',
                'initial_ballot':True,'sample_n':800,'sample_base':'full interviewed likely voter sample',
                'geography_scope':'statewide','geography_state':'NY','prompt':'synthetic named candidate ballot',
                'results_pct':[{'label':'Kathy Hochul','pct':48},{'label':'Bruce Blakeman','pct':44}]}]}]}


class IntakeTests(unittest.TestCase):
    def test_discovery_cannot_self_approve_and_deduplicates_tracking_links(self):
        report=discovery();report['records'].append({**report['records'][0],
            'source_url':'https://pollster.example/release?releaseid=123&utm_source=test'})
        rows,bad=discovery_candidates(report,C);self.assertFalse(bad)
        result=build_intake(rows,board(),DAY,STAMP)
        self.assertEqual(result['summary']['candidate_documents'],1)
        self.assertFalse(result['records'][0]['signal_eligible'])
        self.assertEqual(result['records'][0]['status'],'primary_review_required')
        self.assertIn('releaseid=123',result['records'][0]['source_url'])

    def test_original_discovery_facts_and_changed_versions_survive(self):
        rows,_=discovery_candidates(discovery(),C);a=build_intake(rows,board(),DAY,STAMP)
        rows[0]['evidence']['displayed_results']='different unreviewed values'
        b=build_intake(rows,board(),DAY,STAMP,a)
        self.assertEqual(len(b['records']),1);self.assertEqual(len(b['records'][0]['versions']),2)
        self.assertEqual(b['summary']['changed_documents'],1)
        self.assertEqual(b['records'][0]['versions'][0]['evidence'],a['records'][0]['versions'][0]['evidence'])

    def test_repeat_is_idempotent_and_outage_preserves_original_seen_dates(self):
        rows,_=discovery_candidates(discovery(),C);a=build_intake(rows,board(),DAY,STAMP)
        b=build_intake(rows,board(),DAY,STAMP,a)
        self.assertEqual(b['records'],a['records']);self.assertEqual(b['summary']['new_documents'],0)
        carried=build_intake([],board(),'2026-10-22','2026-10-22T01:00:00Z',b,{'fixture':{'status':'unavailable'}})
        self.assertEqual(carried['records'][0]['last_seen_at'],STAMP)
        self.assertEqual(carried['records'][0]['collection_state'],'carried_forward')
        self.assertEqual(carried['summary']['candidate_documents'],1);self.assertEqual(carried['status'],'partial')

    def test_house_focus_is_dynamic_and_sorts_before_other_races(self):
        report=discovery();report['records'].append({**report['records'][0],'race_id':'USA:NY:house:17'})
        rows,_=discovery_candidates(report,C);result=build_intake(rows,board(),DAY,STAMP)
        self.assertEqual(result['records'][0]['race_id'],'USA:NY:house:17')
        self.assertEqual(result['summary']['priority_house_documents'],1)
        self.assertEqual(result['summary']['focus_races_with_candidates'],1)
        self.assertEqual(result['summary']['focus_races_without_candidates'],[])
        empty=board();empty['house_poll_focus']['races']={}
        self.assertEqual(build_intake(rows,empty,DAY,STAMP)['summary']['priority_house_documents'],0)

    def test_research_jobs_keep_priority_and_actual_candidate_metadata_without_approval(self):
        report=discovery();report['records'].append({**report['records'][0],'race_id':'USA:NY:house:17'})
        rows,_=discovery_candidates(report,C);b=board();queue=build_intake(rows,b,DAY,STAMP)
        tasks=research_tasks(queue,b)
        self.assertEqual(tasks['jobs'][0]['race_id'],'USA:NY:house:17')
        self.assertEqual(tasks['jobs'][1]['reviewed_candidates'],b['races'][RID]['candidates'])
        self.assertTrue(all(j['output_schema']=='usa_state_research_dossier_v1' and not j['signal_eligible'] for j in tasks['jobs']))

    def test_finished_election_retains_audit_without_active_research_jobs(self):
        rows,_=discovery_candidates(discovery(),C);b=board();b['races'][RID]['phase']='certified_result'
        queue=build_intake(rows,b,DAY,STAMP)
        self.assertEqual(queue['records'][0]['status'],'election_closed_reference')
        self.assertEqual(research_tasks(queue,b)['jobs'],[])

    def test_bad_url_and_nonexistent_district_are_isolated(self):
        report=discovery();report['records'].extend([
            {'id':'bad-url','source_url':'file:///etc/passwd','race_id':RID},
            {'id':'bad-district','source_url':'https://example.org/poll','race_id':'USA:FL:house:59'}])
        rows,bad=discovery_candidates(report,C)
        self.assertEqual(len(rows),1);self.assertEqual(len(bad),2)

    def test_complete_research_is_ready_for_human_review_only(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);d=dossier(root);rows,bad=research_candidates(d,root,C,DAY,STAMP)
        self.assertFalse(bad);self.assertEqual(rows[0]['reasons'],[])
        b=board();original=deepcopy(b['races'])
        result=build_intake(rows,b,DAY,STAMP)
        self.assertEqual(result['records'][0]['status'],'ready_for_human_review')
        self.assertFalse(result['records'][0]['signal_eligible']);self.assertEqual(b['races'],original)
        self.assertEqual(result['records'][0]['versions'][0]['evidence']['question']['sample_n'],800)

    def test_full_sample_and_unweighted_n_do_not_fill_question_sample(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);d=dossier(root);q=d['polls'][0]['questions'][0]
            q.pop('sample_n');q['unweighted_n']=799
            rows,bad=research_candidates(d,root,C,DAY,STAMP)
        self.assertFalse(bad);self.assertIn('question_sample_n_missing',rows[0]['reasons'])
        result=build_intake(rows,board(),DAY,STAMP)
        self.assertEqual(result['records'][0]['status'],'research_gaps')

    def test_missing_release_and_forced_choice_stay_pending(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);d=dossier(root);d['polls'][0]['released_on']=None
            d['polls'][0]['questions'][0]['initial_ballot']=False
            rows,bad=research_candidates(d,root,C,DAY,STAMP)
        self.assertFalse(bad)
        self.assertIn('release_date_not_disclosed',rows[0]['reasons'])
        self.assertIn('initial_question_not_verified',rows[0]['reasons'])
        self.assertIsNone(rows[0]['evidence']['poll']['released_on'])

    def test_reported_incomplete_ballots_and_null_numbers_are_not_completed(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);d=dossier(root);p=d['polls'][0]
            p['reported_figures_not_complete_ballots']=p.pop('questions')
            rows,bad=research_candidates(d,root,C,DAY,STAMP)
            self.assertFalse(bad);self.assertIn('incomplete_reported_ballot',rows[0]['reasons'])
            p['reported_figures_not_complete_ballots'][0]['results_pct'][0]['pct']=None
            rows,bad=research_candidates(d,root,C,DAY,STAMP)
            self.assertFalse(rows);self.assertEqual(len(bad),1)
            self.assertEqual(bad[0]['error_code'],'invalid_percentage')

    def test_hash_mismatch_and_path_escape_are_rejected_without_losing_other_records(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);d=dossier(root)
            changed=deepcopy(d['polls'][0]);changed['id']='changed';changed['sha256']='0'*64
            escape=deepcopy(changed);escape['id']='escape';escape['local_file']='../outside.pdf'
            d['polls'].extend([changed,escape])
            rows,bad=research_candidates(d,root,C,DAY,STAMP)
            self.assertEqual(len(rows),1);self.assertEqual(len(bad),2)
            self.assertEqual({r['error_code'] for r in bad},{'source_fingerprint_changed','source_file_outside_dossier'})

    def test_candidate_spelling_party_conflict_and_withdrawal_need_review(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);d=dossier(root);d['polls'][0]['questions'][0]['results_pct'][0]['party']='REP'
            rows,_=research_candidates(d,root,C,DAY,STAMP)
        result=build_intake(rows,board(),DAY,STAMP)
        reasons=result['records'][0]['versions'][0]['review_readiness']
        self.assertIn('candidate_party_conflict',reasons)
        b=board();b['races'][RID]['candidates'].pop('Kathy Hochul')
        result=build_intake(rows,b,DAY,STAMP,result)
        self.assertIn('candidate_identity_review_required',result['records'][0]['versions'][0]['review_readiness'])
        self.assertEqual(result['records'][0]['status'],'research_gaps')

    def test_older_complete_version_does_not_hide_new_incomplete_research(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);d=dossier(root);d['checked_on']='2026-10-20'
            rows,_=research_candidates(d,root,C,DAY,STAMP);old=build_intake(rows,board(),DAY,STAMP)
            d['checked_on']=DAY;d['polls'][0]['questions'][0].pop('prompt')
            rows,_=research_candidates(d,root,C,DAY,STAMP)
        new=build_intake(rows,board(),DAY,STAMP,old)
        self.assertEqual(len(new['records'][0]['versions']),2)
        self.assertEqual(new['records'][0]['status'],'research_gaps')

    def test_same_url_observation_is_a_hint_not_same_wave_admission(self):
        b=board();b['races'][RID]['observations']=[{'id':'earlier-wave','source_url':'https://pollster.example/release?releaseid=123',
            'field_end':'2026-10-14','aggregation_eligibility':{'eligible':True}}]
        rows,_=discovery_candidates(discovery(),C);result=build_intake(rows,b,DAY,STAMP)
        self.assertEqual(result['records'][0]['source_url_observation_matches'],['earlier-wave'])
        self.assertEqual(result['records'][0]['status'],'primary_review_required')
        self.assertEqual(result['summary']['recent_poll_race_coverage']['governor'],{'7':0,'14':1})

    def test_artifact_is_bound_to_original_provider_snapshot_and_carries_last_good(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);checkpoint=root/'capture.json'
            provider=[{'id':'synthetic-provider'}];checkpoint.write_text(json.dumps({'provider_rows':provider}))
            report=discovery();report['provider_comparison']={'captured_at':STAMP,'provider_rows_sha256':digest(provider)}
            sidecar=checkpoint.with_suffix('.discovery.json');sidecar.write_text(json.dumps(report))
            b=board();queue_path=root/'intake.json';attach_saved_intake(b,None,checkpoint,queue_path)
            self.assertEqual(b['poll_intake_health']['status'],'ok')
            self.assertEqual(b['poll_intake']['schema'],'usa_poll_intake_summary_v1')
            self.assertNotIn('records',b['poll_intake']);original=queue_path.read_bytes()
            old=deepcopy(b);report['provider_comparison']['provider_rows_sha256']='0'*64
            sidecar.write_text(json.dumps(report));attach_saved_intake(b,old,checkpoint,queue_path)
            self.assertEqual(b['poll_intake'],old['poll_intake'])
            self.assertEqual(queue_path.read_bytes(),original)
            self.assertEqual(b['poll_intake_health']['status'],'carried_forward')
            sidecar.unlink();fresh=board();attach_saved_intake(fresh,None,checkpoint,root/'missing.json')
            self.assertEqual(fresh['poll_intake_health']['status'],'unavailable')
            self.assertNotIn('poll_intake',fresh)

    def test_queue_write_failure_does_not_replace_existing_queue_or_block_polls(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);checkpoint=root/'capture.json';queue_path=root/'intake.json'
            provider=[{'id':'synthetic'}];checkpoint.write_text(json.dumps({'provider_rows':provider}))
            report=discovery();report['provider_comparison']={'captured_at':STAMP,'provider_rows_sha256':digest(provider)}
            checkpoint.with_suffix('.discovery.json').write_text(json.dumps(report))
            b=board();attach_saved_intake(b,None,checkpoint,queue_path)
            before=queue_path.read_bytes();old=deepcopy(b);polls=deepcopy(b['races'])
            with patch('election_watch.polls.atomic',side_effect=OSError('synthetic disk write failure')):
                attach_saved_intake(b,old,checkpoint,queue_path)
            self.assertEqual(b['poll_intake_health']['status'],'carried_forward')
            self.assertEqual(b['races'],polls);self.assertEqual(queue_path.read_bytes(),before)

    def test_publisher_stages_only_existing_queue_without_raw_research_files(self):
        import publish_polling_run as publisher
        from election_watch.poll_intake import INTAKE_FILE
        with patch('election_watch.state_inputs.packets',return_value=[]), \
             patch.object(Path,'read_text',return_value='{"states":{}}'), \
             patch.object(Path,'is_file',return_value=False):
            self.assertNotIn(publisher.PUBLIC+INTAKE_FILE,publisher.stage_paths())
        with patch('election_watch.state_inputs.packets',return_value=[]), \
             patch.object(Path,'read_text',return_value='{"states":{}}'), \
             patch.object(Path,'is_file',return_value=True):
            paths=publisher.stage_paths()
            self.assertIn(publisher.PUBLIC+INTAKE_FILE,paths)
            self.assertFalse(any('/raw/' in p or '/research/' in p for p in paths))

    def test_daily_discovery_cli_keeps_podcast_and_cursor_inputs_and_binds_provider_hash(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);d=dossier(root);input_file=root/'NY_2026_records.json'
            input_file.write_text(json.dumps(d))
            config=root/'config/usa_polls';config.mkdir(parents=True)
            (config/'targets_2026.json').write_text(json.dumps(C))
            provider=[{'id':'synthetic-provider'}];provider_file=root/'capture.provider.json'
            provider_file.write_text(json.dumps({'schema':'usa_poll_provider_capture_v1',
                'provider_rows':provider,'captured_at':STAMP}))
            output=root/'capture.discovery.json';report=discovery()
            report['records'][0]['source_url']='https://pollster.example/release?releaseid=123'
            with patch.object(cli,'ROOT',root), \
                 patch.object(sys,'argv',['discover','--as-of',DAY,'--output',str(output),
                    '--provider-capture',str(provider_file),'--research-dossier',str(input_file)]), \
                 patch.object(cli,'collect_270',return_value=report), \
                 patch.object(cli,'collect_additional',return_value={'records':[],'commentary':[{'id':'synthetic-podcast'}],'source_health':{}}), \
                 patch.object(cli,'collect_primary',return_value={'records':[],'source_health':{}}) as primary:
                self.assertEqual(cli.main(),0)
            saved=json.loads(output.read_text());primary.assert_called_once()
            self.assertEqual(saved['commentary'],[{'id':'synthetic-podcast'}])
            self.assertEqual(saved['provider_comparison']['provider_rows_sha256'],digest(provider))
            self.assertEqual(len(saved['research_intake'][0]['candidates']),1)
            self.assertFalse(saved['research_intake'][0]['rejected_inputs'])

    def test_unsafe_source_url_cannot_be_normalized(self):
        for url in ('http://example.org/','https://user:password@example.org/','https://example.org:8080/'):
            with self.subTest(url=url),self.assertRaises(ValueError):canonical_url(url)
