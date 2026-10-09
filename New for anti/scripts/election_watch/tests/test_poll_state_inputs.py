"""State PR isolation, original capture replay and publication races."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from election_watch.polls import read
from election_watch.state_inputs import CONFIG, CATALOGS, apply_operations, digest, packets, validate_packet
from election_watch.poll_run_capture import make_capture, validate_capture
from election_watch.poll_refresh_provenance import retain_state_provenance
from freeze_state_inputs import make_operations
from check_state_packet_changes import violations, PACKETS, INTEGRATION
from publish_state_packets import rebuild
import publish_polling_run as publisher

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT.parent.parent/'public/data'
REPO = ROOT.parents[2]


class StateInputTests(unittest.TestCase):
    def test_actual_review_packets_are_scoped_and_legacy_catalogs_are_unchanged(self):
        self.assertTrue({'CT', 'AL', 'NJ', 'NM', 'NH'} <= {p['state'] for p in packets()})
        for file in CATALOGS:
            raw = json.loads((CONFIG/file).read_text())
            effective = read(CONFIG/file)
            before = json.loads(subprocess.check_output(['git', 'show', 'HEAD:'+str((CONFIG/file).relative_to(REPO))]))
            self.assertEqual(raw, before)
            self.assertIsInstance(effective, dict)

    def test_cross_state_record_or_operation_is_rejected(self):
        original = packets()[0]
        names = {s:d['name'] for s,d in read(CONFIG/'usa_polls/targets_2026.json')['states'].items()}
        packet = deepcopy(original); packet['capture']['provider_records'][0]['subject'] = '2026 TX-01'
        packet['capture']['provider_records_sha256'] = digest(packet['capture']['provider_records'])
        with self.assertRaisesRegex(ValueError, 'another state'): validate_packet(packet, names)
        packet = deepcopy(original)
        packet['config_operations'].append({'file':'federal_matchups/2026.json', 'path':['races','USA:TX:house:01'],
            'action':'set', 'before_exists':False, 'value':{}})
        with self.assertRaisesRegex(ValueError, 'outside owned'): validate_packet(packet, names)

    def test_newer_main_review_is_held_and_applied_review_is_idempotent(self):
        old = {'races':{'USA:CT:house:01':{'name':'old'}}}
        op = {'file':'federal_matchups/2026.json', 'path':['races','USA:CT:house:01'],
              'action':'set', 'before_exists':True, 'before_sha256':digest(old['races']['USA:CT:house:01']),
              'value':{'name':'reviewed'}}
        updated = apply_operations(old, [op])
        self.assertEqual(updated, apply_operations(updated, [op]))
        changed = deepcopy(old); changed['races']['USA:CT:house:01']['name'] = 'newer main review'
        with self.assertRaisesRegex(ValueError, 'newer baseline'): apply_operations(changed, [op])
        self.assertEqual(old['races']['USA:CT:house:01']['name'], 'old')

    def test_different_states_apply_in_either_order_without_losing_reviews(self):
        old = {'races':{}}
        ops = [{'file':'federal_matchups/2026.json', 'path':['races',f'USA:{s}:house:01'],
                'action':'set', 'before_exists':False, 'value':{'state':s}} for s in ('CT','AL')]
        self.assertEqual(apply_operations(old, ops), apply_operations(old, list(reversed(ops))))

    def test_freezing_rejects_global_or_other_state_edits(self):
        before = {'races':{'USA:CT:house:01':{'x':1}, 'USA:TX:house:01':{'x':1}}}
        after = deepcopy(before); after['races']['USA:CT:house:01']['x'] = 2
        ops = make_operations(before, after, 'federal_matchups/2026.json', 'CT', set())
        self.assertEqual(apply_operations(before, ops), after)
        after['races']['USA:TX:house:01']['x'] = 3
        with self.assertRaisesRegex(ValueError, 'unowned'): make_operations(before, after, 'federal_matchups/2026.json', 'CT', set())

    def test_state_pr_cannot_reintroduce_shared_files(self):
        packet = PACKETS+'CT.json'
        for shared in ('New for anti/public/data/usa_election_live_polls_v1.json',
                       'New for anti/scripts/election_watch/election_watch/live_polls.py', 'docs/ops/TASKS.md'):
            self.assertEqual(violations([packet, shared], 'codex/ct-evidence-next'), [shared])
        self.assertFalse(violations([packet], 'codex/ct-evidence-next'))
        self.assertFalse(violations([packet, shared], INTEGRATION))
        self.assertTrue(violations([packet, shared], INTEGRATION+'-extra'))

    def test_offline_rebuild_preserves_other_states_dates_and_focus(self):
        def baseline(name):
            return json.loads(subprocess.check_output(['git','show','HEAD:New for anti/public/data/'+name]))
        old = baseline('usa_election_live_polls_v1.json')
        archive = baseline('usa_election_poll_history_2026.json')
        with patch('urllib.request.urlopen', side_effect=AssertionError('offline replay must not fetch')):
            board, history = rebuild(old, archive, packets(), PUBLIC)
        states = {p['state'] for p in packets()}
        for rid, race in old['races'].items():
            if race['state'] not in states:
                self.assertEqual(board['races'][rid], race, rid)
                if rid in archive['races']: self.assertEqual(history['races'][rid], archive['races'][rid])
        self.assertEqual(board['as_of'], old['as_of'])
        self.assertEqual(board['fetched_at'], old['fetched_at'])
        self.assertEqual(board['house_poll_focus']['race_count'], 104)
        for packet in packets():
            state = packet['state']
            self.assertEqual(board['state_captures'][state], packet['capture']['receipt'])
            self.assertEqual(board['state_packet_replays'][state]['original_captured_at'], packet['capture']['fetched_at'])
        again, again_history = rebuild(board, history, packets(), PUBLIC)
        self.assertEqual(again, board); self.assertEqual(again_history, history)

    def test_newer_manual_state_capture_cannot_be_rolled_back(self):
        old = read(PUBLIC/'usa_election_live_polls_v1.json')
        packet = packets()[0]; old.setdefault('state_captures', {})[packet['state']] = {'captured_at':'2026-10-11T00:00:00Z'}
        with self.assertRaisesRegex(ValueError, 'newer state capture'):
            rebuild(old, read(PUBLIC/'usa_election_poll_history_2026.json'), [packet], PUBLIC)

    def test_fresh_national_build_imports_receipts_without_replaying_old_polls(self):
        packet = packets()[0]; state = packet['state']; rid = f'USA:{state}:house:01'
        old = {'schema':'usa_live_polls_v1', 'cycle':2026, 'races':{}, 'state_captures':{}}
        fresh = {'schema':'usa_live_polls_v1', 'cycle':2026, 'races':{rid:{'observations':[{'id':'fresh API row'}]}}}
        history = {'cycle':2026, 'races':{rid:{'observations':[{'id':'fresh API row'}]}}}
        retain_state_provenance(fresh, history, old, [packet])
        self.assertEqual(fresh['races'][rid]['observations'], [{'id':'fresh API row'}])
        self.assertEqual(fresh['state_captures'][state], packet['capture']['receipt'])
        self.assertTrue(fresh['state_packet_replays'][state]['receipt_import_only'])

    def test_packet_receipt_cannot_replace_newer_manual_collection_receipt(self):
        packet = packets()[0]; state = packet['state']
        old = {'schema':'usa_live_polls_v1', 'cycle':2026, 'races':{},
               'state_captures':{state:{'captured_at':'2026-10-12T00:00:00Z'}}}
        board = {'schema':'usa_live_polls_v1', 'cycle':2026, 'races':{}}
        history = {'cycle':2026, 'races':{}}
        retain_state_provenance(board, history, old, [packet])
        self.assertEqual(board['state_captures'], old['state_captures'])


class PublicationRetryTests(unittest.TestCase):
    def capture(self):
        return make_capture([{'id':'primary'}], [{'id':'provider'}],
            'https://api.votehub.com/polls?subject=2026', '2026-10-09', '2026-10-09T12:34:56Z',
            [{'status':'primary_documents_rechecked', 'original_reviewed_on':'2026-10-08'}])

    def test_retry_input_preserves_source_time_and_document_receipts(self):
        payload = self.capture()
        self.assertEqual(validate_capture(payload)['captured_at'], '2026-10-09T12:34:56Z')
        self.assertEqual(payload['primary_receipts'][0]['original_reviewed_on'], '2026-10-08')
        payload['rows'][0]['id'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'changed'): validate_capture(payload)

    def test_invalid_checkpoint_source_or_future_date_is_rejected(self):
        for url, day in [('https://example.org/', '2026-10-09'),
                         ('https://api.votehub.com/polls?subject=2026', '2026-10-11')]:
            with self.assertRaises(ValueError): make_capture([{}], [{}], url, day, '2026-10-09T12:34:56Z')

    def test_collector_retry_uses_checkpoint_without_network_or_new_dates(self):
        import refresh_live_polls as refresh
        from test_live_polls import POLICY, RID, poll
        day = '2026-10-09'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = root/'live.json'
            policy = root/'policy.json'; policy.write_text(json.dumps(POLICY))
            quality = root/'quality.json'; quality.write_text(json.dumps({'schema':'usa_poll_quality_reviews_v1','cycle':2026,'reviews':{}}))
            checkpoint = root/'capture.json'
            row = poll(start_date='2026-10-07', end_date='2026-10-08', created_at=day)
            payload = make_capture([row], [row], 'https://api.votehub.com/polls?subject=2026', day, day+'T01:23:45Z')
            checkpoint.write_text(json.dumps(payload))
            with patch.object(sys,'argv',['refresh','--retry-capture',str(checkpoint),'--policy',str(policy),
                    '--quality-reviews',str(quality),'--output',str(output),'--as-of','2026-10-10']), \
                 patch.object(refresh,'fetch_polls',side_effect=AssertionError('no network on retry')), \
                 patch.object(refresh,'fetch_florida',side_effect=AssertionError('no network on retry')), \
                 patch.object(refresh,'merge_primary_supplements',side_effect=AssertionError('no network on retry')), \
                 patch.object(refresh,'publish_scenarios',return_value={'status':'ok'}):
                self.assertEqual(refresh.main(), 0)
            result = json.loads(output.read_text())
            self.assertEqual(result['fetched_at'], payload['captured_at'])
            self.assertEqual(result['as_of'], day)
            self.assertEqual(len(result['races'][RID]['observations']), 1)

    def test_retry_cannot_roll_back_newer_national_collection(self):
        import refresh_live_polls as refresh
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); output = root/'live.json'; checkpoint = root/'capture.json'
            original = json.dumps({'fetched_at':'2026-10-10T00:00:00Z'})
            output.write_text(original); checkpoint.write_text(json.dumps(self.capture()))
            with patch.object(sys,'argv',['refresh','--retry-capture',str(checkpoint),'--output',str(output)]):
                with self.assertRaisesRegex(ValueError,'Newer national collection'): refresh.main()
            self.assertEqual(output.read_text(), original)
            self.assertFalse((root/'usa_election_live_polls_status_v1.json').exists())

    def test_push_race_rebuilds_on_latest_main_from_same_checkpoint(self):
        calls = []; pushes = []
        def git(*args, check=True):
            calls.append(args)
            if args[0] == 'push':
                pushes.append(args); return subprocess.CompletedProcess(args, int(len(pushes)==1))
            return subprocess.CompletedProcess(args, 1 if args[0]=='diff' else 0)
        with patch.dict('os.environ', {'GITHUB_ACTIONS':'true','GITHUB_REF':'refs/heads/main'}), \
             patch.object(sys, 'argv', ['publisher','--checkpoint','/tmp/original-capture.json']), \
             patch.object(publisher, 'git', side_effect=git), \
             patch.object(publisher, 'stage_paths', return_value=['output.json']), \
             patch.object(publisher.subprocess, 'run') as run:
            publisher.main()
        self.assertIn(('fetch','origin','main'), calls)
        self.assertIn(('reset','--hard','origin/main'), calls)
        self.assertFalse(any('rebase' in c or 'merge' in c for c in calls))
        self.assertEqual(len(pushes), 2)
        self.assertTrue(any('--retry-capture' in c.args[0] and '/tmp/original-capture.json' in c.args[0]
                            for c in run.call_args_list))

    def test_local_publication_is_blocked_before_any_git_action(self):
        with patch.dict('os.environ', {'GITHUB_ACTIONS':'false'}), \
             patch.object(sys,'argv',['publisher','--checkpoint','/tmp/capture.json']), \
             patch.object(publisher,'git') as git:
            with self.assertRaises(SystemExit): publisher.main()
        git.assert_not_called()
