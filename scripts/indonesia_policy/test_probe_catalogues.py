import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import requests
from catalogue import run as catalogue_run
from probe_catalogues import check, inspect_response, probe_url, run, snapshot


class ProbeTests(unittest.TestCase):
 def source(self):
  return dict(source_id='test-original',adapter='unverified',url='https://example.go.id/',scope='Original ministry; enumeration adapter is not verified',verification={'observed_listing_url':'https://example.go.id/list'})
 def test_maintenance_and_dynamic_empty_shells_are_not_enumeration_or_zero_laws(self):
  s=self.source()
  for b,outcome in [(b'<title>ESDM-MAINTENANCE</title>Sistem sedang dalam perbaikan','maintenance'),(b'<main>Loading peraturan...</main>','reachable_dynamic_shell_unverified'),(b'<main>Official regulations</main>','reachable_catalogue_unverified')]:
   r=inspect_response(b,probe_url(s),s);self.assertEqual(r['outcome'],outcome);self.assertFalse(r['enumeration_verified']);self.assertNotIn('record_count',r)
 def test_failure_is_a_single_observation_without_retry_or_secret_exception_copy(self):
  s=self.source();calls=[]
  def fetch(url,_):
   calls.append(url);response=requests.Response();response.status_code=403;raise requests.HTTPError('opaque-private-example',response=response)
  with tempfile.TemporaryDirectory() as d:
   result=run([s],d,{s['source_id']},fetcher=fetch,delay=0);row=result['sources'][0]
   self.assertEqual(len(calls),1);self.assertEqual(row['stop_reason'],'http_403');self.assertEqual(row['failures'][0]['http_status'],403)
   self.assertEqual(row['status'],'held');self.assertEqual(row['records'],[]);self.assertEqual(row['visited_urls'],[])
   self.assertEqual(row['source_config']['verification']['observed_listing_url'],probe_url(s));self.assertNotIn('opaque-private',json.dumps(result))
   with self.assertRaisesRegex(ValueError,'new_probe'):run([s],d,{s['source_id']},fetcher=fetch,delay=0)
   self.assertEqual(len(calls),1)
 def test_source_hash_and_redirect_must_match_registered_official_response(self):
  s=self.source();b=b'<html>Official list</html>';h=hashlib.sha256(b).hexdigest()
  for actual,sha in [('https://other.go.id/list',h),(probe_url(s),'a'*64)]:
   r=check(s,Path('/unused'),fetcher=lambda *_:(b,actual,sha));self.assertEqual(r['outcome'],'probe_error');self.assertFalse(r['enumeration_verified'])
  s['verification']['observed_listing_url']='https://other.go.id/list'
  with self.assertRaises(ValueError):probe_url(s)
 def test_stop_duplicate_hosts_and_low_disk_make_no_network_requests(self):
  s=self.source()
  with tempfile.TemporaryDirectory() as d:
   Path(d,'STOP').touch();result=run([s],d,{s['source_id']},fetcher=lambda *_:self.fail('no fetch'),delay=0);self.assertEqual(result['sources'],[])
  with tempfile.TemporaryDirectory() as d,patch('probe_catalogues.shutil.disk_usage',return_value=SimpleNamespace(free=0)):
   with self.assertRaisesRegex(OSError,'disk_space'):run([s],d,{s['source_id']},fetcher=lambda *_:self.fail('no fetch'),delay=0)
  second={**s,'source_id':'second-original'}
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaisesRegex(ValueError,'one_probe'):run([s,second],d,{s['source_id'],second['source_id']},fetcher=lambda *_:self.fail('no fetch'),delay=0)
 def test_catalogue_low_disk_preserves_cursor_and_can_resume(self):
  s=dict(source_id='test',adapter='jateng_table',url='https://example.go.id/list',scope='Published regulation table')
  b=b'<span class="category-count">1</span><tr class="info-row"><td class="info-cell-title">Law</td><td class="info-cell-file"><a href="/law.pdf">PDF</a></td></tr>'
  with tempfile.TemporaryDirectory() as d:
   with patch('catalogue.shutil.disk_usage',return_value=SimpleNamespace(free=0)):
    a=catalogue_run([s],d,set(),1,fetcher=lambda *_:self.fail('no fetch'),delay=0)['sources'][0]
   self.assertEqual(a['stop_reason'],'local_disk_space');self.assertEqual(a['visited_urls'],[])
   r=catalogue_run([s],d,set(),1,resume=True,fetcher=lambda url,_:(b,url,'a'*64),delay=0)['sources'][0]
   self.assertEqual(r['status'],'enumerated_scope');self.assertEqual(len(r['records']),1)
 def test_disk_write_failure_is_not_an_origin_server_failure(self):
  s=dict(source_id='test',adapter='jateng_table',url='https://example.go.id/list',scope='Published regulation table')
  def full(*_):raise OSError(28,'No space left on device')
  with tempfile.TemporaryDirectory() as d:
   r=catalogue_run([s],d,set(),1,fetcher=full,delay=0)['sources'][0]
   self.assertEqual(r['status'],'partial');self.assertEqual(r['stop_reason'],'local_disk_space');self.assertEqual(r['failures'],[]);self.assertEqual(r['visited_urls'],[])


if __name__=='__main__':unittest.main()
