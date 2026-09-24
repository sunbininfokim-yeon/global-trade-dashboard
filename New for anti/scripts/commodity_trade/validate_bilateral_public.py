"""Offline pre-deploy integrity check and compact evidence report."""
from collections import Counter
from hashlib import sha256
import argparse
import json
from pathlib import Path
import re

from bilateral import build_partition, ContractError
from pipeline_store import read_json


def validate(out_dir):
    out_dir = Path(out_dir)
    index = read_json(out_dir / 'index.json')
    if index.get('schema') != 'commodity-trade-bilateral-index-v1':
        raise ContractError('index schema')
    row_count = 0
    candidates = Counter()
    for entry in index['entries']:
        if not re.fullmatch(r'parts/[a-f0-9]{64}\.json', entry['path']):
            raise ContractError('invalid part path')
        part = read_json(out_dir / entry['path'])
        content = json.dumps(part, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
        if sha256(content).hexdigest() != Path(entry['path']).stem:
            raise ContractError('part hash mismatch')
        for key in ('source', 'reporter', 'hs', 'hs_version', 'period', 'frequency', 'value_basis'):
            if part['meta'][key] != entry[key]:
                raise ContractError('index/part scope mismatch')
        rows = []
        for flow, block in part['flows'].items():
            for r in block['rows']:
                row_count += 1
                if r['partner'] == '0':
                    raise ContractError('World in partner rows')
                if r['export_control']['legal_clearance'] is not None:
                    raise ContractError('trade data cannot certify clearance')
                candidates.update(c['id'] for c in r['export_control']['candidates'])
                rows.append(dict(partner=r['partner'], flow=flow, period=part['meta']['period'],
                                 metrics=r['metrics'], quality=r['quality']))
            world = {k: v['world_total'] for k, v in block['metrics'].items()}
            if any(v is not None for v in world.values()):
                rows.append(dict(partner='0', flow=flow, period=part['meta']['period'], metrics=world))
        expected = build_partition(part['meta'], rows)
        for flow, block in expected['flows'].items():
            actual = {r['partner']: r for r in part['flows'][flow]['rows']}
            for r in block['rows']:
                if r['analysis'] != actual[r['partner']]['analysis']:
                    raise ContractError('share/rank mismatch')
    return {'parts': len(index['entries']), 'partner_rows': row_count,
            'reporters': sorted({e['reporter_iso3'] for e in index['entries'] if e['reporter_iso3']}),
            'periods': sorted({e['period'] for e in index['entries']}),
            'statuses': dict(Counter(j['status'] for j in index['jobs'].values())),
            'queried_product_policy_candidates': dict(Counter(c['id'] for p in index.get('product_policy_screens', [])
                for c in p['export_control']['candidates'])),
            'policy_candidates': dict(candidates)}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('out_dir', type=Path)
    args = p.parse_args()
    print(json.dumps(validate(args.out_dir), ensure_ascii=False))
