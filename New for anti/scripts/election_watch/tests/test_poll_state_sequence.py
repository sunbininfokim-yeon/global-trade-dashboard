import json
from pathlib import Path
import tempfile
import unittest
from election_watch.state_sequence import state_range,run_sequence

ROOT=Path(__file__).resolve().parents[1]
DAY='2026-10-08'


class StateSequenceTests(unittest.TestCase):
    def setUp(self):
        self.plan=json.loads((ROOT/'config/usa_polls/state_evidence_plan_2026.json').read_text())

    def row(self,state,group):
        return {'state':state,'group':group,'status':'poll_transport_updated_partial',
                'finance_collection':'not_run_existing_observations_preserved'}

    def test_plan_order_range_and_invalid_shortcuts(self):
        rows=state_range(self.plan,DAY,'GA','WY')
        self.assertEqual(len(rows),48);self.assertEqual(rows[:3],[('A','GA'),('A','FL'),('A','PA')])
        with self.assertRaises(ValueError):state_range(self.plan,DAY,'FL','GA')
        with tempfile.TemporaryDirectory() as t,self.assertRaises(ValueError):
            run_sequence(Path(t),self.plan,[('A','GA'),('A','PA')],DAY,'run',self.row)

    def test_failure_stops_at_that_state_and_resume_does_not_repeat_success(self):
        selected=state_range(self.plan,DAY,'GA','PA');calls=[]
        def fail(state,group):
            calls.append(state)
            if state=='FL':raise ValueError('source failed')
            return self.row(state,group)
        with tempfile.TemporaryDirectory() as t:
            public=Path(t);last_valid=public/'existing_finance.json';last_valid.write_text('{"as_of":"2026-10-02"}')
            first=run_sequence(public,self.plan,selected,DAY,'run',fail)
            self.assertEqual(calls,['GA','FL']);self.assertEqual(first['status'],'interrupted')
            self.assertEqual(first['blocked_state'],'FL')
            self.assertEqual(json.loads((public/'usa_election_state_sequence_v1.json').read_text()),first)
            calls.clear()
            def recover(state,group):calls.append(state);return self.row(state,group)
            second=run_sequence(public,self.plan,selected,DAY,'run',recover,first)
            self.assertEqual(calls,['FL','PA']);self.assertEqual(second['status'],'transport_sequence_completed_partial')
            self.assertNotIn('blocked_state',second);self.assertIsNone(second['next_state'])
            self.assertEqual(last_valid.read_text(),'{"as_of":"2026-10-02"}')

    def test_wrong_state_result_and_different_resume_scope_cannot_complete(self):
        selected=state_range(self.plan,DAY,'GA','GA')
        with tempfile.TemporaryDirectory() as t:
            public=Path(t)
            result=run_sequence(public,self.plan,selected,DAY,'run',lambda s,g:self.row('NY',g))
            self.assertEqual(result['status'],'interrupted')
            with self.assertRaises(ValueError):run_sequence(public,self.plan,selected,DAY,'another-run',self.row,result)


if __name__=='__main__':unittest.main()
