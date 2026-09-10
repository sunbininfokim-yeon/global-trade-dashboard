import unittest
from election_watch.districts import normalize_house, district_code

class DistrictTests(unittest.TestCase):
    def test_same_cycle_unique_master_and_money_preserved(self):
        row = dict(candidate_id='H2NC06098', office='house', state='ND', district='04', election_type='P2026', support_cents=29850, records=1)
        master = [dict(candidate_id='H2NC06098', office='H', state='NC', district='04', election_year=2026)]
        result, _ = normalize_house([row], master, {('NC','04'): {}}, 2026)
        self.assertEqual((result[0]['state'], result[0]['district']), ('NC','04'))
        self.assertEqual(result[0]['support_cents'], row['support_cents'])
        self.assertEqual(row['state'], 'ND')
        self.assertEqual(result[0]['district_source']['reported_state'], 'ND')
        for phase in ('UNKNOWN','G2024'):
            result, _ = normalize_house([dict(row,election_type=phase)], master, {('NC','04'): {}}, 2026)
            self.assertEqual(result[0]['state'], 'ND')
        duplicate = dict(master[0],district='01')
        result, _ = normalize_house([row],master+[duplicate],{('NC','04'): {},('NC','01'): {}},2026)
        self.assertEqual(result[0]['state'],'ND')

    def test_at_large_delegate_missing_and_bad_registration(self):
        geometry = {('AK','00'): {},('DC','98'): {},('FL','01'): {}}
        roster = [dict(candidate_id='x',office='H',state=s,district=d,election_year=2026) for s,d in [('AK','01'),('DC','00'),('FL','59'),('FL','')]]
        _, result = normalize_house([],roster,geometry,2026)
        self.assertEqual([r['district'] for r in result],['00','98','59','UNKNOWN'])
        self.assertEqual(result[2]['district_source']['status'],'invalid_fec_registration_district')
        self.assertEqual(result[3]['district_source']['status'],'missing_district')
        self.assertEqual(district_code(None),'UNKNOWN')
