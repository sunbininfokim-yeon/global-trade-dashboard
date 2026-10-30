"""Publish verified Saudi oil-export VALUE context, separate from crude trade.

Default: three bounded official requests (listing, publication, XLSX).
Offline: --input-xlsx with --month and --source-url. Never synthesizes partners.
Any failed discovery/download/contract/regression leaves public output intact.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pipeline_store import atomic_json
from sources.saudi_gastat_bulletin import (LISTING_URL, discover_publication, discover_workbook,
                                         fetch, official_url, parse_bulletin)

PUBLIC = Path(__file__).resolve().parents[2] / 'public/data'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input-xlsx', type=Path)
    ap.add_argument('--month')
    ap.add_argument('--source-url')
    ap.add_argument('--out', type=Path, default=PUBLIC / 'commodity_trade_saudi_bulletin_v1.json')
    args = ap.parse_args()
    try:
        if args.input_xlsx:
            if not args.month or not args.source_url:
                raise ValueError('offline mode requires --month and --source-url')
            month, publication, url = args.month, None, official_url(args.source_url)
            raw = args.input_xlsx.read_bytes()
        else:
            month, publication = discover_publication(fetch(LISTING_URL).decode('utf-8'))
            url = discover_workbook(fetch(publication).decode('utf-8'), publication)
            raw = fetch(url)
        points = parse_bulletin(raw, month)
        previous = json.loads(args.out.read_text()) if args.out.exists() else {}
        if previous.get('latest_available_month', '') > month:
            raise ValueError('source regressed; preserving newer public observations')
        result = {
            'schema_version': 'commodity-trade-saudi-bulletin-v1',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'reporter_iso3': 'SAU', 'flow': 'X', 'partner': 'WORLD',
            'series_id': 'oil_exports_aggregate_value',
            'label_ko': '사우디 석유류 전체 수출액 (원유 단독·물량 아님)',
            'hs': None, 'quantity_available': False, 'bilateral_available': False,
            'latest_available_month': month,
            'source': {'agency': 'GASTAT', 'url': url, 'publication_url': publication,
                       'sha256': hashlib.sha256(raw).hexdigest(), 'sheet': '1.2'},
            'points': points,
            'limits': ['Not HS2709 alone', 'Not barrels or tonnes',
                       'No destination-country breakdown', 'Never merge into crude_oil observations'],
        }
        # Same source and observations: no meaningless scheduled PR every day.
        if previous.get('source', {}).get('sha256') == result['source']['sha256'] and previous.get('points') == points:
            print('GASTAT bulletin unchanged; retained public file')
            return 0
        atomic_json(args.out, result)
        print(json.dumps({'latest_month': month, 'points': len(points), 'bilateral_available': False}))
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f'GASTAT bulletin not published: {type(exc).__name__}: {exc}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
