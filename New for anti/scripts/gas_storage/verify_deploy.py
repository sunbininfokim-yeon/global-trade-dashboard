#!/usr/bin/env python3
"""Check the bytes served after deployment against this checkout."""
import hashlib
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

PATH = 'public/data/gas_storage_v1.json'


def verify():
    expected = (Path(__file__).resolve().parents[2] / PATH).read_bytes()
    url = 'https://chokemonitor.com/' + PATH + '?verify=' + str(time.time_ns())
    request = Request(url, headers={'Cache-Control':'no-cache', 'Accept-Encoding':'identity',
                                   'User-Agent':'GlobalTradeDashboard-DataVerification/1.0'})
    with urlopen(request, timeout=30) as response:
        actual = response.read()
    if hashlib.sha256(expected).digest() != hashlib.sha256(actual).digest():
        raise ValueError('Deployed gas data differs from checkout')
    data = json.loads(actual)
    if data.get('schema_version') != 'gas_storage_v1' or not data.get('series'):
        raise ValueError('Gas data schema is unavailable')
    print(json.dumps({'verified':PATH, 'as_of':data['as_of'], 'series':len(data['series']),
                      'status':data['status']}))


if __name__ == '__main__':
    for attempt in range(5):
        try:
            verify()
            break
        except Exception:
            if attempt == 4:
                raise
            time.sleep(10)
