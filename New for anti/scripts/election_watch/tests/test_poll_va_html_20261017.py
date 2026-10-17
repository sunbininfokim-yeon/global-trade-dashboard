"""Real VA-02 primary HTML capture replay, without another network collection."""
from pathlib import Path
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch
from election_watch.polls import read,digest
from election_watch.state_inputs import validate_packet
from election_watch.live_polls import apply_watchlist,build_live
from election_watch.poll_priorities import apply_priorities
from election_watch.poll_targets import apply_targets
from election_watch.poll_html_tables import bind_html_reviews

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'config'
PUBLIC=ROOT.parent.parent/'public/data'

class VirginiaHtmlEvidenceTests(TestCase):
    def test_real_primary_capture_and_state_scope(self):
        packet=read(CONFIG/'state_evidence/2026/VA.json')
        validate_packet(packet,{'VA':'Virginia'})
        saved=packet['capture'];r=saved['primary_records'][0]
        self.assertEqual(saved['provider_records_sha256'],digest(saved['provider_records']))
        self.assertEqual(r['subject'],'2026 VA-02');self.assertEqual(r['sample_size'],702)
        self.assertEqual(r['population'],'lv')
        self.assertEqual({a['choice']:a['pct']for a in r['answers']},{'Elaine Luria':46,'Jen Kiggans':43})
        self.assertEqual(len(r['primary_source_capture']['documents']),4)
        self.assertTrue(all(o['file']=='usa_polls/html_table_sources_2026.json' for o in packet['config_operations']))
    def test_primary_replay_uses_14_day_window_and_candidate_aliases(self):
        saved=read(CONFIG/'state_evidence/2026/VA.json')['capture'];c=CONFIG/'usa_polls';day=saved['as_of']
        p=apply_priorities(apply_watchlist(read(c/'live_2026.json'),read(c/'watchlist_2026.json')),
            read(c/'priorities_2026.json'),PUBLIC/'congressional_districts/USA',day)
        p=apply_targets(p,read(c/'targets_2026.json'),read(c/'ballot_reviews_2026.json'),day)
        p['races']={k:v for k,v in p['races'].items()if v['state']=='VA'}
        p['quality_reviews']=read(c/'quality_reviews_2026.json')['reviews']
        rows=deepcopy(saved['provider_records']+saved['primary_records'])
        with patch('election_watch.poll_html_tables.document',side_effect=AssertionError('offline replay')):
            p=bind_html_reviews(p,rows,saved['receipt']['primary_supplement_receipts'],read(c/'html_table_sources_2026.json'),day)
            board=build_live(rows,p,read(c/'results_2026.json'),day,saved['fetched_at'],saved['receipt']['source_url'])
        race=board['races']['USA:VA:house:02']
        self.assertEqual(race['windows']['7']['included_ids'],[])
        self.assertIn(saved['primary_records'][0]['id'],race['windows']['14']['included_ids'])
        self.assertEqual(race['windows']['14']['party'],'DEM')
        observation=next(o for o in race['observations']if o['id']==saved['primary_records'][0]['id'])
        self.assertEqual(observation['source_quality']['reported_precision']['half_width_pp'],4)
        self.assertEqual(observation['primary_source_capture']['checked_at'],saved['primary_records'][0]['primary_source_capture']['checked_at'])
        self.assertNotIn('USA:VA:senate:',observation['race_id'])
