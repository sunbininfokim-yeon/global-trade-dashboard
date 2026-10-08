import copy,hashlib,json
from pathlib import Path
import unittest
from election_watch.poll_primary_supplements import merge_primary_supplements
from election_watch.live_polls import normalize,summarize
from election_watch.governor_matchups import apply_matchups
from election_watch.poll_targets import apply_targets
ROOT=Path(__file__).resolve().parents[1];CONFIG=ROOT/'config/usa_polls';PUBLIC=ROOT.parent.parent/'public/data'

class Response:
    def __init__(self,url,body):self.url=url;self.body=body;self.status=200
    def geturl(self):return self.url
    def read(self,n):return self.body[:n]
    def __enter__(self):return self
    def __exit__(self,*args):pass

class PennsylvaniaPrimaryTests(unittest.TestCase):
    def setUp(self):
        read=lambda p:json.loads(p.read_text())
        self.policy=apply_targets(apply_matchups(read(CONFIG/'live_2026.json'),read(ROOT/'config/governor_matchups/2026.json'),'2026-10-08'),read(CONFIG/'targets_2026.json'),read(CONFIG/'ballot_reviews_2026.json'),'2026-10-08')
        self.policy['quality_reviews']=read(CONFIG/'quality_reviews_2026.json')['reviews']
        self.rows=[r['provider_record'] for r in read(PUBLIC/'usa_election_poll_release_reviews/2026/PA-primary-20261008.json')['records']]
        self.snapshot=read(CONFIG/'primary_supplements_2026.json');self.body=b'%PDF-1.7 synthetic test content'
        for d in self.snapshot['records'][0]['documents']:d['sha256']=hashlib.sha256(self.body).hexdigest()
        self.policy['quality_reviews'][self.snapshot['records'][0]['record']['id']]['primary_documents']=copy.deepcopy(self.snapshot['records'][0]['documents'])
        self.opener=lambda req,timeout:Response(req.full_url,self.body)

    def test_primary_ballot_and_question_samples_keep_leaners_one_wave(self):
        accepted,rejected=normalize(self.rows,self.policy,'2026-10-08')
        self.assertFalse(rejected);self.assertEqual(len(accepted),4)
        byid={r['id']:r for r in accepted}
        self.assertEqual(byid['us-202fraa24d50e1']['source_quality']['question_sample_n'],350)
        self.assertEqual(byid['us-202frae23de26f']['source_quality']['question_sample_n'],378)
        self.assertEqual(byid['us-202fraa24d50e1']['answers'][0]['pct'],40)
        for rid in ['USA:PA:house:07','USA:PA:house:10']:
            self.assertEqual(summarize([r for r in accepted if r['race_id']==rid],self.policy['races'][rid],'2026-10-08',14)['pollster_count'],0)

    def test_api_missing_primary_release_is_current_without_becoming_two_party_ballot(self):
        rows,receipts=merge_primary_supplements([],self.snapshot,'2026-10-08',['PA'],self.opener)
        accepted,rejected=normalize(rows,self.policy,'2026-10-08');self.assertFalse(rejected)
        o=accepted[0];self.assertEqual(o['verification'],'reviewed_primary_source_snapshot')
        self.assertEqual(o['answers'][-1],{'name':'Ken Krawchuk','pct':2.0,'party':None})
        self.assertEqual(receipts[0]['status'],'primary_documents_rechecked')
        s=summarize(accepted,self.policy['races']['USA:PA:governor'],'2026-10-08',7)
        self.assertEqual((s['status'],s['party'],s['pollster_count']),('single_poll_lead','DEM',1))

    def test_later_identical_api_import_counts_once_and_retains_api_id(self):
        raw=copy.deepcopy(self.snapshot['records'][0]['record']);raw['id']='api-future-test'
        rows,receipts=merge_primary_supplements([raw],self.snapshot,'2026-10-08',['PA'],self.opener)
        self.assertEqual(len(rows),1);self.assertEqual(receipts[0]['provider_duplicate_ids'],['api-future-test'])

    def test_conflicting_same_wave_never_picks_favorite_values(self):
        raw=copy.deepcopy(self.snapshot['records'][0]['record']);raw['id']='api-future-test'
        for change in ['value','sample','sponsor','internal']:
            r=copy.deepcopy(raw)
            if change=='value':r['answers'][0]['pct']-=1
            elif change=='sample':r['sample_size']+=1
            elif change=='sponsor':r['sponsors']=['Campaign']
            else:r['internal']=True
            with self.assertRaisesRegex(ValueError,'primary_and_provider_wave_conflict'):
                merge_primary_supplements([r],self.snapshot,'2026-10-08',['PA'],self.opener)

    def test_document_outage_or_change_preserves_original_reference_and_no_signal(self):
        def fail(req,timeout):raise OSError('test outage')
        changed=lambda req,timeout:Response(req.full_url,b'%PDF-changed')
        for opener in [fail,changed]:
            rows,receipts=merge_primary_supplements([],self.snapshot,'2026-10-08',['PA'],opener)
            a,r=normalize(rows,self.policy,'2026-10-08');self.assertFalse(r)
            self.assertFalse(a[0]['aggregation_eligibility']['eligible']);self.assertEqual(a[0]['provider_record_date'],'2026-10-07')
            self.assertEqual(receipts[0]['original_reviewed_on'],'2026-10-08')
            self.assertEqual(summarize(a,self.policy['races']['USA:PA:governor'],'2026-10-08',7)['pollster_count'],0)

    def test_metadata_and_number_changes_require_new_review(self):
        for raw in self.rows:
            for key,value in [('sample_size',999),('sponsors',['Unreviewed funder'])]:
                a,r=normalize([{**raw,key:value}],self.policy,'2026-10-08');self.assertFalse(a);self.assertEqual(len(r),1)

    def test_supplement_scope_host_and_raw_snapshot_guards(self):
        rows,receipts=merge_primary_supplements([],self.snapshot,'2026-10-08',['MI'],self.opener)
        self.assertEqual((rows,receipts),([],[]))
        bad=copy.deepcopy(self.snapshot);bad['records'][0]['documents'][0]['url']='https://docs.google.com/test.pdf'
        with self.assertRaisesRegex(ValueError,'unreviewed primary document'):merge_primary_supplements([],bad,'2026-10-08',opener=self.opener)
        bad=copy.deepcopy(self.snapshot);bad['records'][0]['record']['answers'][0]['pct']=60
        with self.assertRaisesRegex(ValueError,'snapshot changed'):merge_primary_supplements([],bad,'2026-10-08',opener=self.opener)
