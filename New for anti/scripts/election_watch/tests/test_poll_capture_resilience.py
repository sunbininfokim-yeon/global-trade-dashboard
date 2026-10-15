"""Source capture survives unrelated regression/forecast problems, never publishes unchecked data."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import patch
from contextlib import nullcontext
import refresh_live_polls as refresh
from election_watch import live_polls
from election_watch.poll_run_capture import validate_capture
from test_live_polls import POLICY,poll


class CaptureTests(unittest.TestCase):
    def run_capture(self, root, failure=None, later_review_failure=False):
        policy=root/'policy.json';policy.write_text(json.dumps(POLICY))
        quality=root/'quality.json';quality.write_text(json.dumps({'schema':'usa_poll_quality_reviews_v1','cycle':2026,'reviews':{}}))
        output=root/'public.json';checkpoint=root/'capture.json'
        output.write_text('{"fetched_at":"2026-10-01T00:00:00Z"}')
        with patch.object(sys,'argv',['capture','--capture-only','--capture-output',str(checkpoint),
                '--policy',str(policy),'--quality-reviews',str(quality),'--output',str(output),'--as-of','2026-10-09']), \
             patch.object(refresh,'fetch_polls',side_effect=failure,return_value=([poll()],'https://api.votehub.com/polls?subject=2026')), \
             patch.object(refresh,'build_live',side_effect=AssertionError('capture must not publish')), \
             patch.object(refresh,'publish_scenarios',side_effect=AssertionError('capture must not forecast')), \
             (patch.object(refresh,'apply_priorities',side_effect=[POLICY,ValueError('changed ballot review')])
                 if later_review_failure else nullcontext()):
            code=refresh.main()
        return code,output,checkpoint

    def test_capture_succeeds_without_publishing_or_touching_original_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);code,output,checkpoint=self.run_capture(root)
            self.assertEqual(code,0)
            captured=validate_capture(json.loads(checkpoint.read_text()))
            self.assertEqual(captured['as_of'],'2026-10-09')
            self.assertEqual(len(captured['provider_rows']),1)
            self.assertEqual(json.loads(output.read_text())['fetched_at'],'2026-10-01T00:00:00Z')
            self.assertFalse((root/'usa_election_live_polls_status_v1.json').exists())

    def test_actual_provider_response_survives_later_review_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            code,output,checkpoint=self.run_capture(Path(tmp),later_review_failure=True)
            self.assertEqual(code,1);self.assertFalse(checkpoint.exists())
            raw=json.loads(checkpoint.with_suffix('.provider.json').read_text())
            self.assertEqual(raw['schema'],'usa_poll_provider_capture_v1')
            self.assertEqual(raw['provider_rows'],[poll()]);self.assertEqual(raw['as_of'],'2026-10-09')
            status=json.loads(checkpoint.with_suffix('.status.json').read_text())
            self.assertTrue(status['provider_checkpoint_saved_for_attempt'])
            self.assertFalse(status['public_data_modified'])
            self.assertEqual(json.loads(output.read_text())['fetched_at'],'2026-10-01T00:00:00Z')

    def test_provider_only_audit_cannot_be_replayed_for_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            _,_,checkpoint=self.run_capture(Path(tmp))
            with self.assertRaises(ValueError):
                validate_capture(json.loads(checkpoint.with_suffix('.provider.json').read_text()))
            self.assertEqual(json.loads(checkpoint.with_suffix('.status.json').read_text())['status'],'captured_unpublished')

    def test_failure_records_attempt_without_replacing_last_valid_public_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);code,output,checkpoint=self.run_capture(root,URLError('temporary outage'))
            self.assertEqual(code,1);self.assertFalse(checkpoint.exists())
            self.assertEqual(json.loads(output.read_text())['fetched_at'],'2026-10-01T00:00:00Z')
            status=json.loads(checkpoint.with_suffix('.status.json').read_text())
            self.assertEqual(status['status'],'capture_failed');self.assertFalse(status['public_data_modified'])
            self.assertFalse((root/'usa_election_live_polls_status_v1.json').exists())

    def test_capture_cannot_publish_replay_or_omit_checkpoint_path(self):
        for args in (['--capture-only'],['--capture-only','--capture-output','/tmp/test.json','--input','/tmp/replay.json']):
            with patch.object(sys,'argv',['capture',*args]),patch.object(refresh,'fetch_polls') as fetch:
                with self.assertRaises(SystemExit):refresh.main()
                fetch.assert_not_called()

    def test_workflow_captures_independently_but_publication_requires_validation(self):
        path=Path(__file__).resolve().parents[4]/'.github/workflows/us_election_polls_refresh.yml'
        text=path.read_text();capture=text.split('  capture:',1)[1].split('  validate:',1)[0]
        self.assertNotIn('needs:',capture);self.assertNotIn('contents: write',capture)
        self.assertIn('--capture-only',capture);self.assertIn('if: always()',capture)
        refresh_job=text.split('  refresh:',1)[1]
        self.assertIn('needs: [validate, capture]',refresh_job)
        self.assertIn('actions/download-artifact@v4',refresh_job)
        self.assertIn('--retry-capture',refresh_job)
        self.assertIn("group: us-election-polls-",text);self.assertIn("cron: '10 21 * * *'",text)


class TransportTests(unittest.TestCase):
    def response(self, body=b'[{"id":"fixture"}]',url='https://api.votehub.com/polls?subject=2026'):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,*args):return body
        r=Response();r.url=url;return r

    def test_transient_http_failure_retries_and_caps_retry_after(self):
        error=HTTPError('https://api.votehub.com/polls',429,'limit',{'Retry-After':'600'},None)
        with patch.object(live_polls,'urlopen',side_effect=[error,self.response()]) as get,patch.object(live_polls,'sleep') as sleep:
            rows,_=live_polls.fetch_polls(2026,'2026-10-14')
        self.assertEqual(rows,[{'id':'fixture'}]);self.assertEqual(get.call_count,2);sleep.assert_called_once_with(30)

    def test_network_failure_is_bounded_to_three_attempts(self):
        with patch.object(live_polls,'urlopen',side_effect=URLError('offline')) as get,patch.object(live_polls,'sleep') as sleep:
            with self.assertRaises(URLError):live_polls.fetch_polls(2026,'2026-10-14')
        self.assertEqual(get.call_count,3);self.assertEqual([c.args[0] for c in sleep.call_args_list],[2,5])

    def test_denial_and_schema_change_do_not_retry_or_become_empty_success(self):
        for outcome in (HTTPError('https://api.votehub.com/polls',403,'denied',{},None),self.response(b'[]'),self.response(url='https://wrong.example/')):
            with patch.object(live_polls,'urlopen',side_effect=outcome if isinstance(outcome,Exception) else None,return_value=outcome) as get,patch.object(live_polls,'sleep') as sleep:
                with self.assertRaises((HTTPError,ValueError)):live_polls.fetch_polls(2026,'2026-10-14')
                self.assertEqual(get.call_count,1);sleep.assert_not_called()


if __name__=='__main__':unittest.main()
