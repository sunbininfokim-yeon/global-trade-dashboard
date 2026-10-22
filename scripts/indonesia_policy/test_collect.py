import unittest
import subprocess
import sys
import tempfile
import io
import requests
from pypdf import PdfWriter
from unittest.mock import patch
from pathlib import Path
from collect import classify_pdf, collect, html_content, official_url, pdf_content, verify_identity, reviewed_pdf_kind


class SourceEvidenceTests(unittest.TestCase):
    def test_draft_pdf_cannot_be_final_text(self):
        self.assertEqual(classify_pdf("RANCANGAN PERATURAN MENTERI NOMOR 15 TAHUN 2026"), "draft")

    def test_visual_final_form_review_is_pinned_and_preserves_original_text(self):
        text = 'RANCANGAN PERATURAN NOMOR 15 TAHUN 2026 ' * 5
        review = dict(raw_sha256='a'*64, method='visual_final_form', decision='official_text',
                      pages=[1,9], note='White template text; visible dated publication and signatures reviewed.')
        entry = dict(document_id='idn-review',title='Coal',title_ko='Coal',issuer_name='Government',
                     issuer_level='national',jurisdiction='Indonesia',document_type='Permendag',
                     document_number='15',document_year=2026,topics=['coal'],primary_stage='coal',
                     scope_note='Test',url='https://example.go.id/final.pdf',
                     identity_phrases=['NOMOR 15 TAHUN 2026'],pdf_review=review)
        with patch('collect.fetch',return_value=(b'%PDF-test',entry['url'],'a'*64)),patch('collect.pdf_content',return_value=text):
            result=collect(entry,Path('/tmp'))
        self.assertEqual(result['content_kind'],'official_text')
        self.assertEqual(result['text_content'],text)
        self.assertEqual(result['pdf_review'],review)
        self.assertEqual(result['legal_status'],'unverified')
        with self.assertRaisesRegex(ValueError,'invalid_or_stale_pdf_review'):
            reviewed_pdf_kind(text,entry,'b'*64)
        self.assertEqual(reviewed_pdf_kind(text,{},'a'*64),'draft')

    def test_visual_review_cannot_promote_abstracts_or_unclassified_text(self):
        review = dict(raw_sha256='a'*64,method='visual_final_form',decision='official_text',
                      pages=[1,9],note='White template text; visible dated publication and signatures reviewed.')
        for text in ['ABSTRAK PERATURAN', 'A general government catalogue']:
            with self.assertRaisesRegex(ValueError,'does_not_match_draft'):
                reviewed_pdf_kind(text,{'pdf_review':review},'a'*64)

    def test_visual_review_still_requires_exact_document_identity(self):
        entry=dict(url='https://example.go.id/final.pdf',identity_phrases=['NOMOR 99 TAHUN 2026'],
                   pdf_review=dict(raw_sha256='a'*64,method='visual_final_form',decision='official_text',
                                   pages=[1,9],note='White template text; visible dated publication and signatures reviewed.'))
        with patch('collect.fetch',return_value=(b'%PDF-test',entry['url'],'a'*64)),patch('collect.pdf_content',return_value='RANCANGAN PERATURAN NOMOR 15 TAHUN 2026 '*5):
            with self.assertRaisesRegex(ValueError,'document_identity_not_verified'):
                collect(entry,Path('/tmp'))

    def test_abstract_is_not_full_text(self):
        self.assertEqual(classify_pdf("PERATURAN MENTERI ABSTRAK : dasar hukum"), "abstract")

    def test_final_regulation_may_reference_its_earlier_draft(self):
        self.assertEqual(classify_pdf("- 1 - PERATURAN GUBERNUR BANTEN NOMOR 18 TAHUN 2025 Menimbang fasilitasi Rancangan Peraturan Gubernur"), "official_text")

    def test_all_identity_phrases_are_required(self):
        entry = {"identity_phrases": ["Nomor 15 Tahun 2026", "Batubara"]}
        self.assertFalse(verify_identity("Nomor 15 Tahun 2026 tentang Kelapa Sawit", entry))
        self.assertTrue(verify_identity("NOMOR 15 TAHUN 2026 tentang BATUBARA", entry))

    def test_official_host_boundary(self):
        self.assertTrue(official_url("https://jdih.kemenkeu.go.id/dok/test"))
        self.assertFalse(official_url("https://go.id.evil.example/doc"))
        self.assertFalse(official_url("http://jdih.kemenkeu.go.id/doc"))

    def test_page_scripts_never_become_evidence(self):
        text, _ = html_content(b'<script>Batubara</script><main>Kelapa Sawit</main>')
        self.assertEqual(text, "Kelapa Sawit")

    def test_direct_final_pdf_has_extracted_body_status(self):
        entry = dict(document_id='idn-test', title='Biofuel', title_ko='바이오연료',
                     issuer_name='ESDM', issuer_level='national', jurisdiction='Indonesia',
                     document_type='Permen', document_number='4', document_year=2025,
                     topics=['biofuel'], primary_stage='biofuel', scope_note='Test',
                     url='https://www.peraturan.go.id/files/test.pdf',
                     identity_phrases=['NOMOR 4 TAHUN 2025', 'BAHAN BAKAR NABATI'])
        text = 'PERATURAN MENTERI NOMOR 4 TAHUN 2025 BAHAN BAKAR NABATI ' * 5
        with patch('collect.fetch', return_value=(b'%PDF-test', entry['url'], 'a'*64)), patch('collect.pdf_content', return_value=text):
            result = collect(entry, Path('/tmp'))
        self.assertEqual(result['body_status'], 'extracted')
        self.assertEqual(result['content_kind'], 'official_text')

    def test_catalogue_origin_is_retained_without_changing_legal_effect(self):
        review=dict(source_id='official-list',source_record_id='42',source_page='https://example.go.id/list',
                    decision='collect_identified_official_text_not_legal_effect')
        entry=dict(document_id='idn-list-law',title='Coal',title_ko='Coal',issuer_name='Government',
                   issuer_level='national',jurisdiction='Indonesia',document_type='PP',document_number='18',
                   document_year=2025,topics=['coal'],primary_stage='coal',scope_note='Review',
                   url='https://example.go.id/18.pdf',identity_phrases=['NOMOR 18 TAHUN 2025'],catalogue_review=review)
        text='PERATURAN PEMERINTAH NOMOR 18 TAHUN 2025 '+ 'Legal text '*30
        with patch('collect.fetch',return_value=(b'%PDF-test',entry['url'],'a'*64)),patch('collect.pdf_content',return_value=text):
            result=collect(entry,Path('/tmp'))
        self.assertEqual(result['catalogue_review'],review)
        self.assertEqual(result['legal_status'],'unverified')
        with patch('collect.fetch') as fetcher:
            with self.assertRaisesRegex(ValueError,'invalid_catalogue_review'):
                collect({**entry,'catalogue_review':{**review,'source_page':'https://evil.example/list'}},Path('/tmp'))
            fetcher.assert_not_called()

    def test_existing_checkpoint_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / 'collection.json'
            checkpoint.write_text('{"previous":"evidence"}')
            run = subprocess.run([sys.executable, str(Path(__file__).with_name('collect.py')),
                                  '--stage', 'biofuel', '--output-dir', directory],
                                 capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn('collection exists', run.stderr)
            self.assertEqual(checkpoint.read_text(), '{"previous":"evidence"}')

    def test_pdf_page_limit_cannot_silently_look_complete(self):
        writer = PdfWriter()
        for _ in range(301):
            writer.add_blank_page(width=72, height=72)
        data = io.BytesIO()
        writer.write(data)
        with self.assertRaises(subprocess.CalledProcessError):
            pdf_content(data.getvalue())

    def test_official_fulltext_html_is_not_discarded_as_missing_pdf(self):
        entry=dict(document_id='idn-test-html',title='Mining',title_ko='광업',issuer_name='Government',
                   issuer_level='national',jurisdiction='Indonesia',document_type='UU',document_number='4',
                   document_year=2009,topics=['coal'],primary_stage='coal',scope_note='Test',
                   url='https://example.go.id/dok/uu-4',identity_phrases=['4 TAHUN 2009','MINERAL'])
        metadata=b'<main>UNDANG-UNDANG 4 TAHUN 2009 MINERAL '+b'Catalogue '*20+b'<a href="/api/download/fulltext/law.HTM">Fulltext HTML (Indonesia)</a></main>'
        legal=b'<main>UNDANG-UNDANG NOMOR 4 TAHUN 2009 MINERAL MEMUTUSKAN Pasal 1 '+b'Legal text '*30+b'</main>'
        with patch('collect.fetch',side_effect=[(metadata,entry['url'],'a'*64),(legal,'https://example.go.id/api/download/fulltext/law.HTM','b'*64)]),patch('collect.time.sleep'):
            result=collect(entry,Path('/tmp'))
        self.assertEqual(result['content_kind'],'official_text')
        self.assertIn('Legal text',result['text_content'])
        self.assertTrue(result['text_source_url'].endswith('.HTM'))

    def test_explicit_download_block_preserves_metadata_and_stops_the_host(self):
        entry=dict(document_id='idn-download',title='Environment',title_ko='환경',issuer_name='Government',
                   issuer_level='national',jurisdiction='Indonesia',document_type='PP',document_number='4',
                   document_year=2021,topics=['coal'],primary_stage='coal',scope_note='Test',
                   url='https://example.go.id/law',identity_phrases=['4 TAHUN 2021'])
        metadata=b'<main>PERATURAN 4 TAHUN 2021 '+b'Catalogue '*20+b'<a href="/Download/text.pdf">Download</a></main>'
        response=requests.Response();response.status_code=429
        with patch('collect.fetch',side_effect=[(metadata,entry['url'],'a'*64),requests.HTTPError('429',response=response)]),patch('collect.time.sleep'):
            result=collect(entry,Path('/tmp'))
        self.assertEqual(result['content_kind'],'official_metadata')
        self.assertEqual(result['body_fetch_blocked_host'],'example.go.id')

    def test_literal_official_attachment_link_is_parsed_without_running_script(self):
        entry=dict(document_id='idn-attachment',title='Environment',title_ko='환경',issuer_name='Government',
                   issuer_level='national',jurisdiction='Indonesia',document_type='PP',document_number='4',
                   document_year=2021,topics=['coal'],primary_stage='coal',scope_note='Test',
                   url='https://example.go.id/law',identity_phrases=['4 TAHUN 2021'])
        metadata=b'<main>PERATURAN 4 TAHUN 2021 '+b'Catalogue '*20+b'<a id="link_lampiran" href="#" onclick="window.open(\'https://example.go.id/files/doc.pdf\')">Lampiran</a></main>'
        text='PERATURAN 4 TAHUN 2021 '+ 'Legal text '*30
        with patch('collect.fetch',side_effect=[(metadata,entry['url'],'a'*64),(b'%PDF-test','https://example.go.id/files/doc.pdf','b'*64)]),patch('collect.pdf_content',return_value=text),patch('collect.time.sleep'):
            result=collect(entry,Path('/tmp'))
        self.assertEqual(result['content_kind'],'official_text')
        self.assertEqual(result['text_source_url'],'https://example.go.id/files/doc.pdf')
        with patch('collect.fetch',return_value=(metadata,entry['url'],'a'*64)) as fetcher:
            metadata_only=collect({**entry,'metadata_only':True},Path('/tmp'))
        fetcher.assert_called_once()
        self.assertEqual(metadata_only['content_kind'],'official_metadata')
        self.assertEqual(metadata_only['body_status'],'metadata_requested')

    def test_body_host_cooldown_avoids_another_attachment_request(self):
        entry=dict(document_id='idn-cooldown',title='Environment',title_ko='환경',issuer_name='Government',
                   issuer_level='national',jurisdiction='Indonesia',document_type='PP',document_number='4',
                   document_year=2021,topics=['coal'],primary_stage='coal',scope_note='Test',
                   url='https://catalogue.go.id/law',identity_phrases=['4 TAHUN 2021'])
        metadata=b'<main>PERATURAN 4 TAHUN 2021 '+b'Catalogue '*20+b'<a href="https://files.go.id/Download/text.pdf">Download</a></main>'
        with patch('collect.fetch',return_value=(metadata,entry['url'],'a'*64)) as fetcher:
            result=collect(entry,Path('/tmp'),{'files.go.id'})
        fetcher.assert_called_once()
        self.assertEqual(result['content_kind'],'official_metadata')
        self.assertIn('body_host_in_cooldown',result['body_status'])


if __name__ == "__main__":
    unittest.main()
