#!/usr/bin/env bash
# 작업 시작: 브랜치 생성 + TASKS 안내
# 사용: ./tools/ops/claim.sh <agent> <task_id> [slug]
# 예:   ./tools/ops/claim.sh codex T03 india-wheat
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

AGENT="${1:-}"
TASK_ID="${2:-}"
SLUG="${3:-work}"

if [[ -z "$AGENT" || -z "$TASK_ID" ]]; then
  echo "Usage: $0 <claude|codex|cursor|anti> <task_id> [slug]"
  exit 1
fi

case "$AGENT" in
  claude|codex|cursor|anti) ;;
  *)
    echo "Unknown agent: $AGENT (use claude|codex|cursor|anti)"
    exit 1
    ;;
esac

if [[ -n "$(git status --porcelain)" ]]; then
  echo "WARNING: working tree is not clean."
  git status -sb
  echo
  echo "Continue only if you own these changes. Ctrl-C to abort, Enter to proceed."
  read -r _
fi

BRANCH="${AGENT}/${TASK_ID}-${SLUG}"
# sanitize
BRANCH="$(echo "$BRANCH" | tr ' ' '-' | tr -cd '[:alnum:]/_.-')"

CURRENT="$(git branch --show-current)"
if [[ "$CURRENT" != "$BRANCH" ]]; then
  if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git checkout "$BRANCH"
  else
    git checkout -b "$BRANCH"
  fi
fi

echo "On branch: $(git branch --show-current)"
echo
echo "Manual step: set TASKS.md row $TASK_ID → status=in_progress, owner=$AGENT, branch=$BRANCH"
echo "  file: docs/ops/TASKS.md"
echo
echo "Then implement only OWNERS.md paths for $AGENT."
echo "When finished: ./tools/ops/handoff.sh $AGENT \"summary\""
