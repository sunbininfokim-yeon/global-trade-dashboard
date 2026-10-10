import copy
import hashlib
import json
from pathlib import Path
import unittest
from election_watch.co_ballot import parse_ballot
from election_watch.governor_matchups import apply_matchups, validate_snapshot, apply_ballot_reviews
from election_watch.superpac import SourceError
from election_watch.poll_targets import apply_targets
from election_watch.live_polls import normalize, summarize
from election_watch.poll_primary_supplements import merge_primary_supplements

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'config/usa_polls'
PUBLIC=ROOT.parent.parent/'public/data'
DAY='2026-10-09'
read=lambda p:json.loads(p.read_text())

class ColoradoPrimaryTests(unittest.TestCase):
    def setUp(self):
        self.policy=apply_targets(apply_matchups(read(CONFIG/'live_2026.json'),
            read(ROOT/'config/governor_matchups/2026.json'),DAY),
            read(CONFIG/'targets_2026.json'),read(CONFIG/'ballot_reviews_2026.json'),DAY)
        self.policy['quality_reviews']=read(CONFIG/'quality_reviews_2026.json')['reviews']
        self.audit=read(PUBLIC/'usa_election_poll_release_reviews/2026/CO-primary-20261009.json')
        self.raw=[x['provider_record'] for x in self.audit['records']]
    def observations(self):
        obs,rejected=normalize(self.raw,self.policy,DAY)
        self.assertFalse(rejected);self.assertEqual(len(obs),2)
        return {o['race_id']:o for o in obs}
    def test_official_full_minor_party_and_write_in_roster_not_only_dem_rep(self):
        federal=read(ROOT/'config/federal_matchups/2026.json')['races']
        house=[r for r in federal.values() if r['state']=='CO' and r['office']=='house']
        self.assertEqual(len(house),8)
        self.assertEqual(sum(len(r['candidates']) for r in house),38)
        senate=federal['USA:CO:senate']['candidates']
        self.assertEqual(len(senate),9);self.assertEqual(sum(c['party']=='WRI' for c in senate),3)
        self.assertEqual(next(c for c in senate if c['name']=='Ryan Apelbaum')['reported_party'],'Republican Party')
        gov=self.policy['races']['USA:CO:governor']
        self.assertEqual(len(gov['candidates']),7)
        self.assertEqual(set(gov['required_candidates']),{'Phil Weiser','Victor Marx'})
        self.assertFalse(gov['ballot_competition']['general_unopposed'])
        self.assertIsNone(next(c for c in federal['USA:CO:house:06']['candidates'] if c['name']=='Patty McMahon')['candidate_id'])
    def test_governor_comparison_override_is_explicit_and_future_guarded(self):
        snapshot=read(ROOT/'config/governor_matchups/2026.json')
        with self.assertRaises(SourceError):validate_snapshot(snapshot,2026,'2026-10-08')
        reviews=read(ROOT/'config/governor_matchups/2026_ballot_reviews.json')
        result=apply_ballot_reviews(snapshot,reviews,DAY)
        self.assertEqual(result,apply_ballot_reviews(result,reviews,DAY))
        self.assertEqual(result['contests']['CO']['poll_required_candidates'],['Victor Marx','Phil Weiser'])
        for names in (['Unknown person','Phil Weiser'],['Phil Weiser','Phil Weiser'],['Phil Weiser']):
            invalid=copy.deepcopy(snapshot);invalid['contests']['CO']['poll_required_candidates']=names
            with self.assertRaises(SourceError):validate_snapshot(invalid,2026,DAY)
    def test_initial_internal_ballot_not_informed_or_statewide_governor(self):
        o=self.observations()['USA:CO:house:05']
        self.assertEqual([a['pct'] for a in o['answers']],[44,45])
        self.assertTrue(o['commissioning']['internal'])
        self.assertTrue(o['commissioning']['provider_internal'])
        self.assertEqual(o['sample_n'],450)
        self.assertIsNone(o['source_quality']['question_sample_n'])
        self.assertFalse(o['aggregation_eligibility']['eligible'])
        self.assertIn('party_internal_reference',o['aggregation_eligibility']['reasons'])
        self.assertEqual(o['source_quality']['disclosure_review']['excluded_informed_ballot']['Jessica Killin'],47)
        self.assertNotIn('USA:CO:governor',self.observations())
    def test_advocacy_named_question_keeps_decimals_and_actual_mode(self):
        o=self.observations()['USA:CO:house:08']
        self.assertEqual([a['pct'] for a in o['answers']],[46.3,48])
        self.assertEqual(o['sample_n'],400)
        self.assertEqual(o['source_quality']['question_sample_n'],400)
        self.assertEqual(o['source_quality']['disclosure_review']['mode']['cellphone_pct'],63.6)
        self.assertEqual(o['commissioning']['sponsors'],['Enhancing American Competitiveness'])
        self.assertFalse(o['aggregation_eligibility']['eligible'])
        self.assertIsNone(o['source_quality']['accuracy_grade'])
        for days in (7,14):
            s=summarize([o],self.policy['races'][o['race_id']],DAY,days)
            self.assertFalse(s['included_ids']);self.assertIsNone(s['party'])
    def test_exact_internal_review_cannot_be_changed_or_future_auto_approved(self):
        for field,value in [('id','new-internal-release'),('internal',False),('sample_size',451),
                            ('sponsors',['Someone else']),('start_date','2026-10-01')]:
            raw=copy.deepcopy(self.raw[0]);raw[field]=value
            self.assertFalse(normalize([raw],self.policy,DAY)[0],field)
        policy=copy.deepcopy(self.policy)
        policy['quality_reviews'][self.raw[0]['id']]['admission']['signal_eligible']=True
        self.assertFalse(normalize([self.raw[0]],policy,DAY)[0])
        policy=copy.deepcopy(self.policy)
        del policy['quality_reviews'][self.raw[0]['id']]['provider_record_sha256']
        self.assertFalse(normalize([self.raw[0]],policy,DAY)[0])
    def test_old_primary_opponent_is_not_reassigned_to_current_nominee(self):
        raw=self.audit['held_records'][0]['provider_record']
        self.assertEqual(self.policy['races']['USA:CO:house:03']['required_candidates'],['Dwayne L. Romero','Jeff Hurd'])
        self.assertFalse(normalize([raw],self.policy,DAY)[0])
    def test_same_wave_agrees_and_changed_document_retains_original_reference(self):
        snapshot=read(CONFIG/'primary_supplements_2026.json')
        entry=copy.deepcopy(next(x for x in snapshot['records'] if x['record']['id']==self.raw[0]['id']))
        body=b'%PDF-test';entry['documents'][0]['sha256']=hashlib.sha256(body).hexdigest()
        snapshot['records']=[entry]
        class Response:
            status=200
            def geturl(self):return entry['documents'][0]['url']
            def read(self,*a):return body
            def __enter__(self):return self
            def __exit__(self,*a):return False
        rows,receipts=merge_primary_supplements([entry['record']],snapshot,DAY,['CO'],lambda *a,**k:Response())
        self.assertEqual(len(rows),1)
        self.assertEqual(receipts[0]['status'],'primary_documents_rechecked')
        self.assertEqual(len(receipts[0]['provider_duplicate_ids']),1)
        entry['documents'][0]['sha256']='0'*64
        rows,receipts=merge_primary_supplements([],snapshot,DAY,['CO'],lambda *a,**k:Response())
        self.assertEqual(receipts[0]['status'],'carried_forward_reference_only')
        self.assertEqual(rows[0]['answers'][0]['pct'],44)
        raw=copy.deepcopy(entry['record']);raw['answers'][0]['pct']=46
        with self.assertRaises(ValueError):merge_primary_supplements([raw],snapshot,DAY,['CO'])
    def test_shared_cdn_does_not_approve_all_future_documents(self):
        snapshot=read(CONFIG/'primary_supplements_2026.json')
        entry=copy.deepcopy(next(x for x in snapshot['records'] if x['record']['id']==self.raw[0]['id']))
        entry['documents'][0]['url']='https://newspack-coloradosun.s3.amazonaws.com/new-poll.pdf'
        snapshot['records']=[entry]
        with self.assertRaises(ValueError):merge_primary_supplements([],snapshot,DAY,['CO'])

class ColoradoBallotParserTests(unittest.TestCase):
    def html(self,extra=''):
        rows=[f'<tr><td>Candidate {d}</td><td>US House of Representatives</td><td>{d}</td><td>Democratic Party</td><td>N</td></tr>' for d in range(1,9)]
        rows += ['<tr><td>Senator</td><td>US Senate</td><td>State</td><td>Republican Party</td><td>N</td></tr>',
                 '<tr><td>Governor</td><td>Governor</td><td>State</td><td>Unaffiliated</td><td>N</td></tr>']
        return '<h1>2026 General Election Official Candidate List</h1><p>certified to the counties on September 4</p><table class="w3-cmsTable"><tr>'+''.join('<th>'+x+'</th>' for x in ['Candidate name','Office','District','Party','Write in?'])+'</tr>'+''.join(rows)+extra+'</table>'
    def test_state_legislature_lieutenant_governor_and_withdrawn_excluded(self):
        extra=''.join('<tr><td>'+name+'</td><td>'+office+'</td><td>'+district+'</td><td>Republican Party</td><td>'+w+'</td></tr>'
          for name,office,district,w in [('Legislator','State Senate','35','N'),('Lt Gov','Lieutenant Governor','State','N'),('Write in','US Senate','State','Y'),('<s>Withdrawn</s>','Governor','State','N')])
        out=parse_ballot(self.html(extra),DAY)
        self.assertEqual(len(out),10);self.assertEqual(len(out['USA:CO:governor']['candidates']),1)
        self.assertEqual(out['USA:CO:governor']['excluded_candidates'][0]['agency_status'],'withdrawn')
        self.assertEqual(out['USA:CO:senate']['candidates'][1]['party'],'WRI')
    def test_changed_cycle_schema_universe_and_duplicate_fail_closed(self):
        duplicate='<tr><td>Candidate 1</td><td>US House of Representatives</td><td>1</td><td>Democratic Party</td><td>N</td></tr>'
        for html in [self.html().replace('2026 General','2024 General'),self.html().replace('Write in?','Status'),
                     self.html().replace('<td>8</td>','<td>9</td>'),self.html(duplicate),'<html>blocked</html>']:
            with self.assertRaises(ValueError):parse_ballot(html,DAY)
        with self.assertRaises(ValueError):parse_ballot(self.html(),'2026-09-03')
