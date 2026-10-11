"""Research-only branches and stacked bases must obey state isolation too."""
from pathlib import Path
from fnmatch import fnmatchcase
import re
import subprocess
import tempfile
import unittest

from check_state_packet_changes import PACKETS, REVIEW_DIRS, unmerged_base_inputs, violations


BACKEND = 'New for anti/scripts/election_watch/'
PUBLIC = 'New for anti/public/data/'
REVIEW = PUBLIC + 'usa_election_poll_release_reviews/2026/CT-primary.json'


class StateResearchScopeTests(unittest.TestCase):
    def test_source_only_research_paths_trigger_existing_pr_validation(self):
        repo = Path(__file__).resolve().parents[4]
        workflow = (repo/'.github/workflows/us_election_polls_refresh.yml').read_text()
        pr_paths = workflow.split('  pull_request:', 1)[1].split('\npermissions:', 1)[0]
        patterns = re.findall(r"^\s+- '([^']+)'", pr_paths, flags=re.MULTILINE)
        for directory in REVIEW_DIRS:
            file = PUBLIC + directory + '/2026/CT.json'
            self.assertTrue(any(fnmatchcase(file, pattern) for pattern in patterns), file)

    def test_source_only_research_is_checked_on_arbitrary_provider_branch(self):
        shared = BACKEND + 'config/usa_polls/quality_reviews_2026.json'
        for branch in ('codex/research-next', 'claude/research-next', 'cursor/research-next'):
            self.assertEqual(violations([REVIEW, shared], branch), [shared])
            self.assertFalse(violations([REVIEW], branch))

    def test_two_state_audits_and_branch_state_mismatch_are_rejected(self):
        other = REVIEW.replace('/CT-', '/AL-')
        self.assertEqual(violations([REVIEW, other], 'codex/research-next'), sorted([REVIEW, other]))
        for owner in ('codex', 'claude', 'cursor'):
            self.assertEqual(violations([other], f'{owner}/ct-evidence-next'), [other])

    def test_other_state_adapters_tests_and_handoffs_are_rejected(self):
        for other in (BACKEND+'election_watch/governor_al.py',
                      BACKEND+'tests/test_poll_al_primary.py',
                      BACKEND+'tests/test_superpac_governor_al.py',
                      'docs/ops/handoff/2026-10-11-codex-state-evidence-AL.md'):
            self.assertEqual(violations([PACKETS+'CT.json', other], 'codex/ct-evidence-next'), [other])

    def test_own_adapter_test_and_review_remain_allowed(self):
        changed = [PACKETS+'CT.json', REVIEW, BACKEND+'election_watch/governor_ct.py',
                   BACKEND+'tests/test_poll_ct_primary.py',
                   'docs/ops/handoff/2026-10-11-codex-state-evidence-CT.md']
        self.assertFalse(violations(changed, 'codex/ct-evidence-next'))

    def test_unlisted_national_data_config_and_agent_rules_are_protected(self):
        for shared in (PUBLIC+'usa_election_finance_index_v1.json',
                       PUBLIC+'usa_governor_finance/2026/CT.json',
                       BACKEND+'config/usa_polls/targets_2026.json',
                       'AGENTS.md', 'CLAUDE.md', 'docs/ops/START_PROMPTS.md',
                       'New for anti/js/elections/finance.js', '.github/workflows/deploy.yml'):
            self.assertEqual(violations([REVIEW, shared], 'codex/research-next'), [shared])

    def test_packet_free_foundation_can_add_adapter_and_common_code(self):
        changed = [BACKEND+'election_watch/governor_ks.py', BACKEND+'election_watch/live_polls.py',
                   BACKEND+'tests/test_poll_ranked_choice.py']
        self.assertFalse(violations(changed, 'codex/election-b-foundation-20261011'))

    def test_actual_git_base_rejects_state_chain_but_allows_foundation_and_main(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.check_output(['git', '-c', 'core.fsmonitor=false', *args], cwd=root, text=True)
            git('init', '-q')
            git('config', 'user.name', 'Scope test')
            git('config', 'user.email', 'scope-test@example.invalid')
            git('commit', '--allow-empty', '-qm', 'main')
            git('update-ref', 'refs/remotes/origin/main', 'HEAD')
            self.assertEqual(unmerged_base_inputs('HEAD', cwd=root), [])
            adapter = root/BACKEND/'election_watch/governor_ct.py'
            adapter.parent.mkdir(parents=True)
            adapter.write_text('# packet-free shared foundation\n')
            git('add', str(adapter.relative_to(root)))
            git('commit', '-qm', 'foundation')
            foundation = git('rev-parse', 'HEAD').strip()
            self.assertEqual(unmerged_base_inputs(foundation, cwd=root), [])
            packet = root/(PACKETS+'CT.json')
            packet.parent.mkdir(parents=True)
            packet.write_text('{}\n')
            git('add', str(packet.relative_to(root)))
            git('commit', '-qm', 'unmerged CT state PR')
            self.assertEqual(unmerged_base_inputs('HEAD', cwd=root), [PACKETS+'CT.json'])
            git('update-ref', 'refs/remotes/origin/main', 'HEAD')
            self.assertEqual(unmerged_base_inputs('HEAD', cwd=root), [])
            review = root/REVIEW
            review.parent.mkdir(parents=True)
            review.write_text('{}\n')
            git('add', str(review.relative_to(root)))
            git('commit', '-qm', 'source-only CT research')
            self.assertEqual(unmerged_base_inputs('HEAD', cwd=root), [REVIEW])


if __name__ == '__main__':
    unittest.main()
