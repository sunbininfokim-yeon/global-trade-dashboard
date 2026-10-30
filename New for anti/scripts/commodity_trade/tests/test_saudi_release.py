import copy
import sys
import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sources import saudi_gastat_bulletin as bulletin
from sources.jodi_oil import PREFERRED_UNITS
from series_quality import unit_class
from repair_monthly_units import repair
from build_monthly import _validate_monthly_contract
import build_saudi_bulletin
from validate_release import validate_bulletin


class BulletinTests(unittest.TestCase):
    def cells(self):
        return {'A3': 'Goods exports, monthly, value in SAR million', 'H5':'Oil exports',
                'P4':'Total exports', 'A10':'2026*', 'C10':'June', 'H10':'60', 'P10':'100',
                'A11':'2026*', 'C11':'Q2', 'H11':'180', 'P11':'300'}

    def test_monthly_only_and_scope(self):
        with patch.object(bulletin, 'worksheet_cells', return_value=self.cells()):
            points = bulletin.parse_bulletin(b'', '2026-06')
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]['share_of_total_goods_export_value'], .6)
        self.assertTrue(points[0]['preliminary'])
        self.assertEqual(points[0]['unit'], 'SAR_million')

    def test_changed_headers_missing_values_and_bad_units_block(self):
        for key, value in [('H5','Crude tonnes'), ('H10','-'), ('H10','nan'), ('H10','101')]:
            cells = self.cells(); cells[key] = value
            with patch.object(bulletin, 'worksheet_cells', return_value=cells), self.assertRaises(ValueError):
                bulletin.parse_bulletin(b'', '2026-06')

    def test_month_mismatch_and_duplicates_block(self):
        with patch.object(bulletin, 'worksheet_cells', return_value=self.cells()), self.assertRaises(ValueError):
            bulletin.parse_bulletin(b'', '2026-07')
        cells = self.cells(); cells['C11'] = 'June'
        with patch.object(bulletin, 'worksheet_cells', return_value=cells), self.assertRaises(ValueError):
            bulletin.parse_bulletin(b'', '2026-06')

    def test_discovery_chooses_latest_and_requires_official_source(self):
        html = '<a href="/en/w/international-trade-in-goods-may-2026">May</a><a href="/ar/w/international-trade-in-goods-june-2026?q=1">June</a>'
        self.assertEqual(bulletin.discover_publication(html)[0], '2026-06')
        for html in ('<html>not found</html>', '<a href="https://evil.example/en/w/international-trade-in-goods-june-2026">x</a>'):
            with self.assertRaises(ValueError):
                bulletin.discover_publication(html)
        with self.assertRaises(ValueError):
            bulletin.discover_workbook('<a href="/one.xlsx/x">x</a>', 'https://stats.gov.sa/')

    def test_failed_refresh_preserves_public_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'public.json'
            output.write_text('{"existing":true}')
            with patch.object(sys,'argv',['build_saudi_bulletin.py','--out',str(output)]), patch.object(
                    build_saudi_bulletin,'fetch',side_effect=OSError('unavailable')):
                self.assertEqual(build_saudi_bulletin.main(),2)
            self.assertEqual(output.read_text(),'{"existing":true}')

    def test_regressed_source_preserves_public_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'source.xlsx'; source.write_bytes(b'fixture')
            output = Path(tmp)/'public.json'
            output.write_text('{"latest_available_month":"2026-07"}')
            with patch.object(sys,'argv',['build_saudi_bulletin.py','--out',str(output),
                    '--input-xlsx',str(source),'--month','2026-06','--source-url','https://stats.gov.sa/test']), patch.object(
                    bulletin,'worksheet_cells',return_value=self.cells()):
                self.assertEqual(build_saudi_bulletin.main(),2)
            self.assertEqual(json.loads(output.read_text())['latest_available_month'],'2026-07')

    def test_release_rejects_crude_or_bilateral_mislabel(self):
        base = {'schema_version':'commodity-trade-saudi-bulletin-v1','reporter_iso3':'SAU',
                'series_id':'oil_exports_aggregate_value','flow':'X','partner':'WORLD',
                'hs':None,'quantity_available':False,'bilateral_available':False,'latest_available_month':'2026-06'}
        with patch.object(bulletin,'worksheet_cells',return_value=self.cells()):
            base['points'] = bulletin.parse_bulletin(b'', '2026-06')
        validate_bulletin(base)
        for key,value in [('hs','2709'),('quantity_available',True),('bilateral_available',True)]:
            bad = copy.deepcopy(base); bad[key] = value
            with self.assertRaises(ValueError):
                validate_bulletin(bad)


class RepairTests(unittest.TestCase):
    def fixture(self):
        return {'calendar_month_now':'2026-08','sectors': {'energy': {'commodities': {'crude_oil': {
            'countries': {
                'SAU': {'points': [{'month':'2026-01','value':2,'unit':'KTONS','normalized':{'value':2000,'unit':'kg'}}]},
                'USA': {'points': [{'month':'2026-01','value':7,'unit':'CONVBBL'}]},
            }, 'country_count':2}}}}}

    def test_factor_exclusion_and_raw_preservation_idempotent(self):
        old = self.fixture(); snapshot = copy.deepcopy(old)
        new, counts = repair(old)
        c = new['sectors']['energy']['commodities']['crude_oil']
        self.assertEqual(old, snapshot)
        self.assertEqual(counts, {'conversion_factors_excluded':1,'ktons_normalizations_corrected':1})
        p = c['countries']['SAU']['points'][0]
        self.assertEqual((p['value'],p['unit'],p['normalized']['value']), (2,'KTONS',2_000_000))
        self.assertEqual(c['country_count'],1)
        self.assertEqual(c['unavailable_countries']['USA']['excluded_conversion_factors'][0]['value'],7)
        self.assertEqual(repair(new)[0],new)
        _validate_monthly_contract(new,{})

    def test_legacy_file_is_blocked_and_factor_is_not_volume(self):
        with self.assertRaises(ValueError):
            _validate_monthly_contract(self.fixture(),{})
        self.assertNotIn('CONVBBL',PREFERRED_UNITS)
        self.assertEqual(unit_class('CONVBBL'),'conversion_factor')


if __name__ == '__main__':
    unittest.main()
