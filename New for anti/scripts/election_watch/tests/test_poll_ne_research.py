"""NE reviewed dossier -> production overlays, capture replay and fail-closed transport."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from urllib.error import URLError
from election_watch.polls import read
from election_watch.state_inputs import validate_packet
from election_watch.poll_primary_supplements import merge_primary_supplements
from publish_state_packets import rebuild
ROOT=Path(__file__).resolve().parents[1];PUBLIC=ROOT.parent.parent/'public/data'
RESEARCH=ROOT/'research/2026/NE';PACKET=ROOT/'config/state_evidence/2026/NE.json'
class Response:
    status=200
    def __init__(self,url,body):self.url,self.body=url,body
    def geturl(self):return self.url
    def read(self,n):return self.body[:n]
    def __enter__(self):return self
    def __exit__(self,*args):pass
class NETests(unittest.TestCase):
    def setUp(self):
        self.packet=json.loads(PACKET.read_text());self.dossier=json.loads((RESEARCH/'NE_2026_records.json').read_text())
        self.entries=[o['value'] for o in self.packet['config_operations'] if o['file']=='usa_polls/primary_supplements_2026.json']
        self.files={s['url']:RESEARCH/s['local_file'] for s in self.dossier['sources']}
    def opener(self,req,**kwargs):return Response(req.full_url,self.files[req.full_url].read_bytes())
    def merge(self,rows=(),opener=None):
        return merge_primary_supplements(list(rows),{'schema':'usa_reviewed_primary_poll_supplements_v1','cycle':2026,'records':self.entries},'2026-10-20',opener=opener or self.opener,reviewed_entries=self.entries)
    def test_original_artifacts_and_corrected_metadata(self):
        for s in self.dossier['sources']:
            self.assertEqual(hashlib.sha256((RESEARCH/s['local_file']).read_bytes()).hexdigest(),s['sha256'])
        npa=self.dossier['polls'][2];self.assertIsNone(npa['released_on']);self.assertEqual(npa['memo_dated_on'],'2026-10-12')
        self.assertEqual(npa['sample']['total_interviews'],800);self.assertEqual(npa['sample']['ne02_interviews'],377)
    def test_official_rosters_full_field_ticket_and_petition_preserved(self):
        ballots=read(ROOT/'config/usa_polls/ballot_reviews_2026.json')['races']
        for office,count in [('governor',4),('senate',5),('house:01',4),('house:02',3),('house:03',5)]:
            r=ballots['USA:NE:'+office];self.assertEqual(len(r['candidates']),count);self.assertEqual(r['status'],'certified_ballot')
        osborn=next(c for c in ballots['USA:NE:senate']['candidates'] if c['name']=='Dan Osborn')
        self.assertEqual(osborn['reported_party'],'By Petition');self.assertEqual(osborn['party'],'IND')
        self.assertEqual(ballots['USA:NE:governor']['candidates'][0]['running_mate']['name'],'Joe Kelly')
    def test_replay_keeps_other_states_original_dates_and_no_recent_leads(self):
        names={s:v['name'] for s,v in read(ROOT/'config/usa_polls/targets_2026.json')['states'].items()};validate_packet(self.packet,names)
        before=read(PUBLIC/'usa_election_live_polls_v1.json');after,hist=rebuild(before,read(PUBLIC/'usa_election_poll_history_2026.json'),[self.packet],PUBLIC)
        self.assertTrue(all(r==after['races'][rid] for rid,r in before['races'].items() if not rid.startswith('USA:NE:')))
        for rid,race in after['races'].items():
            if rid.startswith('USA:NE:'):
                # Research-only primaries never lead; a lead may come only from the
                # reviewed Echelon/NetChoice release admitted 2026-10-30.
                for window in race['windows'].values():
                    if window['party']:self.assertLessEqual(set(window['included_ids']),{'us-202ech8ce34abf','gov202ech6a54009b'})
        primary=[o for rid,r in hist['races'].items() if rid.startswith('USA:NE:') for o in r['observations'] if o['id'].startswith('primary-')]
        self.assertEqual(len(primary),4)
        self.assertTrue(all(not o['aggregation_eligibility']['eligible'] for o in primary))
        dated=[o for o in primary if o['id'].startswith('primary-html-coefficient-')]
        self.assertEqual(len(dated),1);self.assertEqual(dated[0]['provider_record_date'],'2026-10-02')
        self.assertEqual(sum(o['provider_record_date'] is None for o in primary),3)
    def test_provider_duplicate_and_conflict(self):
        r=copy.deepcopy(self.entries[0]['record']);r['id']='later-ne-api-record';r['created_at']='2026-10-06'
        rows,receipts=self.merge([r]);self.assertEqual(len(rows),4);self.assertIn(r['id'],receipts[0]['provider_duplicate_ids'])
        r['answers'][0]['pct']+=1
        with self.assertRaisesRegex(ValueError,'wave_conflict'):self.merge([r])
    def test_document_outage_preserves_all_reviewed_values(self):
        def fail(*a,**kw):raise URLError('offline')
        rows,_=self.merge(opener=fail);self.assertEqual(len(rows),4)
        self.assertTrue(all(r['primary_source_capture']['status']=='carried_forward_reference_only' for r in rows))
        self.assertEqual(rows[0]['answers'],self.entries[0]['record']['answers']);self.assertIsNone(rows[0]['created_at'])
