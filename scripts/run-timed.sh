#!/usr/bin/env bash
# Runs one scripts/*.js sync for up to N hours, then stops it cleanly --
# for a long unattended local backfill session without babysitting it or
# manually restarting a script that only processes MAX_BILLS items per run.
#
# Nothing about the time limit changes how fast requests go out: the
# request-rate cap (CONGRESS_REQUEST_INTERVAL_MS, 850ms by default) lives in
# scripts/lib/sync-utils.js and applies no matter how this is invoked. This
# wrapper only decides how long one process keeps going before it stops.
#
# Safe to interrupt any time (Ctrl+C) or let the time budget stop it: every
# scripts/*.js sync here checkpoints its own progress per item (a queue row's
# status, or a saved cursor), so a run that stops partway never loses or
# duplicates what it already did -- the next run picks up where this one
# left off.
#
# Usage:
#   ./scripts/run-timed.sh sync-congress.js 6 MAX_BILLS=1000000
#   ./scripts/run-timed.sh sync-federal-register.js 3 EO_RELATION_BACKFILL=true SKIP_EMBEDDINGS=true
#
# Uses macOS's built-in `caffeinate` so the Mac going to sleep doesn't kill
# the run partway through -- no extra install needed.

set -uo pipefail

SCRIPT_NAME="${1:?사용법: ./scripts/run-timed.sh <스크립트 파일명> [시간, 기본 6] [추가 환경변수=값 ...]}"
HOURS="${2:-6}"
EXTRA_ENV=("${@:3}")

cd "$(dirname "$0")/.."

if [ ! -f "scripts/${SCRIPT_NAME}" ]; then
  echo "scripts/${SCRIPT_NAME} 를 찾을 수 없습니다." >&2
  exit 1
fi

mkdir -p scripts/logs
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="scripts/logs/${SCRIPT_NAME%.js}-${STAMP}.log"
SECONDS_BUDGET=$(( HOURS * 3600 ))

echo "${SCRIPT_NAME} 를 최대 ${HOURS}시간 동안 실행합니다."
echo "로그: ${LOG_FILE}"
echo "그만두고 싶으면 이 창에서 Ctrl+C 를 누르세요 -- 어디서 멈추든 지금까지 처리된 건 안전하게 남습니다."
echo

caffeinate -i env "${EXTRA_ENV[@]}" node "scripts/${SCRIPT_NAME}" > "${LOG_FILE}" 2>&1 &
RUN_PID=$!

# The watchdog only ever sends one signal, well after the run started, so it
# cannot race the real process's own exit -- if RUN_PID already finished
# naturally, `kill -0` below simply fails and the watchdog does nothing.
(
  sleep "${SECONDS_BUDGET}"
  if kill -0 "${RUN_PID}" 2>/dev/null; then
    echo "$(date '+%H:%M:%S') -- ${HOURS}시간 예산 소진, 정상 종료 신호 전송" >> "${LOG_FILE}"
    kill -TERM "${RUN_PID}" 2>/dev/null
  fi
) &
WATCHDOG_PID=$!

wait "${RUN_PID}" 2>/dev/null
kill "${WATCHDOG_PID}" 2>/dev/null

echo
echo "종료됨. 최근 로그 20줄:"
tail -n 20 "${LOG_FILE}"
echo
echo "전체 로그: cat ${LOG_FILE}"
