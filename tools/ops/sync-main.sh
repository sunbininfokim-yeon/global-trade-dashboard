#!/usr/bin/env bash
# main 최신 동기화 (더러운 워킹트리면 중단)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "ABORT: working tree not clean. Commit, stash, or hand off first."
  git status -sb
  exit 1
fi

git fetch origin
git checkout main
git pull --ff-only origin main
echo "main is up to date at $(git rev-parse --short HEAD)"
echo "Create a feature branch before editing: ./tools/ops/claim.sh <agent> <id> <slug>"
