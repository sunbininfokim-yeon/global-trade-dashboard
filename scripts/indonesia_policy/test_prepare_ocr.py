import copy
import hashlib
import json
import unittest
from prepare_ocr import prepare


class ReviewedOCRTests(unittest.TestCase):
    def fixture(self):
        e={'document_id':'idn-test-ocr','title':'PERATURAN MENTERI NOMOR 26 TAHUN 2020','title_ko':'테스트','issuer_name':'Ministry','issuer_level':'national','jurisdiction':'Indonesia','document_type':'PMK','document_number':'26','document_year':2020,'topics':['coal'],'primary_stage':'coal','scope_note':'Review candidate only.','url':'https://example.go.id/law.pdf','identity_phrases':['NOMOR 26 TAHUN 2020']}
        text='PERATURAN MENTERI NOMOR 26 TAHUN 2020. '+ 'Pasal 1 Barang Impor Curah. '*8
        o={'engine':'Apple Vision VNRecognizeTextRequest','language_correction':False,'pages':[{'page':1,'text':text,'lines':[{'text':text,'confidence':.99}]}]}
        b=json.dumps(o).encode();pdf=b'%PDF-test';r={'pdf_sha256':hashlib.sha256(pdf).hexdigest(),'ocr_sha256':hashlib.sha256(b).hexdigest(),'method':'identity_and_selected_pages','pages':[1],'note':'Selected identity and page visually reviewed; full transcription remains unverified.'}
        return e,pdf,b,r,o

    def test_valid_text_keeps_ocr_limitations_and_raw_hash(self):
        e,pdf,b,r,o=self.fixture();d=prepare(e,pdf,b,r,1)
        self.assertFalse(d['ocr_review']['full_transcription_verified'])
        self.assertEqual(d['legal_status'],'unverified')
        self.assertEqual(d['raw_text_sha256'],r['pdf_sha256'])
        self.assertEqual(d['content_hash'],hashlib.sha256(d['text_content'].encode()).hexdigest())

    def test_changed_source_output_missing_pages_and_identity_are_rejected(self):
        e,pdf,b,r,o=self.fixture()
        for args in [(e,pdf+b'x',b,r,1),(e,pdf,b+b' ',r,1),(e,pdf,b,r,2)]:
            with self.assertRaises(ValueError):prepare(*args)
        bad=copy.deepcopy(e);bad['url']='https://example.go.id.evil.test/law.pdf'
        with self.assertRaises(ValueError):prepare(bad,pdf,b,r,1)
        bad=copy.deepcopy(e);bad['identity_phrases']=['NOMOR 27 TAHUN 2020']
        with self.assertRaises(ValueError):prepare(bad,pdf,b,r,1)

    def test_no_blank_page_or_rewritten_line_is_silently_accepted(self):
        e,pdf,b,r,o=self.fixture();o['pages'][0]['lines']=[]
        b=json.dumps(o).encode();r['ocr_sha256']=hashlib.sha256(b).hexdigest()
        with self.assertRaises(ValueError):prepare(e,pdf,b,r,1)


if __name__=='__main__':unittest.main()
