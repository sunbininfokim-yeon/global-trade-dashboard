#!/usr/bin/env python3
"""Collect state-published election-night counts into usa_election_official_results_v1.json.

Runs in GitHub Actions: the cloud sandbox cannot reach state results hosts, and
Clarity answers plain HTTP with an empty 202 bot challenge, so Clarity pages are
read through headless Chromium.

A source that fails this run keeps its previous races, marked ``stale``. Only
race ids on the published board (usa_election_live_polls_v1.json) are written.

    python3 collect_official_results.py              # fetch and write
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from election_watch.official_results import parse_clarity, parse_enhanced_voting  # noqa: E402

CONFIG = ROOT / 'config' / 'official_results_2026.json'
PUBLIC = ROOT.parents[1] / 'public' / 'data'
OUT = PUBLIC / 'usa_election_official_results_v1.json'
# Clarity's bot gate answers HeadlessChrome's default user agent with 403; the same agent
# tools/ops/fetch_sources.py uses passes (11-04 probes).
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'


class Fetcher:
    def __init__(self):
        self.pw = self.browser = None

    def text(self, url: str) -> str:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json,text/plain,*/*'})
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read()
                if resp.status == 200 and body.strip():
                    return body.decode('utf-8', 'replace')
        except Exception:
            pass
        return self.rendered(url)

    def rendered(self, url: str) -> str:
        if not self.browser:
            from playwright.sync_api import sync_playwright
            self.pw = sync_playwright().start()
            self.browser = self.pw.chromium.launch()
        page = self.browser.new_page(user_agent=UA)
        try:
            page.goto(url, wait_until='networkidle', timeout=90000)
            page.wait_for_timeout(1500)
            return page.inner_text('body')
        finally:
            page.close()

    def close(self):
        if self.browser:
            self.browser.close()
            self.pw.stop()


def collect_source(source: dict, fetcher) -> tuple[dict, dict]:
    now = datetime.now(timezone.utc).isoformat()
    if source['kind'] == 'clarity':
        base = source['base_url'].rstrip('/')
        version = fetcher.text(f'{base}/current_ver.txt').strip()
        if not version.isdigit():
            raise ValueError(f'unexpected Clarity version: {version[:40]!r}')
        url = f'{base}/{version}/json/en/summary.json'
        races = parse_clarity(source['state'], json.loads(fetcher.text(url)))
        receipt = {'state': source['state'], 'kind': 'clarity', 'url': url, 'version': version,
                   'page_url': f'{base}/{version}/', 'fetched_at': now}
    elif source['kind'] == 'enhanced_voting':
        export = json.loads(fetcher.text(source['url']))
        races = parse_enhanced_voting(source['state'], export)
        receipt = {'state': source['state'], 'kind': 'enhanced_voting', 'url': source['url'],
                   'page_url': source.get('page_url'), 'published_at': export.get('createdAt'), 'fetched_at': now,
                   # Precinct counts come only from county rows; record how many arrived.
                   'county_rows': len((export.get('results') or {}).get('localResults') or [])}
    else:
        raise ValueError(f"unknown source kind {source['kind']}")
    receipt['authority_ko'] = source.get('authority_ko')
    for race in races.values():
        race['source_url'] = receipt.get('page_url') or receipt['url']
        race['authority_ko'] = source.get('authority_ko')
        race['fetched_at'] = now
    return races, receipt


def build(config: dict, fetcher, known: set[str], previous: dict | None) -> dict:
    out = {'schema': 'usa_election_official_results_v1', 'cycle': config['cycle'],
           'election_date': config['election_date'], 'generated_at': datetime.now(timezone.utc).isoformat(),
           'basis_ko': '주 선거 당국이 공개한 비공식 개표(인증 전)다. 투표구 보고 수는 그 주가 낸 숫자이고, '
                       '남은 표를 추정하지 않는다. 당선 판정을 하지 않는다.',
           'sources': [], 'races': {}}
    prev_races = (previous or {}).get('races', {})
    for source in config['sources']:
        try:
            races, receipt = collect_source(source, fetcher)
            receipt['status'] = 'ok'
        except Exception as exc:  # keep the last good count for this state
            receipt = {'state': source['state'], 'kind': source['kind'], 'status': 'failed',
                       'error': f'{type(exc).__name__}: {exc}'[:200], 'fetched_at': datetime.now(timezone.utc).isoformat()}
            races = {rid: dict(r, stale=True) for rid, r in prev_races.items() if r.get('state') == source['state']}
        out['sources'].append(receipt)
        for rid, race in races.items():
            if rid in known:
                out['races'][rid] = race
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args(argv)
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    known = set(json.loads((PUBLIC / 'usa_election_live_polls_v1.json').read_text(encoding='utf-8'))['races'])
    previous = json.loads(args.output.read_text(encoding='utf-8')) if args.output.exists() else None
    fetcher = Fetcher()
    try:
        doc = build(config, fetcher, known, previous)
    finally:
        fetcher.close()
    args.output.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    ok = sum(s['status'] == 'ok' for s in doc['sources'])
    print(json.dumps({'sources_ok': ok, 'sources': len(doc['sources']), 'races': len(doc['races'])}))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
