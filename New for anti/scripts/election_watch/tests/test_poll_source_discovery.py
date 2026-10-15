"""Secondary links cannot become votes, field dates or complete coverage."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from urllib.error import HTTPError
from unittest.mock import patch
import discover_poll_sources as cli
from election_watch.poll_source_discovery import parse_270, collect_270, annotate_provider_links, MAX_BYTES

STATES = {'NY': 'New York', 'AK': 'Alaska', 'TX': 'Texas', 'UT': 'Utah'}


def row(office='house', state='new-york', district='/district-21', label='NY-21',
        source='https://pollster.example/release', phase='General Election', shown='10/09/2026', rowspan=1):
    return f'''<tr><td rowspan="{rowspan}">{shown}</td><td rowspan="{rowspan}">{phase}</td>
      <td rowspan="{rowspan}"><a href="{source}">University &amp; News</a></td>
      <td rowspan="{rowspan}"><a href="/2026-{office}-polls/{state}{district}">{label}</a></td>
      <td><table><tr class="fill-D"><td>Candidate D</td><td>46%</td></tr>
      <tr class="fill-R"><td>Candidate R</td><td>42%</td></tr></table></td><td>D</td><td>+4</td></tr>'''


def table(rows):
    return '<table id="polls-list"><thead><tr><th>Date</th></tr></thead><tbody>'+rows+'</tbody></table>'


class Response:
    def __init__(self, url, body): self.url, self.body = url, body
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, limit): return self.body[:limit]


class DiscoveryTests(unittest.TestCase):
    def parse(self, html, office='house'):
        return parse_270(html, office, 2026, '2026-10-15', STATES)

    def test_nested_candidates_advertisements_and_duplicates_do_not_inflate_counts(self):
        records, skipped = self.parse(table(row()+'<tr><td colspan="7">Advertisement</td></tr>'+row()))
        self.assertEqual(len(records), 1); self.assertEqual(skipped, [])
        r=records[0];self.assertEqual(r['race_id'], 'USA:NY:house:21')
        self.assertEqual([a['pct'] for a in r['answers']], [46,42])
        self.assertEqual(r['pollster_label'], 'University & News')
        self.assertFalse(r['signal_eligible']);self.assertEqual(r['status'], 'primary_review_required')
        self.assertIsNone(r['field_end']);self.assertIsNone(r['population']);self.assertIsNone(r['sample_n'])
        self.assertEqual(r['aggregator_date'], '2026-10-09')

    def test_at_large_and_primary_stay_explicit_and_link_query_is_preserved(self):
        records,_=self.parse(table(row(state='alaska',district='',label='AK-AL',phase='Primary Election',
            source='https://results.example/report?g=wave1')))
        self.assertEqual(records[0]['race_id'],'USA:AK:house:00')
        self.assertEqual(records[0]['election_phase'],'primary')
        self.assertEqual(records[0]['source_url'],'https://results.example/report?g=wave1')
        self.assertNotEqual(records[0]['id'],self.parse(table(row(state='alaska',district='',label='AK-AL',phase='Primary Election',
            source='https://results.example/report?g=wave2')))[0][0]['id'])

    def test_bad_rows_and_future_dates_are_reported_without_losing_other_valid_links(self):
        records,skipped=self.parse(table(row()+row(shown='10/16/2026')+row(source='javascript:alert(1)')+row(label='NY-22')))
        self.assertEqual(len(records),1);self.assertEqual(len(skipped),3)
        self.assertIn('future',skipped[0]['reason'])

    def test_missing_table_or_entirely_invalid_table_is_a_failure(self):
        for html in ('Access denied',table(''),table(row(label='Unknown'))):
            with self.assertRaises(ValueError): self.parse(html)

    def test_incomplete_candidate_table_is_held_instead_of_supplying_an_opponent(self):
        broken=row().replace('<tr class="fill-R"><td>Candidate R</td><td>42%</td></tr>','')
        records,skipped=self.parse(table(row()+broken))
        self.assertEqual(len(records),1);self.assertEqual(skipped[0]['reason'],'missing discovery candidates')

    def test_provider_url_hint_cannot_merge_distinct_questions_or_drop_query_identity(self):
        records,_=self.parse(table(row(source='https://results.example/report?g=wave1')))
        report={'records':records}
        annotate_provider_links(report,[{'url':'https://results.example/report?g=wave2'}],'2026-10-15T00:00:00Z')
        self.assertEqual(report['provider_comparison']['records_without_same_source_url'],1)
        self.assertFalse(report['records'][0]['signal_eligible'])

    def test_rowspans_keep_distinct_question_rows_without_claiming_two_independent_polls(self):
        first=row(rowspan=2)
        continuation='<tr><td><table><tr class="fill-D"><td>Candidate D</td><td>48%</td></tr><tr class="fill-R"><td>Candidate R</td><td>43%</td></tr></table></td><td>D</td><td>+5</td></tr>'
        records,skipped=self.parse(table(first+continuation))
        self.assertEqual(skipped,[]);self.assertEqual(len(records),2)
        self.assertTrue(all(r['ballot_format']=='not_reviewed' and not r['signal_eligible'] for r in records))

    def test_one_source_failure_does_not_erase_other_chambers_or_invent_zero_polls(self):
        def opener(request,timeout):
            if 'election_types%5B%5D=S' in request.full_url:
                raise HTTPError(request.full_url,403,'denied',{},None)
            office='house' if 'election_types%5B%5D=H' in request.full_url else 'governor'
            html=table(row() if office=='house' else row(office=office,state='texas',district='',label='Texas'))
            return Response(request.full_url,html.encode())
        report=collect_270(2026,'2026-10-15','2026-10-15T01:00:00Z',STATES,opener)
        self.assertEqual(report['status'],'partial');self.assertEqual(len(report['records']),2)
        self.assertEqual(report['source_health']['senate']['status'],'unavailable')
        self.assertNotIn('record_count',report['source_health']['senate'])
        self.assertEqual(report['summary']['signal_eligible_records'],0)

    def test_oversize_and_redirect_are_unavailable_without_silent_empty_success(self):
        for opener in (lambda req,timeout:Response(req.full_url,b'x'*(MAX_BYTES+1)),
                       lambda req,timeout:Response('https://other.example/',table(row()).encode())):
            report=collect_270(2026,'2026-10-15','2026-10-15T01:00:00Z',STATES,opener)
            self.assertEqual(report['status'],'partial');self.assertEqual(report['records'],[])
            self.assertTrue(all(s['status']=='unavailable' for s in report['source_health'].values()))

    def test_workflow_collects_discovery_even_after_primary_capture_failure(self):
        workflow=(Path(__file__).resolve().parents[4]/'.github/workflows/us_election_polls_refresh.yml').read_text()
        step=workflow.split('      - name: Discover supplemental individual poll links',1)[1].split('      - name:',1)[0]
        self.assertIn('if: always()',step);self.assertIn('continue-on-error: true',step)
        self.assertIn('us-polls-capture.discovery.json',step)
        self.assertIn('us-polls-capture*.json',workflow)

    def test_malformed_provider_checkpoint_does_not_discard_valid_secondary_capture(self):
        records,_=self.parse(table(row()))
        report={'records':records,'summary':{'discovered_records':1},'status':'ok'}
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint=Path(tmp)/'provider.json';checkpoint.write_text('{invalid')
            output=Path(tmp)/'discovery.json'
            with patch.object(sys,'argv',['discovery','--output',str(output),'--provider-capture',str(checkpoint)]), \
                 patch.object(cli,'collect_270',return_value=report):
                self.assertEqual(cli.main(),0)
            saved=json.loads(output.read_text())
            self.assertEqual(saved['records'],records)
            self.assertEqual(saved['provider_comparison']['status'],'unavailable')


if __name__=='__main__': unittest.main()
