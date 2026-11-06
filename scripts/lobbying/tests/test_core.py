import csv
import io
import json
from pathlib import Path
import sys
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import fara_record, fara_records, lda_record, policy_refs, read_bulk, source_date
from sync import lda_sync, next_lda_url


def filing(uid='00000000-0000-0000-0000-000000000001', description='General trade; no specific legislation'):
    return {'filing_uuid':uid,'filing_type':'Q1','filing_year':2026,
            'registrant':{'id':1,'name':'Fixture lobby firm'},'client':{'name':'Fixture client','country':'US'},
            'income':None,'expenses':'0.00','lobbying_activities':[{'description':description,
              'government_entities':[{'name':'Treasury, Dept of'},{'name':'SENATE'}]}]}


class SourceContractTests(unittest.TestCase):
    def test_roc_name_does_not_override_reported_taiwan(self):
        row={'Registration Number':'3988','Foreign Principal':'Republic of China MOEA',
             'Foreign Principal Registration Date':'09/26/2025','Country/Location Represented':'TAIWAN'}
        result=fara_record(row,'principal')
        self.assertEqual(result['country_codes'],['TW'])
        self.assertEqual(result['raw_payload'],row)

    def test_registrant_country_scope_is_not_document_country(self):
        row={'Registration Number':'1','URL':'https://efile.fara.gov/docs/test.pdf','Date Stamped':'11/16/0200'}
        record=fara_record(row,'document',{'1':{'KR','JP'}})
        self.assertEqual(record['country_codes'],[])
        self.assertEqual(record['related_countries'],['JP','KR'])
        self.assertIsNone(record['source_date'])
        self.assertEqual(record['raw_payload']['Date Stamped'],'11/16/0200')

    def test_office_only_document_is_kept_without_a_fabricated_pdf(self):
        row={'Registration Number':'1','URL':'Available-FARA-Public-Office','Date Stamped':'01/01/1970'}
        record=fara_record(row,'document')
        self.assertEqual(record['text_state'],'source_unavailable')
        self.assertEqual(record['raw_payload']['URL'],'Available-FARA-Public-Office')
        self.assertNotIn('/docs/',record['source_url'])

    def test_conflicting_observations_and_malformed_rows_are_preserved(self):
        rows=[{'Registration Number':'1','Termination Date':'01/01/2001'},
              {'Registration Number':'1','Termination Date':'01/01/2002'}]
        result=fara_records(rows,'registrant')
        self.assertEqual(len(result),1)
        self.assertEqual(len(result[0]['raw_payload']['_observations']),2)
        bad=fara_record({'Registration Number':'03/20/2024','Country/Location Represented':'7383',
                         '_source_parse_status':'column_mismatch'},'principal')
        self.assertEqual(bad['country_codes'],[])
        self.assertIsNone(bad['registrant_id'])

    def test_lda_preserves_null_and_zero_and_issue_grain(self):
        record=lda_record(filing(description='H.R. 4687. General immigration issues.'))
        self.assertIsNone(record['raw_payload']['income'])
        self.assertEqual(record['raw_payload']['expenses'],'0.00')
        self.assertEqual(len(record['activities']),1)
        self.assertEqual(record['activities'][0]['grain'],'filing_issue_block')
        self.assertEqual(len(record['activities'][0]['government_entities']),2)
        self.assertEqual(record['references'][0]['resolution_status'],'ambiguous')
        self.assertIsNone(record['references'][0]['target_id'])

    def test_explicit_congress_and_multiple_congress_ambiguity(self):
        self.assertEqual(policy_refs('119th Congress H.R. 1234',{})[0]['target_id'],'119-hr-1234')
        self.assertIsNone(policy_refs('118th Congress, H.R. 1234; 119th Congress',{})[0]['target_id'])
        self.assertEqual(policy_refs('no specific legislation',{}),[])

    def test_lda_pagination_cannot_leak_token(self):
        for url in ['https://example.org/api/v1/filings/','https://lda.gov@evil.test/api/v1/filings/',
                    'http://lda.gov/api/v1/filings/','https://lda.gov/api/other/']:
            with self.assertRaises(ValueError): next_lda_url(url)
        self.assertEqual(next_lda_url('https://lda.gov/api/v1/filings/?page=2'),'https://lda.gov/api/v1/filings/?page=2')

    def test_latin1_quoted_multiline_bulk_and_identity_stability(self):
        buf=io.StringIO();writer=csv.DictWriter(buf,fieldnames=['Registration Number','Name']);writer.writeheader();writer.writerow({'Registration Number':'12','Name':'Société\nExample'})
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as archive:archive.writestr('source.csv',buf.getvalue().encode('latin-1'))
        row=read_bulk(data.getvalue())[0]
        self.assertEqual(row['Name'],'Société\nExample')
        self.assertEqual(fara_record(row,'registrant')['record_id'],fara_record({**row,'Name':'new name'},'registrant')['record_id'])


class DurableCursorTests(unittest.TestCase):
    def test_schema_failure_preserves_last_committed_next_link(self):
        class DB:
            def __init__(self): self.state={};self.events=[]
            def rpc(self,name,**args):
                if name=='lobby_database_bytes':return 0
                stream=args['p_stream']
                if name=='lobby_claim_stream': return {'cursor':self.state.get(stream,{})}
                if name=='lobby_commit_batch': self.state[stream]=args['p_cursor'];self.events.append(args)
        class HTTP:
            def get(self,url,**kwargs):
                if 'page=2' in url:return b'{"results": "changed schema"}'
                return json.dumps({'count':2,'results':[filing()], 'next':'https://lda.gov/api/v1/filings/?page=2'}).encode()
        db=DB();results=lda_sync(db,HTTP(),3)
        self.assertTrue(all(r['status']=='source_unavailable' for r in results))
        self.assertEqual(db.state['lda:backfill']['next'],'https://lda.gov/api/v1/filings/?page=2')
        self.assertEqual(len(db.events),2)

    def test_403_does_not_commit_a_cursor(self):
        class DB:
            def rpc(self,name,**args):
                if name=='lobby_database_bytes':return 0
                if name=='lobby_claim_stream':return {}
                if name=='lobby_commit_batch':raise AssertionError('cursor advanced after 403')
        class HTTP:
            def get(self,*args,**kwargs):raise RuntimeError('Source HTTP 403')
        self.assertTrue(all(x['status']=='source_unavailable' for x in lda_sync(DB(),HTTP(),2)))


if __name__=='__main__':unittest.main()
