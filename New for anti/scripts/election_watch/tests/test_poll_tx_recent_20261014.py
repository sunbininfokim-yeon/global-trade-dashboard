"""Texas actual primary questions, exact question-base correction and state preservation."""
import copy
from pathlib import Path
import unittest
from election_watch.polls import read
from election_watch.state_inputs import packets
from election_watch.poll_targets import apply_targets
from election_watch.governor_matchups import apply_matchups
from election_watch.live_polls import normalize,summarize
from publish_state_packets import rebuild
from tests.poll_config_fixture import SNAPSHOT_DAY
ROOT=Path(__file__).resolve().parents[1];PUBLIC=ROOT.parents[1]/'public/data'
IDS={'us-202recc152b3f7','gov202rec101a5410','us-202quaee83ce98'}

class TexasRecentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet=next(p for p in packets() if p['state']=='TX')
        cls.policy=apply_targets(apply_matchups(read(ROOT/'config/usa_polls/live_2026.json'),read(ROOT/'config/governor_matchups/2026.json'),SNAPSHOT_DAY),read(ROOT/'config/usa_polls/targets_2026.json'),read(ROOT/'config/usa_polls/ballot_reviews_2026.json'),SNAPSHOT_DAY)
        cls.policy['quality_reviews']=read(ROOT/'config/usa_polls/quality_reviews_2026.json')['reviews']
        cls.rows=[r for r in cls.packet['capture']['provider_records'] if r['id'] in IDS]

    def test_primary_values_and_inconsistent_institution_label_are_explicit(self):
        rows,held=normalize(self.rows,self.policy,'2026-10-14');self.assertFalse(held)
        senate=next(r for r in rows if r['id']=='us-202recc152b3f7')
        governor=next(r for r in rows if r['id']=='gov202rec101a5410')
        self.assertEqual({a['name']:a['pct'] for a in senate['answers']},{'James Talarico':48,'Ken Paxton':44})
        self.assertEqual({a['name']:a['pct'] for a in governor['answers']},{'Greg Abbott':48,'Gina Hinojosa':47})
        self.assertEqual(senate['pollster_group'],'reconmr')
        self.assertEqual(senate['source_quality']['disclosure_review']['primary_pollster_name'],'ReconMR')
        self.assertIn('Siena',senate['source_quality']['limitations_ko'])
        self.assertTrue(all(r['aggregation_eligibility']['eligible'] for r in rows))
        self.assertTrue(all(r['source_quality']['accuracy_grade'] is None for r in rows))

    def test_quantus_q1_is839_not854_and_full_study_precision_is_not_question_precision(self):
        rows,held=normalize(self.rows,self.policy,'2026-10-14');self.assertFalse(held)
        row=next(r for r in rows if r['id']=='us-202quaee83ce98')
        self.assertEqual(row['sample_n'],839)
        self.assertEqual(row['provider_sample_correction']['original_provider_sample_n'],854)
        self.assertEqual({a['name']:a['pct'] for a in row['answers']},{'James Talarico':46.7,'Ken Paxton':47.2,'Ted Brown':2.2})
        self.assertEqual(row['source_quality']['reported_precision']['scope'],'whole_study_base854')
        self.assertIsNone(row['margin_of_error_pp'])
        senators=[r for r in rows if r['race_id']=='USA:TX:senate']
        summary=summarize(senators,self.policy['races']['USA:TX:senate'],'2026-10-14',7)
        self.assertEqual(summary['status'],'tie');self.assertIsNone(summary['party'])

    def test_changed_sample_or_future_release_requires_new_primary_review(self):
        for raw in self.rows:
            changed=copy.deepcopy(raw);changed['sample_size']+=1
            rows,held=normalize([changed],self.policy,'2026-10-14')
            self.assertFalse(rows);self.assertEqual(held[0]['reason'],'primary_review_provider_metadata_changed')
        raw=copy.deepcopy(next(r for r in self.rows if r['id']=='us-202recc152b3f7'));raw['id']='new-unreviewed-tx-wave'
        rows,held=normalize([raw],self.policy,'2026-10-14');self.assertFalse(rows)
        self.assertEqual(held[0]['reason'],'unregistered_primary_host')

    def test_replay_only_replaces_texas_and_recalculates_own_house_focus(self):
        old=read(PUBLIC/'usa_election_live_polls_v1.json');history=read(PUBLIC/'usa_election_poll_history_2026.json')
        new,archive=rebuild(old,history,[self.packet],PUBLIC)
        for rid,race in old['races'].items():
            if race['state']!='TX':
                self.assertEqual(new['races'][rid],race,rid)
                if rid in history['races']:self.assertEqual(archive['races'][rid],history['races'][rid],rid)
        for key in ('as_of','fetched_at'):self.assertEqual(new[key],old[key])
        for rid,race in old['house_poll_focus']['races'].items():
            if race['state']!='TX':self.assertEqual(new['house_poll_focus']['races'][rid],race,rid)
        self.assertEqual(new['house_poll_focus']['race_count'],104)
        self.assertEqual(new['state_captures']['TX']['captured_at'],'2026-10-14T05:14:02.840821+00:00')

if __name__=='__main__':unittest.main()
