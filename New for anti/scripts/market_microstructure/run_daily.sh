#!/usr/bin/env bash
# Daily L1/L3 refresh (no UI). Run from repo root or this directory.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$ROOT/../../.." && pwd)"
if [[ -x "${REPO}/.venv/bin/python" ]]; then
  PY="${REPO}/.venv/bin/python"
else
  PY="${PYTHON:-python3}"
fi
cd "$ROOT"

echo "[daily] $(date -Iseconds) conc + D&S + FreeSIS + US→KR L3 + derivatives + investor×price"
"$PY" build_conc_history.py --append-only --print-stats || \
  "$PY" build_conc_history.py --live --months 6 --print-stats

"$PY" build_market_microstructure.py --live --source auto --print-stats
"$PY" build_deposit_credit.py --print-stats
"$PY" build_us_kr_l3.py --live --print-stats
"$PY" build_derivatives_board.py --live --print-stats
"$PY" build_investor_price_levels.py --live --universe both --top 10 --pool 100 --print-stats

echo "[daily] done"
