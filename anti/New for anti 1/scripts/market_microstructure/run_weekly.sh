#!/usr/bin/env bash
# Weekly: rediscover Tier B edges + hit-rate + regime-proxy backtest.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$ROOT/../../.." && pwd)"
PY="${REPO}/.venv/bin/python"
cd "$ROOT"

echo "[weekly] $(date -Iseconds)"
"$PY" build_conc_history.py --live --months 6 --print-stats
"$PY" build_us_kr_discovery.py --live --print-stats
"$PY" - <<'PY'
import json, sys
from pathlib import Path
ROOT = Path(".").resolve()
sys.path.insert(0, str(ROOT))
from market_microstructure.us_kr_hitrate import build_hitrate_report
from market_microstructure.regime_proxy_backtest import run_regime_proxy_backtest

pub = ROOT / "../../public/data"
bt = json.loads((pub / "us_kr_open30m_backtest_v1.json").read_text()) if (pub / "us_kr_open30m_backtest_v1.json").exists() else None
hit = build_hitrate_report(backtest_000660=bt)
reg = run_regime_proxy_backtest()
(pub / "us_kr_hitrate_v1.json").write_text(json.dumps(hit, ensure_ascii=False, indent=2) + "\n")
(pub / "us_kr_regime_proxy_backtest_v1.json").write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n")
print("Wrote hitrate + regime_proxy_backtest")
ch = (reg.get("channel_summary") or {}).get("downside") or {}
print("downside overnight", (ch.get("overnight") or {}))
PY

echo "[weekly] done"
