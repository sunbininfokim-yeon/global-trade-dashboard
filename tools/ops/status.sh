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

echo "=== comtrade 연간 데이터 상태 ==="
COMTRADE_STATUS_URL="https://global-trade-dashboard.sunbin-info-kim.workers.dev/api/comtrade/status"
COMTRADE_RESP="$(curl -fsS --max-time 5 "$COMTRADE_STATUS_URL" 2>/dev/null || true)"
if [[ -n "$COMTRADE_RESP" ]]; then
  echo "$COMTRADE_RESP" | node -e '
    let d = "";
    process.stdin.on("data", (c) => (d += c));
    process.stdin.on("end", () => {
      try {
        const j = JSON.parse(d);
        console.log(`발행: ${j.published}년` + (j.next ? ` (다음 후보 ${j.next}년)` : " (마지막 연도)"));
        console.log(`화면 표시: ${j.display}`);
        if (j.next) {
          console.log(`${j.next}년 캐시: ${j.cached[j.next]}/${j.commodities}개 원자재`);
          const partial = j.partial[j.next] || [];
          if (partial.length) console.log(`  부분 캐시(재시도 필요): ${partial.join(", ")}`);
          console.log(`신고국 수 — ${j.published}년: ${j.reporters[j.published]}, ${j.next}년: ${j.reporters[j.next] ?? 0}`);
        }
        if (j.next_rule) console.log(`승격 규칙: ${j.next_rule}`);
      } catch (e) {
        console.log("(응답 파싱 실패 -- 원문 확인: " + process.argv[1] + ")");
      }
    });
  ' "$COMTRADE_STATUS_URL" 2>/dev/null || echo "(파싱 실패 -- 원문: $COMTRADE_STATUS_URL)"
else
  echo "(네트워크 없음 또는 응답 없음 -- 건너뜀. 직접 확인: curl $COMTRADE_STATUS_URL)"
fi
echo

echo "=== ops docs ==="
ls -1 docs/ops 2>/dev/null || true
echo
echo "Done. Next: docs/ops/START_PROMPTS.md 또는 claim.sh"
