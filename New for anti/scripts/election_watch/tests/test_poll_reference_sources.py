"""Synthetic fixtures: publisher identity cannot certify individual releases."""
from copy import deepcopy
import unittest
from election_watch.live_polls import normalize, summarize
from election_watch.poll_quality import review_fingerprint
from test_live_polls import POLICY, RID, poll

DAY='2026-10-18'

class PublisherReferenceTests(unittest.TestCase):
    def fixture(self, **changes):
        policy=deepcopy(POLICY)
        policy['reference_sources']={'Unlisted Research':{
            'group':'unlisted_research','hosts':['research.example'],'reference_only':True,
            'source_role':'research_institution','reviewed_on':DAY,
            'evidence':[{'url':'https://research.example/methods','sha256':'a'*64,'checked_at':DAY+'T01:00:00+00:00'}]}}
        raw=poll(pollster='Unlisted Research',url='https://research.example/poll')
        raw.update(start_date='2026-10-14',end_date='2026-10-15',created_at='2026-10-16')
        raw.update(changes)
        return raw,policy
    def test_unknown_publisher_becomes_reference_without_a_lead(self):
        raw,policy=self.fixture();rows,rejected=normalize([raw],policy,DAY)
        self.assertFalse(rejected);self.assertEqual(len(rows),1)
        self.assertFalse(rows[0]['aggregation_eligibility']['eligible'])
        self.assertEqual(rows[0]['source_admission'],'publisher_reference')
        self.assertIsNone(rows[0]['source_quality']['accuracy_grade'])
        self.assertEqual(summarize(rows,policy['races'][RID],DAY,7)['status'],'no_recent_poll')
    def test_missing_question_sample_is_reference_null_not_zero(self):
        raw,policy=self.fixture(sample_size=None);rows,rejected=normalize([raw],policy,DAY)
        self.assertFalse(rejected);self.assertIsNone(rows[0]['sample_n'])
        self.assertIn('sample_n',rows[0]['source_quality']['missing_fields'])
    def test_unknown_flag_cannot_approve_source(self):
        raw,policy=self.fixture();policy['reference_sources']={};raw['reference_only']=True
        rows,rejected=normalize([raw],policy,DAY)
        self.assertFalse(rows);self.assertEqual(rejected[0]['reason'],'pollster_not_selected')
    def test_wrong_host_and_non_https_never_qualify(self):
        for url in ('https://research.example.evil.test/poll','http://research.example/poll',
                    'https://user:pass@research.example/poll','https://research.example:444/poll'):
            raw,policy=self.fixture(url=url)
            self.assertFalse(normalize([raw],policy,DAY)[0])
    def test_shared_cloud_storage_requires_exact_path(self):
        raw,policy=self.fixture();entry=policy['reference_sources'][raw['pollster']]
        entry['hosts']=['docs.google.com'];raw['url']='https://docs.google.com/document/d/reviewed/pub'
        self.assertFalse(normalize([raw],policy,DAY)[0])
        entry['approved_urls']=[raw['url']]
        self.assertEqual(len(normalize([raw],policy,DAY)[0]),1)
        raw['url']='https://docs.google.com/document/d/other/pub'
        self.assertFalse(normalize([raw],policy,DAY)[0])
    def test_party_source_is_reference_and_internal_remains_held(self):
        raw,policy=self.fixture(partisan='REP');rows,_=normalize([raw],policy,DAY)
        self.assertIn('party_commissioned_reference',rows[0]['aggregation_eligibility']['reasons'])
        self.assertEqual(rows[0]['commissioning']['partisan'],'REP')
        raw['internal']=True;self.assertFalse(normalize([raw],policy,DAY)[0])
    def test_existing_registered_source_is_not_downgraded(self):
        raw,policy=self.fixture(pollster='Quinnipiac University',url='https://poll.qu.edu/poll')
        policy['reference_sources'][raw['pollster']]=policy['reference_sources']['Unlisted Research']
        rows,_=normalize([raw],policy,DAY)
        self.assertTrue(rows[0]['aggregation_eligibility']['eligible'])
        self.assertEqual(rows[0]['source_admission'],'registered_pollster')
    def test_future_policy_does_not_break_historical_replay(self):
        raw,policy=self.fixture();policy['reference_sources'][raw['pollster']]['reviewed_on']='2026-10-19'
        rows,rejected=normalize([raw],policy,DAY)
        self.assertFalse(rows);self.assertEqual(rejected[0]['reason'],'pollster_not_selected')
    def test_reference_keeps_candidate_date_and_percentage_guards(self):
        for change in ({'end_date':'2026-10-20'},{'sample_size':0},
                       {'answers':[{'choice':'Wrong Candidate','pct':50},{'choice':'Bruce Blakeman','pct':40}]},
                       {'answers':[{'choice':'Kathy Hochul','pct':float('nan')},{'choice':'Bruce Blakeman','pct':40}]}):
            raw,policy=self.fixture(**change);self.assertFalse(normalize([raw],policy,DAY)[0])
    def test_exact_release_review_promotes_one_record_only(self):
        raw,policy=self.fixture();row=normalize([raw],policy,DAY)[0][0]
        policy['quality_reviews']={raw['id']:{'reviewed_on':DAY,'snapshot_sha256':review_fingerprint(row),
            'primary_toplines':{'Kathy Hochul':48,'Bruce Blakeman':44},'question_sample_n':800,
            'sources':[raw['url']],'disclosure_review':{'mode':'synthetic'},'limitations_ko':'SYNTHETIC',
            'admission':{'pollster':raw['pollster'],'provider_url':raw['url'],'methodology_url':raw['url'],
                'group':'unlisted_research','source_role':'pollster_primary','signal_eligible':True}}}
        rows,rejected=normalize([raw],policy,DAY)
        self.assertFalse(rejected);self.assertTrue(rows[0]['aggregation_eligibility']['eligible'])
        self.assertEqual(rows[0]['source_quality']['verification_level'],'primary_toplines_checked')
        raw['id']='next-release';self.assertFalse(normalize([raw],policy,DAY)[0][0]['aggregation_eligibility']['eligible'])
    def test_registry_evidence_and_no_blanket_promotions(self):
        from urllib.parse import urlparse
        for name,entry in POLICY['reference_sources'].items():
            with self.subTest(name=name):
                self.assertIs(entry['reference_only'],True)
                for evidence in entry['evidence']:
                    self.assertEqual(len(evidence['sha256']),64)
                    self.assertTrue(evidence['checked_at'].startswith(entry['reviewed_on']))
                    self.assertEqual(urlparse(evidence['url']).scheme,'https')
                for host in entry['hosts']:
                    if host.endswith('.cloudfront.net') or host=='docs.google.com':
                        self.assertTrue(entry.get('approved_urls')or entry.get('url_patterns'))
