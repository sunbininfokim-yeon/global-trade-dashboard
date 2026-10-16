"""Product-scope contracts only: no keys, network or published synthetic data."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from priority_universe import PRIORITY_COMMODITIES, PRIORITY_REPORTERS
from hs_match import COMMODITY_HS_STEMS, resolve_commodity_id
from sources.comtrade import fetch_preview_month
from sources.brazil_comexstat import _aggregate_file
from build_comtrade_priority_monthly import _ensure_reporter
from build_national_priority_monthly import _ensure_reporter as ensure_national
from build_bilateral import plan_jobs
from build_monthly import MINERAL_IDS, align_sector_to_board, build_minerals

PRODUCTS = {'manganese': '2602', 'uranium': '284410', 'uranium_ore': '261210'}


class ProductScopeTests(unittest.TestCase):
    def test_universe_exact_hs_scopes_and_existing_country_batches_unchanged(self):
        for cid, hs in PRODUCTS.items():
            self.assertEqual(PRIORITY_COMMODITIES[cid]['hs'], hs)
            self.assertEqual(COMMODITY_HS_STEMS[cid], [hs])
        self.assertEqual(len(PRIORITY_REPORTERS), 27)
        self.assertIn('manganese', MINERAL_IDS)

    def test_hs_resolution_never_widens_to_parent_or_sibling(self):
        for cid, hs in PRODUCTS.items():
            for code in (cid, hs, hs + '00'):
                self.assertEqual(resolve_commodity_id(code), cid)
        for code in ('2844', '284420', '284430', '2612', '261220', '720211', '720219'):
            self.assertIsNone(resolve_commodity_id(code), code)

    def test_both_panel_builders_create_empty_not_zero_shells(self):
        for ensure in (_ensure_reporter, ensure_national):
            doc = {'reporters': {}}
            reporter = ensure(doc, 'CAN')
            for direction in ('exports', 'imports'):
                for cid, hs in PRODUCTS.items():
                    item = reporter['flows'][direction]['commodities'][cid]
                    self.assertEqual(item['hs'], hs)
                    self.assertEqual(item['points'], [])

    def test_bilateral_plan_keeps_products_and_flows_separate(self):
        jobs = plan_jobs(['CAN'], list(PRODUCTS.values()), ['202606'])
        self.assertEqual(len(jobs), 6)
        self.assertEqual(len({j['id'] for j in jobs}), 6)
        self.assertEqual({j['meta']['hs'] for j in jobs}, set(PRODUCTS.values()))

    def test_preview_filters_unrequested_codes_and_retains_explicit_zero(self):
        rows = [{'period': '202606', 'cmdCode': hs, 'netWgt': 0, 'primaryValue': 0}
                for hs in [*PRODUCTS.values(), '720211', '2844', '284420', '2612', '261220']]
        response = MagicMock()
        response.__enter__.return_value = io.StringIO(json.dumps({'data': rows}))
        with tempfile.TemporaryDirectory() as directory, patch('sources.comtrade.urlopen', return_value=response):
            got = fetch_preview_month(hs_codes=list(PRODUCTS.values()), reporter_m49='124',
                                      period='202606', flow='X', cache_dir=Path(directory))
        self.assertEqual(set(got['series_by_hs']), set(PRODUCTS.values()))
        for points in got['series_by_hs'].values():
            self.assertEqual(len(points), 1)
            self.assertEqual(points[0]['value'], 0)
            self.assertEqual(points[0]['unit'], 'kg')

    def test_brazil_ore_does_not_absorb_ferromanganese(self):
        csv = 'CO_ANO;CO_MES;CO_NCM;KG_LIQUIDO\n2026;06;26020010;12\n2026;06;72021100;999\n'
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'fixture.csv'
            file.write_text(csv)
            got = _aggregate_file(file)
        self.assertEqual(dict(got['manganese']), {'2026-06': 12})

    def test_brazil_manganese_survives_builder_and_legacy_board_alignment(self):
        bra = {'series': {'manganese': {'BRA': [{'month': '2026-06', 'value': 12, 'unit': 'kg', 'hs_bridge': '2602'}]}}}
        with patch('build_monthly.brazil_comexstat.load_mineral_exports', return_value=bra), \
             patch('build_monthly.cochilco_copper.load_copper_exports', return_value={}), \
             patch('build_monthly.abs_metal_ore.load_iron_ore_proxy', return_value={}):
            out = build_minerals(Path('/unused'))
        board = {'sectors': [{'id': 'minerals', 'commodities': ['iron_ore']}]}
        aligned = align_sector_to_board('minerals', out, board)
        self.assertEqual(aligned['supplemental_commodities']['manganese']['hs_stems'], ['2602'])
        self.assertEqual(aligned['supplemental_commodities']['manganese']['countries']['BRA']['points'][0]['value'], 12)


if __name__ == '__main__':
    unittest.main()
