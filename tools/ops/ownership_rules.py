"""Narrow, documented workflow scope for the user's polling automation task."""

# The user asked Codex to finish the remaining automation/deploy work on
# 2026-10-06 (T-POLL-DEPLOY-20261005). This exception is tied to one branch
# and three exact files; it does not authorize other workflows or UI files.
POLLING_BRANCH = 'codex/us-polls-deploy'
POLLING_PATHS = frozenset({
    '.github/workflows/us_election_polls_refresh.yml',
    '.github/workflows/deploy.yml',
    '.github/workflows/ownership_guard.yml',
})


def scoped_paths(branch):
    return POLLING_PATHS if branch == POLLING_BRANCH else frozenset()
