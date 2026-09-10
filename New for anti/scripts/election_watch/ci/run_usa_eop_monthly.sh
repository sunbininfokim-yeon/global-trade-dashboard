#!/usr/bin/env bash
# Monthly USA EOP refresh. Called from GitHub Actions after Claude copies
# ci/elections_eop_monthly.yml into .github/workflows/.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m election_watch.extract_usa_eop --fetch --merge-tier12 --write-report
python3 build_board.py --no-betting --print-stats
python3 build_ui_manifest.py
