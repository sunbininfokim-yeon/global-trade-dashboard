#!/usr/bin/env bash
# 멀티 에이전트 상태 요약 (읽기 전용)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo "=== repo ==="
echo "path: $ROOT"
git rev-parse --is-inside-work-tree >/dev/null
echo "branch: $(git branch --show-current 2>/dev/null || echo '?')"
echo "remote: $(git remote get-url origin 2>/dev/null || echo '(none)')"
echo

echo "=== git status (short) ==="
git status -sb
echo

if ! git diff --quiet -- "New for anti/app.js" 2>/dev/null || \
   ! git diff --cached --quiet -- "New for anti/app.js" 2>/dev/null; then
  echo "!! WARNING: New for anti/app.js has local changes (likely Claude UI WIP)."
  echo "   Do NOT edit UI files from other agents until HANDOFF clears T01."
  echo
fi

echo "=== TASKS (open-ish) ==="
if [[ -f docs/ops/TASKS.md ]]; then
  # table rows that are not done
  awk '
    /^\| T[0-9]/ {
      if ($0 !~ /\| done *\|/ && $0 !~ /\|\*\*done\*\*/) print
    }
  ' docs/ops/TASKS.md || true
else
  echo "(missing docs/ops/TASKS.md)"
fi
echo

echo "=== latest HANDOFF (first entry) ==="
LATEST_HANDOFF="$(ls -1 docs/ops/handoff/*.md 2>/dev/null | grep -v README | tail -n 1)"
if [[ -n "${LATEST_HANDOFF:-}" && -f "$LATEST_HANDOFF" ]]; then
  awk '
    BEGIN { n=0 }
    /^## [0-9]{4}-/ { n++; if (n>1) exit }
    n>=1 { print }
  ' "$LATEST_HANDOFF" | head -n 40
else
  echo "(no handoff yet — docs/ops/handoff/)"
fi
echo

echo "=== ops docs ==="
ls -1 docs/ops 2>/dev/null || true
echo
echo "Done. Next: docs/ops/START_PROMPTS.md 또는 claim.sh"
