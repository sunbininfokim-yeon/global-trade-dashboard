from copy import deepcopy
import json
from pathlib import Path
import unittest
from election_watch.federal_poll_ballots import link_house_ballots
from election_watch.poll_targets import competition

ROOT=Path(__file__).resolve().parents[1]


class FederalPollLinkTests(unittest.TestCase):
    def setUp(self):
        self.federal=json.loads((ROOT/'config/federal_matchups/2026.json').read_text())
        self.ballots=json.loads((ROOT/'config/usa_polls/ballot_reviews_2026.json').read_text())

    def test_missing_state_rosters_connect_without_fec_registrants_or_review_date_changes(self):
        rid='USA:GA:house:01';self.ballots['races'].pop(rid,None)
        self.federal['races'][rid]['unconfirmed_candidates']=[{'name':'Unconfirmed Registrant','party':'REP'}]
        original=deepcopy(self.ballots)
        linked,added=link_house_ballots(self.ballots,self.federal,'GA','2026-10-08')
        self.assertEqual(self.ballots,original);self.assertIn(rid,added)
        self.assertEqual(linked['races'][rid]['candidates'],self.federal['races'][rid]['candidates'])
        self.assertEqual(linked['races'][rid]['reviewed_on'],self.federal['races'][rid]['reviewed_on'])
        self.assertEqual(linked['races'][rid]['source_role'],'reviewed_secondary_nominee_listing')
        self.assertNotIn('Unconfirmed Registrant',[c['name'] for c in linked['races'][rid]['candidates']])
        self.assertTrue(all(':GA:house:' in rid for rid in added))

    def test_existing_agency_review_and_verified_alias_are_preserved(self):
        rid='USA:TN:house:09';original=deepcopy(self.ballots['races'][rid])
        linked,added=link_house_ballots(self.ballots,self.federal,'TN','2026-10-08')
        self.assertEqual(linked['races'][rid],original);self.assertNotIn(rid,added)
        rid='USA:CA:house:01';original=deepcopy(self.ballots['races'][rid])
        linked,_=link_house_ballots(self.ballots,self.federal,'CA','2026-10-08')
        self.assertEqual(linked['races'][rid],original)

    def test_official_exclusions_and_rich_roster_metadata_survive_linking(self):
        rid='USA:MI:house:01';self.ballots['races'].pop(rid,None)
        linked,_=link_house_ballots(self.ballots,self.federal,'MI','2026-10-08')
        self.assertEqual(linked['races'][rid],self.federal['races'][rid])
        self.assertIn('excluded_candidates',linked['races'][rid])

    def test_single_secondary_name_does_not_become_unopposed_or_confirmed_winner(self):
        rid='USA:GA:house:01';self.ballots['races'].pop(rid,None)
        self.federal['races'][rid]['candidates']=self.federal['races'][rid]['candidates'][:1]
        self.federal['races'][rid]['absent_parties']=['REP']
        linked,_=link_house_ballots(self.ballots,self.federal,'GA','2026-10-08')
        result=competition(linked['races'][rid])
        self.assertIsNone(result['general_unopposed']);self.assertFalse(result['confirmed_winner'])

    def test_incomplete_or_future_rosters_cannot_admit_new_targets(self):
        for change in ('missing','future','invalid_state'):
            federal=deepcopy(self.federal);state='GA'
            if change=='missing':del federal['races']['USA:GA:house:01']
            elif change=='future':federal['reviewed_on']='2026-10-09'
            else:state='XX'
            with self.assertRaises(ValueError):link_house_ballots(self.ballots,federal,state,'2026-10-08')

    def test_louisiana_multiple_same_party_candidates_remain_a_full_field(self):
        rid='USA:LA:house:01';self.ballots['races'].pop(rid,None)
        linked,_=link_house_ballots(self.ballots,self.federal,'LA','2026-10-08')
        row=linked['races'][rid]
        self.assertEqual(row['election_system'],'all_party_general_with_majority_runoff')
        self.assertGreater(sum(c['party']=='REP' for c in row['candidates']),1)


if __name__=='__main__':unittest.main()
