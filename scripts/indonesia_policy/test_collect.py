import unittest
import subprocess
import sys
import tempfile
import io
from pypdf import PdfWriter
from unittest.mock import patch
from pathlib import Path
from collect import classify_pdf, collect, html_content, official_url, pdf_content, verify_identity


class SourceEvidenceTests(unittest.TestCase):
    def test_draft_pdf_cannot_be_final_text(self):
        self.assertEqual(classify_pdf("RANCANGAN PERATURAN MENTERI NOMOR 15 TAHUN 2026"), "draft")

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


if __name__ == "__main__":
    unittest.main()
