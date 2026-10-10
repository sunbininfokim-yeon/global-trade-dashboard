import csv
import io
import json
import unittest
from pathlib import Path
from build_sanctions import screen, validity, build, REQUIRED, REQUIRED_LISTS

class SanctionsTests(unittest.TestCase):
    def row(self, **extra):
        return {'_id':'123','name':'Example Bank Ltd.','alt_names':'Example Bank','addresses':'Tokyo, JP','source':'Specially Designated Nationals (SDN) - Treasury Department', 'start_date':'','end_date':'',**extra}
    def company(self, **extra):
        return {'id':'jp-bank','screen_names':['Example Bank Ltd.'],'address_country':'JP',**extra}
    def test_exact_name_country_and_no_group_spreading(self):
        self.assertEqual(screen(self.company(),[self.row()],'2026-10-10')['status'],'listed_in_snapshot')
        self.assertEqual(screen(self.company(),[self.row(name='Example Bank Ltd. Subsidiary')],'2026-10-10')['status'],'no_exact_match')
        self.assertEqual(screen(self.company(),[self.row(addresses='Beijing, CN')],'2026-10-10')['status'],'identity_review')
    def test_alias_requires_country_and_dedup_uses_source_plus_id(self):
        a=self.row(name='Official Legal Name')
        c=self.company(screen_names=['Example Bank'])
        out=screen(c,[a,a,self.row(source='Sectoral Sanctions Identifications List (SSI) - Treasury Department')],'2026-10-10')
        self.assertEqual(len(out['matches']),2)
        self.assertEqual({m['restriction_kind'] for m in out['matches']},{'blocking','sectoral'})
    def test_dates_do_not_make_expired_orders_current(self):
        self.assertEqual(validity(self.row(end_date='2026-10-01'),'2026-10-10'),'expired_or_ends_today')
        self.assertEqual(validity(self.row(start_date='2027-01-01'),'2026-10-10'),'future')
        self.assertEqual(validity(self.row(end_date='unknown'),'2026-10-10'),'date_review')
    def test_incomplete_files_fail_before_output(self):
        for raw in [b'bad\nhtml',(','.join(REQUIRED)+'\n').encode()]:
            with self.assertRaises(ValueError):build(raw,'2026-10-10',[],[])
        rows=[self.row() for _ in range(1001)]
        f=io.StringIO();w=csv.DictWriter(f,fieldnames=sorted(set(REQUIRED)|{'source'}));w.writeheader()
        for r in rows:w.writerow({k:r.get(k,'') for k in w.fieldnames})
        with self.assertRaises(ValueError):build(f.getvalue().encode(),'2026-10-10',[],[])
    def test_snapshot_is_four_countries_and_not_top100_or_clean_bill(self):
        p=Path(__file__).resolve().parents[2]/'New for anti/public/data/trade_policy/us_sanctions_v1.json'
        d=json.loads(p.read_text())
        self.assertEqual(d['receipt']['row_count'],26113)
        self.assertEqual(len(d['companies']),40)
        self.assertEqual(sum(c['status']=='listed_in_snapshot' for c in d['companies']),14)
        for iso in ['RUS','CHN','KOR','JPN']:self.assertEqual(sum(c['country']==iso for c in d['companies']),10)
        ids={m['id'] for m in d['measures']}
        for m in d['measures']:self.assertTrue(set(m.get('related_measure_ids',[]))<=ids)
        self.assertNotIn('clear',{c['status'] for c in d['companies']})
        self.assertEqual(next(c for c in d['companies'] if c['id']=='chn-cnooc')['matches'][0]['restriction_kind'],'securities')
if __name__=='__main__':unittest.main()
