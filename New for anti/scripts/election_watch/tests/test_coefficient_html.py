"""Synthetic HTML only; fixtures never become published poll observations."""
from copy import deepcopy
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch
from urllib.error import URLError
from election_watch.poll_html_tables import merge_html_tables,bind_html_reviews,contracts
from election_watch.live_polls import normalize,summarize
from tests.test_poll_html_tables import FakeResponse
ENTRY={'id':'synthetic-coefficient','adapter':'coefficient_public_html_v1','state':'NE','race_id':'USA:NE:senate','index_url':'https://battlegrounds.coefficient.org/','release_url':'https://battlegrounds.coefficient.org/ne/','pollster':'co/efficient','pollster_group':'coefficient','reviewed_on':'2026-10-20'}
SNAP={'schema':'usa_poll_html_table_sources_v1','cycle':2026,'records':[ENTRY]}
RACE={'state':'NE','office':'senate','subject':'2026 Nebraska','poll_type':'us-senator','seat_name':None,'contest_id':'USA:NE:senate:2026:general','general_from':'2026-09-01','election_date':'2026-11-03','required_candidates':['Candidate R','Candidate I'],'candidates':{'Candidate R':{'party':'REP'},'Candidate I':{'party':'IND'}}}
POLICY={'cycle':2026,'races':{ENTRY['race_id']:RACE},'quality_reviews':{}}
INDEX='<html><body><a href="/ne/">Nebraska: October 2, 2026</a><a href="/ne/">NE</a><a href="/ne/">NE</a></body></html>'
METHOD='co/efficient surveyed 1,113 likely general election voters in Nebraska on September 28-30, 2026, using mobile text responses and landline interviews. Results are weighted on age, gender, race, education, congressional district, and community type. The margin of error is ±2.92 percentage points.'
QUESTION='If the November 3rd general election for U.S. Senate were held today, who would you vote for?'
def html(r=45):
    rows=''.join(f'<div class="bar-row"><span class="bar-k">{name}</span><span class="bar-v tnum">{value}%</span></div>' for name,value in [('Candidate R, Republican',r),('Candidate I, Nonpartisan',44),('Undecided',11)])
    return f'<html><body><h1>Nebraska · U.S. Senate</h1><p class="vitals"><span><b>Fielded</b> September 28-30, 2026</span><span><b>Mode</b> Mobile text responses and landline interviews</span><span><b>Sample</b> 1,113 likely general election voters</span><span><b>MoE</b> ±2.92%</span><span><b>Released</b> October 2026</span></p><p class="meth-p">{METHOD}</p><details><summary><span>Q6 </span>{QUESTION}</summary>{rows}</details><p>Independent public polling. Not sponsored by any candidate committee, party committee or other independent expenditure.</p></body></html>'
class FixedCaptureClock(datetime):
    @classmethod
    def now(cls,tz=None):
        return cls(2026,10,20,6,0,0,tzinfo=timezone.utc)

class CoefficientTests(TestCase):
    def setUp(self):
        # The synthetic historical capture must not acquire today's review
        # date, which correctly fails historical normalization as a future review.
        clock=patch('election_watch.poll_coefficient_html.datetime',FixedCaptureClock)
        clock.start();self.addCleanup(clock.stop)
    def capture(self,index=INDEX,body=None,old=(),rows=(),snapshot=SNAP):
        pages={ENTRY['index_url']:index,ENTRY['release_url']:body or html()}
        def opener(req,**kw):
            if req.full_url not in pages:raise URLError('offline')
            return FakeResponse(req.full_url,pages[req.full_url])
        return merge_html_tables(rows,snapshot,POLICY,'2026-10-20',old,opener=opener)
    def test_automatic_extract_enters_existing_normalizer_reference_only(self):
        rows,receipts=self.capture();self.assertEqual(len(rows),1)
        p=bind_html_reviews(POLICY,rows,receipts,SNAP,'2026-10-20');good,bad=normalize(rows,p,'2026-10-20')
        self.assertFalse(bad);self.assertEqual(good[0]['provider_record_date'],'2026-10-02')
        self.assertEqual(good[0]['source_quality']['reviewed_on'],'2026-10-20')
        self.assertEqual(good[0]['field_end'],'2026-09-30');self.assertFalse(good[0]['aggregation_eligibility']['eligible'])
        self.assertIsNone(summarize(good,RACE,'2026-10-20',14)['party'])
    def test_new_wave_discovered_at_same_source_without_manual_values(self):
        rows,old=self.capture();body=html().replace('September 28-30','October 16-18')
        rows,receipt=self.capture(INDEX.replace('October 2,','October 19,'),body,old)
        self.assertEqual(len(rows),2);self.assertIn('2026-10-18',{r['end_date'] for r in rows})
    def test_same_wave_change_keeps_last_values(self):
        _,old=self.capture();rows,receipts=self.capture(body=html(46),old=old)
        self.assertEqual(rows[0]['answers'][0]['pct'],45)
        self.assertEqual(rows[0]['primary_source_capture']['status'],'carried_forward_reference_only')
    def test_unknown_candidate_or_missing_method_no_zero_and_retained_date(self):
        _,old=self.capture()
        for body in (html().replace('Candidate R,','Different nominee,'),html().replace('weighted on age','unweighted on age').replace('Results are weighted','Results are not weighted'),'<html><body>Access denied</body></html>'):
            rows,_=self.capture(body=body,old=old)
            self.assertEqual(rows[0]['end_date'],'2026-09-30');self.assertEqual(rows[0]['answers'][0]['pct'],45)
            self.assertEqual(rows[0]['primary_source_capture']['status'],'carried_forward_reference_only')
    def test_undated_future_or_ambiguous_index_is_held(self):
        for index in (INDEX.replace('October 2, 2026','October 2026'),INDEX.replace('October 2,','October 21,'),INDEX.replace('</body>','<a href="/ne/">October 3, 2026</a></body>')):
            rows,receipts=self.capture(index=index);self.assertFalse(rows);self.assertEqual(receipts[0]['status'],'unavailable_no_previous_data')
    def test_api_duplicate_and_disagreement_never_count_twice(self):
        rows,_=self.capture();api=deepcopy(rows[0]);api['id']='api-later';api.pop('primary_source_capture')
        rows,receipts=self.capture(rows=[api]);self.assertEqual(len(rows),1)
        api['answers'][0]['pct']=46;rows,receipts=self.capture(rows=[api]);self.assertEqual(len(rows),1)
        self.assertEqual(receipts[0]['status'],'provider_wave_conflict_reference_only')
    def test_failed_other_source_does_not_block_working_source(self):
        from tests.test_poll_html_tables import ENTRY as OTHER
        rows,receipts=self.capture(snapshot={**SNAP,'records':[OTHER,ENTRY]})
        self.assertEqual(len(rows),1);self.assertTrue(any(r.get('status')=='unavailable_no_previous_data' for r in receipts))
    def test_url_scope_and_contract_opt_in(self):
        for patch in ({'release_url':'https://evil.example/ne/'},{'race_id':'USA:NE:house:02'},{'pollster':'Unreviewed'}):
            with self.assertRaises(ValueError):contracts({**SNAP,'records':[{**ENTRY,**patch}]},'2026-10-20')

    def test_header_and_method_disagreement_is_held(self):
        for body in (html().replace('<b>Sample</b> 1,113','<b>Sample</b> 900'),html().replace('Candidate I, Nonpartisan','Candidate I, Republican')):
            rows,receipts=self.capture(body=body)
            self.assertFalse(rows);self.assertTrue(receipts[0]['failures'])

    def test_source_health_separates_parsed_reference_from_retained_data(self):
        _,receipts=self.capture();health=receipts[-1]
        self.assertEqual(health['status'],'ok_reference_only');self.assertEqual(health['parsed_observations'],1)
        self.assertEqual(health['signal_eligible_observations'],0)
        _,retained=self.capture(body='<html><body>Unavailable</body></html>',old=receipts)
        self.assertEqual(retained[-1]['parsed_observations'],0)
        self.assertEqual(retained[-1]['carried_forward_observations'],1)
