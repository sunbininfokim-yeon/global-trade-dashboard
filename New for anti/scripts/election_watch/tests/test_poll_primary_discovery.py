"""Publisher listings identify review work, never manufacture eligible polls."""
from copy import deepcopy
from pathlib import Path
import unittest
from xml.sax.saxutils import escape
from election_watch.polls import read
from election_watch.poll_primary_discovery import (SOURCES,collect_primary,parse_emerson,
                                                  parse_index,race_hints)

C=read(Path(__file__).resolve().parents[1]/'config/usa_polls/targets_2026.json')
NAMES={s:r['name'] for s,r in C['states'].items()}
DAY='2026-10-21';STAMP=DAY+'T01:00:00+00:00'


def feed(title='NY-17 2026 Poll: Candidate D 48%, Candidate R 46%',
         when='Thu, 01 Oct 2026 09:58:10 +0000',body='',url='https://emersoncollegepolling.com/synthetic-release/'):
    return (f'<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>Emerson Polling</title>'
            f'<link>https://emersoncollegepolling.com/</link><item><title>{escape(title)}</title>'
            f'<link>{escape(url)}</link><pubDate>{when}</pubDate><content:encoded><![CDATA[{body}]]></content:encoded>'
            '</item></channel></rss>').encode()


class Response:
    status=200
    def __init__(self,url,body):self.url=url;self.body=body
    def geturl(self):return self.url
    def read(self,n):return self.body[:n]
    def __enter__(self):return self
    def __exit__(self,*args):pass


class PrimaryDiscoveryTests(unittest.TestCase):
    def test_rss_preserves_publication_day_without_inventing_field_dates_or_sample(self):
        rows,bad=parse_emerson(feed(),C,DAY,STAMP)
        self.assertEqual(bad,0);self.assertEqual(len(rows),1)
        row=rows[0];self.assertEqual(row['race_id'],'USA:NY:house:17')
        self.assertEqual(row['publisher_article_published_on'],'2026-10-01')
        self.assertNotIn('field_end',row);self.assertNotIn('sample_n',row)
        self.assertFalse(row['signal_eligible']);self.assertEqual(row['election_phase'],'unclassified')

    def test_office_in_intro_is_discovery_hint_not_a_transcribed_poll(self):
        rows,_=parse_emerson(feed('Connecticut 2026 Poll: Candidate A Leads',
            body='<p>A Connecticut gubernatorial poll. Candidate A 51%, Candidate B 38%.</p>'),C,DAY,STAMP)
        self.assertEqual(rows[0]['race_id'],'USA:CT:governor')
        self.assertEqual(len(rows[0]['publisher_context_sha256']),64)
        self.assertNotIn('answers',rows[0]);self.assertNotIn('publisher_context',rows[0])

    def test_future_old_cycle_and_national_generic_ballots_do_not_become_races(self):
        for body in (feed(when='Thu, 22 Oct 2026 09:58:10 +0000'),
                     feed(when='Wed, 01 Oct 2025 09:58:10 +0000'),
                     feed('2026 National Poll: Generic House Ballot D 51 R 40')):
            with self.subTest(body=body[:60]),self.assertRaises(ValueError):parse_emerson(body,C,DAY,STAMP)

    def test_wrong_feed_external_link_and_unsafe_xml_are_rejected(self):
        for body in (feed().replace(b'<title>Emerson Polling',b'<title>Other Polling'),
                     feed(url='https://unreviewed.example/release'),
                     b'<!DOCTYPE x [<!ENTITY a "bad">]>'+feed()):
            with self.subTest(body=body[:60]),self.assertRaises(ValueError):parse_emerson(body,C,DAY,STAMP)

    def test_quinnipiac_uses_date_from_same_card_and_ignores_generic_ballot(self):
        body=b'''<html><body><ul><li><span>October 14, 2026</span><h2><a href="/poll-release?releaseid=1">CT Governor's Race: A 58%, B 38%</a></h2></li>
        <li>October 15, 2026<h2><a href="/poll-release?releaseid=2">National Generic House Ballot</a></h2></li></ul></body></html>'''
        rows,bad=parse_index(body,'quinnipiac_results',C,DAY,STAMP)
        self.assertEqual(bad,0);self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['race_id'],'USA:CT:governor')
        self.assertEqual(rows[0]['publisher_article_published_on'],'2026-10-14')

    def test_ambiguous_page_date_cannot_be_assigned_to_undated_card(self):
        body=b'''<html><body>October 10, 2026 October 11, 2026
        <h2><a href="/poll-release?releaseid=1">CT Governor's Race</a></h2></body></html>'''
        with self.assertRaises(ValueError):parse_index(body,'quinnipiac_results',C,DAY,STAMP)

    def test_suffolk_bellwether_label_is_preserved_as_unclassified_geography(self):
        body=b'''<html><body><a href="/academics/research-at-suffolk/political-research-center/polls/other-states">Maine US Senate and Governor Statewide and Bellwether October 14, 2026</a></body></html>'''
        rows,_=parse_index(body,'suffolk_latest',C,DAY,STAMP)
        self.assertEqual({r['race_id'] for r in rows},{'USA:ME:senate','USA:ME:governor'})
        self.assertTrue(all('Bellwether' in r['poll_label'] and not r['signal_eligible'] for r in rows))

    def test_at_large_invalid_district_unscheduled_senate_and_lt_governor(self):
        self.assertEqual(race_hints('AK-AL 2026 Poll',NAMES,C),['USA:AK:house:00'])
        self.assertEqual(race_hints('FL-59 2026 Poll',NAMES,C),[])
        self.assertEqual(race_hints('Wisconsin Senate 2026 Poll',NAMES,C),[])
        self.assertEqual(race_hints('Connecticut Lieutenant Governor Poll',NAMES,C),[])

    def test_one_source_outage_does_not_erase_other_publishers(self):
        def opener(req,timeout):
            if req.full_url==SOURCES['emerson_rss']:return Response(req.full_url,feed())
            raise OSError('synthetic unavailable source')
        result=collect_primary(C,DAY,STAMP,opener)
        self.assertEqual(len(result['records']),1)
        self.assertEqual(result['source_health']['quinnipiac_results']['status'],'unavailable')
        self.assertNotIn('candidate_records',result['source_health']['quinnipiac_results'])

    def test_redirect_to_error_page_is_not_successful_collection(self):
        result=collect_primary(C,DAY,STAMP,lambda req,timeout:Response('https://www.suffolk.edu/Error/404',b'not a list'))
        self.assertFalse(result['records'])
        self.assertTrue(all(h['status']=='unavailable' for h in result['source_health'].values()))
