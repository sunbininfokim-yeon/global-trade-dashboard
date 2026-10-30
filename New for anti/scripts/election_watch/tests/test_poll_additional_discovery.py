"""Published aggregator tables and commentary cannot silently become poll votes."""
import json,unittest
from election_watch.poll_additional_discovery import live_key,parse_rtwh,parse_rss,collect_additional,extend_report,EMBED,RTWH,RSS,LIVE_BASE
STATES={'OH':'Ohio','CA':'California','PA':'Pennsylvania'}
HEADER=['Added','Section (Links)','Type','Poll (Links)','Leader','Data']
def table():return {'data':[[HEADER.copy(),['Oct 16',{'value':'Governor'},'Ohio - Acton v. Ramaswamy',{'type':'link','href':'https://university.example/poll','value':'Sep 29 - Oct 9: University (A+), 1000 LV'},'Acton D+6','Acton 50% Ramaswamy 44%'],['','', 'Californ. - A v. B',{'type':'link','href':'https://other.example/poll','value':'Oct 8: Other'},'A+2','A 46% B 44%'],['',{'value':'Generic Ballot'},'National',{'type':'link','href':'https://generic.example/poll','value':'generic'},'D+4','D 48 R 44']]]}
def embed(key='60409c42-5e3a-401d-9d59-e1cad2d56e11'):
 doc={'title':'All 2026 Polls','elements':{'content':{'content':{'entities':{'fixture':{'props':{'chartData':{'custom':{'live':{'enabled':True,'provider':'atlas_google_drive','key':key}}}}}}}}}}
 return 'window.infographicData='+json.dumps(doc)+';'
def rss(title='Still Counting',when='Wed, 14 Oct 2026 23:31:00 +0000'):
 return f'<rss><channel><title>{title}</title><item><title>Fixture episode, not a real poll</title><link>https://audioboom.com/posts/123</link><guid>fixture-guid</guid><pubDate>{when}</pubDate></item></channel></rss>'.encode()
class Response:
 def __init__(self,url,body):self.url=url;self.body=body
 def __enter__(self):return self
 def __exit__(self,*a):pass
 def read(self,n):return self.body[:n]
class AdditionalDiscoveryTests(unittest.TestCase):
 def test_rtwh_labels_and_ratings_are_preserved_without_becoming_verified_fields(self):
  rows,skipped=parse_rtwh(table(),2026,STATES);self.assertFalse(skipped);self.assertEqual(len(rows),2);r=rows[0];self.assertEqual(r['race_id'],'USA:OH:governor');self.assertIn('(A+)',r['poll_label']);self.assertFalse(r['signal_eligible']);self.assertIsNone(r['sample_n']);self.assertIsNone(r['field_end']);self.assertIsNone(rows[1]['race_id']);self.assertIsNone(rows[1]['state']);self.assertNotIn('accuracy_grade',r)
 def test_table_schema_and_unsafe_link_fail_without_guessing_a_poll(self):
  d=table();d['data'][0][0][0]='Changed'
  with self.assertRaises(ValueError):parse_rtwh(d,2026,STATES)
  d=table();d['data'][0][1][3]['href']='javascript:alert(1)';rows,bad=parse_rtwh(d,2026,STATES);self.assertEqual(len(rows),1);self.assertEqual(len(bad),1)
 def test_manifest_requires_reviewed_published_chart_shape_and_valid_key(self):
  self.assertEqual(live_key(embed()),'60409c42-5e3a-401d-9d59-e1cad2d56e11')
  for s in (embed().replace('2026','2028'),embed('https://other.example'),'<html>blocked</html>'):
   with self.assertRaises(ValueError):live_key(s)
 def test_podcast_guid_dedup_key_and_date_do_not_produce_poll_numbers(self):
  records=parse_rss(rss(),'2026-10-19');r=records[0];self.assertEqual(r['kind'],'podcast_commentary');self.assertFalse(r['signal_eligible']);self.assertNotIn('answers',r);self.assertNotIn('sample_n',r)
  with self.assertRaises(ValueError):parse_rss(rss(title='Different podcast'),'2026-10-19')
  with self.assertRaises(ValueError):parse_rss(rss(when='Wed, 21 Oct 2026 23:31:00 +0000'),'2026-10-19')
 def test_publisher_must_still_embed_the_reviewed_chart_before_any_live_data_request(self):
  calls=[]
  def open(req,timeout):
   calls.append(req.full_url);return Response(req.full_url,rss()if req.full_url==RSS else b'No reviewed embed')
  d=collect_additional(2026,'2026-10-19','2026-10-19T00:00:00Z',STATES,open);self.assertFalse(d['records']);self.assertEqual(len(d['commentary']),1);self.assertNotIn(EMBED,calls);self.assertEqual(d['source_health']['rtwh_parse']['status'],'unavailable')
 def test_public_embed_chain_is_bounded_and_its_rows_are_not_added_to_poll_count(self):
  def open(req,timeout):
   u=req.full_url;body=(EMBED.encode()if u==RTWH else embed().encode()if u==EMBED else rss()if u==RSS else json.dumps(table()).encode());return Response(u,body)
  d=collect_additional(2026,'2026-10-19','2026-10-19T00:00:00Z',STATES,open);self.assertEqual(len(d['records']),2);self.assertEqual(len(d['commentary']),1)
  r=extend_report({'records':[],'status':'ok','source_health':{}},d);self.assertEqual(r['summary']['signal_eligible_records'],0);self.assertEqual(r['summary']['commentary_entries'],1);self.assertEqual(r['summary']['races'],1)
 def test_source_outages_do_not_erase_existing_270_records_or_turn_into_zero_polls(self):
  def bad(req,timeout):raise OSError('fixture source outage')
  d=collect_additional(2026,'2026-10-19','2026-10-19T00:00:00Z',STATES,bad);r=extend_report({'records':[{'race_id':'USA:OH:senate','office':'senate'}],'status':'ok','source_health':{}},d);self.assertEqual(len(r['records']),1);self.assertEqual(r['status'],'partial');self.assertEqual(r['source_health']['still_counting']['status'],'unavailable');self.assertNotIn('record_count',r['source_health']['rtwh_publisher'])
