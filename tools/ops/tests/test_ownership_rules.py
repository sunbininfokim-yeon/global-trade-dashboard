import unittest
from tools.ops.ownership_rules import scoped_paths


class PollingScopeTests(unittest.TestCase):
    def test_only_three_exact_workflow_files_are_allowed(self):
        self.assertEqual(scoped_paths('codex/us-polls-deploy'), {
            '.github/workflows/us_election_polls_refresh.yml',
            '.github/workflows/deploy.yml', '.github/workflows/ownership_guard.yml'})

    def test_other_codex_branches_receive_no_exception(self):
        for branch in ('codex/us-poll-seat-scenarios', 'codex/us-polls-deploy-extra',
                       'codex/unrelated', 'cursor/us-polls-deploy', 'main'):
            with self.subTest(branch=branch):
                self.assertFalse(scoped_paths(branch))

    def test_ui_and_other_workflows_are_still_excluded(self):
        permitted = scoped_paths('codex/us-polls-deploy')
        for path in ('New for anti/app.js', 'New for anti/market-microstructure.js',
                     '_worker.js', 'wrangler.jsonc', '.github/workflows/overseas_letf_daily.yml',
                     '.github/workflows/deploy.yml.bak', '.github/workflows/nested/deploy.yml'):
            with self.subTest(path=path):
                self.assertNotIn(path, permitted)

    def test_user_requested_election_ui_exception_is_exact(self):
        self.assertEqual(scoped_paths('codex/usa-election-ui'),
                         {'New for anti/index.html', 'New for anti/style.css'})
        self.assertNotIn('New for anti/app.js', scoped_paths('codex/usa-election-ui'))
        self.assertFalse(scoped_paths('codex/usa-election-ui-extra'))
        self.assertNotIn('.github/workflows/deploy.yml', scoped_paths('codex/usa-election-ui'))


if __name__ == '__main__':
    unittest.main()
