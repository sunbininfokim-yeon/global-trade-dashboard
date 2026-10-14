"""Later state reviews validate current catalogs, never rewrite old receipts."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from election_watch.review_clock import validation_day
from election_watch.polls import read
from election_watch.state_inputs import packets
import publish_packet_projections as projection
import publish_state_packets as replay

class CatalogClockTests(unittest.TestCase):
    def test_actual_future_review_still_rejected(self):
        with self.assertRaisesRegex(ValueError,'future catalog review'):
            validation_day('2026-10-09',{'reviewed_on':'2026-10-14'},today='2026-10-13')

    def test_projection_validates_new_catalog_without_advancing_old_state_clock(self):
        board={'as_of':'2026-10-10','races':{'USA:CT:house:01':{'state':'CT','as_of':'2026-10-09','fetched_at':'2026-10-09T12:00:00Z'}}}
        before=deepcopy(board)
        def load(path):
            return board if path.name=='usa_election_live_polls_v1.json' else {'races':{'new':{'reviewed_on':'2026-10-13'}}}
        with patch.object(projection,'read',side_effect=load),patch.object(projection,'packets',return_value=[{'state':'CT'}]), \
             patch.object(projection,'publish') as publish,patch.object(projection.subprocess,'run') as run, \
             patch('sys.argv',['projection']):
            projection.main()
        self.assertEqual(publish.call_args.args[2],'2026-10-13')
        args=run.call_args.args[0]
        self.assertEqual(args[args.index('--as-of')+1],'2026-10-10')
        self.assertEqual(board,before)

    def test_old_state_replay_accepts_later_other_state_review_and_keeps_receipt(self):
        public=Path(replay.ROOT).parents[1]/'public/data'
        board=read(public/'usa_election_live_polls_v1.json');history=read(public/'usa_election_poll_history_2026.json')
        packet=next(p for p in packets() if p['state']=='CT')
        def load(path):
            value=read(path)
            if path.name=='ballot_reviews_2026.json':
                value=deepcopy(value);value['races']['USA:ME:senate']['reviewed_on']='2026-10-13'
            return value
        with patch.object(replay,'read',side_effect=load):
            output,_=replay.rebuild(board,history,[packet],public)
        self.assertEqual(output['state_captures']['CT']['captured_at'],packet['capture']['fetched_at'])
        self.assertEqual(output['as_of'],board['as_of'])
        self.assertEqual(output['races']['USA:ME:senate'],board['races']['USA:ME:senate'])

if __name__=='__main__':unittest.main()
