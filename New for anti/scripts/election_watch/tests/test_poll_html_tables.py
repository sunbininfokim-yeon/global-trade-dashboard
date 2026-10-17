"""Public HTML extraction, source failure, API collision and offline replay boundaries."""
from copy import deepcopy
from datetime import datetime,timezone
import json
from unittest import TestCase
from unittest.mock import patch
from election_watch.polls import digest
from election_watch.poll_html_tables import (contracts,document,article_links,article_metadata,
    question,question_links,merge_html_tables,bind_html_reviews)
from election_watch.live_polls import normalize
from election_watch.poll_run_capture import make_capture,validate_capture

DAY='2026-10-17'
class FixedClock(datetime):
    @classmethod
    def now(cls,tz=None):return cls(2026,10,17,6,0,0,tzinfo=timezone.utc)
ENTRY={'id':'test-cnu-va02','adapter':'cnu_wason_public_html_v1','state':'VA','race_id':'USA:VA:house:02',
    'index_url':'https://cnu.edu/wason/surveys/','pollster':'Christopher Newport University',
    'pollster_group':'cnu_wason','reviewed_on':DAY}
SNAP={'schema':'usa_poll_html_table_sources_v1','cycle':2026,'records':[ENTRY]}
ARTICLE='https://cnu.edu/wason/surveys/archive/2026-10-14.html'
QINDEX='https://docs.google.com/spreadsheets/d/e/test-public-document/pubhtml'
QURL=QINDEX+'/sheet?headers=false&gid=123'
METHOD=('Findings based on 702 interviews of registered second congressional district voters '
    'who are likely general election voters, including 164 on landline and 538 on cell phone, '
    'conducted Oct. 1-10, 2026. The margin of error for the whole survey is +/-4.0% '
    'at the 95% level. Live calling was conducted with disclosed weighted demographics.')
RACE={'state':'VA','district':'02','office':'house','subject':'2026 VA-02','poll_type':'us-representative',
    'seat_name':'VA-02','contest_id':'USA:VA:house:02:2026:general','election_date':'2026-11-03',
    'general_from':'2026-08-05','required_candidates':['Candidate D','Candidate R'],
    'candidates':{'Candidate D':{'party':'DEM'},'Candidate R':{'party':'REP'}}}
POLICY={'races':{ENTRY['race_id']:RACE},'quality_reviews':{}}

def html(body):return '<html><body>'+body+'</body></html>'
def table(d=46,r=43,title='Q4: Virginia’s 2nd Congressional District ballot held TODAY [RANDOMIZE]'):
    rows=[['1',title],['3','','All','Rep'],['4','Candidate D, the Democrat',str(d),'3'],
        ['5','Candidate R, the Republican',str(r),'94'],['6','Someone else','2','1'],
        ['7','Undecided (vol)','6','1'],['8','Don’t know/ref (vol)','4','1']]
    return html('<table class="waffle">'+''.join('<tr>'+''.join('<td>'+v+'</td>'for v in row)+'</tr>'for row in rows)+'</table>')

def pages():return {ENTRY['index_url']:html('<a href="archive/2026-10-14.html">new</a>'),
    ARTICLE:html('<main><p>'+METHOD+'</p><iframe title="Survey Questions" src="'+QINDEX+'"></iframe></main>'),
    QINDEX:html('<script>items.push({name: "Q4", pageUrl: "'+QURL.replace('/','\\/')+'"});'
        'items.push({name: "Q4a", pageUrl: "'+(QINDEX+'/sheet?headers=false&gid=999').replace('/','\\/')+'"});</script>'),
    QURL:table()}

class FakeResponse:
    status=200
    def __init__(self,url,body):self.url=url;self.body=body
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def geturl(self):return self.url
    def read(self,*args):return self.body.encode()

def opener(p):
    def open_(request,**kwargs):return FakeResponse(request.full_url,p[request.full_url])
    return open_

class HtmlTablesTests(TestCase):
    def capture(self,rows=(),previous=(),p=None):
        with patch('election_watch.poll_html_tables.datetime',FixedClock):
            return merge_html_tables(list(rows),SNAP,POLICY,DAY,previous,opener=opener(p or pages()))
    def test_primary_table_normalizes_without_api_or_manual_review(self):
        rows,receipts=self.capture();policy=bind_html_reviews(POLICY,rows,receipts,SNAP,DAY)
        good,bad=normalize(rows,policy,DAY)
        self.assertEqual(bad,[]);self.assertEqual(len(good),1)
        self.assertEqual([a['pct'] for a in good[0]['answers']],[46,43])
        self.assertTrue(good[0]['aggregation_eligibility']['eligible'])
        self.assertEqual(good[0]['source_quality']['reported_precision']['half_width_pp'],4)
        self.assertIn('자동',good[0]['source_quality']['label_ko'])
        self.assertEqual(good[0]['source_quality']['accuracy_grade'],None)
    def test_subgroup_column_is_not_selected(self):
        a,_,_=question(table(),RACE);self.assertEqual(a[0]['pct'],46)
    def test_senate_subsample_question_is_not_statewide_poll(self):
        self.assertEqual(question_links(pages()[QINDEX],QINDEX),[('Q4',QURL)])
        with self.assertRaises(ValueError):question(table(title='Q4a: Senate held TODAY RANDOMIZE'),RACE)
    def test_conditional_question_is_held(self):
        with self.assertRaises(ValueError):question(table(title='Q4: 2nd Congressional District held TODAY RANDOMIZE ASK IF undecided'),RACE)
    def test_wrong_district_is_held(self):
        with self.assertRaises(ValueError):question(table(title='Q4: 3rd Congressional District held TODAY RANDOMIZE'),RACE)
    def test_candidate_change_is_held(self):
        with self.assertRaises(ValueError):question(table().replace('Candidate D,','Unknown D,'),RACE)
    def test_duplicate_candidate_is_held(self):
        with self.assertRaises(ValueError):question(table().replace('Someone else','Candidate D, the Democrat'),RACE)
    def test_missing_all_column_is_held(self):
        with self.assertRaises(ValueError):question(table().replace('>All<','>Dem<'),RACE)
    def test_unexpected_response_sum_is_held(self):
        with self.assertRaises(ValueError):question(table(70,43),RACE)
    def test_missing_non_candidate_categories_is_held(self):
        with self.assertRaises(ValueError):question(table().replace('Someone else','Not asked'),RACE)
    def test_nonfinite_other_value_is_held(self):
        with self.assertRaises(ValueError):question(table().replace('>6<','>nan<'),RACE)
    def test_methodology_missing_n_or_population_is_held(self):
        for old in ('702','likely general election voters','second congressional district'):
            with self.subTest(old=old),self.assertRaises(ValueError):
                article_metadata(pages()[ARTICLE].replace(old,'changed'),ARTICLE,ENTRY)
    def test_new_sponsor_requires_review(self):
        with self.assertRaises(ValueError):article_metadata(pages()[ARTICLE].replace('</main>','<p>Sponsored by a client</p></main>'),ARTICLE,ENTRY)
    def test_shared_document_link_cannot_escape_publisher_document(self):
        with self.assertRaises(ValueError):question_links(pages()[QINDEX].replace('test-public-document','other-document'),QINDEX)
    def test_unapproved_host_never_requested(self):
        for url in ('http://cnu.edu/wason/surveys/','https://evil.example/poll','https://docs.google.com/private'):
            with self.subTest(url=url),self.assertRaises(ValueError):document(url,opener({}))
    def test_future_article_not_fetched(self):
        p=pages();p[ENTRY['index_url']]=p[ENTRY['index_url']].replace('2026-10-14','2026-12-31')
        rows,receipts=self.capture(p=p)
        self.assertEqual(rows,[]);self.assertEqual(receipts[0]['status'],'unavailable_no_previous_data')
    def test_api_duplicate_counted_once(self):
        rows,receipts=self.capture();api=deepcopy(rows[0]);api.pop('primary_source_capture');api['id']='api-later'
        rows,receipts=self.capture([api]);self.assertEqual(len(rows),1)
        self.assertEqual(receipts[0]['record']['primary_source_capture']['provider_duplicate_ids'],['api-later'])
    def test_api_conflict_is_reference_only(self):
        rows,_=self.capture();api=deepcopy(rows[0]);api.pop('primary_source_capture');api['id']='api-conflict';api['answers'][0]['pct']=47
        rows,receipts=self.capture([api]);policy=bind_html_reviews(POLICY,rows,receipts,SNAP,DAY)
        good,bad=normalize(rows,policy,DAY)
        self.assertEqual(bad,[]);self.assertEqual(len(good),1)
        self.assertFalse(good[0]['aggregation_eligibility']['eligible'])
        self.assertEqual(receipts[0]['status'],'provider_wave_conflict_reference_only')
    def test_failure_preserves_original_date_and_values(self):
        original,receipts=self.capture()
        rows,new=self.capture(previous=receipts,p={ENTRY['index_url']:html('down')})
        self.assertEqual(rows[0]['end_date'],original[0]['end_date'])
        self.assertEqual(rows[0]['primary_source_capture']['checked_at'],original[0]['primary_source_capture']['checked_at'])
        self.assertEqual(rows[0]['answers'],original[0]['answers'])
        good,bad=normalize(rows,bind_html_reviews(POLICY,rows,new,SNAP,DAY),DAY)
        self.assertEqual(bad,[]);self.assertFalse(good[0]['aggregation_eligibility']['eligible'])
    def test_duplicate_previous_receipts_do_not_duplicate_observation(self):
        _,old=self.capture();rows,new=self.capture(previous=old+old,p={ENTRY['index_url']:html('down')})
        self.assertEqual(len(rows),1);self.assertEqual(len(new),1)
    def test_offline_checkpoint_replay_does_not_refetch(self):
        rows,receipts=self.capture()
        api=deepcopy(rows[0]);api.pop('primary_source_capture');api['id']='api-later'
        rows,receipts=self.capture([api])
        saved=validate_capture(make_capture(rows,[api],'https://api.votehub.com/polls?subject=2026',DAY,DAY+'T06:00:00+00:00',receipts,{},{}))
        with patch('election_watch.poll_html_tables.document',side_effect=AssertionError('network')):
            policy=bind_html_reviews(POLICY,saved['rows'],saved['primary_receipts'],SNAP,DAY)
            self.assertEqual(normalize(saved['rows'],policy,DAY)[1],[])
    def test_replay_contract_or_record_change_is_held(self):
        rows,receipts=self.capture();changed=deepcopy(SNAP);changed['records'][0]['note']='changed'
        with self.assertRaises(ValueError):bind_html_reviews(POLICY,rows,receipts,changed,DAY)
        rows[0]['answers'][0]['pct']=47
        with self.assertRaises(ValueError):bind_html_reviews(POLICY,rows,receipts,SNAP,DAY)
    def test_empty_html_history_does_not_break_historical_replay(self):
        self.assertEqual(bind_html_reviews(POLICY,[],[],SNAP,'2025-01-01'),POLICY)
    def test_new_dated_release_is_discovered_without_new_record(self):
        p=pages();new_url=ARTICLE.replace('2026-10-14','2026-10-16')
        p[ENTRY['index_url']]=p[ENTRY['index_url']].replace('2026-10-14','2026-10-16')
        p[new_url]=p[ARTICLE]
        rows,_=self.capture(p=p);self.assertEqual(rows[0]['created_at'],'2026-10-16')
