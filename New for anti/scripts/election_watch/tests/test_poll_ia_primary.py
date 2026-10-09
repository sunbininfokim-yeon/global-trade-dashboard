from tests.poll_config_fixture import SNAPSHOT_DAY
import copy
import json
from pathlib import Path
import unittest

from election_watch.governor_matchups import apply_matchups
from election_watch.live_polls import normalize, summarize
from election_watch.poll_targets import apply_targets
from election_watch.state_evidence import build_state, load_finance

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT/'config/usa_polls'
PUBLIC = ROOT.parent.parent/'public/data'
DAY = '2026-10-09'
read = lambda p: json.loads(p.read_text())


class IowaPrimaryTests(unittest.TestCase):
    def setUp(self):
        self.gov = read(ROOT/'config/governor_matchups/2026.json')
        self.policy = apply_targets(apply_matchups(read(CONFIG/'live_2026.json'), self.gov, SNAPSHOT_DAY),
            read(CONFIG/'targets_2026.json'), read(CONFIG/'ballot_reviews_2026.json'), SNAPSHOT_DAY)
        self.policy['quality_reviews'] = read(CONFIG/'quality_reviews_2026.json')['reviews']
        self.audit = read(PUBLIC/'usa_election_poll_release_reviews/2026/IA-primary-20261009.json')
        self.rows = [e['provider_record'] for e in self.audit['records']]

    def current(self):
        obs, rejected = normalize(self.rows, self.policy, DAY)
        self.assertFalse(rejected)
        self.assertEqual(len(obs), 6)
        return obs

    def test_cnn_iowa_sample_is_not_ohio_or_a_screened_lv_subsample(self):
        obs = self.current()
        for rid, party in [('USA:IA:senate', 'REP'), ('USA:IA:governor', 'DEM')]:
            o = next(o for o in obs if o['race_id'] == rid and o['pollster_group'] == 'cnn_ssrs')
            self.assertEqual(o['sample_n'], 801)
            disclosure = o['source_quality']['disclosure_review']
            self.assertEqual(disclosure['sampling_frame'], {'L2_registration_based': 624, 'SSRS_probability_panel': 177})
            self.assertIn('all801RV', disclosure['lv_definition'])
            signal = summarize([p for p in obs if p['race_id'] == rid], self.policy['races'][rid], DAY, 7)
            self.assertEqual(signal['status'], 'single_poll_lead')
            self.assertEqual(signal['party'], party)
            self.assertEqual(signal['pollster_count'], 1)
        senate = next(o for o in obs if o['id'] == 'us-202cnnc393624c')
        self.assertEqual([a['pct'] for a in senate['answers']], [45, 43])
        self.assertEqual(senate['source_quality']['disclosure_review']['non_candidate_responses']['neither'], 8)

    def test_opposing_14_day_leads_are_tied_and_rv_is_not_combined(self):
        obs = [o for o in self.current() if o['race_id'] == 'USA:IA:senate']
        s = summarize(obs, self.policy['races']['USA:IA:senate'], DAY, 14)
        self.assertEqual(s['status'], 'tie')
        self.assertIsNone(s['party'])
        self.assertEqual(s['pollster_count'], 2)
        self.assertNotIn('us-202marf54f428e', s['included_ids'])

    def test_fox_total_rv_and_lv_subsample_stay_separate_and_group_is_stable(self):
        obs = self.current()
        for o in [o for o in obs if o['pollster_group'] == 'beacon_shaw']:
            self.assertEqual(o['sample_n'], 1008)
            self.assertEqual(o['source_quality']['disclosure_review']['total_registered_sample_n'], 1204)
            self.assertEqual(o['source_quality']['reported_precision']['half_width_pp'], 3)
        self.assertEqual(self.policy['pollsters']['Beacon Research/Shaw & Co. Research']['group'], 'beacon_shaw')

    def test_official_minor_candidates_are_present_without_automatic_winners(self):
        for suffix, count in [('senate', 3), ('governor', 2), ('house:01', 3), ('house:02', 4), ('house:03', 2), ('house:04', 2)]:
            race = self.policy['races']['USA:IA:'+suffix]
            self.assertEqual(race['ballot_competition']['candidate_count'], count)
            self.assertFalse(race['ballot_competition']['general_unopposed'])
            self.assertFalse(race['ballot_competition']['confirmed_winner'])
        self.assertEqual(self.policy['races']['USA:IA:senate']['candidates']['Thomas Laehn']['party'], 'LIB')

    def test_unverified_house_reports_do_not_become_polls_or_zeroes(self):
        raw = [e['provider_record'] for e in self.audit['held_records']]
        obs, rejected = normalize(raw, self.policy, DAY)
        self.assertFalse(obs)
        self.assertEqual(len(rejected), 3)
        for suffix in ['01', '02', '03', '04']:
            s = summarize([], self.policy['races']['USA:IA:house:'+suffix], DAY, 7)
            self.assertEqual(s['status'], 'no_recent_poll')
            self.assertIsNone(s['party'])

    def test_changed_provider_metadata_requires_review(self):
        raw = copy.deepcopy(self.rows[0])
        raw['sample_size'] = 760
        self.assertFalse(normalize([raw], self.policy, DAY)[0])
        raw = copy.deepcopy(self.rows[2])
        raw['sponsors'] = ['Different commissioner']
        self.assertFalse(normalize([raw], self.policy, DAY)[0])

    def test_reachable_report_index_does_not_claim_financial_coverage(self):
        access = read(PUBLIC/'usa_governor_source_access/2026/IA.json')
        result = build_state('IA', 'B', read(CONFIG/'state_evidence_plan_2026.json'),
            read(CONFIG/'targets_2026.json'), read(ROOT/'config/federal_matchups/2026.json'),
            self.gov, read(PUBLIC/'usa_election_live_polls_v1.json'),
            load_finance(PUBLIC/'usa_election_finance_index_v1.json', 2026),
            read(ROOT/'config/usa_state_campaign_finance_sources_v1.json'), DAY,
            read(CONFIG/'state_finance_identities_2026.json'), governor_access={'IA': access})
        self.assertEqual(result['work_status'], 'live_poll_sources_reviewed_finance_mapping_required')
        self.assertFalse(result['governor_source_route']['access_check']['candidate_amounts_available'])
        self.assertFalse(access['report_discovery']['cycle_discovery_complete'])
