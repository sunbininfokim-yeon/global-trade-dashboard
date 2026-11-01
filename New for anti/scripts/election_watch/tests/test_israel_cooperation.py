import copy
import json
import unittest
from pathlib import Path
from election_watch.israel_cooperation import validate_cooperation
ROOT=Path(__file__).resolve().parents[1]
DATA=json.loads((ROOT/'tests/fixtures/israel/2026-10-31/cooperation_review.json').read_text())
KNOWN={p['list_id'] for p in DATA['profiles']}

class CooperationTests(unittest.TestCase):
    def test_profiles_and_sources_are_scoped(self):
        validate_cooperation(DATA,KNOWN)
        self.assertEqual(len(DATA['profiles']),11)
        joint=next(p for p in DATA['profiles'] if p['list_id']=='k26:ודם')
        self.assertEqual({c['id'] for c in joint['components']},{'hadash','taal','balad'})
        self.assertTrue(all(c['seats'] is None for c in joint['components']))
    def test_unsupported_claims_do_not_publish(self):
        changes=[lambda d:d['relations'][0].update(kind='coalition_formed'),lambda d:d['relations'][0].update(source_ids=['ap-held']),lambda d:d['profiles'][-1]['components'][0].update(seats=4),lambda d:d['profiles'][0].update(spectrum=0.8),lambda d:d['relations'][0].update(event_date='2026-09-26'),lambda d:d['relations'][0].update(parties=['unknown','k26:עם'])]
        for change in changes:
            d=copy.deepcopy(DATA);change(d)
            with self.assertRaises(ValueError):validate_cooperation(d,KNOWN)
