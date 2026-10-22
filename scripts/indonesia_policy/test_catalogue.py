import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from catalogue import identity, parse_page, run, advance
from catalogue_queue import build

JATENG=b'<span class="category-count">2</span><table><tr class="info-row"><td class="info-cell-title">Undang-undang Nomor 3 Tahun 2020 tentang Minerba</td><td class="info-cell-file"><a href="/law.pdf">Download</a></td></tr><tr class="info-row"><td class="info-cell-title">Peraturan Daerah Provinsi Jawa Tengah Nomor 6 Tahun 2010 tentang Tata Ruang</td><td class="info-cell-file"><a href="https://drive.google.com/file/d/example">Download</a></td></tr></table>'
class CatalogueTests(unittest.TestCase):
 def test_original_ministry_pagination_retains_status_without_claiming_legal_effect(self):
  s=self.source('kemendag_pages');s['url']='https://example.go.id/peraturan'
  data=b'<p>Menampilkan 10 dari 2,406 peraturan</p><div class="flex-grow-1"><span class="badge-status">Peraturan Menteri</span><span class="badge-status">Berlaku</span><h6><a href="/peraturan/law-1">1 Tahun 2026</a></h6><p>Peraturan Menteri Perdagangan Nomor 1 Tahun 2026 tentang Ekspor...</p></div><ul class="pagination"><a href="?page=1">1</a><a href="?page=2">2</a></ul>'
  rows,links,total=parse_page(data,s['url'],s);self.assertEqual(total,2406);self.assertEqual(links,['https://example.go.id/peraturan?page=2'])
  self.assertEqual(rows[0]['publisher_fields']['status'],'Berlaku');self.assertTrue(rows[0]['publisher_fields']['title_truncated']);self.assertNotIn('legal_status',rows[0])
  with tempfile.TemporaryDirectory() as d:
   state=run([s],d,set(),2,fetcher=lambda u,_:(data,u,'a'*64),delay=0)['sources'][0]
   self.assertEqual(state['status'],'failed');self.assertEqual(len(state['visited_urls']),1);self.assertIn('pagination_no_progress',state['failures'][0]['error'])
 def test_original_ministry_cannot_claim_complete_when_reported_total_is_larger(self):
  s=self.source('kemendag_pages');s['url']='https://example.go.id/peraturan'
  data=b'<p>Menampilkan 1 dari 2 peraturan</p><div class="flex-grow-1"><h6><a href="/peraturan/law">Law</a></h6><p>Unknown title</p></div>'
  with tempfile.TemporaryDirectory() as d:
   state=run([s],d,set(),1,fetcher=lambda u,_:(data,u,'a'*64),delay=0)['sources'][0]
   self.assertEqual(state['visited_urls'],[]);self.assertIn('reported_count_mismatch',state['failures'][0]['error'])
 def test_djbc_reported_total_requires_all_pages_and_known_finance_identity(self):
  s=self.source('djbc_pages');s.update(url='https://example.go.id/index.html?page=penerbit/8/menteri-keuangan/1.html',require_reported_total=True)
  row=b'<tr><td><a href="?page=detail/penerbit/8/1/law">Keputusan Menteri Keuangan Nomor 31/MK/BC/2026 Tentang Batubara</a></td></tr>'
  data=b'<p>Of 2 Row Page</p><table>'+row+b'</table>'
  rows,_,total=parse_page(data,s['url'],s);self.assertEqual(total,2);self.assertEqual(rows[0]['issuer_key'],'kemenkeu');self.assertEqual(rows[0]['document_type'],'Keputusan');self.assertEqual(rows[0]['document_number'],'31/MK/BC/2026')
  with self.assertRaisesRegex(ValueError,'count_missing'):parse_page(b'<table>'+row+b'</table>',s['url'],s)
  with tempfile.TemporaryDirectory() as d:
   state=run([s],d,set(),1,fetcher=lambda u,_:(data,u,'a'*64),delay=0)['sources'][0]
   self.assertEqual(state['records'],[]);self.assertIn('reported_count_mismatch',state['failures'][0]['error'])
 def test_changed_djbc_total_holds_the_unprocessed_page(self):
  s=self.source('djbc_pages');s.update(url='https://example.go.id/index.html?page=penerbit/8/minister/1.html',require_reported_total=True)
  first=b'Of 2 Row<table><tr><td><a href="?page=detail/penerbit/8/1/law">Law 1</a></td></tr></table><a href="?page=penerbit/8/minister/2.html">2</a>'
  second=b'Of 3 Row<table><tr><td><a href="?page=detail/penerbit/8/2/law">Law 2</a></td></tr></table>'
  with tempfile.TemporaryDirectory() as d:
   result=run([s],d,set(),2,fetcher=lambda u,_:(first if '/1.html' in u else second,u,'a'*64),delay=0)['sources'][0]
   self.assertEqual(result['status'],'failed');self.assertEqual(len(result['records']),1);self.assertEqual(len(result['visited_urls']),1)
   self.assertIn('total_changed',result['failures'][0]['error']);self.assertIn('/2.html',result['pending_urls'][0])
 def source(self,adapter='jateng_table'):
  return dict(source_id='test',adapter=adapter,url='https://example.go.id/list',scope='All rows of one explicitly bounded published listing')
 def test_inventory_keeps_every_row_without_following_external_attachments(self):
  rows,links,total=parse_page(JATENG,self.source()['url'],self.source());self.assertEqual((len(rows),links,total),(2,[],2))
  self.assertEqual(rows[0]['issuer_level'],'national');self.assertEqual(rows[1]['jurisdiction'],'Jawa Tengah')
  self.assertTrue(rows[1]['external_attachment']);self.assertIsNone(rows[1]['download_url'])
 def test_missing_rows_block_a_false_complete_claim(self):
  with self.assertRaisesRegex(ValueError,'reported_count_mismatch'):parse_page(JATENG.replace(b'>2<',b'>3<'),self.source()['url'],self.source())
 def test_new_pagination_on_a_static_table_requires_adapter_review(self):
  with self.assertRaisesRegex(ValueError,'unhandled_pagination'):
   parse_page(JATENG+b'<a rel="next" href="?page=2">Next</a>',self.source()['url'],self.source())
 def test_review_hints_do_not_drop_unrecognized_titles_or_create_law_inputs(self):
  rows=[dict(source_id='test',source_record_id=str(i),match_status='unmatched',matches=[],metadata=dict(title=t,page_url='https://example.go.id/list')) for i,t in enumerate(['Plain unclassified title','Coal royalty','Ekspor Batubara'])]
  result=build({'status':{'country':'IDN'},'items':rows});self.assertEqual(result['total'],3)
  self.assertTrue(any(not r['topic_hints'] for r in result['records']))
  self.assertTrue(all(x['review_status']=='unreviewed' for x in result['records']))
 def test_empty_challenges_and_unstructured_pages_are_not_zero_records(self):
  for data in [b'<html>Request rejected</html>',b'<html>Sistem sedang dalam perbaikan</html>',b'<main>Nothing here</main>']:
   with self.assertRaises(ValueError):parse_page(data,self.source()['url'],self.source())
 def test_document_identity_never_uses_an_amended_target_or_publisher_category(self):
  d=identity('Peraturan Menteri Perdagangan Nomor 18 Tahun 2026 tentang Perubahan Nomor 16 Tahun 2025')
  self.assertEqual((d['document_number'],d['document_year'],d['issuer_key']),('18',2026,'kemendag'))
  self.assertIsNone(identity('Peraturan Instansi Lain Nomor 456/Tahun/2023 tentang BPOM')['issuer_key'])
 def test_json_feed_is_metadata_not_automatic_law_ingestion(self):
  s=self.source('ildis_json');data=json.dumps([{'idData':'4','judul':'Undang-undang Nomor 1 Tahun 2025 tentang Test','urlDetailPeraturan':'https://example.go.id/law','urlDownload':'-','last_updated':'2025-01-01'}]).encode()
  rows,_,_=parse_page(data,s['url'],s);self.assertEqual(rows[0]['source_record_id'],'4');self.assertIsNone(rows[0]['download_url'])
  self.assertNotIn('legal_status',rows[0]);self.assertNotIn('text_content',rows[0])
 def test_resume_is_atomic_and_does_not_refetch_processed_pages(self):
  s=self.source('djbc_pages');s['url']='https://example.go.id/index.html?page=penerbit/43/minister/1.html'
  first=b'<a href="?page=penerbit/43/minister/2.html">2</a><table><tr><td><a href="?page=detail/penerbit/43/1/law">Peraturan Menteri Perdagangan Nomor 1 Tahun 2025</a></td></tr></table>'
  second=b'<table><tr><td><a href="?page=detail/penerbit/43/2/law">Peraturan Menteri Perdagangan Nomor 2 Tahun 2025</a></td></tr></table>'
  calls=[]
  def fetch(url,_):calls.append(url);return (first if len(calls)==1 else second,url,'a'*64)
  with tempfile.TemporaryDirectory() as d:
   a=run([s],d,set(),1,fetcher=fetch,delay=0);self.assertEqual(a['sources'][0]['status'],'partial')
   b=run([s],d,set(),1,resume=True,fetcher=fetch,delay=0);self.assertEqual(b['sources'][0]['status'],'enumerated_scope');self.assertEqual(len(b['sources'][0]['records']),2)
   self.assertEqual(len(calls),2);self.assertIn('/2.html',calls[1])
   run([s],d,set(),1,resume=True,fetcher=fetch,delay=0);self.assertEqual(len(calls),2)
 def test_failed_parse_never_advances_cursor_and_resume_does_not_retry_blocked_pages(self):
  calls=[]
  def fetch(url,_):calls.append(url);return (b'Access denied',url,'a'*64)
  with tempfile.TemporaryDirectory() as d:
   a=run([self.source()],d,set(),1,fetcher=fetch,delay=0)['sources'][0];self.assertEqual(a['status'],'failed');self.assertEqual(a['visited_urls'],[]);self.assertEqual(len(a['pending_urls']),1)
   run([self.source()],d,set(),1,resume=True,fetcher=fetch,delay=0);self.assertEqual(len(calls),1)
 def test_repeated_pagination_cannot_masquerade_as_completion(self):
  s=self.source('djbc_pages');s['url']='https://example.go.id/index.html?page=penerbit/43/minister/1.html'
  data=b'<a href="?page=penerbit/43/minister/2.html">2</a><table><tr><td><a href="?page=detail/penerbit/43/1/law">Peraturan Menteri Perdagangan Nomor 1 Tahun 2025</a></td></tr></table>'
  with tempfile.TemporaryDirectory() as d:
   a=run([s],d,set(),3,fetcher=lambda u,_:(data,u,'a'*64),delay=0)['sources'][0]
   self.assertEqual(a['status'],'failed');self.assertEqual(len(a['visited_urls']),1);self.assertIn('pagination_no_progress',a['failures'][0]['error'])
 def test_stop_and_changed_registry_are_respected(self):
  with tempfile.TemporaryDirectory() as d:
   Path(d,'STOP').touch();a=run([self.source()],d,set(),1,fetcher=lambda *_:self.fail('must not fetch'),delay=0);self.assertEqual(a['sources'][0]['stop_reason'],'operator_stop')
   s=self.source();s['scope']='Changed source scope needs a new run'
   with self.assertRaisesRegex(ValueError,'registry_changed'):run([s],d,set(),1,resume=True,delay=0)
if __name__=='__main__':unittest.main()
