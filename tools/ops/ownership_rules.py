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

# User requested monthly acquisition and existing Cloudflare-key integration
# on 2026-10-07. No UI, wrangler settings or shared deployment workflow grant.
COMMODITY_BRANCH = 'codex/commodity-monthly-automation'
COMMODITY_PATHS = frozenset({
    '_worker.js',
    '.github/workflows/commodity_trade_refresh.yml',
    '.github/workflows/commodity_trade_watchdog.yml',
})


def scoped_paths(branch):
    return {POLLING_BRANCH: POLLING_PATHS, ELECTION_UI_BRANCH: ELECTION_UI_PATHS,
            COMMODITY_BRANCH: COMMODITY_PATHS}.get(branch, frozenset())
