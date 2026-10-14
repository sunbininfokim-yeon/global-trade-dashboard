"""Narrow, documented workflow scope for the user's polling automation task."""

# The user asked Codex to finish the remaining automation/deploy work on
# 2026-10-06 (T-POLL-DEPLOY-20261005). This exception is tied to one branch
# and three exact files. The user separately requested the election UI on
# 2026-10-06; its two existing shared UI files get an exact branch exception.
POLLING_BRANCH = 'codex/us-polls-deploy'
POLLING_PATHS = frozenset({
    '.github/workflows/us_election_polls_refresh.yml',
    '.github/workflows/deploy.yml',
    '.github/workflows/ownership_guard.yml',
})

ELECTION_UI_BRANCH = 'codex/usa-election-ui'
ELECTION_UI_PATHS = frozenset({'New for anti/index.html', 'New for anti/style.css'})

# User explicitly requested daily polling Actions on 2026-10-08.
# Only the polling collector is in scope; this grants no permission to change
# deploy.yml, merge, dispatch production collection or deploy.
DAILY_POLLING_BRANCH = 'codex/us-house-poll-priority-20261008'
DAILY_POLLING_PATHS = frozenset({
    '.github/workflows/us_election_polls_refresh.yml',
})

# 2026-10-10 user-requested root fix for state-stack/generated-data conflicts.
# The existing polling workflow is the sole workflow exception.
STATE_INTEGRATION_BRANCH = 'codex/election-state-integration-20261010'

# 2026-10-11: user requested rules for subsequent state research and other
# sessions. Include source-only PRs in the existing polling validation hook.
# This allows only that workflow, never deploy.yml or production dispatch.
STATE_RESEARCH_RULES_BRANCH = 'codex/election-research-rules-20261011'

# User requested monthly acquisition and existing Cloudflare-key integration
# on 2026-10-07. No UI, wrangler settings or shared deployment workflow grant.
COMMODITY_BRANCH = 'codex/commodity-monthly-automation'
COMMODITY_PATHS = frozenset({
    '_worker.js',
    '.github/workflows/commodity_trade_refresh.yml',
    '.github/workflows/commodity_trade_watchdog.yml',
})

# 2026-10-12: user requested monthly pipeline hardening, explicitly excluding
# Korea authentication. Only dedicated commodity workflows; no Worker/UI/deploy.
COMMODITY_OPS_BRANCH = 'codex/commodity-monthly-ops'
COMMODITY_OPS_PATHS = frozenset({
    '.github/workflows/commodity_trade_refresh.yml',
    '.github/workflows/commodity_trade_watchdog.yml',
    '.github/workflows/commodity_trade_contracts.yml',
})


def scoped_paths(branch):
    return {POLLING_BRANCH: POLLING_PATHS, ELECTION_UI_BRANCH: ELECTION_UI_PATHS,
            DAILY_POLLING_BRANCH: DAILY_POLLING_PATHS,
            STATE_INTEGRATION_BRANCH: DAILY_POLLING_PATHS,
            STATE_RESEARCH_RULES_BRANCH: DAILY_POLLING_PATHS,
            COMMODITY_BRANCH: COMMODITY_PATHS,
            COMMODITY_OPS_BRANCH: COMMODITY_OPS_PATHS}.get(branch, frozenset())
