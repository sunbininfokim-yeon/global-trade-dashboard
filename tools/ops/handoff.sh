#!/usr/bin/env bash
# 인수인계 블록을 그 에이전트 자신의 파일에 덧붙인다.
# 사용: ./tools/ops/handoff.sh <agent> "요약 한 줄 이상"
#
# 예전에는 공유 HANDOFF.md 하나의 맨 위에 끼워 넣었다. 2026-08-07 에 두 세션이
# 같은 파일을 편집하다 한쪽 내용이 통째로 사라졌다 -- 그래서 파일을 나눈다.
# 자세한 규칙은 docs/ops/handoff/README.md.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

AGENT="${1:-}"
SUMMARY="${2:-}"

if [[ -z "$AGENT" || -z "$SUMMARY" ]]; then
  echo "Usage: $0 <agent> \"summary\""
  exit 1
fi

DATE="$(date +%Y-%m-%d)"
FILE="docs/ops/handoff/${DATE}-${AGENT}.md"
mkdir -p docs/ops/handoff
if [[ ! -f "$FILE" ]]; then
  printf '# 인수인계 %s — %s\n' "$DATE" "$AGENT" > "$FILE"
fi

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

# 덧붙이기. 남의 줄을 건드리지 않으므로 병합 충돌이 생길 여지가 없다.
printf '\n%s' "$BLOCK" >> "$FILE"

echo "Updated $FILE"
echo "Also update docs/ops/TASKS.md status → review/done (자기 owner 행만)."
echo "Commit when ready:"
echo "  git add $FILE docs/ops/TASKS.md"
echo "  git commit -m \"handoff(${AGENT}): …\""
