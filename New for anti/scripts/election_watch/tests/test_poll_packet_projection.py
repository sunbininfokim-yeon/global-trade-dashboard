"""Projection clock is independent of preserved original collection receipts."""
import unittest
from unittest.mock import patch
import publish_packet_projections as projection

class ProjectionClockTests(unittest.TestCase):
    def check(self, national, state, expected):
        board={'as_of':national,'races':{'USA:AK:senate':{'state':'AK','as_of':state}}}
        with patch.object(projection,'read',return_value=board), \
             patch.object(projection,'packets',return_value=[{'state':'AK'}]), \
             patch.object(projection,'publish') as publish, \
             patch.object(projection.subprocess,'run') as run, \
             patch('sys.argv',['publish_packet_projections.py']):
            projection.main()
        self.assertEqual(publish.call_args.args[2],expected)
        args=run.call_args.args[0]
        self.assertEqual(args[args.index('--as-of')+1],expected)
        self.assertEqual(board['races']['USA:AK:senate']['as_of'],state)

    def test_older_packet_uses_national_validation_date_without_changing_receipt(self):
        self.check('2026-10-11','2026-10-09','2026-10-11')

    def test_newer_state_uses_its_own_validation_date(self):
        self.check('2026-10-08','2026-10-09','2026-10-09')

if __name__=='__main__':unittest.main()
