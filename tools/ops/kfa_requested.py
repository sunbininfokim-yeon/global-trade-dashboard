#!/usr/bin/env python3
"""Companies readers asked for (/api/kfa-request queue) that still have no
engine snapshot. Prints two lines for the workflow:

    KR=<corp codes ...>
    US=<tickers ...>

Capped per run so one burst of searches cannot eat the OpenDART budget the
daily batch needs."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAP = ROOT / 'New for anti' / 'public' / 'data' / 'kfa_pecr'
SITE = os.environ.get('KFA_SITE', 'https://global-trade-dashboard.sunbin-info-kim.workers.dev')
MAX_KR, MAX_US = int(os.environ.get('KFA_MAX_KR', 8)), int(os.environ.get('KFA_MAX_US', 5))


def main() -> int:
    req = urllib.request.Request(f'{SITE}/api/kfa-request?list=1', headers={'User-Agent': 'global-trade-dashboard/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            queue = json.loads(res.read()).get('requests') or []
    except Exception as exc:  # noqa: BLE001 -- queue unreachable: nothing to build this round
        print(f'queue unavailable: {exc}', file=sys.stderr)
        queue = []
    kr = [r['corp'] for r in queue if r.get('market') == 'KR' and not (SNAP / f"{r['corp']}_v1.json").exists()]
    us = [r['ticker'] for r in queue if r.get('market') == 'US' and not (SNAP / f"us_{r['ticker']}_v1.json").exists()]
    print(f'KR={" ".join(kr[:MAX_KR])}')
    print(f'US={" ".join(us[:MAX_US])}')
    print(f'queue={len(queue)} pending_kr={len(kr)} pending_us={len(us)}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
