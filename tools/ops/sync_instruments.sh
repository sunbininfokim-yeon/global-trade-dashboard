#!/usr/bin/env bash
# 종목 표와 성향 한도를 배포 경로로 복사한다.
# 정본은 엔진 쪽(scripts/금융_재무분석/instruments/)이고 여기는 사본이다.
# scripts/ 는 Cloudflare 가 배포하지 않아 브라우저에서 직접 못 읽는다.
set -euo pipefail
cd "$(dirname "$0")/../.."
SRC="New for anti/scripts/금융_재무분석/instruments"
DST="New for anti/public/data"
cp "$SRC/registry.json"      "$DST/instruments_v1.json"
cp "$SRC/risk_profiles.json" "$DST/risk_profiles_v1.json"
echo "synced -> $DST/instruments_v1.json, risk_profiles_v1.json"
