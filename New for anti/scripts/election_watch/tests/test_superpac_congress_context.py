import unittest
from election_watch.congress_context import house_context, swing_seats

class CongressTests(unittest.TestCase):
    def test_history_requires_comparable_geography_and_evidence(self):
        seat={'chamber':'house','state':'AK','district':'00','geography_comparable':True,'elections':[{'year':y,'party_abbr':p} for y,p in [(2020,'GOP'),(2022,'DEM'),(2024,'GOP')]]}
        self.assertEqual(len(swing_seats({'seats':[seat]})),1)
        self.assertEqual(swing_seats({'seats':[dict(seat,geography_comparable=False)]}),[])
        self.assertEqual(swing_seats({'seats':[dict(seat,elections=seat['elections'][-2:])]}),[])
    def test_roster_incomplete_fails_closed(self):
        with self.assertRaises(ValueError):house_context('<MemberData publish-date="September 2, 2026"><members/></MemberData>','')
