#!/usr/bin/env bash
# Quarterly USA standing-committee roster refresh (monthly in Q1).
# Called from GitHub Actions after Claude copies
# ci/elections_committees_quarterly.yml into .github/workflows/.
# Cursor may also run this locally. Do not commit raw/ .cache/ .venv/ .verify_live/.
set -euo pipefail

EW="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$EW/../../.." && pwd)"
RAW="$EW/raw/usa"
CACHE="$REPO/.cache/official-rosters"

cd "$REPO"

echo "== official House/Senate roster cache =="
node scripts/fetch-committee-membership-rosters.js
node scripts/build-committee-memberships.js
node scripts/lib/committee-membership-source.test.js
node scripts/lib/committee-agency-jurisdiction-source.test.js

mkdir -p "$RAW"
if [[ -f "$CACHE/MemberData.xml" ]]; then
  cp "$CACHE/MemberData.xml" "$RAW/MemberData.xml"
fi
if [[ -f "$CACHE/senate-cvc-memberships.json" ]]; then
  cp "$CACHE/senate-cvc-memberships.json" "$RAW/senate-cvc-memberships.json"
fi

echo "== election_watch extract + committee cards =="
cd "$EW"
python3 -m election_watch.extract_usa_committees
python3 -m election_watch.usa_committee_cards
python3 -m unittest tests.test_usa_committee_cards tests.test_extract_usa_senate_terms -v
python3 build_board.py --no-betting --print-stats
python3 build_ui_manifest.py

echo "done. commit extracted JSON + public board; never git add raw/ or .cache/"
