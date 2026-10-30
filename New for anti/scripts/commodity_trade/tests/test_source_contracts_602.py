"""Synthetic regression fixtures for #602 B01-B07; never published data."""
from __future__ import annotations

import io
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sources import usa_ers_agri as ers, jodi_oil as jodi, norway_ssb as ssb
from sources import korea_customs as korea, brazil_comexstat as brazil
from series_quality import annotate_point, annotate_monthly_payload
from world_link import link_country_world, to_kg
from build_monthly import build_energy, build_minerals, align_sector_to_board
from repair_source_scopes import repair
from validate_release import validate_source_scopes
from reconcile_source_contracts import reconcile


class Sheet:
    title = 'Aug. update of Jun. data'
    def __init__(self, current=None, previous=99, year=2026):
        self.current, self.previous, self.year = current, previous, year
    def __getitem__(self, row):
        values = [None,None,None,'June',None] if row == 2 else [None,None,None,2025,self.year]
        return [SimpleNamespace(value=v) for v in values]
    def iter_rows(self, **kw):
        return iter([('Corn',None,None,None,None),('World total',None,None,self.previous,self.current)])


class ErsCurrentColumnTests(unittest.TestCase):
    def test_current_missing_never_uses_comparison_year(self):
        self.assertEqual(ers._parse_sheet(Sheet()), [])
    def test_current_zero_is_not_missing(self):
        p = ers._parse_sheet(Sheet(current=0))[0]
        self.assertEqual((p['month'],p['value']), ('2026-06',0))
    def test_comparison_year_header_never_labels_current_column(self):
        self.assertEqual(ers._parse_sheet(Sheet(current=12,year=None)), [])
    def test_current_observation_is_unchanged(self):
        self.assertEqual(ers._parse_sheet(Sheet(current=12))[0]['value'],12)
    def test_nonfinite_negative_and_boolean_are_not_volumes(self):
        for value in (float('nan'),float('inf'),-1,True):
            self.assertEqual(ers._parse_sheet(Sheet(current=value)),[],value)
    def test_title_fallback_still_does_not_borrow_comparison_values(self):
        class HeaderlessSheet(Sheet):
            def __getitem__(self,row):
                return [SimpleNamespace(value=None) for _ in range(5)] if row==2 else super().__getitem__(row)
        sheet=HeaderlessSheet()
        class Book:
            sheetnames=[sheet.title]
            def __getitem__(self,name): return sheet
        with patch.object(ers,'fetch',return_value=Path('/unused.xlsx')),patch.object(ers,'load_workbook',return_value=Book()):
            self.assertFalse(ers.load_us_agri_exports(cache_dir=Path('/unused'))['available'])


class JodiProductTests(unittest.TestCase):
    def load(self, rows):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)/'fixture.csv'
            p.write_text('FLOW_BREAKDOWN,ENERGY_PRODUCT,UNIT_MEASURE,OBS_VALUE,REF_AREA,TIME_PERIOD\n'+
                         ''.join(f'TOTEXPSB,{prod},{unit},{value},US,2026-06\n' for prod,unit,value in rows))
            with patch.object(jodi,'_fetch',return_value=p):
                return jodi.load_export_series(cache_dir=Path(temp),years=[2026])
    def test_distinct_products_survive_without_a_fabricated_total(self):
        r=self.load([('GASDIES','KTONS',10),('MOTORGAS','KTONS',20)])['series']
        self.assertNotIn('petroleum_products',r)
        self.assertEqual(r['gasoil_diesel']['US'][0]['value'],10)
        self.assertEqual(r['motor_gasoline']['US'][0]['value'],20)
    def test_only_explicit_totprods_supplies_total(self):
        r=self.load([('GASDIES','KTONS',10),('TOTPRODS','KTONS',100)])['series']
        p=r['petroleum_products']['US'][0]
        self.assertEqual(p['value'],100)
        self.assertEqual(p['comparison_scope'],'JODI:TOTPRODS')
        self.assertIsNone(p['hs_bridge'])
    def test_totcrude_is_crude_ngl_other_not_hs2709_crude(self):
        r=self.load([('CRUDEOIL','KTONS',10),('TOTCRUDE','KTONS',20)])['series']
        self.assertEqual(r['crude_oil']['US'][0]['value'],10)
        self.assertEqual(r['crude_ngl_other']['US'][0]['value'],20)
        self.assertIsNone(r['crude_ngl_other']['US'][0]['hs_bridge'])
    def test_zero_and_unit_preference_stay_within_product(self):
        r=self.load([('GASDIES','KBBL',90),('GASDIES','KTONS',0),('LPG','KTONS',8)])['series']
        self.assertEqual(r['gasoil_diesel']['US'][0]['value'],0)
        self.assertEqual(r['lpg']['US'][0]['value'],8)
    def test_primary_secondary_2025_have_distinct_cache_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            legacy=Path(temp)/'2025.csv'
            legacy.write_bytes(b'ambiguous-legacy\n'*100)
            legacy.with_suffix('.csv.complete').write_text('complete')
            with patch.object(jodi,'urlopen',side_effect=lambda *a,**k:io.BytesIO(b'source-specific-data\n'*100)) as request:
                primary=jodi._fetch(jodi.PRIMARY_URLS[2025],Path(temp))
                secondary=jodi._fetch(jodi.SECONDARY_URLS[2025],Path(temp))
                again=jodi._fetch(jodi.SECONDARY_URLS[2025],Path(temp))
            self.assertNotEqual(primary,secondary)
            self.assertEqual(again,secondary)
            self.assertNotEqual(primary,legacy)
            self.assertEqual(request.call_count,2)
    def test_builder_preserves_subproducts_outside_board_contract(self):
        oil=self.load([('GASDIES','KTONS',10)])
        with patch('build_monthly.jodi_oil.load_export_series',return_value=oil), \
             patch('build_monthly.jodi_gas.load_lng_export_series',return_value={'available':False}):
            r=build_energy(Path('/unused'))
        board={'sectors':[{'id':'energy','commodities':['petroleum_products']}]}
        r=align_sector_to_board('energy',r,board)
        self.assertEqual(r['commodities']['petroleum_products']['countries'],{})
        self.assertEqual(r['supplemental_commodities']['gasoil_diesel']['countries']['USA']['points'][0]['value'],10)
    def test_conflicting_same_product_month_unit_fails(self):
        with self.assertRaisesRegex(ValueError,'conflicting JODI'):
            self.load([('GASDIES','KTONS',10),('GASDIES','KTONS',11)])
    def test_cache_digest_detects_equal_length_corruption(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(jodi,'urlopen',side_effect=lambda *a,**k:io.BytesIO(b'original-data')) as request:
                path=jodi._fetch(jodi.PRIMARY_URLS[2026],Path(temp))
                path.write_bytes(b'tampered-data')
                jodi._fetch(jodi.PRIMARY_URLS[2026],Path(temp))
            self.assertEqual(request.call_count,2)
            self.assertEqual(path.read_bytes(),b'original-data')
    def test_incomplete_transport_is_not_a_completed_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            response=io.BytesIO(b'x'*1200)
            response.headers={'Content-Length':'2400'}
            with patch.object(jodi,'urlopen',return_value=response):
                with self.assertRaisesRegex(OSError,'incomplete'):
                    jodi._fetch(jodi.PRIMARY_URLS[2026],Path(temp))
            self.assertEqual(list(Path(temp).glob('*.complete')),[])
            self.assertEqual(list(Path(temp).glob('*.csv')),[])


class SsbCompleteMetricTests(unittest.TestCase):
    lines=['26020010_2000','26020090_2000']
    def fetch(self, mass, money):
        metadata={'variables':[{'code':'Varekoder','values':self.lines,
            'valueTexts':['A (2000-) (Q1=kg)','B (2000-) (Q1=kg)']}]}
        rows=[({'Varekoder':line,'ContentsCode':metric},value)
              for metric,values in [('Mengde1',mass),('Verdi',money)]
              for line,value in zip(self.lines,values)]
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(ssb,'_load_metadata',return_value=(metadata,False,None)), \
             patch.object(ssb,'_fetch_json',return_value={}), \
             patch.object(ssb,'_dataset_values',return_value=rows):
            return ssb.fetch_monthly_hs_world(period='202606',flow='X',hs_codes=['2602'],cache_dir=Path(temp))
    def test_partial_mass_does_not_become_complete_total(self):
        r=self.fetch([10,None],[None,None])
        self.assertFalse(r['available'])
        self.assertEqual(r['series_by_hs']['2602'],[])
        self.assertEqual(r['diagnostics_by_hs']['2602']['partial_net_weight_kg'],10)
    def test_missing_money_is_null_not_zero(self):
        p=self.fetch([10,20],[None,None])['series_by_hs']['2602'][0]
        self.assertEqual(p['value'],30)
        self.assertIsNone(p['primary_value_nok'])
    def test_money_completeness_is_independent_from_mass(self):
        p=self.fetch([10,None],[20,30])['series_by_hs']['2602'][0]
        self.assertEqual((p['value'],p['unit']),(50,'NOK'))
        self.assertIsNone(p['net_weight_kg'])
        self.assertFalse(p['quality']['metric_completeness']['net_weight_kg']['complete'])
    def test_explicit_zero_is_complete(self):
        p=self.fetch([0,0],[0,0])['series_by_hs']['2602'][0]
        self.assertEqual((p['value'],p['primary_value_nok']),(0,0))
    def test_partial_money_does_not_understate_value(self):
        p=self.fetch([10,20],[100,None])['series_by_hs']['2602'][0]
        self.assertIsNone(p['primary_value_nok'])
    def test_nonkg_tariff_line_cannot_silently_disappear_from_hs_total(self):
        metadata={'variables':[{'code':'Varekoder','values':['27090001_2000','27090009_2000'],
            'valueTexts':['A (2000-) (Q1=kg)','B (2000-) (Q1=number)']}]}
        rows=[({'Varekoder':'27090001_2000','ContentsCode':'Mengde1'},10)]
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(ssb,'_load_metadata',return_value=(metadata,False,None)), \
             patch.object(ssb,'_fetch_json',return_value={}), \
             patch.object(ssb,'_dataset_values',return_value=rows):
            r=ssb.fetch_monthly_hs_world(period='202606',flow='X',hs_codes=['2709'],cache_dir=Path(temp))
        self.assertFalse(r['available'])
        self.assertEqual(r['diagnostics_by_hs']['2709']['unsupported_current_line_codes'],['27090009_2000'])


class KoreaIndependentMetricsTests(unittest.TestCase):
    def parse(self, weight='',usd='100'):
        xml=(f'<response><body><items><item><year>2026.06</year><hsCode>2602</hsCode>'
             f'<expWgt>{weight}</expWgt><expDlr>{usd}</expDlr></item></items></body></response>').encode()
        return korea.parse_itemtrade_xml(xml,period='202606',hs_code='2602')['X']
    def test_missing_weight_preserves_money(self):
        p=self.parse()[0]
        self.assertEqual((p['value'],p['unit']),(100,'usd'))
        self.assertIsNone(p['net_weight_kg'])
    def test_zero_money_and_weight_are_not_missing(self):
        self.assertEqual(self.parse(usd='0')[0]['value'],0)
        self.assertEqual(self.parse(weight='0')[0]['unit'],'kg')
    def test_both_missing_emit_no_observation(self):
        self.assertEqual(self.parse(usd=''),[])


class BrazilFormTests(unittest.TestCase):
    def aggregate(self, rows):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'fixture.csv'
            p.write_text('CO_ANO;CO_MES;CO_NCM;KG_LIQUIDO\n'+rows)
            return brazil._aggregate_file(p)
    def test_nickel_forms_are_never_summed_together(self):
        r=self.aggregate('2026;06;26040000;10\n2026;06;75021000;20\n2026;06;75011000;30\n')
        self.assertEqual(r['nickel']['2026-06'],10)
        self.assertEqual(r['nickel_unwrought']['2026-06'],20)
        self.assertEqual(r['nickel_mattes']['2026-06'],30)
    def test_missing_mass_invalidates_total_instead_of_zero_fill(self):
        r=self.aggregate('2026;06;26060000;10\n2026;06;26060000;\n')
        self.assertIsNone(r['bauxite']['2026-06'])
    def test_real_zero_is_preserved(self):
        self.assertEqual(self.aggregate('2026;06;26060000;0\n')['bauxite']['2026-06'],0)
    def test_invalid_mass_and_month_are_not_observations(self):
        for raw in ('nan','inf','-1'):
            self.assertIsNone(self.aggregate(f'2026;06;26060000;{raw}\n')['bauxite']['2026-06'])
        self.assertEqual(self.aggregate('2026;13;26060000;1\n'),{})
    def test_missing_mass_not_published_and_product_scope_is_exact(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'fixture.csv'
            p.write_text('CO_ANO;CO_MES;CO_NCM;KG_LIQUIDO\n2026;06;26040000;10\n2026;06;75021000;20\n2026;06;26060000;\n')
            with patch.object(brazil,'fetch_year_csv',return_value=p):
                r=brazil.load_mineral_exports(cache_dir=Path(temp),years=[2026])
        self.assertNotIn('bauxite',r['series'])
        self.assertEqual(len(r['incomplete_cells']),1)
        p=r['series']['nickel_unwrought']['BRA'][0]
        self.assertEqual((p['hs_bridge'],p['product_form']),('7502','unwrought_metal'))


class CopperMeasurementBasisTests(unittest.TestCase):
    def test_contained_copper_conversion_is_not_comparable_goods_mass(self):
        p={'month':'2026-06','value':1,'unit':'kMT_cu_content'}
        annotate_point(p)
        self.assertEqual(p['normalized']['value'],1e6)
        self.assertEqual(p['normalized']['comparison_class'],'contained_metal_kg')
        self.assertFalse(p['normalized']['comparable_across_reporters'])
    def test_mixed_copper_cannot_produce_5050_goods_shares(self):
        r=link_country_world('copper',{
            'CHL':{'points':[{'month':'2026-06','value':1,'unit':'kMT_cu_content'}]},
            'BRA':{'points':[{'month':'2026-06','value':1e6,'unit':'kg'}]}})
        self.assertNotIn('CHL',r['latest_contributor_shares'])
        self.assertEqual(r['partial_sum_series'][0]['value_kg'],1e6)
        self.assertTrue(any(e['from']=='CHL' and e['link_type']=='incomparable' for e in r['edges']))
    def test_commodity_policy_rejects_contained_mass(self):
        sectors={'minerals':{'commodities':{'copper':{'countries':{
            'CHL':{'points':[{'month':'2026-06','value':1,'unit':'kMT_cu_content'}]}}}}}}
        annotate_monthly_payload(sectors,'2026-06')
        self.assertEqual(sectors['minerals']['commodities']['copper']['comparison_policy']['cross_reporter_numeric_comparison'],'not_allowed')
    def test_same_goods_mass_still_has_exact_conversion(self):
        r=link_country_world('corn',{'BRA':{'points':[{'month':'2026-06','value':1000,'unit':'kg'}]},
                                   'USA':{'points':[{'month':'2026-06','value':1,'unit':'metric_tons'}]}})
        self.assertEqual(r['latest_contributor_shares'],{'BRA':0.5,'USA':0.5})
    def test_invalid_values_have_no_normalized_mass(self):
        for val in (True,-1,float('inf'),float('nan')):
            self.assertIsNone(to_kg(val,'kg'))


class StoredScopeRepairTests(unittest.TestCase):
    def payload(self):
        return {'generated_at':'2026-08-14T00:00:00Z','calendar_month_now':'2026-08',
            'sectors':{'energy':{'commodities':{'petroleum_products':{
                'commodity_id':'petroleum_products','countries':{'USA':{'retrieved_at':'2026-08-13T00:00:00Z',
                    'points':[{'month':'2026-06','value':10,'unit':'KTONS','source':'jodi_oil','product_code':'GASDIES'}]}}}}}}}
    def test_reclassification_keeps_value_unit_month_and_acquisition_time(self):
        before=self.payload()
        after,stats=repair(before)
        self.assertEqual(stats['reclassified_points'],1)
        c=after['sectors']['energy']['supplemental_commodities']['gasoil_diesel']['countries']['USA']
        self.assertEqual((c['points'][0]['value'],c['points'][0]['unit'],c['points'][0]['month']),(10,'KTONS','2026-06'))
        self.assertEqual(c['retrieved_at'],'2026-08-13T00:00:00Z')
        self.assertEqual(after['generated_at'],before['generated_at'])
        self.assertEqual(after['sectors']['energy']['commodities']['petroleum_products']['countries'],{})
        self.assertEqual(before,self.payload())
    def test_repair_is_idempotent(self):
        once,_=repair(self.payload())
        twice,stats=repair(once)
        self.assertEqual(once,twice)
        self.assertEqual(stats['reclassified_points'],0)
    def test_release_gate_rejects_legacy_misclassification(self):
        with self.assertRaisesRegex(ValueError,'misclassified'):
            validate_source_scopes(self.payload())
        repaired,_=repair(self.payload())
        self.assertEqual(validate_source_scopes(repaired),1)
    def test_conflicting_preexisting_supplement_is_not_overwritten(self):
        payload=self.payload()
        old=copy.deepcopy(payload['sectors']['energy']['commodities']['petroleum_products'])
        old['countries']['USA']['points'][0]['value']=11
        payload['sectors']['energy']['supplemental_commodities']={'gasoil_diesel':old}
        with self.assertRaisesRegex(ValueError,'conflicting'):
            repair(payload)


class SourceReconciliationTests(unittest.TestCase):
    payload = StoredScopeRepairTests.payload
    def compare(self,payload,raw_value):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'source.csv'
            p.write_text('REF_AREA,TIME_PERIOD,ENERGY_PRODUCT,FLOW_BREAKDOWN,UNIT_MEASURE,OBS_VALUE\n'
                         f'US,2026-06,GASDIES,TOTEXPSB,KTONS,{raw_value}\n')
            return reconcile(payload,jodi_files=[p])
    def test_native_value_match_is_distinct_from_wrong_product_bucket(self):
        before=self.compare(self.payload(),10)
        self.assertEqual(before['counts']['jodi_oil:native_value_matches'],1)
        self.assertEqual(before['counts']['jodi_oil:classification_mismatch'],1)
        corrected,_=repair(self.payload())
        self.assertNotIn('jodi_oil:classification_mismatch',self.compare(corrected,10)['counts'])
    def test_source_revision_is_not_automatically_a_historical_parser_error(self):
        r=self.compare(self.payload(),11)
        self.assertEqual(r['review_items'][0]['status'],'source_value_changed_requires_revision_review')
    def test_missing_source_observation_is_not_filled_with_zero(self):
        r=self.compare(self.payload(),'')
        self.assertIsNone(r['review_items'][0]['current_source_value'])
        self.assertEqual(r['review_items'][0]['status'],'source_observation_not_present')


if __name__=='__main__':
    unittest.main()
