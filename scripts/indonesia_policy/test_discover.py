import unittest
from discover import catalogue_links


class DiscoveryTests(unittest.TestCase):
    def test_candidates_keep_legal_catalogue_links_only(self):
        html=b'''<main><a href="/dok/pp-96-tahun-2021">PP 96 TAHUN 2021 Pelaksanaan Kegiatan Usaha Pertambangan</a>
        <a href="https://go.id.evil.example/dok/law">Official looking malicious link</a>
        <a href="https://example.com/dok/law">A long external title</a>
        <a href="/berita/story">General government story</a></main>'''
        links=catalogue_links(html,'https://jdih.kemenkeu.go.id/dok/seed')
        self.assertEqual(len(links),1)
        self.assertEqual(links[0]['url'],'https://jdih.kemenkeu.go.id/dok/pp-96-tahun-2021')

    def test_pdf_does_not_become_a_catalogue(self):
        self.assertEqual(catalogue_links(b'%PDF-1.4','https://example.go.id/file.pdf'),[])


if __name__=='__main__':
    unittest.main()
