#!/usr/bin/env python3
"""Verify that deployed public bytes match the checked-out LETF data commit."""
import argparse
import gzip
import hashlib
import json
import time
import urllib.request
from pathlib import Path

PUBLIC = Path(__file__).resolve().parent / '../../public/data'
FILES = ('overseas_letf_board_v1.json', 'overseas_letf_pipeline_status_v1.json',
         'overseas_letf_history_v1.jsonl.gz', 'overseas_letf_listings_v1.jsonl.gz')


def uncompressed(payload):
    return gzip.decompress(payload) if payload[:2] == b'\x1f\x8b' else payload


def verify(base, public=PUBLIC):
    for filename in FILES:
        expected = uncompressed((public / filename).read_bytes())
        request = urllib.request.Request(f'{base.rstrip("/")}/public/data/{filename}?verify={time.time_ns()}',
                                         headers={'Cache-Control': 'no-cache', 'Accept-Encoding': 'identity'})
        with urllib.request.urlopen(request, timeout=30) as response:
            actual = uncompressed(response.read())
        if hashlib.sha256(expected).digest() != hashlib.sha256(actual).digest():
            raise ValueError(f'Deployed asset differs from checkout: {filename}')
    board = json.loads((public / FILES[0]).read_text())
    print(json.dumps({'verified': list(FILES), 'as_of': board['as_of'],
                      'product_count': len(board['products']), 'pipeline': board['pipeline']}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='https://global-trade-dashboard.sunbin-info-kim.workers.dev')
    args = parser.parse_args()
    for attempt in range(5):
        try:
            verify(args.base_url)
            break
        except Exception:
            if attempt == 4:
                raise
            time.sleep(10)
