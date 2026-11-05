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
import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from election_watch.official_results import enhanced_local_results, parse_clarity, parse_enhanced_voting  # noqa: E402

CONFIG = ROOT / 'config' / 'official_results_2026.json'
PUBLIC = ROOT.parents[1] / 'public' / 'data'
OUT = PUBLIC / 'usa_election_official_results_v1.json'
# Clarity's bot gate answers HeadlessChrome's default user agent with 403; the same agent
# tools/ops/fetch_sources.py uses passes (11-04 probes).
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'


def load_config(path: Path = CONFIG, source_dir: Path | None = None) -> dict:
    """Load independent state descriptors without editing a shared source list."""
    config = json.loads(path.read_text(encoding='utf-8'))
    directory = source_dir if source_dir is not None else path.parent / 'official_results_sources' / str(config['cycle'])
    sources = list(config['sources'])
    for entry in sorted(directory.glob('*.json')):
        source = json.loads(entry.read_text(encoding='utf-8'))
        if source.get('state') != entry.stem or not entry.stem.isalpha() or len(entry.stem) != 2 or entry.stem != entry.stem.upper():
            raise ValueError(f'source filename/state mismatch: {entry.name}')
        if source.get('cycle') != config['cycle'] or source.get('election_date') != config['election_date']:
            raise ValueError(f'source election mismatch: {entry.name}')
        sources.append(source)
    states = [source['state'] for source in sources]
    if len(set(states)) != len(states):
        raise ValueError('duplicate official results source state')
    config['sources'] = sources
    return config


def published_time(value: str) -> datetime:
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('source publication timestamp must include timezone')
    return stamp


class Fetcher:
    def __init__(self):
        self.pw = self.browser = None

    def text(self, url: str, *, render_fallback: bool = True) -> str:
        failure = None
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json,text/plain,*/*'})
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read()
                if resp.status == 200 and body.strip():
                    return body.decode('utf-8', 'replace')
        except Exception as exc:
            failure = exc
        if not render_fallback:
            raise ValueError('official JSON request failed; no browser retry') from failure
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


def collect_source(source: dict, fetcher, election_date: str | None = None) -> tuple[dict, dict]:
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
        raw = fetcher.text(source['url'], render_fallback=source.get('render_fallback', True))
        export = json.loads(raw)
        if election_date and export.get('electionDate') != election_date:
            raise ValueError('Enhanced Voting election date mismatch')
        if source.get('expected_result_name') and (export.get('results') or {}).get('name') != source['expected_result_name']:
            raise ValueError('Enhanced Voting state identity mismatch')
        if published_time(export['createdAt']) > datetime.now(timezone.utc):
            raise ValueError('source publication timestamp is in the future')
        races = parse_enhanced_voting(source['state'], export)
        receipt = {'state': source['state'], 'kind': 'enhanced_voting', 'url': source['url'],
                   'page_url': source.get('page_url'), 'published_at': export.get('createdAt'), 'fetched_at': now,
                   # Precinct counts come only from county rows; record how many arrived.
                   'county_rows': len(enhanced_local_results(export)),
                   'document_sha256': hashlib.sha256(raw.encode('utf-8')).hexdigest()}
    else:
        raise ValueError(f"unknown source kind {source['kind']}")
    receipt['authority_ko'] = source.get('authority_ko')
    for race in races.values():
        race['source_url'] = receipt.get('page_url') or receipt['url']
        race['authority_ko'] = source.get('authority_ko')
        race['fetched_at'] = now
        if receipt.get('published_at'):
            race['source_published_at'] = receipt['published_at']
    return races, receipt


def build(config: dict, fetcher, known: set[str], previous: dict | None) -> dict:
    if previous and (previous.get('cycle') != config['cycle'] or previous.get('election_date') != config['election_date']):
        raise ValueError('previous results belong to a different election')
    out = {'schema': 'usa_election_official_results_v1', 'cycle': config['cycle'],
           'election_date': config['election_date'], 'generated_at': datetime.now(timezone.utc).isoformat(),
           'basis_ko': '주 선거 당국이 공개한 비공식 개표(인증 전)다. 투표구 보고 수는 그 주가 낸 숫자이고, '
                       '남은 표를 추정하지 않는다. 당선 판정을 하지 않는다.',
           'sources': [], 'races': {}}
    prev_races = (previous or {}).get('races', {})
    prev_sources = {s['state']: s for s in (previous or {}).get('sources', [])}
    for source in config['sources']:
        try:
            races, receipt = collect_source(source, fetcher, config['election_date'])
            races = {rid: r for rid, r in races.items() if rid in known}
            if not races:
                raise ValueError('source contains no matching board races')
            old = prev_sources.get(source['state'], {})
            if receipt.get('published_at') and old.get('published_at') and published_time(receipt['published_at']) < published_time(old['published_at']):
                raise ValueError('source publication timestamp regressed')
            previous_ids = {rid for rid, r in prev_races.items() if r.get('state') == source['state'] and rid in known}
            if not previous_ids.issubset(races):
                raise ValueError('previously observed board races missing from source')
            receipt['status'] = 'ok'
        except Exception as exc:  # keep the last good count for this state
            receipt = dict(prev_sources.get(source['state'], {}))
            receipt.update({'state': source['state'], 'kind': source['kind'], 'status': 'failed',
                            'error': f'{type(exc).__name__}: {exc}'[:200],
                            'attempted_at': datetime.now(timezone.utc).isoformat()})
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
    config = load_config()
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
