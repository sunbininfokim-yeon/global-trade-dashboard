"""Small cross-file guards in addition to real actionlint context validation."""
from pathlib import Path
import unittest

REPO=Path(__file__).resolve().parents[4]


class WorkflowContracts(unittest.TestCase):
    def workflow(self,name):
        return (REPO/'.github/workflows'/name).read_text()

    def test_runner_context_is_not_at_job_env(self):
        text=self.workflow('commodity_trade_refresh.yml')
        job_env=text.split('    env:',1)[1].split('    steps:',1)[0]
        self.assertNotIn('runner.',job_env)
        self.assertIn('TRADE_CHECKPOINT=$RUNNER_TEMP/trade-state/checkpoint.json',text)

    def test_daily_resume_retains_trusted_progress_and_review_boundary(self):
        text=self.workflow('commodity_trade_refresh.yml')
        self.assertIn("cron: '37 3 * * *'",text)
        self.assertIn('EXTRA+=(--resume-only)',text)
        self.assertIn("r.path!=='.github/workflows/commodity_trade_refresh.yml'",text)
        self.assertIn("r.head_branch!=='main'",text)
        self.assertIn('trade-state/*.json',text)
        self.assertIn('gh pr create',text)
        self.assertNotIn('gh pr merge',text)
        self.assertNotIn('git push origin main',text)

    def test_watchdog_tee_cannot_mask_python_failure(self):
        text=self.workflow('commodity_trade_watchdog.yml')
        self.assertIn('shell: bash',text)  # GitHub explicit bash enables pipefail.
        self.assertIn('check_freshness.py',text)
        self.assertNotIn('continue-on-error',text)
        self.assertIn('if: always()',text)

    def test_ci_checks_real_contexts_and_actual_assets_without_fetching(self):
        text=self.workflow('commodity_trade_contracts.yml')
        self.assertIn('actionlint',text)
        self.assertIn('sha256sum --check',text)
        self.assertIn('validate_release.py',text)
        self.assertNotIn('--fetch',text)
        self.assertNotIn('secrets.',text)


if __name__=='__main__': unittest.main()
