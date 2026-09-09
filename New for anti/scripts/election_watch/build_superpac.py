#!/usr/bin/env python3
"""Fetch processed regular FEC reports and publish small, immutable state shards."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from election_watch.superpac import FecClient, SourceError, build_snapshot, fetch_candidates, import_governor, now
from election_watch.superpac_schedule import reporting_cycle

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT.parents[1] / 'public' / 'data'
INDEX = 'usa_superpac_index_v1.json'


def atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n'
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as file:
        file.write(data)
        name = file.name
    os.replace(name, path)


def publish(snapshot, public):
    cycle = snapshot['cycle']
    index_path = public / INDEX
    index = json.loads(index_path.read_text()) if index_path.exists() else {'schema': 'usa_superpac_index_v1', 'cycles': {}}
    states = sorted(set(['US'] + [c['state'] for c in snapshot['candidates'] if c.get('state')] + [r['state'] for r in snapshot['spending']]))
    files = {}
    for state in states:
        if not state.isalpha() or len(state) != 2:
            raise ValueError('Invalid state shard key')
        shard = {'schema': 'usa_superpac_state_v1', 'cycle': cycle, 'state': state,
                 'generated_at': snapshot['generated_at'], 'status': snapshot['status'],
                 'candidates': [c for c in snapshot['candidates'] if ('US' if c['office'] == 'P' else c['state']) == state],
                 'spending': [r for r in snapshot['spending'] if r['state'] == state]}
        # A successful daily check need not duplicate every unchanged state asset.
        content = {k: v for k, v in shard.items() if k != 'generated_at'}
        digest = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()[:16]
        relative = f'usa_superpac/{cycle}/{state}-{digest}.json'
        if not (public / relative).exists():
            atomic_json(public / relative, shard)
        files[state] = relative
    meta = {k: v for k, v in snapshot.items() if k not in ('candidates', 'spending')}
    meta['state_files'] = files
    index['cycles'][str(cycle)] = meta
    index.update(generated_at=now(), status='available')
    # Index becomes visible only after every shard is durable. Failure leaves last good index intact.
    atomic_json(index_path, index)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cycle', type=int, default=reporting_cycle())
    parser.add_argument('--public', type=Path, default=PUBLIC)
    parser.add_argument('--governor-import', action='append', type=Path, default=[])
    parser.add_argument('--initialize', action='store_true', help='Create an explicit unavailable index, without overwriting collected data')
    args = parser.parse_args()
    if args.cycle < 2010 or args.cycle % 2:
        parser.error('FEC reporting cycle must be an even year >= 2010')
    if args.initialize:
        path = args.public / INDEX
        if not path.exists():
            atomic_json(path, {'schema': 'usa_superpac_index_v1', 'generated_at': now(), 'status': 'unconfigured', 'cycles': {},
                              'reason_ko': '전국 수집 전입니다. FEC 또는 data.gov API 키를 사용하는 수집 실행이 필요합니다. 주지사 자동 수집은 미지원입니다.'})
        return 0
    key = os.environ.get('FEC_API_KEY') or os.environ.get('DATA_GOV_API_KEY', '')
    if not key or key == 'DEMO_KEY':
        print('FEC_API_KEY / DATA_GOV_API_KEY missing: existing published data preserved.', file=sys.stderr)
        return 2
    try:
        candidates, source = fetch_candidates(args.cycle)
        client = FecClient(key)
        rows = client.rows('schedules/schedule_e/', cycle=args.cycle, most_recent='true', is_notice='false', sort='expenditure_date')
        snapshot = build_snapshot(args.cycle, candidates, rows)
        snapshot['sources'] = [source] + client.sources
        imports = sorted((ROOT / 'config' / 'governor_ie' / str(args.cycle)).glob('*.json')) + args.governor_import
        imported_states = set()
        for path in imports:
            payload = json.loads(path.read_text())
            if payload.get('state') in imported_states:
                raise ValueError('One consolidated governor import per state is required')
            imported_states.add(payload.get('state'))
            import_governor(snapshot, payload)
        publish(snapshot, args.public)
        print(json.dumps({'cycle': args.cycle, 'candidates': len(candidates), 'quality': snapshot['quality'], 'requests': client.requests}))
        return 0
    except (SourceError, ValueError, OSError) as exc:
        reason = str(exc) if isinstance(exc, SourceError) else type(exc).__name__
        print(f'Super PAC refresh failed ({reason}); existing index preserved.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
