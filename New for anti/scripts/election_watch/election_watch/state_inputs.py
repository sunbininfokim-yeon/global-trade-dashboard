"""State-owned reviewed inputs over a shared legacy baseline.

State PRs own one packet, never the national config/output files. Preconditions
hold conflicting reviews instead of silently overwriting a newer main review.
"""
from copy import deepcopy
from datetime import datetime
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

CONFIG = Path(__file__).resolve().parents[1] / 'config'
CATALOGS = frozenset((
    'federal_matchups/2026.json', 'governor_matchups/2026.json',
    'governor_matchups/2026_ballot_reviews.json',
    'usa_polls/ballot_reviews_2026.json', 'usa_polls/quality_reviews_2026.json',
    'usa_polls/live_2026.json', 'usa_polls/primary_supplements_2026.json',
    'usa_polls/state_finance_identities_2026.json',
    'usa_state_campaign_finance_sources_v1.json',
))


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    allow_nan=False).encode()).hexdigest()


def validate_packet(packet, state_names):
    state = packet['state']
    if (packet['schema'] != 'usa_state_evidence_packet_v1' or packet['cycle'] != 2026
            or state not in state_names):
        raise ValueError('state input packet scope/schema')
    capture = packet['capture']; receipt = capture['receipt']
    if receipt['state'] != state or receipt['cycle'] != 2026 or capture['fetched_at'] != receipt['captured_at']:
        raise ValueError('state input capture provenance mismatch')
    datetime.fromisoformat(capture['fetched_at'].replace('Z', '+00:00'))
    if digest(capture['provider_records']) != capture['provider_records_sha256']:
        raise ValueError('state input provider snapshot changed')
    rows = capture['provider_records'] + capture['primary_records']
    ids = {r['id'] for r in rows}
    if len(ids) != len(rows):
        raise ValueError('state input duplicate record')
    def owned_subject(subject):
        return subject == f'2026 {state_names[state]}' or bool(re.fullmatch(rf'2026 {state}-\d{{2}}', subject))
    for row in rows:
        if not owned_subject(row['subject']):
            raise ValueError('state input contains another state')
    seen = set()
    for op in packet['config_operations']:
        file, path, action = op['file'], op['path'], op['action']
        if file not in CATALOGS or not path or any(not isinstance(k, str) for k in path):
            raise ValueError('unreviewed state input config path')
        if action not in ('set', 'delete', 'append_item', 'remove_item'):
            raise ValueError('unreviewed state input operation')
        # Lists at the root are collections of separately owned state records.
        if action in ('append_item', 'remove_item'):
            owned = (len(path) == 1 and path[0] in ('records', 'source_snapshots', 'additional_sources', 'held_candidates')
                     and op['value'].get('state') == state)
        else:
            owned = (len(path) == 2 and (
                path[0] == 'races' and path[1].startswith(f'USA:{state}:') or
                path[0] in ('contests', 'states') and path[1] == state or
                path[0] == 'source_snapshots' and isinstance(op.get('value'), dict)
                    and op['value'].get('state') == state or
                path[0] in ('reviews', 'excluded_records', 'excluded_record_reviews') and path[1] in ids))
            if type(op.get('before_exists')) is not bool or (
                    op['before_exists'] and not re.fullmatch('[a-f0-9]{64}', op.get('before_sha256', ''))):
                raise ValueError('missing state input precondition')
        if not owned:
            raise ValueError('state input operation outside owned state')
        if (file=='usa_polls/primary_supplements_2026.json' and action=='append_item'
                and not owned_subject(op['value']['record']['subject'])):
            raise ValueError('state primary review contains another state')
        key = (file, tuple(path), action, digest(op.get('value')) if action.endswith('item') else '')
        if key in seen:
            raise ValueError('duplicate state input operation')
        seen.add(key)
    return packet


@lru_cache(maxsize=16)
def _packets(signature, root):
    root = Path(root)
    names = {s: d['name'] for s, d in json.loads((root/'usa_polls/targets_2026.json').read_text())['states'].items()}
    result = []
    for path, _, _ in signature:
        packet = validate_packet(json.loads(Path(path).read_text()), names)
        if Path(path).stem != packet['state']:
            raise ValueError('state input filename mismatch')
        result.append(packet)
    return result


def packets(root=CONFIG):
    root = Path(root)
    files = sorted((root/'state_evidence/2026').glob('*.json'))
    signature = tuple((str(f), f.stat().st_mtime_ns, f.stat().st_size) for f in files)
    return deepcopy(_packets(signature, str(root))) if files else []


def apply_operations(value, operations):
    result = deepcopy(value)
    for op in operations:
        target = result
        for key in op['path'][:-1]:
            if not isinstance(target, dict) or key not in target:
                raise ValueError('state input parent no longer exists')
            target = target[key]
        key = op['path'][-1]; action = op['action']
        if action in ('append_item', 'remove_item'):
            items = target[key]
            if not isinstance(items, list):
                raise ValueError('state input collection changed')
            if action == 'append_item' and op['value'] not in items:
                items.append(deepcopy(op['value']))
            elif action == 'remove_item' and op['value'] in items:
                items.remove(op['value'])
            continue
        exists = key in target
        # Materialized legacy catalogs are idempotent, never double-applied.
        if action == 'set' and exists and target[key] == op['value'] or action == 'delete' and not exists:
            continue
        if exists != op['before_exists'] or exists and digest(target[key]) != op['before_sha256']:
            raise ValueError('state input conflicts with newer baseline: ' + op['file'] + '/' + '/'.join(op['path']))
        if action == 'set': target[key] = deepcopy(op['value'])
        else: del target[key]
    return result


def overlay(path, value, root=CONFIG):
    """Only production reviewed catalogs are overlaid; fixtures/public JSON are raw."""
    path = Path(path).resolve(); root = Path(root).resolve()
    try: relative = path.relative_to(root).as_posix()
    except ValueError: return value
    if relative not in CATALOGS: return value
    for packet in packets(root):
        value = apply_operations(value, [o for o in packet['config_operations'] if o['file'] == relative])
    return value


def primary_document_approved(entry, document):
    """An exact reviewed state entry can approve one file, never a CDN host."""
    for packet in packets():
        if packet['state'] != entry['state']:
            continue
        for op in packet['config_operations']:
            if (op['file']=='usa_polls/primary_supplements_2026.json' and op['path']==['records']
                    and op['action']=='append_item' and op['value']==entry
                    and document in op['value']['documents']):
                return True
    return False
