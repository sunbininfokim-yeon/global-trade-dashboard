import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from automatic_admission import prepare,validate_document,Held,topics
from scheduled_sync import catalogue_snapshot,admission_artifact,run

SOURCE=dict(source_id='test',url='https://example.go.id/list',adapter='ildis_json',scope='Published official listing only')
TITLE='Peraturan Menteri Perdagangan Nomor 17 Tahun 2026 tentang Ekspor Paduan Besi'
def row():
 from catalogue import identity
 return dict(source_id='test',source_record_id='17',metadata_hash='a'*32,match_status='unmatched',matches=[],matched_document=None,
  metadata=dict(title=TITLE,page_url=SOURCE['url'],detail_url='https://example.go.id/17',download_url=None,**identity(TITLE)))
def doc(entry):
 text=entry['title'].upper()+' MEMUTUSKAN: PASAL 1. '+('Ketentuan final resmi. '*20)
 return {**{k:v for k,v in entry.items() if k not in ('expected_identity','url','identity_phrases')},'country_code':'IDN','legal_status':'unverified',
  'text_content':text,'content_hash':hashlib.sha256(text.encode()).hexdigest(),'content_kind':'official_text','text_truncated':False,
  'source_url':entry['url'],'observed_at':'2026-10-21T00:00:00Z','body_status':'extracted'}

class AdmissionTests(unittest.TestCase):
 def test_complete_identity_and_topics_are_required_and_country_stays_unverified(self):
  r=row();e=prepare(r,SOURCE);d=validate_document(doc(e),e,r)
  self.assertEqual(d['topics'],['iron_steel']);self.assertFalse(d['automatic_admission']['legal_effect_verified'])
  wrong=doc(e);wrong['text_content']=wrong['text_content'].replace('17 TAHUN','18 TAHUN');wrong['content_hash']=hashlib.sha256(wrong['text_content'].encode()).hexdigest()
  with self.assertRaises(Held):validate_document(wrong,e,r)
  for patch_value in [{'content_kind':'official_metadata'},{'text_truncated':True}]:
   with self.assertRaises(Held):validate_document({**doc(e),**patch_value},e,r)
 def test_issuer_words_do_not_classify_energy_as_mining_and_amendment_target_never_supplies_identity(self):
  self.assertEqual(topics('Peraturan Menteri Energi dan Sumber Daya Mineral Nomor 1 Tahun 2026 tentang Usaha Jasa Konservasi Energi'),[])
  self.assertEqual(topics('Peraturan tentang timah hitam'),[])
  r=row();r['metadata']['document_number']='18'
  with self.assertRaisesRegex(Held,'catalogue_identity_conflict'):prepare(r,SOURCE)
  r=row();r['match_status']='ambiguous'
  with self.assertRaises(Held):prepare(r,SOURCE)
 def test_drafts_foreign_links_wrong_hash_and_unclassified_documents_hold(self):
  r=row();e=prepare(r,SOURCE);d=doc(e);d['text_content']='RANCANGAN '+d['text_content'];d['content_hash']=hashlib.sha256(d['text_content'].encode()).hexdigest()
  with self.assertRaisesRegex(Held,'draft'):validate_document(d,e,r)
  with self.assertRaisesRegex(Held,'invalid_document'):validate_document({**doc(e),'content_hash':'b'*64},e,r)
  r['metadata']['detail_url']='https://evil.example/law'
  with self.assertRaisesRegex(Held,'official'):prepare(r,SOURCE)
 def test_local_authority_stays_local_and_cross_sector_tags_are_not_legal_findings(self):
  from catalogue import identity
  r=row();title='Peraturan Gubernur Kalimantan Utara Nomor 1 Tahun 2026 tentang Perizinan Berusaha'
  r['metadata'].update(title=title,**identity(title));e=prepare(r,SOURCE)
  self.assertEqual(e['issuer_level'],'provincial');self.assertEqual(e['jurisdiction'],'Kalimantan Utara')
  self.assertEqual(len(validate_document(doc(e),e,r)['topics']),14)
 def test_catalogue_head_is_partial_not_country_complete_and_failures_remain_failures(self):
  with tempfile.TemporaryDirectory() as root:
   data=json.dumps([dict(idData='17',judul=TITLE,urlDetailPeraturan='https://example.go.id/17')]).encode()
   snap=catalogue_snapshot(SOURCE,Path(root),{},lambda *_:(data,SOURCE['url'],'a'*64))
   self.assertEqual(len(snap['records']),1)
   bad=catalogue_snapshot(SOURCE,Path(root),{},Mock(side_effect=ValueError('blocked')))
   self.assertEqual(bad['status'],'failed');self.assertTrue(bad['pending_urls']);self.assertEqual(bad['records'],[])
 def test_metadata_only_is_not_admitted_and_known_host_cooldown_skips_fetch(self):
  import time
  collector=Mock(side_effect=lambda e,*_:{**doc(e),'content_kind':'official_metadata'})
  with tempfile.TemporaryDirectory() as root:
   r=admission_artifact(row(),SOURCE,Path(root),{},collector);self.assertEqual(r['p_outcome'],'held');self.assertIsNone(r['p_document'])
   collector.reset_mock();r=admission_artifact(row(),SOURCE,Path(root),{'example.go.id':time.time()+1000},collector)
   collector.assert_not_called();self.assertEqual(r['p_reason'],'host_cooldown')
 def test_database_failure_reuses_collected_artifact_and_does_not_refetch(self):
  import uuid
  with tempfile.TemporaryDirectory() as root:
   calls=[];fail=[True];token=str(uuid.uuid4())
   def rpc(name,args):
    calls.append(name)
    if name=='idn_acquire_sync_lease':return dict(acquired=True,lease_token=token)
    if name=='idn_ingestion_queue':return dict(country='IDN',items=[row()])
    if name=='idn_sync_store_catalogue':return dict(changed=True)
    if name=='idn_complete_ingestion':
     if fail[0]:fail[0]=False;raise RuntimeError('DB unavailable')
     return dict(new_version=True,state='stored',stale=False)
    return True
   collector=Mock(side_effect=lambda e,*_:doc(e))
   registry=[SOURCE];html=json.dumps([dict(idData='17',judul=TITLE,urlDetailPeraturan='https://example.go.id/17')]).encode()
   fetcher=Mock(return_value=(html,SOURCE['url'],'a'*64))
   def refreshed(*args,**kwargs):
    p=Path(args[1]);p.mkdir();(p/'status.json').write_text('{"cooldowns":{}}');return dict(state='ok')
   original=Path.read_text
   def read(p,*a,**kw):return json.dumps(registry) if p.name=='catalogue-sources.json' else original(p,*a,**kw)
   with patch('scheduled_sync.Path.read_text',read),patch('scheduled_sync.refresh',refreshed):
    with self.assertRaisesRegex(RuntimeError,'DB unavailable'):run(root,rpc,collector=collector,fetcher=fetcher,pause=lambda _:None)
    result=run(root,rpc,collector=collector,fetcher=fetcher,pause=lambda _:None)
   self.assertEqual(result['admitted'],1);self.assertEqual(collector.call_count,1);self.assertEqual(fetcher.call_count,1)
   self.assertEqual(calls.count('idn_ingestion_queue'),1)
   self.assertTrue((Path(root)/'reviewed'/'status.json').exists())
   self.assertTrue((Path(root)/'regional-reviewed'/'status.json').exists())
 def test_global_stop_never_connects(self):
  with tempfile.TemporaryDirectory() as root:
   Path(root,'STOP').touch();rpc=Mock();self.assertEqual(run(root,rpc)['state'],'stopped');rpc.assert_not_called()

if __name__=='__main__':unittest.main()
