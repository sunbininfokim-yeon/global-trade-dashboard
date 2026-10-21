import importlib.util
import io
import json
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

spec = importlib.util.spec_from_file_location("collect", Path(__file__).resolve().parents[1] / "collect.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# The paragraph of the ministry's press release for 1-14 August 2026 (esdm.go.id,
# read from a GitHub runner on 2026-10-21), with the page furniture around it.
AUG_1 = (
    "ESDM Tetapkan HBA Periode Pertama Agustus 2026 USD 124,44 per Ton, Turun 5,62 Persen Jakarta - ... "
    "Untuk masa berlaku 1-14 Agustus 2026, Kementerian ESDM menetapkan empat kategori harga acuan sebagai berikut: "
    "HBA untuk 6.322 GAR sebesar USD 124,44 per ton, turun 5,62 persen dibandingkan periode kedua Juli 2026. "
    "HBA I untuk 5.300 GAR sebesar USD 93,27 per ton, naik 3,75 persen. "
    "HBA II untuk 4.100 GAR sebesar USD 65,48 per ton, naik 3,53 persen. "
    "HBA III untuk 3.400 GAR sebesar USD 45,27 per ton, naik 0,42 persen. Bagikan Ini! Berita Terkini ..."
)


def col(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def make_xlsx(sheets):
    """A minimal workbook: shared strings for text, plain numbers."""
    strings, index = [], {}

    def sid(text):
        if text not in index:
            index[text] = len(strings)
            strings.append(text)
        return index[text]

    sheet_xml = []
    for rows in sheets.values():
        body = []
        for r, row in enumerate(rows, start=1):
            cells = []
            for c, v in enumerate(row):
                if v is None:
                    continue
                ref = f"{col(c)}{r}"
                if isinstance(v, str):
                    cells.append(f'<c r="{ref}" t="s"><v>{sid(v)}</v></c>')
                else:
                    cells.append(f'<c r="{ref}"><v>{v}</v></c>')
            body.append(f'<row r="{r}">{"".join(cells)}</row>')
        sheet_xml.append('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                         f'<sheetData>{"".join(body)}</sheetData></worksheet>')
    wb = ('<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
          + "".join(f'<sheet name="{escape(n)}" sheetId="{i}" r:id="rId{i}"/>' for i, n in enumerate(sheets, 1))
          + "</sheets></workbook>")
    rels = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(f'<Relationship Id="rId{i}" Type="x" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheets) + 1))
            + "</Relationships>")
    sst = ('<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
           + "".join(f"<si><t>{escape(s)}</t></si>" for s in strings) + "</sst>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("xl/workbook.xml", wb)
        zf.writestr("xl/_rels/workbook.xml.rels", rels)
        zf.writestr("xl/sharedStrings.xml", sst)
        for i, xml in enumerate(sheet_xml, 1):
            zf.writestr(f"xl/worksheets/sheet{i}.xml", xml)
    return buf.getvalue()


def pink_sheet(unit="($/mt)", coal=True):
    names = ["", "Crude oil, average", "Coal, Australian" if coal else "Coal, Other", "Coal, South African"]
    return {
        "Description": [["Pink Sheet"]],
        "Monthly Prices": [
            ["World Bank Commodity Price Data (The Pink Sheet)"],
            ["Updated on October 02, 2026"],
            [],
            names,
            ["", "($/bbl)", unit, unit],
            ["1960M01", 1.63, 12.5, 10.0],
            ["2026M06", 70.1, 138.5, 96.3],
            ["2026M07", 71.2, "…", 97.4],      # a gap is not a zero
            ["2026M08", 72.0, 140.25, 98.0],
        ],
    }


class HbaParseTests(unittest.TestCase):
    def test_august_announcement(self):
        got = m.parse_hba_announcement(AUG_1, "https://x/hba", "ESDM Tetapkan HBA Periode Pertama Agustus 2026")
        self.assertEqual((got["start"], got["end"]), ("2026-08-01", "2026-08-14"))
        by = {g["name"]: g for g in got["grades"]}
        self.assertEqual([g["name"] for g in got["grades"]], ["HBA", "HBA I", "HBA II", "HBA III"])
        self.assertEqual((by["HBA II"]["gar"], by["HBA II"]["usd_per_t"], by["HBA II"]["change_pct"]), (4100, 65.48, 3.53))
        self.assertEqual((by["HBA"]["gar"], by["HBA"]["usd_per_t"], by["HBA"]["change_pct"]), (6322, 124.44, -5.62))
        self.assertEqual(by["HBA III"]["usd_per_t"], 45.27)

    def test_second_half_period_from_the_title_when_the_text_has_no_dates(self):
        text = AUG_1.replace("Untuk masa berlaku 1-14 Agustus 2026,", "Untuk periode ini,")
        got = m.parse_hba_announcement(text, "u", "ESDM Tetapkan HBA Periode Kedua Oktober 2026")
        self.assertEqual((got["start"], got["end"]), ("2026-10-15", "2026-10-31"))

    def test_an_en_dash_in_the_period(self):
        got = m.parse_hba_announcement(AUG_1.replace("1-14 Agustus", "15–31 Agustus"), "u")
        self.assertEqual((got["start"], got["end"]), ("2026-08-15", "2026-08-31"))

    def test_never_guesses(self):
        # a grade missing
        with self.assertRaises(m.SourceError) as e:
            m.parse_hba_announcement(AUG_1.replace("HBA III untuk 3.400 GAR sebesar USD 45,27 per ton", ""), "u")
        self.assertEqual(str(e.exception), "grades_missing")
        # grades out of order (a typo in the release would show as a price)
        with self.assertRaises(m.SourceError) as e:
            m.parse_hba_announcement(AUG_1.replace("USD 65,48", "USD 165,48"), "u")
        self.assertEqual(str(e.exception), "grades_inconsistent")
        # no period anywhere
        with self.assertRaises(m.SourceError) as e:
            m.parse_hba_announcement(AUG_1.replace("masa berlaku 1-14 Agustus 2026", "masa berlaku segera").replace("Periode Pertama Agustus 2026", ""), "u")
        self.assertEqual(str(e.exception), "period_unreadable")

    def test_indonesian_numbers(self):
        self.assertEqual(m.id_number("124,44", True), 124.44)
        self.assertEqual(m.id_number("1.234,5", True), 1234.5)
        self.assertEqual(m.id_number("6.322", False), 6322)
        with self.assertRaises(m.SourceError):
            m.id_number("abc", True)

    def test_list_page_links_keep_only_hba_announcements(self):
        html = (
            '<a href="/id/media-center/arsip-berita/esdm-tetapkan-hba-periode-kedua-oktober-2026-usd-12681-per-ton">ESDM Tetapkan HBA</a>'
            '<a href="/id/media-center/arsip-berita/bahlil-pastikan-stok-bbm-aman">BBM</a>'
            '<a href="/id/media-center/arsip-berita/harga-batu-bara-acuan-hba-september-2026">HBA Sept</a>'
            '<a href="/id/media-center/arsip-berita/jangan-tunggu-sakit">hbahaha</a>'
            '<a href="/id/other/hba-page">not news</a>'
        )
        got = m.hba_links(html, "https://www.esdm.go.id/id/media-center/arsip-berita")
        self.assertEqual([u.rsplit("/", 1)[-1] for u, _ in got],
                         ["esdm-tetapkan-hba-periode-kedua-oktober-2026-usd-12681-per-ton", "harga-batu-bara-acuan-hba-september-2026"])


class HbaFetchTests(unittest.TestCase):
    BASE = "https://www.esdm.go.id/id/media-center/arsip-berita"

    def site(self, hits):
        """pages: {1: [slug...], 2: [...]}; articles: slug -> text."""
        pages = {}
        for n, slugs in hits["pages"].items():
            url = self.BASE if n == 1 else f"{self.BASE}?page={n}"
            pages[url] = "".join(f'<a href="/id/media-center/arsip-berita/{s}">t</a>' for s in slugs).encode()
        for slug, text in hits["articles"].items():
            pages[f"{self.BASE}/{slug}"] = f"<html><body><p>{text}</p></body></html>".encode()
        calls = []

        def get(url):
            calls.append(url)
            if url not in pages:
                raise m.SourceError("http_404")
            return pages[url]
        return get, calls

    def text(self, first, last, month, w=(124.44, 93.27, 65.48, 45.27)):
        return (f"Untuk masa berlaku {first}-{last} {month} 2026, Kementerian ESDM ... HBA untuk 6.322 GAR sebesar USD {str(w[0]).replace('.', ',')} per ton, "
                f"naik 1,0 persen. HBA I untuk 5.300 GAR sebesar USD {str(w[1]).replace('.', ',')} per ton, naik 1,0 persen. "
                f"HBA II untuk 4.100 GAR sebesar USD {str(w[2]).replace('.', ',')} per ton, turun 1,0 persen. "
                f"HBA III untuk 3.400 GAR sebesar USD {str(w[3]).replace('.', ',')} per ton, naik 0,5 persen.")

    def test_first_run_pages_down_to_the_announcements(self):
        get, calls = self.site({
            "pages": {1: ["a-news", "b-news"], 2: ["c-news", "esdm-tetapkan-hba-kedua-oktober"], 3: ["d-news", "esdm-tetapkan-hba-pertama-oktober"]},
            "articles": {"esdm-tetapkan-hba-kedua-oktober": self.text(15, 31, "Oktober", (126.81, 94.0, 66.1, 46.0)),
                         "esdm-tetapkan-hba-pertama-oktober": self.text(1, 14, "Oktober", (122.52, 90.0, 63.45, 44.0))},
        })
        got = m.fetch_hba(None, get=get, pause=0, max_pages=6)
        self.assertEqual([p["start"] for p in got["periods"]], ["2026-10-01", "2026-10-15"])
        self.assertEqual(got["latest_end"], "2026-10-31")
        self.assertEqual(got["periods"][-1]["grades"][2]["usd_per_t"], 66.1)

    def test_a_later_run_stops_at_the_announcement_it_already_has(self):
        get, calls = self.site({
            "pages": {1: ["x"], 2: ["esdm-tetapkan-hba-kedua-oktober", "y"], 3: ["esdm-tetapkan-hba-pertama-oktober"], 4: ["z"]},
            "articles": {"esdm-tetapkan-hba-kedua-oktober": self.text(15, 31, "Oktober"),
                         "esdm-tetapkan-hba-pertama-oktober": self.text(1, 14, "Oktober")},
        })
        first = m.fetch_hba(None, get=get, pause=0)
        calls.clear()
        again = m.fetch_hba(first, get=get, pause=0)
        # page 1 (nothing new), page 2 (the known announcement): stop. No article is fetched twice.
        self.assertEqual(calls, [self.BASE, f"{self.BASE}?page=2"])
        self.assertEqual(again["periods"], first["periods"])

    def test_history_accumulates_beyond_what_the_archive_still_shows(self):
        old = {"periods": [{"start": "2026-07-15", "end": "2026-07-31", "url": "old", "grades": []}]}
        get, _ = self.site({"pages": {1: ["esdm-tetapkan-hba-agustus"]}, "articles": {"esdm-tetapkan-hba-agustus": self.text(1, 14, "Agustus")}})
        got = m.fetch_hba(old, get=get, pause=0, max_pages=1)
        self.assertEqual([p["start"] for p in got["periods"]], ["2026-07-15", "2026-08-01"])

    def test_an_unreadable_announcement_is_skipped_and_named(self):
        get, _ = self.site({"pages": {1: ["esdm-tetapkan-hba-ok", "esdm-tetapkan-hba-broken"]},
                            "articles": {"esdm-tetapkan-hba-ok": self.text(1, 14, "Agustus"),
                                         "esdm-tetapkan-hba-broken": "Pengumuman HBA tanpa angka"}})
        got = m.fetch_hba(None, get=get, pause=0, max_pages=1)
        self.assertEqual(len(got["periods"]), 1)
        self.assertTrue(any("esdm-tetapkan-hba-broken" in s for s in got["skipped"]))

    def test_nothing_found_is_an_error_not_an_empty_success(self):
        get, _ = self.site({"pages": {1: ["a-news"]}, "articles": {}})
        with self.assertRaises(m.SourceError) as e:
            m.fetch_hba(None, get=get, pause=0, max_pages=1)
        self.assertEqual(str(e.exception), "no_announcements_found")


class WorldBankTests(unittest.TestCase):
    def test_xlsx_roundtrip_keeps_row_positions(self):
        rows = m.read_xlsx_sheet(make_xlsx(pink_sheet()), "monthly prices")   # sheet names match any case
        self.assertEqual(rows[3][2], "Coal, Australian")
        self.assertEqual(rows[6][2], 138.5)
        self.assertEqual(rows[2], [])

    def test_coal_series(self):
        got = m.parse_worldbank_monthly(m.read_xlsx_sheet(make_xlsx(pink_sheet()), "Monthly Prices"))
        aus = next(s for s in got["series"] if s["id"] == "coal_australian")
        sa = next(s for s in got["series"] if s["id"] == "coal_south_african")
        self.assertEqual(aus["points"], [["1960-01", 12.5], ["2026-06", 138.5], ["2026-08", 140.25]])   # July's gap is absent, not 0
        self.assertEqual(sa["points"][-1], ["2026-08", 98.0])
        self.assertEqual(aus["source_name"], "Coal, Australian")
        self.assertEqual(aus["unit"], "$/mt")

    def test_a_changed_unit_is_refused(self):
        with self.assertRaises(m.SourceError) as e:
            m.parse_worldbank_monthly(m.read_xlsx_sheet(make_xlsx(pink_sheet(unit="($/kg)")), "Monthly Prices"))
        self.assertEqual(str(e.exception), "unit_changed")

    def test_a_missing_column_is_refused(self):
        with self.assertRaises(m.SourceError) as e:
            m.parse_worldbank_monthly(m.read_xlsx_sheet(make_xlsx(pink_sheet(coal=False)), "Monthly Prices"))
        self.assertEqual(str(e.exception), "coal_columns_missing")

    def test_not_a_workbook_and_missing_sheet(self):
        with self.assertRaises(m.SourceError):
            m.read_xlsx_sheet(b"<html>blocked</html>", "Monthly Prices")
        with self.assertRaises(m.SourceError) as e:
            m.read_xlsx_sheet(make_xlsx({"Other": [["x"]]}), "Monthly Prices")
        self.assertEqual(str(e.exception), "sheet_missing")

    def test_fetch_finds_the_workbook_link_on_the_page(self):
        link = "https://thedocs.worldbank.org/en/doc/abc-0050012026/related/CMO-Historical-Data-Monthly.xlsx"
        page = f'<a href="{link}">Monthly</a><a href="https://thedocs.worldbank.org/en/doc/abc/related/CMO-Historical-Data-Annual.xlsx">Annual</a>'.encode()
        blob = make_xlsx(pink_sheet())
        got = m.fetch_worldbank(lambda url: page if url == m.WB_PAGE else blob if url == link else (_ for _ in ()).throw(m.SourceError("http_404")))
        self.assertEqual((got["status"], got["file_url"], got["latest_period"]), ("ok", link, "2026-08"))
        with self.assertRaises(m.SourceError) as e:
            m.fetch_worldbank(lambda url: b"<html>no links</html>")
        self.assertEqual(str(e.exception), "workbook_link_missing")


class CollectTests(unittest.TestCase):
    NOW = datetime(2026, 10, 21, 1, 0, tzinfo=timezone.utc)

    def test_a_failed_source_keeps_its_last_good_data_marked(self):
        previous = {"hba": {"status": "ok", "periods": [{"start": "2026-10-01", "end": "2026-10-14", "url": "u", "grades": []}]},
                    "worldbank": {"status": "ok", "latest_period": "2026-08", "series": [{"id": "coal_australian", "points": [["2026-08", 140.25]]}]}}

        def blocked(url):
            raise m.SourceError("http_403")

        doc = m.collect(previous, now=self.NOW, get=blocked, pause=0)
        self.assertEqual(doc["schema_version"], "coal_prices_v1")
        for key in ("hba", "worldbank"):
            self.assertEqual((doc[key]["status"], doc[key]["error"]), ("error", "http_403"))
        self.assertEqual(doc["worldbank"]["series"][0]["points"], [["2026-08", 140.25]])   # kept, with its date
        self.assertEqual(doc["hba"]["periods"][0]["start"], "2026-10-01")

    def test_a_failed_first_run_has_no_numbers_at_all(self):
        def blocked(url):
            raise m.SourceError("unreachable")

        doc = m.collect(None, now=self.NOW, get=blocked, pause=0)
        self.assertNotIn("periods", doc["hba"])
        self.assertNotIn("series", doc["worldbank"])
        json.dumps(doc)


if __name__ == "__main__":
    unittest.main()
