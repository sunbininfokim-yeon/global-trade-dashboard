"""Maine official field, RV/RCV semantics and state-only replay."""
from pathlib import Path
import json
import unittest
from election_watch.polls import read
from election_watch.state_inputs import packets
from election_watch.poll_targets import apply_targets
from election_watch.governor_matchups import apply_matchups
from election_watch.live_polls import normalize, summarize
from publish_state_packets import rebuild
from election_watch.superpac import build_snapshot
from election_watch.federal_matchups import validate_snapshot,merge_ballot_reviews
from election_watch.review_clock import validation_day
from tests.poll_config_fixture import SNAPSHOT_DAY

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'config'
PUBLIC=ROOT.parents[1]/'public/data'
DAY='2026-10-14'

class MaineEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet=next(p for p in packets() if p['state']=='ME')
        cls.ballots=read(CONFIG/'usa_polls/ballot_reviews_2026.json')
        cls.policy=apply_targets(apply_matchups(read(CONFIG/'usa_polls/live_2026.json'),
            read(CONFIG/'governor_matchups/2026.json'),SNAPSHOT_DAY),read(CONFIG/'usa_polls/targets_2026.json'),cls.ballots,SNAPSHOT_DAY)
        cls.policy['quality_reviews']=read(CONFIG/'usa_polls/quality_reviews_2026.json')['reviews']
        cls.observations,cls.held=normalize(cls.packet['capture']['provider_records'],cls.policy,DAY)

    def test_official_printed_field_and_writeins_are_separate_without_winners(self):
        field=[r for r in self.ballots['races'].values() if r['state']=='ME']
        self.assertEqual(len(field),4)
        self.assertEqual(sum(len(r['candidates']) for r in field),9)
        self.assertEqual(sum(len(r.get('declared_write_ins',[])) for r in field),9)
        self.assertTrue(all(r['source_role']=='state_election_agency' for r in field))
        for rid in ('USA:ME:house:01','USA:ME:house:02','USA:ME:senate','USA:ME:governor'):
            self.assertFalse(self.policy['races'][rid]['ballot_competition']['general_unopposed'])
            self.assertFalse(self.policy['races'][rid]['ballot_competition']['confirmed_winner'])
        self.assertNotIn('Graham Platner',self.policy['races']['USA:ME:senate']['candidates'])

    def test_marist_rv_is_not_lv_or_district_poll_and_rcv_is_reference(self):
        rows=[r for r in self.observations if r['id'] in ('us-202mare89f317d','gov202mar89bef491')]
        self.assertEqual(len(rows),2)
        for row in rows:
            self.assertEqual(row['sample_n'],1505)
            self.assertEqual(row['population'],'rv')
            self.assertEqual(row['source_quality']['verification_level'],'primary_toplines_checked')
            self.assertIsNone(row['source_quality']['accuracy_grade'])
            self.assertNotIn(':house:',row['race_id'])
        senate=next(r for r in rows if r['race_id'].endswith('senate'))
        self.assertFalse(senate['aggregation_eligibility']['eligible'])
        self.assertIsNone(summarize([senate],self.policy['races'][senate['race_id']],DAY,14)['party'])

    def test_federal_probe_is_scoped_and_not_claimed_as_published_finance(self):
        capture=self.packet['federal_finance_review']
        self.assertEqual(capture['status'],'candidate_scoped_regular_report_capture')
        self.assertEqual(len(capture['candidates']),6)
        self.assertEqual(len(capture['raw_records']),219)
        self.assertEqual(capture['quality']['included_records'],210)
        self.assertTrue(all(r['state']=='ME' for r in capture['spending']))
        self.assertEqual(capture['publication_status'],'review_input_only_national_finance_publisher_not_replaced')
        self.assertNotIn('api_key',json.dumps(capture['sources']))
        replay=build_snapshot(2026,capture['candidates'],capture['raw_records'])
        self.assertEqual(replay['spending'],capture['spending'])
        self.assertEqual(replay['quality'],capture['quality'])

    def test_official_federal_input_has_absent_party_contract_before_projection(self):
        snapshot=read(CONFIG/'federal_matchups/2026.json')
        day=validation_day(DAY,snapshot,self.ballots)
        validate_snapshot(snapshot,day)
        projected=merge_ballot_reviews(snapshot,self.ballots,day)
        for rid,race in projected['races'].items():
            if race['state']=='ME':
                self.assertEqual(race['absent_parties'],[],rid)
                self.assertEqual({c['party'] for c in race['candidates']},{'DEM','REP'})

    def test_replay_preserves_all_other_races_history_and_original_dates(self):
        old=read(PUBLIC/'usa_election_live_polls_v1.json')
        history=read(PUBLIC/'usa_election_poll_history_2026.json')
        board,archive=rebuild(old,history,[self.packet],PUBLIC)
        for rid,race in old['races'].items():
            if race['state']!='ME':
                self.assertEqual(board['races'][rid],race,rid)
                if rid in history['races']:self.assertEqual(archive['races'][rid],history['races'][rid],rid)
        self.assertEqual(board['as_of'],old['as_of'])
        self.assertEqual(board['fetched_at'],old['fetched_at'])
        self.assertEqual(board['house_poll_focus'],old['house_poll_focus'])
        self.assertEqual(board['state_captures']['ME']['captured_at'],self.packet['capture']['fetched_at'])

    def test_actual_api_refresh_does_not_advance_primary_or_finance_review_dates(self):
        original=self.packet['capture_history'][0]
        self.assertEqual(original['fetched_at'],'2026-10-13T13:05:08.953432+00:00')
        # 2026-10-23 refresh: full-range VoteHub response fetched by source_fetch.yml.
        self.assertEqual(self.packet['capture']['fetched_at'],'2026-10-23T02:32:01.138221+00:00')
        self.assertEqual(len(self.packet['capture']['provider_records']),65)
        for row in self.observations:
            if row['id'] in ('us-202mare89f317d','gov202mar89bef491'):
                self.assertEqual(row['source_quality']['reviewed_on'],'2026-10-13')
        self.assertFalse(any(r['field_end']>='2026-10-08' for r in self.observations))

if __name__=='__main__':unittest.main()
