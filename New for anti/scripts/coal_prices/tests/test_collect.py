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
m.note = lambda msg: None   # CI-log diagnostics, not test output

# Annex II of decision 384.K/MB.01/MEM.B/2026 (HBA, first period of October 2026), the text
# layer of the PDF on jdih.esdm.go.id as a GitHub runner read it on 2026-10-21 -- OCR noise
# ("rNo.", "12 26%", stray pipes) included. The "mulai berlaku" clause is worded as in the
# May decision (179.K), whose body was read the same day.
ANNEX_OCT_1 = (
    "KELIMA : Keputusan Menteri ini mulai berlaku pada tanggal 1 Oktober 2026 , dengan ketentuan apabila di kemudian hari "
    "terdapat kekeliruan ... LAMPIRAN II KEPUTUSAN MENTERI ENERGI DAN SUMBER DAYA MINERAL REPUBLIK INDONESIA NOMOR :384.K/MB.01/MEM.B/2026 "
    "TANGGAL :30 September 2026 TENTANG HARGA MINERAL LOGAM ACUAN DAN HARGA BATUBARA ACUAN UNTUK PERIODE PERTAMA BULAN OKTOBER TAHUN 2026 "
    "BESARAN HARGA BATUBARA ACUAN PERIODE PERTAMA BULAN OKTOBER TAHUN 2026 rNo. Komoditas Satuan Nilai Keterangan "
    ". HBA dalam kesetaraan nilai kalor 6.322 kcal/kg GAR, Total Moisture 1. | Batubara (6.322 GAR) USD/ton 122,52 | 12 26%, Total Sulphur 0,66%, dan Ash 7,94% "
    "HBA I dalam kesetaraan nilai kalor 5.300 kcal/kg GAR, Total Moisture 2. | Batubara I (5.300 GAR) USD/ton 90,60 21,32%, Total Sulphur 0,75%, dan Ash 6,04% | . "
    "HBA II dalam kesetaraan nilai kalor 4.100 kcal/kg GAR, Total Moisture 3. | Batubara II (4.100 GAR) USD/ton 63,45 35,73%, Total Sulphur 0,23%, dan Ash 3,90% "
    "HBA III dalam kesetaraan nilai kalor 3.400 kcal/kg GAR, Total Moisture | 4 | Batubara III (3.400 GAR) USD/ton 43,84 44.30%, Total Sulphur 0,24%, dan Ash 3,88% "
    ": ...7 MARAS BEESY MENTERI ENERGI DAN SUMBER DAYA MINERAL REPUBLIK INDONESIA, ttd. BAHLIL LAHADALIA"
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
    def test_first_period_of_october(self):
        got = m.parse_hba_decree(ANNEX_OCT_1, "https://jdih/384.pdf")
        self.assertEqual((got["start"], got["end"], got["decree"]), ("2026-10-01", "2026-10-14", "384.K/MB.01/MEM.B/2026"))
        self.assertEqual([(g["name"], g["gar"], g["usd_per_t"]) for g in got["grades"]],
                         [("HBA", 6322, 122.52), ("HBA I", 5300, 90.60), ("HBA II", 4100, 63.45), ("HBA III", 3400, 43.84)])

    def test_second_half_runs_to_the_last_day_of_the_month(self):
        text = (ANNEX_OCT_1.replace("PERIODE PERTAMA BULAN OKTOBER", "PERIODE KEDUA BULAN OKTOBER")
                .replace("tanggal 1 Oktober 2026", "tanggal 15 Oktober 2026"))
        got = m.parse_hba_decree(text, "u")
        self.assertEqual((got["start"], got["end"]), ("2026-10-15", "2026-10-31"))
        feb = (ANNEX_OCT_1.replace("PERIODE PERTAMA BULAN OKTOBER", "PERIODE KEDUA BULAN FEBRUARI")
               .replace("tanggal 1 Oktober 2026", "tanggal 15 Februari 2026").replace("TAHUN 2026", "TAHUN 2026"))
        self.assertEqual(m.parse_hba_decree(feb, "u")["end"], "2026-02-28")

    def test_never_guesses(self):
        def refused(text):
            with self.assertRaises(m.SourceError) as e:
                m.parse_hba_decree(text, "u")
            return str(e.exception)

        # a grade missing (a row the OCR lost)
        self.assertEqual(refused(ANNEX_OCT_1.replace("Batubara III (3.400 GAR) USD/ton 43,84", "")), "grades_missing")
        # a digit misread so the prices no longer fall with calorific value
        self.assertEqual(refused(ANNEX_OCT_1.replace("USD/ton 63,45", "USD/ton 163,45")), "grades_inconsistent")
        # a calorific class the dashboard does not know: the ministry changed the scheme
        self.assertEqual(refused(ANNEX_OCT_1.replace("(4.100 GAR)", "(4.200 GAR)")), "grades_changed")
        # no period in the annex heading
        self.assertEqual(refused(ANNEX_OCT_1.replace("BESARAN HARGA BATUBARA ACUAN PERIODE PERTAMA", "BESARAN HARGA")), "period_unreadable")
        # the decision's own effective date disagrees with the heading
        self.assertEqual(refused(ANNEX_OCT_1.replace("tanggal 1 Oktober 2026", "tanggal 15 Oktober 2026")), "period_mismatch")

    def test_indonesian_numbers(self):
        self.assertEqual(m.id_number("124,44", True), 124.44)
        self.assertEqual(m.id_number("1.234,5", True), 1234.5)
        self.assertEqual(m.id_number("6.322", False), 6322)
        with self.assertRaises(m.SourceError):
            m.id_number("abc", True)

    def test_list_rows_pair_a_title_with_its_pdf(self):
        row = lambda vid, title, pdf: (f'<tr><td><a href="/dokumen/view?id={vid}">{title}</a></td>'
                                       f'<td><a href="/dokumen/download?id={pdf}">Dokumen</a></td></tr>')
        html = (row(2829, "Keputusan Menteri ESDM Nomor 381.K/KP.01/MEM.H/2026 tentang Pelimpahan Kewenangan", "2026kmesdm381k.pdf")
                + row(2827, "Keputusan Menteri ESDM Nomor 384.K/MB.01/MEM.B/2026 tentang Harga Mineral Logam Acuan dan Harga Batubara Acuan Untuk Periode Pertama", "2026kmesdm384k.pdf")
                + row(2826, "Keputusan Menteri ESDM Nomor 365.K/MB.01/MEM.B/2026 tentang Pedoman Teknis", "2026kmesdm365k.pdf"))
        got = m.hba_decree_links(html, "https://jdih.esdm.go.id/dokumen/peraturan")
        self.assertEqual([u for u, _ in got], ["https://jdih.esdm.go.id/dokumen/download?id=2026kmesdm384k.pdf"])

    def test_change_since_the_previous_half_month_is_computed_not_copied(self):
        def period(start, end, prices):
            return {"start": start, "end": end, "grades": [{"name": n, "gar": g, "usd_per_t": v} for (n, g), v in zip(
                [("HBA", 6322), ("HBA I", 5300), ("HBA II", 4100), ("HBA III", 3400)], prices)]}

        got = m.with_changes([period("2026-10-01", "2026-10-14", [122.52, 90.60, 63.45, 43.84]),
                              period("2026-10-15", "2026-10-31", [126.81, 93.62, 66.10, 54.53])])
        self.assertNotIn("change_pct", got[0]["grades"][0])
        self.assertEqual([g["change_pct"] for g in got[1]["grades"]], [3.5, 3.33, 4.18, 24.38])
        # a gap in the history is not a change
        gap = m.with_changes([period("2026-08-01", "2026-08-14", [124.44, 93.27, 65.48, 45.27]),
                              period("2026-10-01", "2026-10-14", [122.52, 90.60, 63.45, 43.84])])
        self.assertNotIn("change_pct", gap[1]["grades"][0])


class HbaFetchTests(unittest.TestCase):
    LIST = m.JDIH_LIST

    def site(self, pages):
        """pages: {1: [(slug, title)...]}; each slug's PDF text is TEXTS[slug]."""
        html = {}
        for n, rows in pages.items():
            url = self.LIST if n == 1 else f"{self.LIST}&page={n}"
            html[url] = "".join(
                f'<a href="/dokumen/view?id={i}">{title}</a><a href="/dokumen/download?id={slug}.pdf">Dokumen</a>'
                for i, (slug, title) in enumerate(rows)).encode()
        calls = []

        def get(url):
            calls.append(url)
            if url in html:
                return html[url]
            if "/dokumen/download" in url:
                return url.encode()
            raise m.SourceError("http_404")
        return get, calls

    def annex(self, half, month, day, prices):
        names = ["Batubara", "Batubara I", "Batubara II", "Batubara III"]
        gars = ["6.322", "5.300", "4.100", "3.400"]
        rows = " ".join(f"{n} ({g} GAR) USD/ton {str(v).replace('.', ',')}" for n, g, v in zip(names, gars, prices))
        return (f"mulai berlaku pada tanggal {day} {month.title()} 2026 , ... BESARAN HARGA BATUBARA ACUAN PERIODE {half} BULAN {month} TAHUN 2026 {rows}")

    def setUp(self):
        hba = "Keputusan Menteri ESDM Nomor 1.K/MB.01/MEM.B/2026 tentang Harga Mineral Logam Acuan dan Harga Batubara Acuan Untuk Periode"
        self.hba = hba
        self.texts = {
            "2026kmesdm401k.pdf": self.annex("KEDUA", "OKTOBER", 15, [126.81, 93.62, 66.1, 54.53]),
            "2026kmesdm384k.pdf": self.annex("PERTAMA", "OKTOBER", 1, [122.52, 90.60, 63.45, 43.84]),
            "2026kmesdm364k.pdf": self.annex("KEDUA", "SEPTEMBER", 15, [126.87, 91.0, 64.0, 44.0]),
        }
        self.extract = lambda blob: self.texts[blob.decode().rsplit("=", 1)[-1]]

    def test_first_run_reads_the_newest_decisions(self):
        get, calls = self.site({1: [("other", "Keputusan Menteri tentang Peta Jabatan"), ("2026kmesdm384k", self.hba)],
                                2: [("2026kmesdm364k", self.hba)]})
        got = m.fetch_hba(None, get=get, extract=self.extract, pause=0, max_pages=4)
        self.assertEqual([p["start"] for p in got["periods"]], ["2026-09-15", "2026-10-01"])
        self.assertEqual(got["latest_end"], "2026-10-14")
        self.assertEqual(got["periods"][1]["grades"][2]["usd_per_t"], 63.45)
        self.assertEqual(got["periods"][1]["grades"][2]["change_pct"], round((63.45 / 64.0 - 1) * 100, 2))

    def test_a_later_run_stops_at_the_decision_it_already_has(self):
        get, calls = self.site({1: [("2026kmesdm401k", self.hba), ("2026kmesdm384k", self.hba)], 2: [("2026kmesdm364k", self.hba)]})
        first = m.fetch_hba(None, get=get, extract=self.extract, pause=0, max_pages=4)
        calls.clear()
        again = m.fetch_hba(first, get=get, extract=self.extract, pause=0, max_pages=4)
        self.assertEqual(calls, [self.LIST])           # nothing new on page 1 -> one request, no PDF
        self.assertEqual(again["periods"], first["periods"])

    def test_history_accumulates_beyond_what_the_list_still_shows(self):
        old = {"periods": [{"start": "2026-08-01", "end": "2026-08-14", "url": "press", "grades": []}]}
        get, _ = self.site({1: [("2026kmesdm384k", self.hba)]})
        got = m.fetch_hba(old, get=get, extract=self.extract, pause=0, max_pages=1)
        self.assertEqual([p["start"] for p in got["periods"]], ["2026-08-01", "2026-10-01"])

    def test_an_unreadable_decision_is_skipped_and_named(self):
        self.texts["2026kmesdm364k.pdf"] = "scan without a text layer"
        get, _ = self.site({1: [("2026kmesdm384k", self.hba), ("2026kmesdm364k", self.hba)]})
        got = m.fetch_hba(None, get=get, extract=self.extract, pause=0, max_pages=1)
        self.assertEqual(len(got["periods"]), 1)
        self.assertTrue(any("2026kmesdm364k" in s for s in got["skipped"]))

    def test_nothing_found_is_an_error_not_an_empty_success(self):
        get, _ = self.site({1: [("other", "Keputusan Menteri tentang Peta Jabatan")]})
        with self.assertRaises(m.SourceError) as e:
            m.fetch_hba(None, get=get, extract=self.extract, pause=0, max_pages=1)
        self.assertEqual(str(e.exception), "no_decisions_found")


class WorldBankTests(unittest.TestCase):
    def test_xlsx_roundtrip_keeps_row_positions(self):
        rows = m.read_xlsx_sheet(make_xlsx(pink_sheet()), "monthly prices")   # sheet names match any case
        self.assertEqual(rows[3][2], "Coal, Australian")
        self.assertEqual(rows[6][2], 138.5)
        self.assertEqual(rows[2], [])

    def test_footnote_marks_on_a_column_title_are_ignored(self):
        sheets = pink_sheet()
        sheets["Monthly Prices"][3] = ["", "Crude oil, average", "Coal, Australian *", "Coal, South African **"]
        sheets["Description"] = [["Coal, South African **", "f.o.b. Richards Bay"]]
        got = m.parse_worldbank_monthly(m.read_xlsx_sheet(make_xlsx(sheets), "Monthly Prices"))
        self.assertEqual([s["id"] for s in got["series"]], ["coal_australian", "coal_south_african"])
        self.assertEqual(m.worldbank_definitions(make_xlsx(sheets)), {"coal_south_african": "f.o.b. Richards Bay"})

    def test_coal_series(self):
        got = m.parse_worldbank_monthly(m.read_xlsx_sheet(make_xlsx(pink_sheet()), "Monthly Prices"))
        aus = next(s for s in got["series"] if s["id"] == "coal_australian")
        sa = next(s for s in got["series"] if s["id"] == "coal_south_african")
        self.assertEqual(aus["points"], [["1960-01", 12.5], ["2026-06", 138.5], ["2026-08", 140.25]])   # July's gap is absent, not 0
        self.assertEqual(sa["points"][-1], ["2026-08", 98.0])
        self.assertEqual(aus["source_name"], "Coal, Australian")
        self.assertEqual(aus["unit"], "$/mt")

    def test_the_workbooks_own_definition_is_kept_verbatim(self):
        sheets = pink_sheet()
        sheets["Description"] = [["Commodity", "Definition"], ["Coal, Australian", "Thermal, f.o.b. Newcastle"], ["Coal, South African", None, "f.o.b. Richards Bay"], ["Crude oil", "x"]]
        defs = m.worldbank_definitions(make_xlsx(sheets))
        self.assertEqual(defs, {"coal_australian": "Thermal, f.o.b. Newcastle", "coal_south_african": "f.o.b. Richards Bay"})
        self.assertEqual(m.worldbank_definitions(make_xlsx(pink_sheet())), {})     # no sheet, no definition invented

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
