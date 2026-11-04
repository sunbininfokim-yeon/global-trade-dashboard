#!/usr/bin/env bash
# Push the data commit a refresh workflow just made (to the branch the run is on, main when scheduled). Collectors run on overlapping
# schedules, so main often moves while one runs (2026-11-04: the QRA and policy-board refreshes
# were both rejected behind the public-series push). Rebase onto the new main and try again;
# a conflict on the same file still fails the run, so it shows instead of being forced through.
set -u
# The branch actually checked out. GITHUB_REF_NAME is the ref the run started on, which is
# main for a scheduled run even after a step switches to a review branch -- pushing there
# would land unreviewed data on main. Fall back to it only on a detached HEAD.
branch="$(git rev-parse --abbrev-ref HEAD)"
if [ "$branch" = "HEAD" ]; then branch="${GITHUB_REF_NAME:?no branch to push}"; fi
for attempt in 1 2 3 4; do
  if git push origin "HEAD:$branch"; then exit 0; fi
  echo "push rejected (attempt $attempt); rebasing onto the latest $branch"
  git fetch origin "$branch" || true
  if ! git rebase "origin/$branch"; then
    git rebase --abort 2>/dev/null || true
    echo "the same files changed on $branch meanwhile; not forcing it"
    exit 1
  fi
  sleep $((attempt * 10))
done
exit 1
