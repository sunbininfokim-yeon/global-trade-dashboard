#!/usr/bin/env bash
# 인수인계 블록을 HANDOFF.md 상단에 삽입
# 사용: ./tools/ops/handoff.sh <agent> "요약 한 줄 이상"
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

AGENT="${1:-}"
SUMMARY="${2:-}"

if [[ -z "$AGENT" || -z "$SUMMARY" ]]; then
  echo "Usage: $0 <agent> \"summary\""
  exit 1
fi

FILE="docs/ops/HANDOFF.md"
mkdir -p docs/ops
if [[ ! -f "$FILE" ]]; then
  printf '# HANDOFF\n\n' > "$FILE"
fi

DATE="$(date +%Y-%m-%d)"
BRANCH="$(git branch --show-current 2>/dev/null || echo '?')"
HEAD="$(git rev-parse --short HEAD 2>/dev/null || echo '?')"

# changed files (unstaged+staged+untracked names)
CHANGED="$(git status --porcelain 2>/dev/null | sed 's/^...//' | head -n 40 || true)"
if [[ -z "$CHANGED" ]]; then
  CHANGED="(clean working tree — already committed? list files in PR)"
fi

BLOCK=$(cat <<EOF
## ${DATE} — ${AGENT}

### Goal / summary
${SUMMARY}

### Meta
- branch: \`${BRANCH}\`
- head: \`${HEAD}\`

### Files (working tree at handoff time)
\`\`\`
${CHANGED}
\`\`\`

### Not done / risks
_(작성자 보완)_

### Next
_(다음 에이전트/사람 액션)_

### Commands
\`\`\`bash
./tools/ops/status.sh
git push -u origin ${BRANCH}
\`\`\`

---

EOF
)

TMP="$(mktemp)"
# insert after first line if title-only, else after first heading block intro
{
  if head -n 1 "$FILE" | grep -q '^#'; then
    head -n 1 "$FILE"
    echo
    printf '%s' "$BLOCK"
    # skip original first line
    tail -n +2 "$FILE"
  else
    printf '%s' "$BLOCK"
    cat "$FILE"
  fi
} > "$TMP"
mv "$TMP" "$FILE"

echo "Updated $FILE"
echo "Also update docs/ops/TASKS.md status → review/done."
echo "Commit when ready:"
echo "  git add docs/ops/HANDOFF.md docs/ops/TASKS.md"
echo "  git commit -m \"handoff(${AGENT}): …\""
