#!/usr/bin/env python3
"""Build New for anti/public/data/dart_unlisted_filers_v1.json.

The company calculator resolves Korean filers through
dart_corp_codes_v1.json, which only carries KRX-listed companies (keyed by
6-digit stock code). Unlisted companies that still file 사업보고서 with
DART -- bond issuers such as 연합자산관리, large private companies,
delisted ones -- have no stock code and could not be opened at all.

This script lists them:

1. OpenDART list.json, corp_cls=E (기타법인), pblntf_detail_ty=A001
   (사업보고서), over the last LOOKBACK_DAYS. Without corp_code the API
   only accepts a 3-month window, so the range is walked in 90-day steps.
2. Drop anything already in the listed index.
3. Probe fnlttSinglAcntAll for the fiscal year the report covers, CFS
   then OFS. Only filers with XBRL facts are kept: a filer whose 사업보고서
   has no machine-readable statements would just open to an empty screen.

Output: {"index": {corp_code: [name, fs_div, fiscal_year]}}. fs_div and
fiscal_year are what the probe found, kept for auditing; the Worker does its
own CFS->OFS resolution on every request and does not trust these.

Usage (key is read from the environment only, never written anywhere):
    DART_API_KEY=... python3 tools/ops/build_dart_unlisted_filers.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'New for anti' / 'public' / 'data'
LISTED = DATA / 'dart_corp_codes_v1.json'
OUT = DATA / 'dart_unlisted_filers_v1.json'
API = 'https://opendart.fss.or.kr/api'
LOOKBACK_DAYS = 455   # 15 months: covers one full spring filing season plus non-December year ends
PAUSE = 0.12          # OpenDART throttles bursts (status 020); stay well under it


def call(key: str, path: str, **params) -> dict:
    q = urllib.parse.urlencode({'crtfc_key': key, **params})
    for attempt in range(4):
        try:
            req = urllib.request.Request(f'{API}/{path}?{q}', headers={'User-Agent': 'global-trade-dashboard/1.0'})
            with urllib.request.urlopen(req, timeout=30) as res:
                body = res.read()
            data = json.loads(body)
        except Exception as exc:  # network / non-JSON: back off and retry
            err = re.sub(re.escape(key), '<key>', str(exc))
            print(f'  retry {path} ({err})', file=sys.stderr)
            time.sleep(2 * (attempt + 1))
            continue
        if data.get('status') == '020':
            time.sleep(5 * (attempt + 1))
            continue
        time.sleep(PAUSE)
        return data
    raise RuntimeError(f'{path} failed after retries')


def report_filers(key: str, today: dt.date) -> dict[str, dict]:
    filers: dict[str, dict] = {}
    end = today
    start_limit = today - dt.timedelta(days=LOOKBACK_DAYS)
    while end > start_limit:
        bgn = max(start_limit, end - dt.timedelta(days=89))
        page = 1
        while True:
            d = call(key, 'list.json', bgn_de=bgn.strftime('%Y%m%d'), end_de=end.strftime('%Y%m%d'),
                     corp_cls='E', pblntf_detail_ty='A001', page_count=100, page_no=page)
            if d.get('status') == '013':
                break
            if d.get('status') != '000':
                raise RuntimeError(f"list.json {bgn}..{end}: {d.get('status')} {d.get('message')}")
            for row in d.get('list', []):
                m = re.search(r'\((\d{4})\.(\d{2})\)', row.get('report_nm', ''))
                if not m:
                    continue
                cc = row['corp_code']
                fy = int(m.group(1))
                prev = filers.get(cc)
                # Keep the newest fiscal year seen; the name from the newest filing.
                if prev is None or fy > prev['fy']:
                    filers[cc] = {'name': row['corp_name'].strip(), 'fy': fy,
                                  'stock_code': (row.get('stock_code') or '').strip()}
            print(f'  {bgn}..{end} page {page}/{d.get("total_page")}: {len(filers)} filers so far', file=sys.stderr)
            if page >= int(d.get('total_page') or 1):
                break
            page += 1
        end = bgn - dt.timedelta(days=1)
    return filers


def probe(key: str, corp_code: str, fy: int) -> str | None:
    for fs_div in ('CFS', 'OFS'):
        d = call(key, 'fnlttSinglAcntAll.json', corp_code=corp_code, bsns_year=str(fy),
                 reprt_code='11011', fs_div=fs_div)
        if d.get('status') == '000' and d.get('list'):
            return fs_div
        if d.get('status') not in ('000', '013'):
            raise RuntimeError(f"probe {corp_code} FY{fy} {fs_div}: {d.get('status')} {d.get('message')}")
    return None


def main() -> int:
    key = os.environ.get('DART_API_KEY', '').strip()
    if not key:
        print('DART_API_KEY is not set', file=sys.stderr)
        return 2
    listed = json.loads(LISTED.read_text())['index']
    listed_corp = {row[0] for row in listed.values()}

    today = dt.date.today()
    filers = report_filers(key, today)
    candidates = {cc: f for cc, f in filers.items()
                  if cc not in listed_corp and f['stock_code'] not in listed}
    print(f'{len(filers)} 기타법인 filers, {len(candidates)} not in the listed index', file=sys.stderr)

    index: dict[str, list] = {}
    skipped = 0
    for i, (cc, f) in enumerate(sorted(candidates.items())):
        fs_div = probe(key, cc, f['fy'])
        if fs_div:
            index[cc] = [f['name'], fs_div, f['fy']]
        else:
            skipped += 1
        if (i + 1) % 100 == 0:
            print(f'  probed {i + 1}/{len(candidates)}: {len(index)} with XBRL', file=sys.stderr)

    OUT.write_text(json.dumps({
        'schema': 'dart_unlisted_filers_v1',
        'generated_at': today.isoformat(),
        'source': 'OpenDART list.json (corp_cls=E, A001) + fnlttSinglAcntAll probe',
        'lookback_days': LOOKBACK_DAYS,
        'count': len(index),
        'skipped_no_xbrl': skipped,
        'index': dict(sorted(index.items())),
    }, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(f'wrote {OUT.relative_to(ROOT)}: {len(index)} filers ({skipped} without XBRL skipped)', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
